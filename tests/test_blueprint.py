"""Replay Frigate MQTT messages through Home Assistant's actual script engine.

Run with Python 3.14 and requirements-test.txt installed:
    python -m unittest discover -s tests -v
Delays advance a controlled clock; all other actions/templates use HA itself.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from inspect import signature
from importlib.metadata import version
from pathlib import Path
import tempfile
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch

from homeassistant import bootstrap, config_entries, loader
from homeassistant.core import Context, HomeAssistant, SupportsResponse
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA, PLATFORM_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.components.mqtt import trigger as mqtt_trigger
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import trigger as trigger_helper
from homeassistant.helpers.script import Script, async_validate_actions_config
from homeassistant.helpers.selector import ObjectSelector, SelectSelector
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml_dict


ROOT = Path(__file__).resolve().parents[1]


BLUEPRINT = load_yaml_dict(ROOT / "frigate-ai-notification.yaml")


def defaults():
    result = {}
    for key, config in BLUEPRINT["blueprint"]["input"].items():
        if "input" in config:
            result.update({k: v["default"] for k, v in config["input"].items()})
        elif "default" in config:
            result[key] = config["default"]
    result.update(camera=["camera.front_door"], notify_device=["phone"])
    return result


def materialize(inputs):
    """Use HA's actual blueprint loader, defaults and !input substitution."""
    blueprint = Blueprint(deepcopy(BLUEPRINT), expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)
    instance = BlueprintInputs(blueprint, {"use_blueprint": {"path": "frigate-ai-notification.yaml", "input": inputs}})
    instance.validate()
    expanded = instance.async_substitute()
    PLATFORM_SCHEMA(deepcopy(expanded))
    return expanded


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
        # Load actual MQTT trigger code without needing a configured broker entry.
        original_platform = trigger_helper._async_get_trigger_platform
        async def platform_for_wait(hass, key):
            if key == "mqtt":
                return "mqtt", mqtt_trigger
            if key == "event":
                return "homeassistant", event_trigger
            return await original_platform(hass, key)
        self.enterContext(patch.object(trigger_helper, "_async_get_trigger_platform", side_effect=platform_for_wait))
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
        self.utc_patch = patch("homeassistant.util.dt.utcnow", side_effect=lambda: self.clock)
        self.utc_patch.start()
        self.epoch_patch = patch("homeassistant.core.time.time", side_effect=lambda: self.clock.timestamp())
        self.epoch_patch.start()
        self.entity_clock_patch = patch("homeassistant.helpers.entity.timer", side_effect=lambda: self.clock.timestamp())
        self.entity_clock_patch.start()
        for domain, config in {
            "input_text": {"silence": {"max": 255, "initial": "{}"}, "small_silence": {"max": 30, "initial": "{}"}, "ai_log": {"max": 255, "initial": ""}, "small_log": {"max": 40, "initial": ""}},
            "timer": {"front_activity": {"duration": "00:02:00", "restore": True}, "back_activity": {"duration": "00:02:00", "restore": True}},
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
        self.ai_hook = None

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
            if self.ai_hook:
                await self.ai_hook()
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
        self.utc_patch.stop()
        self.epoch_patch.stop()
        self.entity_clock_patch.stop()
        self.temp.cleanup()

    async def run_event(self, kind="new", before=None, after=None, inputs=None, mobile=None):
        selected = defaults() | (inputs or {})
        selected["notify_device"] = [self.devices.get(device, device) for device in selected["notify_device"]]
        config = materialize(selected)
        # Check the real, unmodified action schema as well as the accelerated script.
        cv.SCRIPT_SCHEMA(config["actions"])
        sequence = await async_validate_actions_config(self.hass, cv.SCRIPT_SCHEMA(fast_delays(config["actions"])))
        script = Script(self.hass, sequence, "Frigate regression", "automation", script_mode="parallel")
        trigger = {"id": "frigate-event", "payload_json": {"type": kind, "before": before or {}, "after": after if after is not None else tracked()}}
        if mobile is not None:
            trigger = {"id": "mobile-action", "event": SimpleNamespace(data=mobile)}
        await script.async_run({"trigger": trigger, "this": self.hass.states.get("automation.frigate_test")}, context=Context())
        return script

    async def attach_triggers(self, inputs=None):
        """Keep HA's real MQTT/event triggers; replace only broker transport."""
        selected = {"camera": ["camera.front_door"], "notify_device": [self.devices["phone"]]} | (inputs or {})
        raw_config = materialize(selected)
        config = PLATFORM_SCHEMA({**raw_config, "actions": fast_delays(raw_config["actions"])})
        subscriptions = {}
        self.mqtt_subscriptions = subscriptions

        def subscribe(hass, topic, callback, **kwargs):
            subscriptions.setdefault(topic, []).append(callback)
            def remove():
                callbacks = subscriptions.get(topic, [])
                if callback in callbacks:
                    callbacks.remove(callback)
                if not callbacks:
                    subscriptions.pop(topic, None)
            return remove

        # Keep HA's actual trigger schema, matching and wait lifecycle. Replace
        # broker transport and platform discovery (no broker config entry in tests).
        self.enterContext(patch.object(mqtt_trigger, "async_subscribe_internal", side_effect=subscribe))
        actions = await async_validate_actions_config(self.hass, config["actions"])
        script = Script(self.hass, actions, "Trigger regression", "automation", script_mode=config["mode"])

        async def run(variables, context=None):
            await script.async_run({"this": self.hass.states.get("automation.frigate_test"), **variables}, context=context or Context())

        trigger_variables = config["trigger_variables"].async_render(self.hass, {}, limited=True) if config.get("trigger_variables") else {}
        for index, trigger in enumerate(config["triggers"]):
            enabled = trigger.get("enabled", True)
            if hasattr(enabled, "async_render"):
                enabled = enabled.async_render(trigger_variables, limited=True)
            if not enabled:
                continue
            platform = {"mqtt": mqtt_trigger, "event": event_trigger}[trigger["platform"]]
            trigger = platform.TRIGGER_SCHEMA(trigger)
            info = {"domain": "automation", "name": "Frigate regression", "variables": trigger_variables, "trigger_data": {"id": trigger["id"], "idx": str(index), "alias": None}}
            with patch.object(mqtt_trigger, "async_subscribe_internal", side_effect=subscribe):
                remove = await platform.async_attach_trigger(self.hass, trigger, run, info)
            self.addCleanup(remove)

        async def publish(payload, topic="frigate/events", wait=True):
            for callback in list(subscriptions.get(topic, [])):
                callback(ReceiveMessage(topic, payload, 0, False, topic, self.clock.timestamp()))
            if wait:
                await self.hass.async_block_till_done()

        return publish

    async def test_actual_mqtt_trigger_parses_custom_topic_and_all_event_types(self):
        publish = await self.attach_triggers({"mqtt_topic": "custom/events"})
        message = {"type": "new", "before": {}, "after": tracked()}
        await publish(json.dumps(message))
        self.assertEqual(self.notifications, [])
        for kind in ("new", "update", "end"):
            await publish(json.dumps(message | {"type": kind}), "custom/events")
        self.assertEqual(len(self.notifications), 3)
        self.assertEqual(self.notifications[-1]["data"]["tag"], "automation.frigate_test::front_door")

    async def test_actual_mqtt_trigger_rejects_invalid_json_and_non_object_payloads(self):
        publish = await self.attach_triggers({"debug": True})
        for payload in ("not JSON", "[]", "null", '"text"', '{}'):
            await publish(payload)
        self.assertEqual(self.notifications, [])
        self.assertEqual(len(self.logs), 5)
        self.assertTrue(all("invalid_payload" in log["message"] for log in self.logs))

    async def test_actual_mobile_event_trigger_routes_silence_to_own_automation(self):
        await self.attach_triggers({"silence_table": "input_text.silence"})
        self.hass.bus.async_fire("mobile_app_notification_action", {"action": "SILENCE_automation.other__front_door", "reply_text": "5"})
        await self.hass.async_block_till_done()
        self.assertEqual(self.hass.states.get("input_text.silence").state, "{}")
        self.hass.bus.async_fire("mobile_app_notification_action", {"action": "SILENCE_automation.frigate_test__front_door", "reply_text": "5"})
        await self.hass.async_block_till_done()
        self.assertEqual(json.loads(self.hass.states.get("input_text.silence").state)["front_door"], int(self.clock.timestamp()) + 300)
        self.assertEqual(self.notifications, [])

    async def test_custom_labels_are_selectable_and_filter_events(self):
        selector = SelectSelector(BLUEPRINT["blueprint"]["input"]["labels"]["selector"]["select"])
        labels = selector(["truck", "custom_object"])
        self.assertEqual(labels, ["truck", "custom_object"])
        for label in ("truck", "CUSTOM_OBJECT", "person"):
            await self.run_event(after=tracked(label=label), inputs={"labels": labels})
        self.assertEqual(len(self.notifications), 2)

    async def test_rejection_debug_names_camera_label_type_and_missing_id(self):
        for kind, event, reason in (
            ("new", tracked(camera="unknown"), "camera_unmatched"),
            ("new", tracked(label="truck"), "label_unselected"),
            ("invalid", tracked(), "unsupported_event_type"),
            ("end", tracked(id=""), "missing_event_id"),
        ):
            await self.run_event(kind, after=event, inputs={"debug": True})
            self.assertIn(reason, self.logs[-1]["message"])
        self.assertEqual(self.notifications, [])
        self.logs.clear()
        await self.run_event(after=tracked(camera="unknown"))
        self.assertEqual(self.logs, [])

    async def test_zone_migration_and_debug_explain_full_id_matching(self):
        event = tracked(current_zones=["front_porch"], entered_zones=["front_porch"])
        await self.run_event(after=event, inputs={"zones": "porch", "debug": True})
        self.assertEqual(self.notifications, [])
        self.assertIn("include_unmatched", self.logs[-1]["message"])
        self.assertIn("front_porch", self.logs[-1]["message"])
        await self.run_event(after=event, inputs={"zones": "*porch*"})
        await self.run_event(after=event, inputs={"zones_exclude": "porch"})
        await self.run_event(after=event, inputs={"zones_exclude": "*porch*", "debug": True})
        self.assertEqual(len(self.notifications), 2)
        self.assertIn("zone_reason=excluded", self.logs[-1]["message"])

    async def test_live_urls_work_for_both_platforms_and_no_media_taps(self):
        self.fail_other_phone = False
        for has_media in (True, False):
            await self.run_event(after=tracked(has_clip=has_media, has_snapshot=False), inputs={"notify_device": ["phone", "other_phone"], "ios_live_view": True, "base_url": "https://ha.example"})
        live = "/?more-info-entity-id=camera.front_door"
        for notification in self.notifications:
            data = notification["data"]
            self.assertEqual(data["url"], data["clickAction"])
            self.assertTrue(any(action.get("uri") == live for action in data["actions"]))
        self.assertEqual([n["data"]["url"] for n in self.notifications[-2:]], [live, live])

    async def test_legacy_temperature_is_accepted_but_obsolete_fields_are_not_sent(self):
        await self.run_event("end", inputs={"provider": "test", "temperature": .8})
        self.assertEqual(len(self.ai_calls), 1)
        self.assertNotIn("temperature", self.ai_calls[0])
        self.assertNotIn("remember", self.ai_calls[0])
        self.assertTrue(self.ai_calls[0]["store_in_timeline"])

    async def test_overlapping_end_events_wait_for_busy_helper_and_keep_own_tags(self):
        first_started, release_first = asyncio.Event(), asyncio.Event()

        async def hold_first_analysis():
            if len(self.ai_calls) == 1:
                first_started.set()
                await release_first.wait()

        self.ai_hook = hold_first_analysis
        publish = await self.attach_triggers({"provider": "test", "helper": "input_boolean.busy", "camera": ["camera.front_door", "camera.back_yard"]})
        first = tracked()
        second = tracked(id="1800000001.123456-back", camera="back_yard")
        await publish(json.dumps({"type": "end", "after": first}), wait=False)
        await asyncio.wait_for(first_started.wait(), timeout=5)
        try:
            await publish(json.dumps({"type": "end", "after": second}), wait=False)
            await asyncio.sleep(.02)
            self.assertEqual(len(self.ai_calls), 1)
            self.assertEqual(len(self.notifications), 2)
        finally:
            release_first.set()
        await asyncio.wait_for(self.hass.async_block_till_done(), timeout=5)
        self.assertEqual(len(self.ai_calls), 2)
        self.assertEqual(len(self.notifications), 4)
        self.assertEqual(sorted(n["data"]["tag"] for n in self.notifications), sorted(["automation.frigate_test::front_door"] * 2 + ["automation.frigate_test::back_yard"] * 2))
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")

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
        expanded = materialize({"camera": ["camera.front_door"], "notify_device": [self.devices["phone"]]})
        self.assertEqual(expanded["triggers"][0]["topic"], "frigate/events")
        self.assertEqual(expanded["mode"], "parallel")

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
        self.assertEqual(self.notifications[0]["data"]["url"], "/?more-info-entity-id=camera.front_door")
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

    async def test_zone_entry_notifies_but_face_change_alone_does_not(self):
        await self.run_event("update", before=tracked(entered_zones=[], current_zones=[]), after=tracked(), inputs={"zones": "driveway"})
        await self.run_event("update", before=tracked(), after=tracked(sub_label=["Visitor", .92]))
        self.assertEqual(len(self.notifications), 1)

    async def test_snapshot_updates_do_not_resend_notifications(self):
        await self.run_event("update", before=tracked(), after=tracked())
        await self.run_event("update", before=tracked(), after=tracked(snapshot={"frame_time": 1800000001}))
        await self.run_event("update", before=tracked(), after=tracked(snapshot={"frame_time": 1800000002}, stationary=True))
        self.assertEqual(len(self.notifications), 0)

    async def test_native_face_tuple_is_suppressed(self):
        for kind in ("new", "update", "end"):
            await self.run_event(kind, after=tracked(sub_label=["John Doe", .92]), inputs={"suppress_known_faces": "john doe", "provider": "test"})
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.ai_calls, [])

    async def test_end_uses_final_clip_and_score(self):
        await self.run_event("end", before=tracked(has_clip=False, top_score=.65), after=tracked(has_clip=True, top_score=.95), inputs={"require_clip": True, "min_score": .9, "provider": "test"})
        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(len(self.ai_calls), 1)
        self.assertEqual(self.notifications[0]["data"]["tag"], "automation.frigate_test::front_door")
        self.assertEqual(self.notifications[1]["data"]["tag"], "automation.frigate_test::front_door")

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
        self.assertEqual(self.notifications[0]["data"]["actions"][1]["uri"], "/?more-info-entity-id=camera.front_door_2")

    async def test_ios_url_and_explicit_base(self):
        await self.run_event(inputs={"ios_live_view": True, "clip_padding_seconds": 0, "base_url": "https://ha.example/", "frigate_url": "https://frigate.example"})
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
        self.assertTrue(ios["url"].endswith("clip.mp4?padding=10"))
        self.assertTrue(android["url"].endswith("clip.mp4?padding=10"))


    async def test_clip_context_uses_mp4_on_both_platforms_and_restores_hls_at_zero(self):
        self.fail_other_phone = False
        for padding in (0, 25):
            await self.run_event(inputs={"notify_device": ["phone", "other_phone"], "ios_live_view": True,
                                         "base_url": "https://ha.example/", "clip_padding_seconds": padding})
            ios, android = [n["data"] for n in self.notifications[-2:]]
            expected = f"https://ha.example/api/frigate/notifications/1800000000.123456-front/front_door/clip.mp4?padding={padding}"
            apple_expected = expected if padding else "https://ha.example/api/frigate/notifications/1800000000.123456-front/front_door/master.m3u8"
            self.assertEqual(ios["url"], apple_expected)
            self.assertEqual(ios["clickAction"], apple_expected)
            self.assertTrue(any(a.get("uri") == apple_expected for a in ios["actions"]))
            self.assertEqual(android["url"], expected)
            self.assertEqual(android["clickAction"], expected)
            self.assertTrue(any(a.get("uri") == expected for a in android["actions"]))

    async def test_clip_context_preserves_quiet_replacements_and_no_media_fallback(self):
        inputs = self.activity_inputs(notify_device=["other_phone"], clip_padding_seconds=15)
        self.fail_other_phone = False
        await self.run_event(after=tracked(has_clip=False, has_snapshot=False), inputs=inputs)
        initial = self.notifications[-1]["data"]
        self.assertEqual(initial["url"], "/?more-info-entity-id=camera.front_door")
        await self.run_event("end", after=tracked(), inputs=inputs)
        final = self.notifications[-1]["data"]
        self.assertTrue(final["url"].endswith("clip.mp4?padding=15"))
        self.assertEqual(initial["tag"], final["tag"])
        self.assertTrue(final["alert_once"])
        self.assertEqual(len(self.fresh_alerts()), 1)

    def activity_inputs(self, **changes):
        return {
            "activity_timer_rows": [
                {"camera": "camera.front_door", "timer": "timer.front_activity"},
                {"camera": "camera.back_yard", "timer": "timer.back_activity"},
            ],
            "camera": ["camera.front_door", "camera.back_yard"],
            **changes,
        }

    def fresh_alerts(self):
        return [n for n in self.notifications if not n["data"]["alert_once"]]

    async def test_activity_picker_rows_keep_independent_rolling_windows(self):
        inputs = {"camera": ["camera.front_door", "camera.back_yard"], "activity_timer_rows": [
            {"camera": "camera.front_door", "timer": "timer.front_activity"},
            {"camera": "camera.back_yard", "timer": "timer.back_activity"},
        ]}
        await self.run_event(inputs=inputs)
        self.clock += timedelta(seconds=119)
        await self.run_event("update", before=tracked(), after=tracked(), inputs=inputs)
        await self.run_event(after=tracked(camera="back_yard", id="back-track"), inputs=inputs)
        await self.run_event(after=tracked(id="split-track"), inputs=inputs)
        self.assertEqual(len(self.fresh_alerts()), 2)
        self.assertEqual(len(self.notifications), 3)
        self.assertTrue(self.notifications[-1]["data"]["alert_once"])
        for timer in ("timer.front_activity", "timer.back_activity"):
            self.assertEqual(self.hass.states.get(timer).state, "active")

    async def test_activity_picker_rows_follow_camera_name_override(self):
        inputs = self.activity_inputs(camera_name_map=json.dumps({"camera.front_door": "EntryCam"}))
        await self.run_event(after=tracked(camera="EntryCam"), inputs=inputs)
        self.assertEqual(len(self.fresh_alerts()), 1)
        self.assertEqual(self.hass.states.get("timer.front_activity").state, "active")
        self.assertEqual(self.hass.states.get("timer.back_activity").state, "idle")

    async def test_activity_picker_rows_reject_duplicates_and_shared_timers(self):
        for rows in ([{"camera": "camera.front_door", "timer": "timer.front_activity"},
                      {"camera": "camera.front_door", "timer": "timer.back_activity"}],
                     [{"camera": "camera.front_door", "timer": "timer.front_activity"},
                      {"camera": "camera.back_yard", "timer": "timer.front_activity"}],
                     [{"camera": "camera.front_door", "timer": "input_boolean.busy"}]):
            await self.run_event(inputs={"activity_timer_rows": rows})
            self.assertEqual(self.notifications, [])
            self.assertIn("one row per camera", self.logs[-1]["message"])

    async def test_activity_picker_uses_real_ha_nested_entity_validation(self):
        config = BLUEPRINT["blueprint"]["input"]["activity_and_silence"]["input"]["activity_timer_rows"]["selector"]["object"]
        picker = ObjectSelector(config)
        row = {"camera": "camera.front_door", "timer": "timer.front_activity"}
        self.assertEqual(picker([row]), [row])
        for invalid in ({"camera": "camera.front_door"}, row | {"timer": "not_an_entity_id"}):
            with self.assertRaises(Exception):
                picker([invalid])

    async def test_activity_groups_changed_ids_faces_and_snapshots_until_quiet(self):
        inputs = self.activity_inputs()
        first = tracked(has_clip=False)
        await self.run_event(after=first, inputs=inputs)
        for i in range(5):
            self.clock += timedelta(seconds=2)
            after = tracked(id=f"split-{i}", sub_label=[f"Unreliable-{i}", .9],
                            snapshot={"frame_time": 1800000001 + i}, has_clip=False)
            await self.run_event("update", before=first, after=after, inputs=inputs)
            first = after
        await self.run_event("update", before=first, after=first | {"has_clip": True}, inputs=inputs)
        await self.run_event("end", before=first | {"has_clip": True}, after=first | {"has_clip": True}, inputs=inputs)
        self.assertEqual(len(self.fresh_alerts()), 1)
        self.assertEqual(len(self.notifications), 3)  # initial, clip and END replacement
        self.assertEqual({n["data"]["tag"] for n in self.notifications}, {"automation.frigate_test::front_door"})
        self.assertTrue(all(n["data"]["push"]["interruption-level"] == "passive" for n in self.notifications[1:]))

    async def test_activity_renews_on_every_eligible_tick_not_a_fixed_cooldown(self):
        inputs = self.activity_inputs()
        await self.run_event(inputs=inputs)
        for _ in range(3):
            self.clock += timedelta(seconds=119)
            await self.run_event("update", before=tracked(), after=tracked(), inputs=inputs)
            finish = datetime.fromisoformat(self.hass.states.get("timer.front_activity").attributes["finishes_at"])
            self.assertAlmostEqual((finish - self.clock).total_seconds(), 120, delta=1)
        self.assertEqual(len(self.fresh_alerts()), 1)
        self.assertEqual(len(self.notifications), 1)

    async def test_activity_alerts_again_after_timer_expires(self):
        inputs = self.activity_inputs()
        await self.run_event(inputs=inputs)
        self.clock += timedelta(seconds=121)
        await self.hass.services.async_call("timer", "finish", {"entity_id": "timer.front_activity"}, blocking=True)
        await self.run_event("update", before=tracked(), after=tracked(id="new-track"), inputs=inputs)
        self.assertEqual(len(self.fresh_alerts()), 2)
        self.assertEqual(self.notifications[0]["data"]["tag"], self.notifications[1]["data"]["tag"])

    async def test_activity_cameras_have_independent_windows(self):
        inputs = self.activity_inputs()
        await asyncio.gather(
            self.run_event(after=tracked(), inputs=inputs),
            self.run_event(after=tracked(camera="back_yard", id="other-track"), inputs=inputs),
        )
        self.assertEqual(len(self.fresh_alerts()), 2)
        self.assertEqual(self.hass.states.get("timer.front_activity").state, "active")
        self.assertEqual(self.hass.states.get("timer.back_activity").state, "active")
        self.assertEqual(len({n["data"]["tag"] for n in self.notifications}), 2)

    async def test_activity_simultaneous_starts_have_one_alert_owner(self):
        inputs = self.activity_inputs()
        await asyncio.gather(*(self.run_event(after=tracked(id=f"overlap-{i}"), inputs=inputs) for i in range(5)))
        self.assertEqual(len(self.fresh_alerts()), 1)
        self.assertEqual(len({n["data"]["tag"] for n in self.notifications}), 1)

    async def test_activity_invalid_timer_stops_with_configuration_message(self):
        await self.run_event(inputs=self.activity_inputs(activity_timer_rows=[{"camera": "camera.front_door", "timer": "timer.missing"}]))
        self.assertEqual(self.notifications, [])
        self.assertIn("missing, unavailable, or shared", self.logs[-1]["message"])

    async def test_activity_rejected_event_does_not_extend_window(self):
        await self.run_event(after=tracked(top_score=.2), inputs=self.activity_inputs())
        self.assertEqual(self.hass.states.get("timer.front_activity").state, "idle")
        self.assertEqual(self.notifications, [])

    async def test_activity_superseded_ai_is_not_analyzed(self):
        changed = False
        async def newer_activity():
            nonlocal changed
            if not changed and self.clock.timestamp() > 1800000020:
                changed = True
                await self.run_event("update", before=tracked(), after=tracked(id="next-track"), inputs=self.activity_inputs())
        self.delay_hook = newer_activity
        await self.run_event("end", inputs=self.activity_inputs(provider="test"))
        self.assertTrue(changed)
        self.assertEqual(self.ai_calls, [])

    async def test_activity_ai_updates_the_camera_card_quietly(self):
        await self.run_event("end", inputs=self.activity_inputs(provider="test"))
        self.assertEqual(len(self.ai_calls), 1)
        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(len(self.fresh_alerts()), 1)
        self.assertEqual(self.notifications[0]["data"]["tag"], self.notifications[1]["data"]["tag"])
        self.assertEqual(self.notifications[-1]["data"]["push"]["interruption-level"], "passive")

    async def test_activity_shared_timer_is_rejected_instead_of_coupling_cameras(self):
        await self.run_event(inputs=self.activity_inputs(activity_timer_rows=[{"camera": "camera.front_door", "timer": "timer.front_activity"}, {"camera": "camera.back_yard", "timer": "timer.front_activity"}]))
        self.assertEqual(self.notifications, [])
        self.assertIn("shared by cameras", self.logs[-1]["message"])

    async def test_activity_same_camera_race_uses_real_delay_scheduling(self):
        inputs = self.activity_inputs()
        config = materialize(defaults() | inputs | {"notify_device": [self.devices["phone"]]})
        script = Script(self.hass, cv.SCRIPT_SCHEMA(config["actions"]), "Activity claim race", "automation", script_mode="parallel")
        async def start(i):
            await script.async_run({"trigger": {"id": "frigate-event", "payload_json": {"type": "new", "before": {}, "after": tracked(id=f"race-{i}")}}, "this": self.hass.states.get("automation.frigate_test")}, context=Context())
        await asyncio.gather(*(start(i) for i in range(8)))
        self.assertEqual(len(self.fresh_alerts()), 1)
        self.assertEqual({n["data"]["tag"] for n in self.notifications}, {"automation.frigate_test::front_door"})

    async def test_activity_ai_result_cannot_overwrite_newer_camera_activity(self):
        async def new_activity_during_analysis():
            self.clock += timedelta(seconds=1)
            await self.run_event("update", before=tracked(), after=tracked(id="newer-track"), inputs=self.activity_inputs())
        self.ai_hook = new_activity_during_analysis
        await self.run_event("end", inputs=self.activity_inputs(provider="test"))
        self.assertEqual(len(self.ai_calls), 1)
        self.assertEqual(len(self.notifications), 1)

    async def test_name_change_is_metadata_not_a_new_alert_or_identity_claim(self):
        await self.run_event(after=tracked(sub_label=["Unreliable Label", .99]))
        self.assertEqual(self.notifications[-1]["title"], "Person detected")
        self.assertIn("Frigate label: Unreliable Label", self.notifications[-1]["message"])

    async def test_activity_start_survives_update_near_wall_clock_second_boundary(self):
        self.clock += timedelta(milliseconds=900)
        ran_update = False
        async def update_while_claim_settles():
            nonlocal ran_update
            if not ran_update:
                ran_update = True
                await self.run_event("update", before=tracked(), after=tracked(), inputs=self.activity_inputs())
        self.delay_hook = update_while_claim_settles
        await self.run_event(inputs=self.activity_inputs())
        self.assertTrue(ran_update)
        self.assertEqual(len(self.fresh_alerts()), 1)
        self.assertEqual(len(self.notifications), 1)

    async def test_activity_new_track_updates_clip_as_soon_as_it_enters_zone(self):
        inputs = self.activity_inputs(zones="driveway")
        await self.run_event(after=tracked(id="previous-track"), inputs=inputs)
        self.clock += timedelta(seconds=60)
        before = tracked(id="current-track", entered_zones=[], current_zones=[], has_clip=True)
        after = tracked(id="current-track", has_clip=True)
        await self.run_event("update", before=before, after=after, inputs=inputs)
        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(len(self.fresh_alerts()), 1)
        update = self.notifications[-1]["data"]
        self.assertIn("/current-track/", update["url"])
        self.assertEqual(update["tag"], self.notifications[0]["data"]["tag"])
        self.assertTrue(update["alert_once"])
        self.assertEqual(update["push"]["interruption-level"], "passive")
        # No END was required, and more snapshots still cannot resend this card.
        await self.run_event("update", before=after, after=after | {"snapshot": {"frame_time": 1800000062}}, inputs=inputs)
        self.assertEqual(len(self.notifications), 2)

    async def start_native_wait(self, event_after=None, **changes):
        inputs = {"ai_source": "frigate", "native_description_timeout": 1, **changes}
        publish = await self.attach_triggers(inputs)
        event = {"type": "end", "before": tracked(), "after": event_after if event_after is not None else tracked()}
        await publish(json.dumps(event), inputs.get("mqtt_topic", "frigate/events"), wait=False)
        prefix = inputs.get("mqtt_topic", "frigate/events").rsplit("/", 1)[0]
        topic = inputs.get("native_mqtt_topic") or prefix + ("/reviews" if inputs.get("frigate_description_type") == "review" else "/tracked_object_update")
        for _ in range(1000):
            if self.hass.bus.async_listeners().get("frigate_ai_notification_description", 0):
                return publish, topic
            await asyncio.sleep(0)
        self.fail("Native description wait did not subscribe")

    async def test_auto_object_text_skips_configured_llmvision(self):
        publish, topic = await self.start_native_wait(ai_source="auto", provider="test")
        await publish(json.dumps({"type": "description", "id": tracked()["id"], "camera": "front_door", "description": "Native object text."}), topic)
        self.assertEqual(self.notifications[-1]["message"], "Native object text.")
        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(self.ai_calls, [])
        # A second text format for the same event cannot produce another update.
        await publish(json.dumps({"type": "genai", "after": {"camera": "front_door", "data": {"detections": [tracked()["id"]], "metadata": {"scene": "Later review text."}}}}), "frigate/reviews")
        self.assertEqual(len(self.notifications), 2)

    async def test_auto_discovers_review_without_selecting_its_type(self):
        publish, _ = await self.start_native_wait(ai_source="auto", provider="test")
        await publish(json.dumps({"type": "genai", "after": {"camera": "front_door", "data": {"detections": [tracked()["id"]], "metadata": {"scene": "Native review text.", "title": "Review title"}}}}), "frigate/reviews")
        self.assertEqual(self.notifications[-1]["message"], "Native review text.")
        self.assertEqual(self.notifications[-1]["title"], "Review title")
        self.assertEqual(self.ai_calls, [])

    async def test_auto_missing_native_text_falls_back_once(self):
        publish = await self.attach_triggers({"ai_source": "auto", "provider": "test", "native_description_timeout": .01})
        await publish(json.dumps({"type": "end", "after": tracked()}))
        self.assertEqual(len(self.ai_calls), 1)
        self.assertEqual(self.notifications[-1]["message"], self.ai_result["response_text"])
        self.assertEqual(self.notifications[-1]["data"]["tag"], self.notifications[0]["data"]["tag"])

    async def test_auto_without_fallback_provider_keeps_basic_alert(self):
        self.hass.services.async_remove("llmvision", "video_analyzer")
        publish = await self.attach_triggers({"ai_source": "auto", "native_description_timeout": .01})
        await publish(json.dumps({"type": "end", "after": tracked()}))
        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.ai_calls, [])
        self.assertFalse(any("provider is not loaded" in str(item) for item in self.logs))

    async def test_auto_without_clip_does_not_call_fallback(self):
        publish = await self.attach_triggers({"ai_source": "auto", "provider": "test", "native_description_timeout": .01})
        await publish(json.dumps({"type": "end", "after": tracked(has_clip=False, has_snapshot=True)}))
        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.ai_calls, [])

    async def test_auto_superseded_wait_does_not_start_fallback(self):
        inputs = self.activity_inputs(ai_source="auto", provider="test", native_description_timeout=.05)
        publish, _ = await self.start_native_wait(**inputs)
        self.clock += timedelta(seconds=1)
        await publish(json.dumps({"type": "new", "after": tracked(id="newer-object")} ), wait=False)
        await self.hass.async_block_till_done()
        self.assertEqual(self.ai_calls, [])

    async def test_auto_silenced_during_native_wait_does_not_start_fallback(self):
        publish, _ = await self.start_native_wait(ai_source="auto", provider="test", native_description_timeout=.05, silence_table="input_text.silence")
        await self.hass.services.async_call("input_text", "set_value", {"entity_id": "input_text.silence", "value": json.dumps({"front_door": int(self.clock.timestamp()) + 300})}, blocking=True)
        await self.hass.async_block_till_done()
        self.assertEqual(self.ai_calls, [])
        self.assertEqual(len(self.notifications), 1)

    async def test_auto_wait_counts_toward_clip_readiness_delay(self):
        publish, _ = await self.start_native_wait(ai_source="auto", provider="test", native_description_timeout=.02)
        # Model an already elapsed 90-second native wait without a real 90s sleep.
        self.clock += timedelta(seconds=90)
        before_fallback = self.clock
        await self.hass.async_block_till_done()
        self.assertEqual(len(self.ai_calls), 1)
        self.assertEqual(self.clock, before_fallback)

    async def test_native_object_description_updates_quietly_without_llmvision(self):
        self.hass.services.async_remove("llmvision", "video_analyzer")
        publish, topic = await self.start_native_wait(provider="test", log_helper="input_text.ai_log")
        self.assertEqual(len(self.notifications), 1)  # alert precedes AI text
        await publish(json.dumps({"type": "description", "id": tracked()["id"], "description": "A person carries a parcel."}), topic)
        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(self.notifications[-1]["message"], "A person carries a parcel.")
        self.assertEqual(self.notifications[-1]["data"]["tag"], self.notifications[0]["data"]["tag"])
        self.assertEqual(self.notifications[-1]["data"]["push"]["interruption-level"], "passive")
        self.assertEqual(self.ai_calls, [])
        self.assertIn("carries a parcel", self.hass.states.get("input_text.ai_log").state)
        self.assertEqual(self.hass.states.get("input_boolean.busy").state, "off")

    async def test_native_review_matches_detection_id_and_uses_scene_and_title(self):
        publish, topic = await self.start_native_wait(frigate_description_type="review")
        payload = {"type": "genai", "after": {"id": "different-review-id", "camera": "front_door", "data": {
            "detections": [tracked()["id"]], "metadata": {"title": "Parcel delivery", "scene": "A courier leaves a parcel and walks away."}}}}
        await publish(json.dumps(payload), topic)
        self.assertEqual(self.notifications[-1]["title"], "Parcel delivery")
        self.assertEqual(self.notifications[-1]["message"], "A courier leaves a parcel and walks away.")
        self.assertIn(tracked()["id"], self.notifications[-1]["data"]["url"])
        self.assertNotIn("different-review-id", self.notifications[-1]["data"]["url"])
        self.assertEqual(self.ai_calls, [])

    async def test_native_object_ignores_unrelated_malformed_empty_and_wrong_camera_updates(self):
        publish, topic = await self.start_native_wait()
        for payload in ("bad json", "[]", json.dumps({"type": "description", "id": "other", "description": "Wrong"}),
                        json.dumps({"type": "face", "id": tracked()["id"], "description": "Wrong"}),
                        json.dumps({"type": "description", "id": tracked()["id"], "description": "  "}),
                        json.dumps({"type": "description", "id": tracked()["id"], "camera": "back_yard", "description": "Wrong"})):
            await publish(payload, topic, wait=False)
            await asyncio.sleep(0)
        await publish(json.dumps({"type": "description", "id": tracked()["id"], "description": "Correct"}), topic)
        self.assertEqual([n["message"] for n in self.notifications][-1], "Correct")
        self.assertEqual(len(self.notifications), 2)

    async def test_native_review_rejects_unrelated_review_camera_and_non_narrative_updates(self):
        publish, topic = await self.start_native_wait(frigate_description_type="review")
        payload = {"type": "genai", "after": {"camera": "front_door", "data": {"detections": [tracked()["id"]], "metadata": {"scene": "Valid"}}}}
        for invalid in (payload | {"type": "end"},
                        payload | {"after": payload["after"] | {"camera": "back_yard"}},
                        payload | {"after": payload["after"] | {"data": {"detections": ["other"], "metadata": {"scene": "Wrong"}}}},
                        payload | {"after": payload["after"] | {"data": []}}):
            await publish(json.dumps(invalid), topic, wait=False)
            await asyncio.sleep(0)
        await publish(json.dumps(payload), topic)
        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(self.notifications[-1]["message"], "Valid")
        self.assertEqual(self.notifications[-1]["title"], "Person detected")

    async def test_native_custom_event_prefix_and_explicit_description_topic(self):
        for extra in ({"mqtt_topic": "outside/events"}, {"native_mqtt_topic": "special/descriptions"}):
            publish, topic = await self.start_native_wait(**extra)
            await publish(json.dumps({"type": "description", "id": tracked()["id"], "description": "Custom topic works"}), topic)
            self.assertEqual(self.notifications[-1]["message"], "Custom topic works")

    async def test_native_timeout_keeps_basic_alert_without_calling_llm(self):
        publish = await self.attach_triggers({"ai_source": "frigate", "native_description_timeout": .02, "debug": True, "provider": "test"})
        await publish(json.dumps({"type": "end", "after": tracked()}))
        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.ai_calls, [])
        self.assertTrue(any("before timeout" in n["message"] for n in self.logs))

    async def test_native_description_can_use_snapshot_without_retained_clip(self):
        publish, topic = await self.start_native_wait(event_after=tracked(has_clip=False, has_snapshot=True))
        await publish(json.dumps({"type": "description", "id": tracked()["id"], "description": "Snapshot description"}), topic)
        self.assertEqual(self.notifications[-1]["message"], "Snapshot description")
        self.assertTrue(self.notifications[-1]["data"]["url"].endswith("snapshot.jpg"))
        self.assertEqual(self.ai_calls, [])

    async def test_native_description_does_not_bypass_quality_zone_or_face_filters(self):
        for after, extra in ((tracked(top_score=.2), {}), (tracked(false_positive=True), {}),
                             (tracked(has_clip=False), {"require_clip": True}),
                             (tracked(), {"zones_exclude": "driveway"}),
                             (tracked(sub_label=["Alex", .9]), {"suppress_known_faces": "Alex"})):
            await self.run_event("end", after=after, inputs={"ai_source": "frigate", "native_description_timeout": .01, **extra})
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.ai_calls, [])

    async def test_off_source_suppresses_llm_even_with_saved_provider(self):
        await self.run_event("end", inputs={"ai_source": "none", "provider": "test"})
        self.assertEqual(self.ai_calls, [])
        self.assertEqual(len(self.notifications), 1)

    async def test_native_result_cannot_overwrite_newer_activity(self):
        inputs = self.activity_inputs()
        publish, topic = await self.start_native_wait(**inputs)
        self.clock += timedelta(seconds=1)
        await self.run_event(after=tracked(id="newer-track"), inputs=inputs | {"ai_source": "none"})
        count = len(self.notifications)
        await publish(json.dumps({"type": "description", "id": tracked()["id"], "description": "Outdated"}), topic)
        self.assertEqual(len(self.notifications), count)
        self.assertFalse(any(n["message"] == "Outdated" for n in self.notifications))

    async def test_native_wait_is_scoped_to_its_own_automation(self):
        publish, topic = await self.start_native_wait()
        self.hass.bus.async_fire("frigate_ai_notification_description", {
            "automation_entity": "automation.another_instance", "event_id": tracked()["id"],
            "camera": "front_door", "description": "Wrong automation", "title": "Wrong"})
        await asyncio.sleep(0)
        await publish(json.dumps({"type": "description", "id": tracked()["id"], "description": "Own automation"}), topic)
        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(self.notifications[-1]["message"], "Own automation")

    async def test_native_review_only_latest_waiter_updates_the_camera_card(self):
        inputs = self.activity_inputs(ai_source="frigate", frigate_description_type="review", native_description_timeout=1)
        publish, topic = await self.start_native_wait(**inputs)
        self.clock += timedelta(seconds=1)
        await publish(json.dumps({"type": "end", "before": tracked(id="later-track"), "after": tracked(id="later-track")}), wait=False)
        for _ in range(1000):
            if self.hass.bus.async_listeners().get("frigate_ai_notification_description", 0) >= 4:
                break
            await asyncio.sleep(0)
        else:
            self.fail("Second native waiter did not start")
        await publish(json.dumps({"type": "genai", "after": {"camera": "front_door", "data": {
            "detections": [tracked()["id"], "later-track"], "metadata": {"scene": "One review narrative"}}}}), topic)
        self.assertEqual(sum(n["message"] == "One review narrative" for n in self.notifications), 1)
        self.assertEqual(len(self.fresh_alerts()), 1)
        self.assertIn("/later-track/", self.notifications[-1]["data"]["url"])

    async def test_native_respects_competing_global_cooldown_while_waiting(self):
        publish, topic = await self.start_native_wait(cooldown={"seconds": 60}, cooldown_timestamp="input_datetime.cooldown")
        self.clock += timedelta(seconds=1)
        await self.hass.services.async_call("input_datetime", "set_datetime", {
            "entity_id": "input_datetime.cooldown", "timestamp": self.clock.timestamp()}, blocking=True)
        await publish(json.dumps({"type": "description", "id": tracked()["id"], "description": "Suppressed"}), topic)
        self.assertEqual(len(self.notifications), 1)

    async def test_native_respects_silence_during_wait(self):
        publish, topic = await self.start_native_wait(silence_table="input_text.silence")
        await self.hass.services.async_call("input_text", "set_value", {"entity_id": "input_text.silence", "value": json.dumps({"front_door": self.clock.timestamp()+60})}, blocking=True)
        await publish(json.dumps({"type": "description", "id": tracked()["id"], "description": "Muted"}), topic)
        self.assertEqual(len(self.notifications), 1)

    async def test_irrelevant_camera_and_event_types_are_ignored(self):
        await self.run_event(after=tracked(camera="other_camera"))
        await self.run_event(kind="invalid")
        self.assertEqual(self.notifications, [])


if __name__ == "__main__":
    unittest.main()
