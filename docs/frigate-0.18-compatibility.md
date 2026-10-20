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

The regression suite loads the YAML with Home Assistant's blueprint loader and substitutes inputs using HA's blueprint model, then runs the actions through its real script engine, input helpers, config entries and device registry. Trigger tests exercise HA's MQTT JSON parser and event-bus listeners, including a custom MQTT topic. The broker subscription transport, phone deliveries and AI responses are simulated. Most delays advance a controlled clock. Busy-helper queue tests wait for actual HA state changes, including two overlapping END runs on one script.

The fresh review replaced the provider-state template stub with real `ConfigEntryState` objects. This exposed an enum-versus-string comparison that skipped AI analysis. Tests now cover that behavior, provider unloads during waits/retries, current and legacy title fields, null response text, deleted/unloaded devices, and mixed Apple/Android delivery.

The minimum supported Home Assistant release is 2026.3.0, matching the [verified Frigate integration's requirement](https://github.com/blakeblackshear/frigate-hass-integration/blob/24660181d6fd73af0ddf27a74e6bb608c96026b6/hacs.json). Use Linux or WSL with Python 3.14:

```sh
python3.14 -m venv .codex/ha-test
.codex/ha-test/bin/python -m pip install -r requirements-test.txt
.codex/ha-test/bin/python -m unittest discover -s tests -v
```

For Home Assistant 2026.10.2, create a separate Python 3.14 environment and install `requirements-test-current.txt`, then run the same tests.

The [compatibility workflow](../.github/workflows/compatibility.yml) runs both pinned environments and resolves the latest stable HA release from PyPI for a third job. It fails if that release needs a newer Python instead of silently testing an older compatible HA version. Pushes and pull requests run the workflow immediately. The workflow also runs weekly from the default branch, `main`.

The upstream contract check downloads public source at the pinned revisions and verifies its Git blob hashes. It checks API routes and object fields, executes Frigate's actual MQTT serialization statements to verify `before`/`after` and event types, and checks every analyzer data key sent by the blueprint against LLMVision's service fields. It also checks response fields and executes the integration's notification URL mapper and LLMVision's event-ID resolver in isolation:

```sh
.codex/ha-test/bin/python tests/check_frigate_018.py
.codex/ha-test/bin/python tests/check_frigate_018.py --version 0.18.0
```

Downloaded source stays in the ignored `.codex/upstream/` directory. The check does not start Frigate or contact a camera, broker, phone, or AI provider.

## Installation checks

Enable MQTT and install a Frigate HA integration release that supports Frigate 0.18. Match the blueprint's MQTT topic to Frigate's `topic_prefix`. Use camera and zone IDs from the Frigate config, including any camera override mapping required by HA entity IDs.

When upgrading from 0.3.x, review include and exclude patterns. V1 matches full zone IDs: `porch` matches only `porch`, while `*porch*` also matches `front_porch`. Review privacy exclusions before enabling the updated automation. Debugging logs show rejected camera/label/type/payload reasons and observed zone IDs.

Enable recording retention for clips and video analysis. Keep the integration's notification proxy enabled and choose a proxy expiry long enough to open notifications. With both HA base URL inputs blank, the Companion app resolves relative media links against its sending server; test one notification on Wi-Fi and another on mobile data.

For AI analysis, HA's URL selection must produce an address reachable from HA itself. Depending on the installation, this can come from its configured network URLs, cloud URL or detected local address. The blueprint's URL overrides affect phone links; LLMVision resolves event IDs independently. Configure temperature in the LLMVision provider. The saved blueprint Temperature input remains accepted but is ignored.

View Live buttons and taps without retained media use the shared relative More Info URL documented by the [Companion apps](https://companion.home-assistant.io/docs/notifications/notifications-basic/#opening-a-url). Verify that it opens the mapped camera entity on each receiving phone.

The automated checks verify event handling and source compatibility. Playback on a real phone, broker delivery, recording availability, and a real provider response still require an installation test. The original v1.0 checks used no live Frigate instance; v1.1.0 server checks are described below.

## Operational limits

The optional busy boolean is a shared flag, not an atomic queue. Simultaneous events can race, and stopping/reloading an automation during a call can interrupt cleanup. Confirm no analysis is running before clearing a stuck flag.

Without a silence table, global mute turns the automation off and relies on a running delay to turn it back on. HA restart or automation reload cancels that delay, which can leave it off. The recommended silence table keeps mute expiry in a helper and avoids that delayed re-enable.

The automation allows 25 concurrent runs. Completed events waiting for AI occupy run slots. A busy installation can reach that limit and drop triggers; check HA's maximum-run warnings when sizing the automation. Global cooldown also uses a shared helper and is a best-effort throttle under simultaneous events.

With activity timers configured, replacements use Android `alert_once` and passive Apple delivery; a new window alerts again. Without activity timers, Apple event updates retain active delivery and may sound or show banners again according to device settings. An update can be an event's first eligible notification.

Verification for v1.0.0: all 51 regression scenarios passed on Home Assistant 2026.3.0 and 2026.10.2 (Python 3.14). The upstream contract checks passed for Frigate 0.18.0 and 0.18.2. Runtime behavior is unchanged from RC2. Live phone playback and provider verification remain outstanding.


## v1.1.0 activity grouping and helper setup

Version 1.1.0 adds a separate restored timer per camera. Its two-minute default window restarts on each eligible MQTT message, without comparing tracking IDs or recognized names. Snapshot-only changes do not resend notifications. Initial, clip, END and AI updates share an automation-and-camera tag; updates within an active window use Android alert-once and passive Apple delivery.

The 72 regression scenarios pass on HA 2026.3.0 and 2026.10.2. They include simultaneous starts using HA's real delay scheduling, clock-second boundaries, split tracks, independent camera windows, timer configuration errors and stale AI results. Frigate 0.18.0/0.18.2 and LLMVision source contract checks still pass.

A timer measures received eligible messages, not continuous physical presence. A persistent false detection can extend a window; missing messages can let it expire. The first alert includes a 100 ms claim-settling delay. Timer helpers must be unique to their camera and automation. Reusing a helper across separate automations can couple their windows and is not detected by the blueprint's within-map validation. Phone delivery remains subject to the Companion app and device settings.

Activity grouping does not use Frigate review IDs. Those can aggregate several tracked objects, but their boundaries do not guarantee the configured quiet interval. Object IDs remain necessary to fetch individual clips. The optional AI step summarizes the latest eligible clip, not an entire camera activity window.

MP4 phone links request configurable event padding (10 seconds by default). Source checks execute Frigate's endpoint range calculation and the integration's query forwarding. A live Frigate 0.17.2 check measured three complete files at about 2, 5 and 10 seconds without padding, and 22, 25 and 30 seconds with 10-second padding. Recordings covered the lead-in. This verifies server-side media coverage; playback on the receiving phone remains unverified. Apple now uses the padded MP4 link too. A live HLS check returned 10.211 seconds with both padding=0 and padding=10, although the API returned a longer range. Set context to zero to keep event HLS playback when iOS Notification is enabled. AI event-ID analysis keeps its existing boundaries, and the camera activity window is not merged into a single video.

The helper form uses repeated object fields with camera and timer entity selectors, supported by both tested HA versions. Existing helper input IDs and legacy timer maps remain accepted. New rows override a legacy mapping for the same camera; duplicate cameras and timers shared between cameras are rejected. Regression coverage includes real nested selector validation and independent rolling windows from form rows. Helpers still require creation through HA's normal picker; the blueprint does not provision them on import.
