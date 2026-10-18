"""Replay Frigate MQTT messages through Home Assistant's actual script engine.

Run with Python 3.14 and requirements-test.txt installed:
    python -m unittest discover -s tests -v
Delays advance a controlled clock; all other actions/templates use HA itself.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from inspect import signature
from importlib.metadata import version
from pathlib import Path
import tempfile
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from homeassistant import bootstrap, config_entries, loader
from homeassistant.core import Context, HomeAssistant, SupportsResponse
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.components.automation.config import PLATFORM_SCHEMA
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.script import Script
from homeassistant.setup import async_setup_component


ROOT = Path(__file__).resolve().parents[1]


class Input(str):
    """Keep !input references distinct from ordinary strings."""


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!input", lambda loader, node: Input(loader.construct_scalar(node)))
BLUEPRINT = yaml.load((ROOT / "frigate-ai-notification.yaml").read_text(), Loader=Loader)


def defaults():
    result = {}
    for key, config in BLUEPRINT["blueprint"]["input"].items():
        if "input" in config:
            result.update({k: v["default"] for k, v in config["input"].items()})
        elif "default" in config:
            result[key] = config["default"]
    result.update(camera=["camera.front_door"], notify_device=["phone"])
    return result


def substitute(value, inputs):
    if isinstance(value, Input):
        return deepcopy(inputs[str(value)])
    if isinstance(value, dict):
        return {key: substitute(item, inputs) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute(item, inputs) for item in value]
    return value


def fast_delays(value):
    """Replace only wall-clock delays, preserving their timing and action order."""
    if isinstance(value, dict):
        if "delay" in value:
            return {"service": "test.advance_time", "data": {"duration": value["delay"]}}
        return {key: fast_delays(item) for key, item in value.items()}
    if isinstance(value, list):
        return [fast_delays(item) for item in value]
    return value


def tracked(**changes):
    # Native 0.18 event fields, including [name, confidence] sub_label values.
    value = {
        "id": "1800000000.123456-front",
        "camera": "front_door",
        "label": "person",
        "top_score": 0.9,
        "score": 0.85,
        "false_positive": False,
        "has_clip": True,
        "entered_zones": ["driveway"],
        "current_zones": ["driveway"],
        "sub_label": None,
        "stationary": False,
        "snapshot": {"frame_time": 1800000000.0},
    }
    value.update(changes)
    return value


class BlueprintTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        (ROOT / ".codex").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".codex")
        self.hass = HomeAssistant(self.temp.name)
        await self.hass.config.async_set_time_zone("UTC")
        loader.async_setup(self.hass)
        self.hass.config_entries = config_entries.ConfigEntries(self.hass, {})
        await bootstrap.async_load_base_functionality(self.hass)
        # Register real entries/devices so templates use HA's actual lookup
        # functions, including ConfigEntryState rather than a mocked string.
        self.entries = {}
        for entry_id, domain in (("test", "llmvision"), ("phone", "mobile_app"), ("other_phone", "mobile_app")):
            extra = {"subentries_data": None} if "subentries_data" in signature(config_entries.ConfigEntry).parameters else {}
            entry = config_entries.ConfigEntry(
                entry_id=entry_id, domain=domain, title=entry_id,
                data={}, options={}, source="user", version=1, minor_version=1,
                unique_id=entry_id, discovery_keys=MappingProxyType({}),
                state=config_entries.ConfigEntryState.LOADED,
                **extra,
            )
            self.hass.config_entries._entries[entry_id] = entry
            self.entries[entry_id] = entry
        registry = dr.async_get(self.hass)
        self.devices = {
            key: registry.async_get_or_create(
                config_entry_id=key, identifiers={("mobile_app", key)},
                name=name, manufacturer=manufacturer,
            ).id
            for key, name, manufacturer in (("phone", "Phone", "Apple"), ("other_phone", "Other Phone", "Google"))
        }
        self.clock = datetime.fromtimestamp(1800000000, timezone.utc)
        self.time_patch = patch("homeassistant.util.dt.now", side_effect=lambda *args: self.clock)
        self.time_patch.start()
        for domain, config in {
            "input_text": {"silence": {"max": 255, "initial": "{}"}, "small_silence": {"max": 30, "initial": "{}"}, "ai_log": {"max": 255, "initial": ""}, "small_log": {"max": 40, "initial": ""}},
            "input_boolean": {"busy": {"initial": False}},
            "input_datetime": {"cooldown": {"has_date": True, "has_time": True}},
        }.items():
            self.assertTrue(await async_setup_component(self.hass, domain, {domain: config}))
        self.hass.states.async_set("automation.frigate_test", "on")
        self.notifications = []
        self.logs = []
        self.ai_calls = []
        self.ai_failures = 0
        self.ai_result = {"title": "Delivery", "response_text": "A person leaves a parcel."}
        self.fail_other_phone = True
        self.delay_hook = None

        async def notify(call):
            self.notifications.append(dict(call.data))

        async def fail_notify(call):
            if self.fail_other_phone:
                raise HomeAssistantError("Phone unavailable")
            self.notifications.append(dict(call.data))

        async def log(call):
            self.logs.append(dict(call.data))

        async def analyzer(call):
            self.ai_calls.append(dict(call.data))
            if self.ai_failures:
                self.ai_failures -= 1
                raise HomeAssistantError("Temporary provider failure")
            return self.ai_result

        async def advance(call):
            duration = call.data["duration"]
            if isinstance(duration, str):
                hours, minutes, seconds = map(float, duration.split(":"))
                seconds += hours * 3600 + minutes * 60
            else:
                seconds = sum(float(duration.get(k, 0)) * scale for k, scale in (("days", 86400), ("hours", 3600), ("minutes", 60), ("seconds", 1), ("milliseconds", .001)))
            self.clock += timedelta(seconds=seconds)
            if self.delay_hook:
                await self.delay_hook()

        self.hass.services.async_register("notify", "mobile_app_phone", notify)
        self.hass.services.async_register("notify", "mobile_app_other_phone", fail_notify)
        self.hass.services.async_register("logbook", "log", log)
        self.hass.services.async_register("persistent_notification", "create", log)
        self.hass.services.async_register("test", "advance_time", advance)
        self.hass.services.async_register("llmvision", "video_analyzer", analyzer, supports_response=SupportsResponse.ONLY)

    async def asyncTearDown(self):
        await self.hass.async_stop()
        self.time_patch.stop()
        self.temp.cleanup()

    async def run_event(self, kind="new", before=None, after=None, inputs=None, mobile=None):
        selected = defaults() | (inputs or {})
        selected["notify_device"] = [self.devices.get(device, device) for device in selected["notify_device"]]
        config = substitute(BLUEPRINT, selected)
        # Check the real, unmodified action schema as well as the accelerated script.
        cv.SCRIPT_SCHEMA(config["action"])
        sequence = cv.SCRIPT_SCHEMA(fast_delays(config["action"]))
        script = Script(self.hass, sequence, "Frigate regression", "automation", script_mode="parallel")
        trigger = {"id": "frigate-event", "payload_json": {"type": kind, "before": before or {}, "after": after if after is not None else tracked()}}
        if mobile is not None:
            trigger = {"id": "mobile-action", "event": SimpleNamespace(data=mobile)}
        await script.async_run({"trigger": trigger, "this": self.hass.states.get("automation.frigate_test")}, context=Context())
        return script

    async def test_default_notification_urls_and_actions(self):
        await self.run_event()
        self.assertEqual(len(self.notifications), 1)
        data = self.notifications[0]["data"]
        self.assertTrue(data["url"].startswith("/api/frigate/notifications/"))
        self.assertEqual(data["url"], data["clickAction"])
        self.assertEqual(len(data["actions"]), 3)
        self.assertTrue(data["actions"][-1]["action"].startswith("SILENCE_automation.frigate_test__"))
        self.assertEqual(data["ttl"], 0)
        self.assertNotIn("data", data)

    async def test_blueprint_and_automation_schemas(self):
        BLUEPRINT_SCHEMA(deepcopy(BLUEPRINT))
        minimum = BLUEPRINT["blueprint"]["homeassistant"]["min_version"]
        self.assertGreaterEqual(tuple(map(int, version("homeassistant").split("."))), tuple(map(int, minimum.split("."))))
        expanded = substitute(BLUEPRINT, defaults())
        PLATFORM_SCHEMA({k: v for k, v in expanded.items() if k != "blueprint"})

    async def test_full_silence_table_preserves_existing_mutes(self):
        value = '{"one":1800009999}'
        await self.hass.services.async_call("input_text", "set_value", {"entity_id": "input_text.small_silence", "value": value}, blocking=True)
        await self.run_event(inputs={"silence_table": "input_text.small_silence"}, mobile={"action": "SILENCE_automation.frigate_test__front_door", "reply_text": "5"})
        self.assertEqual(self.hass.states.get("input_text.small_silence").state, value)
        self.assertTrue(any(item.get("title") == "Frigate silence failed" for item in self.logs))

    async def test_small_log_uses_its_configured_limit(self):
        await self.run_event("end", inputs={"provider": "test", "log_helper": "input_text.small_log"})
        self.assertLessEqual(len(self.hass.states.get("input_text.small_log").state), 40)
        self.assertTrue(self.hass.states.get("input_text.small_log").state)

    async def test_manual_mute_during_retry_stops_analysis(self):
        self.ai_failures = 9
        async def mute_after_failure():
            if self.ai_calls:
                await self.hass.services.async_call("input_text", "set_value", {"entity_id": "input_text.silence", "value": '{"front_door":1800009999}'}, blocking=True)
        self.delay_hook = mute_after_failure
        await self.run_event("end", inputs={"provider": "test", "silence_table": "input_text.silence", "helper": "input_boolean.busy", "frigate_retry_time": {"seconds": 1}})
        self.assertEqual(len(self.ai_calls), 1)
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")

    async def test_other_event_cooldown_during_ai_delay_is_respected(self):
        async def other_event():
            await self.hass.services.async_call("input_datetime", "set_datetime", {"entity_id": "input_datetime.cooldown", "timestamp": self.clock.timestamp()}, blocking=True, context=Context())
        self.delay_hook = other_event
        await self.run_event("end", inputs={"provider": "test", "cooldown_timestamp": "input_datetime.cooldown", "cooldown": {"minutes": 2}})
        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.ai_calls, [])

    async def test_unloaded_ai_provider_does_not_leave_busy_flag(self):
        self.entries["test"]._async_set_state(self.hass, config_entries.ConfigEntryState.NOT_LOADED, None)
        self.hass.services.async_remove("llmvision", "video_analyzer")
        await self.run_event("end", inputs={"provider": "test", "helper": "input_boolean.busy"})
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")
        self.assertEqual(len(self.notifications), 1)

    async def test_provider_unloaded_during_delay_does_not_latch_busy_flag(self):
        async def unload():
            self.entries["test"]._async_set_state(self.hass, config_entries.ConfigEntryState.NOT_LOADED, None)
            self.hass.services.async_remove("llmvision", "video_analyzer")
        self.delay_hook = unload
        await self.run_event("end", inputs={"provider": "test", "helper": "input_boolean.busy"})
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")
        self.assertEqual(self.ai_calls, [])
        self.assertEqual(len(self.notifications), 1)

    async def test_provider_unloaded_during_retry_stops_cleanly(self):
        self.ai_failures = 1
        async def unload_after_failure():
            if self.ai_calls:
                self.entries["test"]._async_set_state(self.hass, config_entries.ConfigEntryState.NOT_LOADED, None)
                self.hass.services.async_remove("llmvision", "video_analyzer")
        self.delay_hook = unload_after_failure
        await self.run_event("end", inputs={"provider": "test", "helper": "input_boolean.busy", "frigate_retry_time": {"seconds": 1}})
        self.assertEqual(len(self.ai_calls), 1)
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")

    async def test_provider_unloaded_while_queued_for_busy_helper(self):
        async def queue_then_unload():
            await self.hass.services.async_call("input_boolean", "turn_on", {"entity_id": "input_boolean.busy"}, blocking=True)
            async def release():
                await asyncio.sleep(.01)
                self.entries["test"]._async_set_state(self.hass, config_entries.ConfigEntryState.NOT_LOADED, None)
                self.hass.services.async_remove("llmvision", "video_analyzer")
                await self.hass.services.async_call("input_boolean", "turn_off", {"entity_id": "input_boolean.busy"}, blocking=True)
            self.hass.async_create_task(release())
        self.delay_hook = queue_then_unload
        await asyncio.wait_for(self.run_event("end", inputs={"provider": "test", "helper": "input_boolean.busy"}), timeout=5)
        self.assertEqual(self.ai_calls, [])
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")

    async def test_manual_mute_while_queued_for_busy_helper(self):
        async def queue_then_mute():
            await self.hass.services.async_call("input_boolean", "turn_on", {"entity_id": "input_boolean.busy"}, blocking=True)
            async def release():
                await asyncio.sleep(.01)
                await self.hass.services.async_call("input_text", "set_value", {"entity_id": "input_text.silence", "value": '{"front_door":1800009999}'}, blocking=True)
                await self.hass.services.async_call("input_boolean", "turn_off", {"entity_id": "input_boolean.busy"}, blocking=True)
            self.hass.async_create_task(release())
        self.delay_hook = queue_then_mute
        await asyncio.wait_for(self.run_event("end", inputs={"provider": "test", "helper": "input_boolean.busy", "silence_table": "input_text.silence"}), timeout=5)
        self.assertEqual(self.ai_calls, [])
        self.assertEqual(len(self.notifications), 1)

    async def test_current_llmvision_title_is_used_in_push_and_log(self):
        await self.run_event("end", inputs={"provider": "test", "log_helper": "input_text.ai_log"})
        self.assertEqual(self.notifications[-1]["title"], "Delivery")
        self.assertIn(": Delivery\n", self.hass.states.get("input_text.ai_log").state)

    async def test_legacy_title_and_disabled_title_generation(self):
        self.ai_result = {"response_title": "Legacy title", "response_text": "A visitor arrives."}
        await self.run_event("end", inputs={"provider": "test"})
        self.assertEqual(self.notifications[-1]["title"], "Legacy title")
        await self.run_event("end", inputs={"provider": "test", "generate_title": False})
        self.assertEqual(self.notifications[-1]["title"], "Person detected")

    async def test_null_ai_response_text_is_not_sent_as_a_summary(self):
        self.ai_result = {"title": "Empty", "response_text": None}
        await self.run_event("end", inputs={"provider": "test", "helper": "input_boolean.busy", "frigate_retry_attempts": 2, "frigate_retry_time": {"seconds": 0}})
        self.assertEqual(len(self.ai_calls), 2)
        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")

    async def test_event_without_retained_media_links_to_live(self):
        await self.run_event("end", after=tracked(has_clip=False, has_snapshot=False), inputs={"provider": "test"})
        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.notifications[0]["data"]["url"], "entityId:camera.front_door")
        self.assertEqual(self.notifications[0]["data"]["actions"][0]["title"], "View Live")
        self.assertEqual(self.ai_calls, [])

    async def test_exclusions_apply_to_every_event_and_ai(self):
        for kind in ("new", "update", "end"):
            await self.run_event(kind, after=tracked(current_zones=["privacy"], entered_zones=["privacy"]), inputs={"zones_exclude": "privacy", "provider": "test"})
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.ai_calls, [])

    async def test_all_zones_requires_every_pattern(self):
        for kind in ("new", "update", "end"):
            await self.run_event(kind, inputs={"zones": "driveway, porch", "zone_logic": "all", "provider": "test"})
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.ai_calls, [])

    async def test_all_zones_allows_a_complete_match_and_exclusion_still_wins(self):
        options = {"zones": "drive*, porch", "zone_logic": "all"}
        event = tracked(entered_zones=["driveway", "porch"])
        await self.run_event(after=event, inputs=options)
        await self.run_event(after=event, inputs=options | {"zones_exclude": "porch"})
        self.assertEqual(len(self.notifications), 1)

    async def test_globs_and_literal_zone_names(self):
        await self.run_event(inputs={"zones": "drive*"})
        await self.run_event(inputs={"zones": "drivewa?"})
        await self.run_event(inputs={"zones": "drive"})
        await self.run_event(after=tracked(entered_zones=["zone+1"]), inputs={"zones": "zone+1", "zone_match_type": "entered"})
        self.assertEqual(len(self.notifications), 3)

    async def test_current_zones_do_not_include_previous_zones(self):
        await self.run_event("update", before=tracked(current_zones=["driveway"]), after=tracked(current_zones=["street"]), inputs={"zones": "driveway", "zone_match_type": "current"})
        self.assertEqual(self.notifications, [])

    async def test_zone_entry_and_face_change_notify_without_score_increase(self):
        await self.run_event("update", before=tracked(entered_zones=[], current_zones=[]), after=tracked(), inputs={"zones": "driveway"})
        await self.run_event("update", before=tracked(), after=tracked(sub_label=["Visitor", .92]))
        self.assertEqual(len(self.notifications), 2)

    async def test_snapshot_updates_only_notify_for_changed_moving_subjects(self):
        await self.run_event("update", before=tracked(), after=tracked())
        await self.run_event("update", before=tracked(), after=tracked(snapshot={"frame_time": 1800000001}))
        await self.run_event("update", before=tracked(), after=tracked(snapshot={"frame_time": 1800000002}, stationary=True))
        self.assertEqual(len(self.notifications), 1)

    async def test_native_face_tuple_is_suppressed(self):
        for kind in ("new", "update", "end"):
            await self.run_event(kind, after=tracked(sub_label=["John Doe", .92]), inputs={"suppress_known_faces": "john doe", "provider": "test"})
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.ai_calls, [])

    async def test_end_uses_final_clip_and_score(self):
        await self.run_event("end", before=tracked(has_clip=False, top_score=.65), after=tracked(has_clip=True, top_score=.95), inputs={"require_clip": True, "min_score": .9, "provider": "test"})
        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(len(self.ai_calls), 1)
        self.assertEqual(self.notifications[0]["data"]["tag"], tracked()["id"])
        self.assertEqual(self.notifications[1]["data"]["tag"], tracked()["id"])

    async def test_quality_filters_apply_to_ai(self):
        for event, options in (
            (tracked(top_score=.65), {"min_score": .9}),
            (tracked(has_clip=False), {"require_clip": True}),
            (tracked(false_positive=True), {"require_not_false_positive": True}),
            (tracked(entered_zones=[], current_zones=[]), {"require_zones": True}),
        ):
            await self.run_event("end", after=event, inputs={"provider": "test"} | options)
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.ai_calls, [])

    async def test_cooldown_blocks_both_normal_and_ai(self):
        await self.hass.services.async_call("input_datetime", "set_datetime", {"entity_id": "input_datetime.cooldown", "timestamp": self.clock.timestamp()}, blocking=True)
        await self.run_event("end", inputs={"provider": "test", "cooldown_timestamp": "input_datetime.cooldown", "cooldown": {"minutes": 2}})
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.ai_calls, [])

    async def test_own_final_card_does_not_block_its_summary(self):
        await self.run_event("end", inputs={"provider": "test", "cooldown_timestamp": "input_datetime.cooldown", "cooldown": {"minutes": 2}})
        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(len(self.ai_calls), 1)

    async def test_short_event_has_ai_with_silence_helper(self):
        inputs = {"provider": "test", "silence_table": "input_text.silence"}
        await self.run_event(inputs=inputs)
        self.clock += timedelta(seconds=5)
        await self.run_event("end", inputs=inputs)
        self.assertEqual(len(self.ai_calls), 1)
        self.assertEqual(self.hass.states.get("input_text.silence").state, "{}")

    async def test_manual_mute_during_ai_delay_is_respected(self):
        async def mute():
            await self.hass.services.async_call("input_text", "set_value", {"entity_id": "input_text.silence", "value": '{"front_door": 1800009999}'}, blocking=True)
        self.delay_hook = mute
        await self.run_event("end", inputs={"provider": "test", "silence_table": "input_text.silence"})
        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.ai_calls, [])

    async def test_busy_flag_released_after_analyzer_failure(self):
        self.ai_failures = 1
        await self.run_event("end", inputs={"provider": "test", "helper": "input_boolean.busy", "frigate_retry_time": {"seconds": 1}})
        self.assertEqual(len(self.ai_calls), 2)
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")
        self.assertEqual(len(self.notifications), 2)

    async def test_all_ai_failures_leave_no_busy_flag_or_fake_summary(self):
        self.ai_failures = 9
        await self.run_event("end", inputs={"provider": "test", "helper": "input_boolean.busy", "frigate_retry_attempts": 2, "frigate_retry_time": {"seconds": 0}})
        self.assertEqual(len(self.ai_calls), 2)
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")
        self.assertEqual(len(self.notifications), 1)
        self.assertTrue(any("AI analysis failed" in item.get("message", "") for item in self.logs))

    async def test_ai_log_is_wired_bounded_and_has_real_newlines(self):
        self.ai_result = {"response_title": "Delivery", "response_text": "A" * 400}
        await self.run_event("end", inputs={"provider": "test", "log_helper": "input_text.ai_log"})
        value = self.hass.states.get("input_text.ai_log").state
        self.assertEqual(len(value), 255)
        self.assertIn("\n", value)
        self.assertNotIn("\\n", value)
        self.assertEqual(len(self.notifications), 2)

    async def test_manual_silence_numeric_reply_is_clamped(self):
        await self.run_event(inputs={"silence_table": "input_text.silence"}, mobile={"action": "SILENCE_automation.frigate_test__front_door", "reply_text": "999"})
        import json
        table = json.loads(self.hass.states.get("input_text.silence").state)
        self.assertEqual(table["front_door"], int(self.clock.timestamp()) + 120 * 60)

    async def test_malformed_helpers_do_not_abort_notifications(self):
        await self.hass.services.async_call("input_text", "set_value", {"entity_id": "input_text.silence", "value": "not JSON"}, blocking=True)
        await self.run_event(inputs={"silence_table": "input_text.silence", "camera_name_map": "[]"})
        self.assertEqual(len(self.notifications), 1)

    async def test_helper_json_accepts_valid_numbers_and_ignores_non_objects(self):
        await self.hass.services.async_call("input_text", "set_value", {"entity_id": "input_text.silence", "value": '{"front_door":1.800009999e9}'}, blocking=True)
        await self.run_event(inputs={"silence_table": "input_text.silence"})
        self.assertEqual(self.notifications, [])
        await self.hass.services.async_call("input_text", "set_value", {"entity_id": "input_text.silence", "value": "[]"}, blocking=True)
        await self.run_event(inputs={"silence_table": "input_text.silence", "camera_name_map": "null"})
        self.assertEqual(len(self.notifications), 1)

    async def test_camera_override_preserves_real_live_entity(self):
        await self.run_event(inputs={"camera": ["camera.front_door_2"], "camera_name_map": '{"camera.front_door_2":"front_door"}'})
        self.assertEqual(self.notifications[0]["data"]["actions"][1]["uri"], "entityId:camera.front_door_2")

    async def test_ios_url_and_explicit_base(self):
        await self.run_event(inputs={"ios_live_view": True, "base_url": "https://ha.example/", "frigate_url": "https://frigate.example"})
        data = self.notifications[0]["data"]
        self.assertTrue(data["url"].startswith("https://ha.example/api/frigate/"))
        self.assertTrue(data["url"].endswith("master.m3u8"))
        self.assertEqual(len(data["actions"]), 4)
        await self.run_event(inputs={"base_url": "  ", "local_url": "http://ha.lan:8123/"})
        self.assertTrue(self.notifications[-1]["data"]["url"].startswith("http://ha.lan:8123/api/frigate/"))

    async def test_failed_device_does_not_block_remaining_devices(self):
        await self.run_event(inputs={"notify_device": ["other_phone", "phone"]})
        self.assertEqual(len(self.notifications), 1)

    async def test_deleted_device_does_not_block_remaining_devices(self):
        await self.run_event(inputs={"notify_device": ["deleted-device", "phone"]})
        self.assertEqual(len(self.notifications), 1)

    async def test_unloaded_mobile_app_does_not_block_remaining_devices(self):
        self.entries["other_phone"]._async_set_state(self.hass, config_entries.ConfigEntryState.NOT_LOADED, None)
        self.hass.services.async_remove("notify", "mobile_app_other_phone")
        await self.run_event(inputs={"notify_device": ["other_phone", "phone"]})
        self.assertEqual(len(self.notifications), 1)

    async def test_mixed_platform_delivery_keeps_android_actions_within_limit(self):
        self.fail_other_phone = False
        await self.run_event(inputs={"notify_device": ["phone", "other_phone"], "ios_live_view": True, "dashboard": "/lovelace/events", "frigate_url": "https://frigate.example"})
        self.assertEqual(len(self.notifications), 2)
        ios, android = [item["data"] for item in self.notifications]
        self.assertEqual(len(ios["actions"]), 5)
        self.assertEqual(len(android["actions"]), 3)
        self.assertTrue(ios["url"].endswith("master.m3u8"))
        self.assertTrue(android["url"].endswith("clip.mp4"))

    async def test_irrelevant_camera_and_event_types_are_ignored(self):
        await self.run_event(after=tracked(camera="other_camera"))
        await self.run_event(kind="invalid")
        self.assertEqual(self.notifications, [])


if __name__ == "__main__":
    unittest.main()
