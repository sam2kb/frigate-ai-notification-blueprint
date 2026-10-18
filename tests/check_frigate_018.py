"""Check pinned Frigate 0.18 and HA integration contracts (network on first run).

Only the notification proxy URL mapper is executed, in isolation with fake
request/config objects. This does not start Frigate or contact a user's server.
"""

from __future__ import annotations

import ast
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.request import urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".codex" / "upstream"
FRIGATE = "77a66e75c61862b048a07c1295877f4b31343504"  # v0.18.0
FRIGATE_0182 = "cfa08c56b23d23280c3d0a218e5a43182c97445b"
INTEGRATION = "24660181d6fd73af0ddf27a74e6bb608c96026b6"
LLMVISION = "b81d62688f549332194413ae500eed81b313a58e"

SOURCES = {
    "frigate_media.py": ("blakeblackshear/frigate", FRIGATE, "frigate/api/media.py", "c6fa90c0684cf94a41848b79c8f2e4e0850586c5"),
    "frigate_events.py": ("blakeblackshear/frigate", FRIGATE, "frigate/api/event.py", "1597c188567714eabc40a7ceaee7ee17037fb428"),
    "frigate_objects.py": ("blakeblackshear/frigate", FRIGATE, "frigate/track/object_processing.py", "999ec5c04b6869182a17e2051af16b797bd7136e"),
    "frigate_tracked.py": ("blakeblackshear/frigate", FRIGATE, "frigate/track/tracked_object.py", "75234c3a87abfe94ce89a0eb68bb5c5df9c3d09c"),
    "ha_frigate_views.py": ("blakeblackshear/frigate-hass-integration", INTEGRATION, "custom_components/frigate/views.py", "497bbdf19be9ede60f47c7b6905f82de7786e92f"),
    "ha_frigate_hacs.json": ("blakeblackshear/frigate-hass-integration", INTEGRATION, "hacs.json", "4132e3461c0b6a156fe819eb2afa19ebe4615d4f"),
    "llmvision_services.yaml": ("valentinfrlch/ha-llmvision", LLMVISION, "custom_components/llmvision/services.yaml", "c5ee604984a68099f56839a7ac5b34bc46a343f2"),
    "llmvision_providers.py": ("valentinfrlch/ha-llmvision", LLMVISION, "custom_components/llmvision/providers.py", "055ddda7f357a64556b5e31be46381831675908c"),
    "llmvision_media.py": ("valentinfrlch/ha-llmvision", LLMVISION, "custom_components/llmvision/media_handlers.py", "eb66e6ca62fa7bbd55d83343b593dec9ae4facf1"),
}


