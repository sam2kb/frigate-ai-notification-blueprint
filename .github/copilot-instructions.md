# Copilot instructions for this repository

This repo contains a single Home Assistant automation blueprint that sends push notifications for Frigate events, optionally augmented by native Frigate descriptions or LLMVision summaries. The test suite executes its actions with Home Assistant's actual script engine, helpers, provider entries and device registry. External deliveries and provider responses are simulated.

## Big picture
- Core file: `frigate-ai-notification.yaml` (Home Assistant blueprint, domain: automation).
- Data flow:
  - Handle each `new`, `update`, and `end` MQTT message independently on the configurable topic (default `frigate/events`). There is no waiting event listener loop.
  - Updates notify when filters first pass or the recording flag becomes available. Snapshot-only and face-name-only changes do not resend.
  - END checks its own final `after` data, then optionally waits for native text or analyzes the event clip with LLMVision.
- Concurrency: `mode: parallel`, `max: 25` to handle multiple cameras/events.

## Important conventions and patterns
- Preserve the native Frigate camera ID in API URLs. Normalize lowercase/hyphens for matching, tags, and silence keys. Keep the selected HA camera entity ID for live links, including overrides.
- Notification deduping: all phases use the same automation-and-camera tag. Optional restored timers group split object tracks into one fresh alert per camera until the rolling quiet period expires. Replacements within that window use Android alert-once and passive Apple delivery; new windows alert again.
- Helper setup: use `activity_timer_rows` (native camera/timer picker rows). The legacy timer-map input was removed in 1.2.0. Map timers by camera entity ID; Camera Name Override Map still resolves Frigate names. Each camera and automation needs its own restored timer. Group activity/silence controls separately from optional AI helpers and global cooldown.
- Mobile devices: notification service names use `notify.mobile_app_<slugified device name>`. Skip missing devices and unloaded mobile app entries. Runtime delivery errors must not block other recipients.
- iOS support: Apple and Android use padded MP4 when clip_padding_seconds > 0 (default 10). With zero context and ios_live_view enabled, Apple uses event HLS and extra actions. Live HLS padding was ineffective through the tested Frigate gateway; do not assume that adding a query expands HLS coverage. Android keeps at most three actions. View Live opens the HA camera entity.
- URLs: default to Companion app relative HA notification-proxy paths. Explicit `base_url` takes precedence over `local_url`. Live buttons and no-media taps use `/?more-info-entity-id=<selected_camera_entity>` on both platforms. `frigate_url` controls only the optional Frigate UI action. Do not restore `state_attr('homeassistant', ...)` URL detection, `sign=true`, or fabricated review routes.
- Zones filtering: `zones` and `zones_exclude` match full IDs with wildcards (`*`, `?`). They are compiled to anchored regex and matched against either `entered`, `current`, or the union (`either`). Include list can require `any` or `all`; exclude always wins. Preserve the 0.3.x migration note: use `*porch*` to retain substring matching in either list.
- All notification and AI paths share score, recording, false-positive, zone-data, include/exclude, and known-face filters. Use namespace objects for assignments inside Jinja loops. `has_clip` means retention eligibility, not download readiness. Native face sublabels may be `[name, confidence]`.
- Labels accept custom values. Debugging logs camera/label/type/payload rejections before the initial gate, and zone decisions after matching. Avoid copying full MQTT payloads into logs.

## Silence and cooldown behavior
- Per-camera silence (recommended): an `input_text` holds a JSON map `{camera_slug: silent_until_epoch}`. The blueprint reads/writes this to suppress sends for that camera.
  - The table stores manual mutes only; there is no automatic per-camera mute.
  - Manual silence: the notification includes a `Silence` action with text input minutes. With a table, only that camera is silenced; without it, the automation turns off globally for that duration.
- Global cooldown: optional date-and-time `input_datetime` stores the last-send timestamp. The event's own END card may be replaced by its summary; another event's cooldown blocks it.

## LLMVision integration (optional)
- Triggered only on END with a retained recording and a loaded provider. Recheck manual silence, competing cooldown and provider readiness after waits and before retries.
- Waits 30s (and optionally for a shared `input_boolean` “busy” gate), then calls `llmvision.video_analyzer` with:
  - Retry timing/attempts while waiting for the Frigate clip, frame count, resize width, tokens, title generation, and optional image exposure. Send only fields verified by the pinned service schema. Keep `store_in_timeline`; do not send obsolete `remember` or `temperature`. Preserve the deprecated Temperature input ID for saved automations; temperature belongs in provider configuration.
