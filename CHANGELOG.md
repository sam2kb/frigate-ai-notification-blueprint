# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2025-09-28

### Added
- Advanced options to configure Frigate UI endpoints:
  - Frigate Instance URL (`frigate_url`)
  - Frigate UI Port (`frigate_port`)
- Auto-detection of Home Assistant URLs when inputs are left blank:
  - Uses `state_attr('homeassistant', 'external_url'|'internal_url')` as fallbacks.
- Zone-based filtering: new "Zones to Notify On" input (comma-separated or blank for ALL) to restrict notifications to specific Frigate zones. Applies to initial notifications, update notifications, and LLMVision analysis.
- Case-insensitive matching against Frigate `entered_zones`.

### Changed
- Replaced hardcoded `:8123` links with derived, resilient URLs:
  - Introduced `clip_url`, `clip_url_signed`, `snapshot_url`, `thumbnail_url`, `thumbnail_android_url`, and `frigate_review_url` helper variables.
  - `frigate_review_url` now derives from the configured Frigate URL or local/internal HA URL and optional port.
- Default `base_url` and `local_url` inputs are now empty strings and auto-resolve from HA config.
- iOS live view now uses the signed clip URL when enabled.

### Fixed
- YAML structure issues in the variables block (indentation), ensuring the blueprint parses correctly.
- `wait_for_trigger` value template now handles both `after` and `before` payloads safely.
- URL composition sanitizes trailing slashes and strips any existing port before applying the configured Frigate port.
- Fix: Moved `ios_live_view` from a grouped input to a top‑level input to prevent “Message malformed: Missing input ios_live_view” in some HA setups and during updates.
 - Mobile app notify service slugification now mirrors HA behavior (non‑alphanumeric → `_`, collapse duplicates, trim edges) to handle names with apostrophes and punctuation.

---

Changes prior to 0.2.0 are available in the git history of the original blueprint by [@zacharyd3](https://github.com/zacharyd3/Frigate-Vision).
