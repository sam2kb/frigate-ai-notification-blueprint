# Changelog

All notable changes to this project will be documented in this file.

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
- Advanced Frigate UI endpoint options:
  - Frigate Instance URL (`frigate_url`)
  - Frigate UI Port (`frigate_port`)
- Auto-detection of Home Assistant URLs when inputs are blank:
  - Falls back to `state_attr('homeassistant', 'external_url'|'internal_url')`.
- Home Assistant version guard: Blueprint declares `homeassistant.min_version: 2024.6.0`.

### Changed
- Automation mode switched to `parallel` with `max: 25` so multiple events can process concurrently.
- Replaced hardcoded `:8123` links with derived, resilient URLs:
  - Introduced helper vars: `clip_url`, `clip_url_signed`, `snapshot_url`, `thumbnail_url`, `thumbnail_android_url`, `frigate_review_url`.
  - `frigate_review_url` is built from `frigate_url` or HA local/external URL with optional port.
- `base_url` / `local_url` defaults are now empty strings and auto-resolve from HA config.
- iOS live view now uses the signed clip URL when enabled.

### Fixed

### Misc
- Default cooldown set to 1 minute.
- `wait_for_trigger` value template now safely handles events with only `before` or `after` data.
- URL building sanitizes trailing slashes and removes any existing port before applying `frigate_port`.
- Mobile app notify service slugification now uses HA’s native rules, handling apostrophes/punctuation (e.g., “Bob’s” → `bob_s_...`).
- Reduced update spam from stationary objects by only notifying on new snapshots or sublabel changes when objects are motionless.

---

Changes prior to 0.2.0 are available in the git history of the original blueprint by [@zacharyd3](https://github.com/zacharyd3/Frigate-Vision).
