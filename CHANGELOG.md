# Changelog

All notable changes to this project will be documented here.

## [0.3.0] - 2025-10-05

### Added
- **iOS HLS live view**: when *iOS Notification* is enabled, notifications use the `.m3u8` stream where possible. Falls back to snapshot if a signed clip URL isn’t available.
- **“View Live” action**: opens the camera entity in the HA app (`entityId:camera.<slug>`). Included on initial, update, end, and LLMVision notifications.
- **Per-camera “Silence” action**:
  - Tap **Silence** and (optionally) enter minutes (default 5, min 1, max 120).
  - Uses an **Input Text** helper to store a JSON map `{camera_slug: silent_until_ts}`.
  - If the helper isn’t configured, falls back to a **global mute** (temporarily turns off this automation).
- **Optional Input Text** setting: *Per-Camera Silence Table (input_text)*.

### Changed
- **Update spam trimmed**:
  - Update notifications now fire only when **clip becomes ready**, **sub-label changes**, or **the zone match set changes**.
  - Pure snapshot churn is ignored for stationary objects.
- **Exclude zones take precedence** over includes at every step (initial, updates, end). Useful for carving out “privacy” pockets inside broad include areas.
- **Zone matcher hardened**: correct wildcard handling, proper escaping of regex metacharacters, and consistent anchoring strategy.
- **Signed clip URLs** preferred for iOS attachments when an external base URL is available.
- **Silence table auto-init**: gracefully treats empty/unknown/unavailable helper values as `{}`.
- **Debug logs cleaned up**: clearer one-liners showing `camera_silenced`, zone decisions, and update reasons.

### Fixed
- iOS attachments sometimes linked to MP4 before ready; now correctly fall back to snapshot or HLS.
- Rare template errors when the silence helper contained non-JSON or was empty.
- Mobile app notify service slugification handles punctuation/apostrophes reliably.
- Update loop now cleanly exits on `end` and won’t echo redundant updates.

---

## [0.2.1] - 2025-09-29
- **Exclude Zones**: list of zones that always suppress notifications, even if also included.
- MQTT trigger filters to `type: new`; updates are handled inside an internal loop.
- Quality check prefers the best of `top_score` or `score`.
- iOS live view toggle moved under Notification Customization; falls back to thumbnail when no external URL.
- Optional cooldown `input_datetime` for cross-update throttling; timestamp written once per notification.
- Expanded debug logging.

## [0.2.0] - 2025-09-28
- Zone-based filtering (includes/excludes with wildcards), match type (`entered`/`current`/`either`), and logic (`any`/`all`).
- Multi-camera support in a single automation; `mode: parallel (max 25)`.
- Optional LLMVision integration (leave Provider blank to disable).
- Signal quality filters (`min_score`, `require_clip`, `require_not_false_positive`).
- Auto-detection of HA base URLs; optional explicit Frigate UI URL.
- iOS live view uses signed clip URLs when enabled.

---

Changes prior to 0.2.0 are available in the git history of the original blueprint by [@zacharyd3](https://github.com/zacharyd3/Frigate-Vision).
