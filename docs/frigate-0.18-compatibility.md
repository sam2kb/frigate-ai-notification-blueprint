# Frigate 0.18 compatibility

The blueprint uses Frigate's MQTT object events and the Home Assistant Frigate integration's notification proxy. It does not read snapshot files from Frigate's disk.

The compatibility check pins these upstream revisions:

| Component | Revision | Contract checked |
| --- | --- | --- |
| Frigate 0.18.0 | [`77a66e75`](https://github.com/blakeblackshear/frigate/tree/77a66e75c61862b048a07c1295877f4b31343504) | `new`, `update`, `end`, object fields, snapshot/thumbnail/MP4/event VOD routes |
| Frigate 0.18.2 | [`cfa08c56`](https://github.com/blakeblackshear/frigate/tree/cfa08c56b23d23280c3d0a218e5a43182c97445b) | Latest 0.18 patch release checked against the same event and media contracts |
| Frigate HA integration | [`24660181`](https://github.com/blakeblackshear/frigate-hass-integration/tree/24660181d6fd73af0ddf27a74e6bb608c96026b6) | Notification proxy mapping for JPEG images, MP4 clips, HLS manifests and segments |
| LLMVision | [`b81d6268`](https://github.com/valentinfrlch/ha-llmvision/tree/b81d62688f549332194413ae500eed81b313a58e) | `video_analyzer` options, `title`/`response_text` fields, event-ID resolution to the HA clip proxy |

Frigate 0.18 saves clean snapshots as WebP files. Its `/api/events/<id>/snapshot.jpg` endpoint still returns the requested snapshot, so the blueprint's HA proxy path remains valid. Native face labels can contain `[name, score]`; suppression and notification text use the name. `has_clip` indicates recording retention eligibility and can already be true in a `new` event. It does not mean a finished clip is immediately downloadable.

Normal notifications and AI analysis share the event filters. END messages use their own `after` payload. AI waits 30 seconds after END, retries failures, and checks manual silence and global cooldown again after waiting. The camera silence table stores only deliberate mutes.

## Automated checks

The regression suite runs the blueprint's actions through Home Assistant's real script engine, input helpers, config entries and device registry. It also validates the blueprint and automation schemas. Test entries represent loaded and unloaded integrations; delivery services and AI responses are simulated. Most delays advance a controlled clock. Busy-helper queue tests wait for actual HA state changes.

The fresh review replaced the provider-state template stub with real `ConfigEntryState` objects. This exposed an enum-versus-string comparison that skipped AI analysis. Tests now cover that behavior, provider unloads during waits/retries, current and legacy title fields, null response text, deleted/unloaded devices, and mixed Apple/Android delivery.

The minimum supported Home Assistant release is 2026.3.0, matching the [verified Frigate integration's requirement](https://github.com/blakeblackshear/frigate-hass-integration/blob/24660181d6fd73af0ddf27a74e6bb608c96026b6/hacs.json). Use Linux or WSL with Python 3.14:

```sh
python3.14 -m venv .codex/ha-test
.codex/ha-test/bin/python -m pip install -r requirements-test.txt
.codex/ha-test/bin/python -m unittest discover -s tests -v
```

For Home Assistant 2026.10.2, create a separate Python 3.14 environment and install `requirements-test-current.txt`, then run the same tests.

The upstream contract check downloads public source at the pinned revisions, verifies its Git blob hashes, checks API routes, MQTT fields and LLMVision response fields, and executes the integration's notification URL mapper and LLMVision's event-ID resolver in isolation:

```sh
.codex/ha-test/bin/python tests/check_frigate_018.py
.codex/ha-test/bin/python tests/check_frigate_018.py --version 0.18.0
```

Downloaded source stays in the ignored `.codex/upstream/` directory. The check does not start Frigate or contact a camera, broker, phone, or AI provider.

## Installation checks

Enable MQTT and install a Frigate HA integration release that supports Frigate 0.18. Match the blueprint's MQTT topic to Frigate's `topic_prefix`. Use camera and zone IDs from the Frigate config, including any camera override mapping required by HA entity IDs.

Enable recording retention for clips and video analysis. Keep the integration's notification proxy enabled and choose a proxy expiry long enough to open notifications. With both HA base URL inputs blank, the Companion app resolves relative media links against its sending server; test one notification on Wi-Fi and another on mobile data.

The automated checks verify event handling and source compatibility. Playback on a real phone, broker delivery, recording availability, and a real provider response still require an installation test. No live Frigate instance was used for this change.

## Operational limits

The optional busy boolean is a shared flag, not an atomic queue. Simultaneous events can race, and stopping/reloading an automation during a call can interrupt cleanup. Confirm no analysis is running before clearing a stuck flag.

Without a silence table, global mute turns the automation off and relies on a running delay to turn it back on. HA restart or automation reload cancels that delay, which can leave it off. The recommended silence table keeps mute expiry in a helper and avoids that delayed re-enable.

The automation allows 25 concurrent runs. Completed events waiting for AI occupy run slots. A busy installation can reach that limit and drop triggers; check HA's maximum-run warnings when sizing the automation. Global cooldown also uses a shared helper and is a best-effort throttle under simultaneous events.

Verification for v1.0.0-rc.1: all 42 regression scenarios passed on Home Assistant 2026.3.0 and 2026.10.2 (Python 3.14). The upstream contract checks passed for Frigate 0.18.0 and 0.18.2.