def git_blob(text):
    data = text.encode()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def source(name):
    repo, commit, path, expected = SOURCES[name]
    cached = CACHE / name
    text = cached.read_text() if cached.exists() else ""
    if git_blob(text) != expected:
        url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
        with urlopen(url, timeout=60) as response:
            text = response.read().decode()
        assert git_blob(text) == expected, f"Upstream content hash mismatch: {name}"
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(text, encoding="utf-8", newline="\n")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=("0.18.0", "0.18.2"), default="0.18.2")
    args = parser.parse_args()
    if args.version == "0.18.2":
        for name, blob in {
            "frigate_media.py": "d6e2a7f8361f38b79cc1f202de47f81e8f3e1eaf",
            "frigate_events.py": "a0313902b13a5aa0ebd6fefda44eb4433f11e954",
            "frigate_objects.py": "201a41b9dc6dc144c27004095daa65a1c7bcf895",
            "frigate_tracked.py": "75234c3a87abfe94ce89a0eb68bb5c5df9c3d09c",
        }.items():
            repo, _, path, _ = SOURCES[name]
            SOURCES[name] = (repo, FRIGATE_0182, path, blob)
    print(f"Checking Frigate {args.version}")
    sources = {key: source(key) for key in SOURCES}
    class BlueprintLoader(yaml.SafeLoader):
        pass
    BlueprintLoader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))
    blueprint = yaml.load((ROOT / "frigate-ai-notification.yaml").read_text(), Loader=BlueprintLoader)
    minimum = blueprint["blueprint"]["homeassistant"]["min_version"]
    integration_minimum = json.loads(sources["ha_frigate_hacs.json"])["homeassistant"]
    assert tuple(map(int, minimum.split("."))) >= tuple(map(int, integration_minimum.split(".")))
    print(f"PASS: HA minimum {minimum} meets the verified Frigate integration's requirement")
    media = ast.parse(sources["frigate_media.py"])
    events = ast.parse(sources["frigate_events.py"])
    routes = {
        value.value
        for tree in (media, events)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        for value in decorator.args[:1]
        if isinstance(value, ast.Constant) and isinstance(value.value, str)
    }
    assert "/events/{event_id}/snapshot.jpg" in routes
    assert "/events/{event_id}/clip.mp4" in routes
    assert "/vod/event/{event_id}" in routes
    assert any(re.fullmatch(r"/events/\{[^}]+\}/thumbnail\.(?:jpg|\{[^}]+\})", path) for path in routes)
    print("PASS: Frigate 0.18 snapshot, thumbnail, MP4, and event VOD API routes")

    tracked = ast.parse(sources["frigate_tracked.py"])
    to_dict = next(node for node in ast.walk(tracked) if isinstance(node, ast.FunctionDef) and node.name == "to_dict")
    fields = {key.value for node in ast.walk(to_dict) if isinstance(node, ast.Dict) for key in node.keys if isinstance(key, ast.Constant)}
    required = {"id", "camera", "label", "sub_label", "top_score", "score", "false_positive", "has_clip", "has_snapshot", "snapshot", "stationary", "entered_zones", "current_zones"}
    assert required <= fields, required - fields
    objects = ast.parse(sources["frigate_objects.py"])
    constants = {node.value for node in ast.walk(objects) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert {"new", "update", "end", "events"} <= constants
    print("PASS: Frigate 0.18 MQTT event types and all fields used by the blueprint")

    views = ast.parse(sources["ha_frigate_views.py"])
    proxy = next(node for node in views.body if isinstance(node, ast.ClassDef) and node.name == "NotificationsProxyView")
    method = next(node for node in proxy.body if isinstance(node, ast.FunctionDef) and node.name == "_get_proxied_url_impl")
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), method], type_ignores=[])
    namespace = {"os": os, "ProxiedURL": lambda **kwargs: SimpleNamespace(**kwargs), "HASSWebProxyLibNotFoundRequestError": RuntimeError, "HASSWebProxyLibForbiddenRequestError": RuntimeError}
    exec(compile(ast.fix_missing_locations(module), "upstream_notifications_proxy", "exec"), namespace)
    fake = SimpleNamespace(_get_config_entry_for_request=lambda *args: object(), _permit_request=lambda *args, **kwargs: True, _get_fqdn_path=lambda request, path, **kwargs: path, _get_query_params=lambda request: {})
    mapper = namespace["_get_proxied_url_impl"]
    for path, expected in {
        "snapshot.jpg": "api/events/event-id/snapshot.jpg",
        "thumbnail.jpg": "api/events/event-id/thumbnail.jpg",
        "clip.mp4": "api/events/event-id/clip.mp4",
        "front_door/clip.mp4": "api/events/event-id/clip.mp4",
        "front_door/master.m3u8": "vod/event/event-id/master.m3u8",
        "front_door/seg-1-v1-a1.ts": "vod/event/event-id/seg-1-v1-a1.ts",
    }.items():
        result = mapper(fake, {}, event_id="event-id", path=path, headers={})
        assert result.url == expected, (path, result.url)
    print("PASS: actual HA Frigate proxy maps blueprint JPEG, MP4, HLS manifest and segment URLs")

    fields = yaml.safe_load(sources["llmvision_services.yaml"])["video_analyzer"]["fields"]
    assert {"event_id", "provider", "model", "max_frames", "target_width", "max_tokens", "generate_title", "expose_images"} <= fields.keys()
    print("PASS: LLMVision video_analyzer accepts Frigate event IDs and analysis options")

    providers = ast.parse(sources["llmvision_providers.py"])
    request = next(node for node in providers.body if isinstance(node, ast.ClassDef) and node.name == "Request")
    call = next(node for node in request.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "call")
    response_keys = {
        node.slice.value for node in ast.walk(call)
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
        and node.value.id == "result" and isinstance(node.slice, ast.Constant)
    }
    assert {"title", "response_text"} <= response_keys
    print("PASS: LLMVision generated-title and response-text field names")

    # Execute the real event-ID resolver without downloading or analyzing video.
    media_handlers = ast.parse(sources["llmvision_media.py"])
    processor = next(node for node in media_handlers.body if isinstance(node, ast.ClassDef) and node.name == "MediaProcessor")
    add_videos = next(node for node in processor.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "add_videos")
    module = ast.Module(body=[add_videos], type_ignores=[])
    namespace = {"asyncio": asyncio, "get_url": lambda hass: "http://ha.test:8123", "_LOGGER": SimpleNamespace(debug=lambda *args: None)}
    exec(compile(ast.fix_missing_locations(module), "upstream_llmvision_media", "exec"), namespace)
    resolved = []
    async def add_video(**kwargs):
        resolved.append(kwargs)
    fake_processor = SimpleNamespace(hass=object(), client=object(), add_video=add_video)
    asyncio.run(namespace["add_videos"](fake_processor, video_paths=[], event_ids=["event-id"], max_frames=3, target_width=1920, include_filename=False, expose_images=True))
    assert resolved[0]["video_path"] == "/api/frigate/notifications/event-id/clip.mp4"
    assert resolved[0]["base_url"] == "http://ha.test:8123"
    print("PASS: actual LLMVision event-ID resolver uses the supported HA clip proxy")
    print("No live camera, phone, broker, or AI provider was contacted.")


if __name__ == "__main__":
    main()
