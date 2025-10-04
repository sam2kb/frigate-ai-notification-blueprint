# Changelog

All notable changes to this project will be documented in this file.

## [0.2.1] - 2025-09-29

- Added Exclude Zones - a list of zones to always suppress notifications, even if they also match the include list.
- MQTT trigger still filters `to type`: new. Event updates are consumed inside the update loop; the first push can be sent immediately (pre-loop) once zone match, cooldown, and quality checks pass. The update loop handles follow-ups (clip ready, zone/sub-label changes, and `end`).
- Zone matching kept as include/exclude with wildcard support; internal matcher was hardened (proper escaping of `.`, `*`, `?` and optional `^…$` anchoring).
- Quality check now prefers the best of `top_score` or `score` when available.
- iOS Live View setting lives under Notification Customization. When External Base URL is blank, iOS falls back to the thumbnail.
- Cooldown: optional `input_datetime` helper provides cross-update throttling; default duration remains 1 minute. Timestamp is written once per notification (not per device).
- Add more debug steps

## [0.2.0] - 2025-09-28

### Added
- Zone-based filtering: New inputs to precisely control zone matching and behavior:
  - Zones to Notify On (`zones`): Comma-separated list of Frigate zones (blank = ALL).
    - Supports wildcards (* and ?), e.g., `*_near` to match all zones ending with `_near`.
  - Zone Filter Mode (`zone_filter_mode`): `include` (only notify on listed zones) or `exclude` (ignore listed zones).
  - Zone Match Type (`zone_match_type`): Match by `entered`, `current`, or `either` set of zones.
  - Zone Logic (`zone_logic`): When mode is `include`, require `any` or `all` of the listed zones to match.
  - Filtering applies to initial notifications, update notifications, and LLMVision analysis.
- Multi-camera input: Select multiple Frigate camera entities; events are filtered to the selected cameras.
 - LLMVision integration is fully optional; leave Provider blank to disable.
 - Signal Quality Filters:
   - `min_score` (default 0.6)
   - `require_clip` (notify only when `has_clip=true`)
   - `require_not_false_positive` (default true)
- Frigate Instance URL (`frigate_url`)
- Auto-detection of Home Assistant URLs when inputs are blank:
  - Falls back to `state_attr('homeassistant', 'external_url'|'internal_url')`.
- Home Assistant version guard: Blueprint declares `homeassistant.min_version: 2024.6.0`.

### Changed
- Automation mode switched to `parallel` with `max: 25` so multiple events can process concurrently.
- Replaced hardcoded links `base_url` / `local_url` / `frigate_review_url` - are now empty strings and auto-resolve from HA config.
- iOS live view now uses the signed clip URL when enabled.

### Misc
- Helper entity is optional and only used when LLM is enabled.
- Fallback to snapshot when clip isn't ready yet
- `wait_for_trigger` value template now safely handles events with only `before` or `after` data.
- Mobile app notify service slugification now uses HA’s native rules, handling apostrophes/punctuation (e.g., “Bob’s” → `bob_s_...`).
- Reduced update spam from stationary objects by only notifying on new snapshots or sublabel changes when objects are motionless.

---

Changes prior to 0.2.0 are available in the git history of the original blueprint by [@zacharyd3](https://github.com/zacharyd3/Frigate-Vision).
