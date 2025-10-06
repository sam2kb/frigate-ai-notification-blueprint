# Copilot instructions for this repository

This repo contains a single Home Assistant automation blueprint that sends low-noise push notifications for Frigate events, optionally augmented by LLMVision summaries. There is no build step or test harness here-productivity means editing `frigate-ai-notification.yaml` safely and predictably.

## Big picture
- Core file: `frigate-ai-notification.yaml` (Home Assistant blueprint, domain: automation).
- Data flow:
  - Trigger on `mqtt` topic `frigate/events` for `type == "new"` to send the initial notification.
  - A timed update loop listens for subsequent MQTT messages for the same `event id` to send meaningful updates (clip ready, zone changes, sublabel changes).
  - A final “end” step can send a last notification if filters still pass.
- Optional LLMVision step analyzes the event clip after a short delay and posts a concise summary.
- Concurrency: `mode: parallel`, `max: 25` to handle multiple cameras/events.

## Important conventions and patterns
- Camera slugs: camera entity ids are normalized to lowercase, hyphens → underscores. Use this slug consistently in variables, URLs, tags, and silence map keys.
- Notification deduping: use `tag` to collapse notifications.
  - Initial/updates use `tag: camera` so each camera has a single updating card.
  - Final “END” uses `tag: id` to give one last per-event card.
- Mobile devices: notification service names are built dynamically as `notify.mobile_app_<slugified device name>` from selected `device` inputs.
- iOS support: when `ios_live_view` is on, use HLS `master.m3u8` for live/clip viewing; otherwise use MP4 URLs.
- URLs: prefer HA's configured `external_url`/`internal_url`; can override Frigate UI via `frigate_url`. Paths under `/api/frigate/...` are used when no explicit Frigate base is given.
- Zones filtering: `zones` and `zones_exclude` accept wildcards (`*`, `?`). They're compiled to regex and matched against either `entered`, `current`, or the union (`either`). Include list can require `any` or `all`; exclude always wins.
- Score/quality gates: guard sends with min detection score, optional `require_clip`, and optional “not false positive”.
- Debugging: when `debug` is true, emits structured messages via `logbook.log` at key decision points.

## Silence and cooldown behavior
- Per-camera silence (recommended): an `input_text` holds a JSON map `{camera_slug: silent_until_epoch}`. The blueprint reads/writes this to suppress sends for that camera.
  - Auto-silence: after a push is sent, a 30s per-camera cool-down is written to the table if present.
  - Manual silence: the notification includes a `Silence` action with text input minutes. With a table, only that camera is silenced; without it, the automation turns off globally for that duration.
- Global cooldown: optional `input_datetime` stores last-send timestamp; subsequent sends are throttled by the configured duration.

## LLMVision integration (optional)
- Triggered only if `provider` is set and the event still passes zone/quality checks and isn't currently silenced.
- Waits 30s (and optionally for a shared `input_boolean` “busy” gate), then calls `llmvision.video_analyzer` with:
  - Retry timing/attempts while waiting for the Frigate clip, frame count, resize width, tokens/temperature, title generation, and optional image exposure.
- Sends a second notification with the generated title/text; on iOS can use a signed clip URL (`clip_url_signed`).

## Editing guidelines specific to this blueprint
- Keep input names, help text, and selectors consistent with README. If you add or rename inputs, update README and descriptions inline.
- Maintain the version tag in `blueprint.description` (e.g., `[3.0.1]`) when changing user-visible behavior; also add an entry to `CHANGELOG.md`.
- Preserve the `SILENCE_<automation_entity_id>__<camera>` action id format; downstream logic depends on this exact scheme.
- Be careful changing zone matching: include/exclude precedence and `any` vs `all` semantics are intentional.
- Don't remove `alert_once: true` or the consistent `tag` usage-these are key to low-noise updates.
- When modifying URL logic, ensure both internal/external HA URL fallbacks and a `frigate_url` override continue to work.

## Examples from this repo
- Zones include with wildcards: `front_yard_*` with `zone_match_type: either` and `zone_logic: any` allows flexible matching; add `zones_exclude: porch_privacy` to suppress a sub-area.
- Silence table JSON stored in `input_text` might look like: `{"back_yard": 1730000000}`; keys must use normalized camera slugs.
- iOS HLS path used when clip ready: `/api/frigate/notifications/{{ id }}/{{ camera }}/master.m3u8`.