- Provider state is a `ConfigEntryState` enum on old HA and a string on current HA. Compare `state.value | default(state)` with `loaded`. Do not mock this template helper in tests. Prefer the current device `config_entry_id` attribute, falling back to legacy `config_entries` only when needed.
- Release the optional busy helper after reported analyzer failures. It is a simple flag, not an atomic mutex; reloads/cancellations can interrupt cleanup.
- Current LLMVision returns `title` and `response_text`; accept legacy `response_title` as a fallback. Blank Model uses the provider default.
- AI uses the same camera tag as END and replaces that card. With activity grouping, skip work/results superseded by newer activity or an expired timer. Log previews and silence JSON must fit input_text's maximum of 255 characters.
- Initialize the analyzer response before its retry loop and verify that successful responses propagate outside the repeat on both supported HA release families. Use HA's `from_json({})` fallback, followed by a mapping check, for helper/config JSON.

## Editing guidelines specific to this blueprint
- Keep input names, help text, and selectors consistent with README. If you add or rename inputs, update README and descriptions inline.
- Maintain the version tag in `blueprint.description` and add an entry to `CHANGELOG.md` when changing user-visible behavior. Keep the local `.codex/HANDOFF.md` out of commits.
- Preserve the `SILENCE_<automation_entity_id>__<camera>` action id format; downstream logic depends on this exact scheme.
- Be careful changing zone matching: include/exclude precedence and `any` vs `all` semantics are intentional.
- Keep consistent tags and quiet replacements. A new timer activity window must be able to alert again; do not force alert_once on its first send.
- When modifying URL logic, preserve explicit External Base URL -> Internal Base URL -> relative path precedence. Frigate UI links are independent. LLMVision uses HA's own URL selection when resolving clips.

## Verification
- Minimum HA 2026.3.0: Python 3.14 and `requirements-test.txt`. This matches the pinned Frigate integration's HACS requirement.
- Current HA check: Python 3.14 and `requirements-test-current.txt`.
- Run `python -m unittest discover -s tests -v` in both environments. Tests use actual HA YAML/input materialization and MQTT/event triggers, replacing only broker transport and external deliveries. Keep the overlapping-event and mixed-platform regressions.
- `.github/workflows/compatibility.yml` also tests latest stable HA explicitly and runs weekly from the default branch.
- Run `python tests/check_frigate_018.py` and `python tests/check_frigate_018.py --version 0.18.0` for pinned upstream contracts. These execute proxy mapping and LLMVision event-ID resolution without a live server.
- Read `docs/frigate-0.18-compatibility.md` for coverage and installation limits. Do not describe source or simulated-delivery checks as live phone/provider verification.

## Examples from this repo
- Zones include with wildcards: `front_yard_*` with `zone_match_type: either` and `zone_logic: any` allows flexible matching; add `zones_exclude: porch_privacy` to suppress a sub-area.
- Silence table JSON stored in `input_text` might look like: `{"back_yard": 1730000000}`; keys must use normalized camera slugs.
- iOS event HLS path: `/api/frigate/notifications/{{ id }}/{{ camera }}/master.m3u8`.

## Native descriptions
- Preserve source modes: Auto prefers the first matching native object/review text, then optionally falls back; Frigate never calls LLMVision; Off disables both. Existing automations default to LLMVision.
- Persistent native MQTT triggers bridge valid messages to scoped local HA events. MQTT value_template has no script variables; filter only context-free message types there. Match object ID, automation and camera inside HA event waits. Review detections contain object IDs; never use the review ID for clips.
- Native messages must not renew timers or send fresh alerts. Preserve shared eligibility/stale guards and require valid response text before the final send. Conditional branches that end on a condition can return to their parent sequence; do not assume they stop the whole automation.
- Native waiting counts toward LLMVision clip-readiness delay. Do not add a further fixed 30 seconds after the default 90-second wait. No helper/API cache is provided; document early-only/late/reload misses.

## Concurrency constraints
- Keep this a self-contained reusable automation blueprint. No companion scripts, custom integration, external worker installation or additional helper requirements.
- Preserve parallel camera processing. Reserve ingress headroom before admitting long AI waits, and cancel older native waits when newer eligible camera activity arrives. Basic delivery remains independent of AI admission.
- Capture native text in the first parallel branch alongside basic END delivery. Join both before summary delivery. Keep captured values initialized in outer scope; HA protects each parallel branch's wait variable.
- Capture cooldown ownership in the basic-delivery branch at the write. Never infer it from the current timestamp after an AI wait.
- Merge silence JSON from states(input_silence_table) inside the native write action, not an earlier variable. Preserve native callback ordering and verify the requested mute was saved; do not introduce a queued companion script.
- Trigger tests must pass configured max_runs and publish actual current/max state attributes. Keep the native helper implementation intact when testing mobile-action interleavings.
