# Copilot instructions for this repository

This repo contains a single Home Assistant automation blueprint that sends push notifications for Frigate events, optionally augmented by LLMVision summaries. The test suite executes its actions with Home Assistant's actual script engine, helpers, provider entries and device registry. External deliveries and provider responses are simulated.

## Big picture
- Core file: `frigate-ai-notification.yaml` (Home Assistant blueprint, domain: automation).
- Data flow:
  - Handle each `new`, `update`, and `end` MQTT message independently on the configurable topic (default `frigate/events`). There is no waiting event listener loop.
  - Updates notify on eligibility, recording flag, zone, recognized name, or moving-object snapshot changes.
  - END checks its own final `after` data, then optionally analyzes the event clip after 30 seconds.
- Concurrency: `mode: parallel`, `max: 25` to handle multiple cameras/events.

## Important conventions and patterns
- Preserve the native Frigate camera ID in API URLs. Normalize lowercase/hyphens for matching, tags, and silence keys. Keep the selected HA camera entity ID for live links, including overrides.
- Notification deduping: use `tag` to collapse notifications.
  - Initial/updates use `tag: camera` so each camera has a single updating card.
  - Final “END” uses `tag: id` to give one last per-event card.
- Mobile devices: notification service names use `notify.mobile_app_<slugified device name>`. Skip missing devices and unloaded mobile app entries. Runtime delivery errors must not block other recipients.
- iOS support: when `ios_live_view` is on, Apple recipients get event HLS `master.m3u8` and extra actions. Android recipients keep MP4 and at most three actions. Event HLS is recorded playback; View Live opens the HA camera entity.
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
- AI uses the same event tag as END and replaces that card. Log previews and silence JSON must fit input_text's maximum of 255 characters.
- Initialize the analyzer response before its retry loop and verify that successful responses propagate outside the repeat on both supported HA release families. Use HA's `from_json({})` fallback, followed by a mapping check, for helper/config JSON.

## Editing guidelines specific to this blueprint
- Keep input names, help text, and selectors consistent with README. If you add or rename inputs, update README and descriptions inline.
- Maintain the version tag in `blueprint.description` and add an entry to `CHANGELOG.md` when changing user-visible behavior. Keep the local `.codex/HANDOFF.md` out of commits.
- Preserve the `SILENCE_<automation_entity_id>__<camera>` action id format; downstream logic depends on this exact scheme.
- Be careful changing zone matching: include/exclude precedence and `any` vs `all` semantics are intentional.
- Don't remove `alert_once: true` or the consistent `tag` usage-these are key to low-noise updates.
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
