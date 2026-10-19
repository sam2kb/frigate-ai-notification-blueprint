# Changelog

All notable changes to this project will be documented here.

## [1.0.0] - 2026-10-19
- Promote the tested RC2 implementation to `main`. Update the blueprint version, source URL and README import badge for the stable release; runtime behavior is unchanged from RC2.
- V1 fixes zone exclusions and `all` matching, final-event data handling, AI filter/cooldown bypasses, notification links, provider readiness and helper cleanup. It also adds custom labels, rejection diagnostics and automated compatibility checks.
- Requires Home Assistant 2026.3+. Frigate 0.18.0/0.18.2 source contracts and 51 regression scenarios cover the supported integration paths. Phone playback, broker delivery and real AI responses still need installation checks.
- When upgrading from 0.3.x, review both zone lists: patterns match full IDs, so use `*porch*` to preserve substring matching. Configure temperature in LLMVision; the old blueprint input is retained but ignored.

## [1.0.0-rc.2] - 2026-10-18
- Use the shared relative More Info URL for View Live buttons and notification taps without retained media, including mapped camera entities on iOS and Android.
- Allow custom Frigate labels in the picker. Add debug reasons for rejected camera, label, event type and payload, plus observed zone IDs and include/exclude decisions.
- Remove obsolete `remember` and `temperature` analyzer parameters. Preserve the deprecated Temperature input for saved automations; configure temperature in LLMVision. Keep timeline storage enabled.
- Document the breaking full-ID zone matching change from 0.3.x, including `*porch*` migration examples for both include and privacy exclusion patterns.
- Test HA's actual blueprint input substitution, MQTT JSON parsing, mobile event routing, mixed-platform live URLs and overlapping END runs. Verify every analyzer call key against the pinned LLMVision schema and execute Frigate's actual MQTT serialization statements.
- Add CI for minimum, pinned current and latest stable HA, plus Frigate 0.18.0/0.18.2 source contracts. Scheduled checks begin once the workflow reaches the default branch.
- Correct cooldown guidance, AI log timing, provider URL requirements and iOS re-alert expectations. Keep the candidate import URL and HA 2026.3 support minimum.

## [1.0.0-rc.1] - 2026-10-17
- First v1 release candidate, published on `codex/v1-candidate`. Requires Home Assistant 2026.3+; live installation testing remains outstanding.
- Compare actual Home Assistant provider-state enum values and recheck readiness after delays and retries, preventing loaded providers from being skipped and unloaded providers from latching the busy helper.
- Read LLMVision's generated `title`, retain the legacy title fallback, and reject null or empty summary text.
- Skip deleted devices and unloaded mobile app entries. Build playback links and actions per device so mixed Apple/Android recipients retain Android's three-button limit.
- Fix zone exclusions and `all` matching, anchor wildcard patterns to full zone IDs, and respect the selected current/entered zone mode.
- Process MQTT `new`, `update`, and `end` messages directly so notification work and timeouts cannot leave gaps in an event listener. Final notifications use final event data.
- Apply score, recording, false-positive, zone, and known-face filters to AI analysis as well as notifications. Handle native Frigate `[name, score]` face labels.
- Remove the hardcoded per-camera auto-mute. Preserve manual silence and configurable global cooldown, while allowing an event's final card to receive its AI summary.
- Recheck silence and competing cooldowns after AI waits and retries; release the busy helper on reported analyzer failures. Skip unloaded providers.
- Repair the AI log helper input, limit preview text to the helper's capacity, and use real line breaks. Validate silence JSON, prune expired mutes when saving, clamp requested durations, and report a full silence table.
- Use Companion app relative media URLs by default, with explicit HA URL overrides. Remove unsupported URL autodetection, fake URL signing, and the nonexistent HA review route. Add the iOS tap URL and correct top-level Android delivery options.
- Keep Android notifications within three action buttons and replace the final event card with its AI summary. Preserve mapped camera entity IDs for live links.
- Add a configurable MQTT event topic and use the selected AI provider's default model when Model is blank. Require Home Assistant 2026.3+, matching the verified Frigate integration, and use HA's built-in JSON parsing fallback for helper values.
- Add Home Assistant script-engine regression tests using real config entries and devices, plus repeatable checks of Frigate 0.18 MQTT fields, media routes, HA notification-proxy mapping, and LLMVision response fields and event-ID resolution.

## [0.3.9] - 2026-07-16
- Add optional AI Description Log Helper (`input_text`) under LLMVision Tweaks. When configured, every LLM-generated summary is persisted to the helper with timestamp, camera, and label. Display it on any dashboard with a markdown card for a scrollable event log.

## [0.3.8] - 2026-06-08
- Add `Suppress Known Faces` input (Quality Filters): comma-separated list of recognized face names to silence. Matches against Frigate's `sub_label` from native face recognition. Applies to initial, update, final, and LLM notifications.

## [0.3.7] - 2026-06-08
- Fix notification tap/action URLs to be absolute on all platforms (Android requires absolute URLs; iOS was tolerant of relative paths).
- Add `effective_base_url` that falls back through `base_url` → `local_url` so `video_ios`, `clip_url`, `snapshot_url`, and `thumbnail_url` are never left relative.
- Fix `silence_table_enabled` always evaluating as truthy when no per-camera silence table was configured, which caused the auto-cooldown to attempt writes against a nonexistent entity.
- Fix LLM notification channel mismatch: LLM summary used `{{ camera }}_notifications` while initial/update/final used `{{ camera_name }} Notifications`, preventing Android from replacing the camera card with the LLM summary.
- Raise default `max_tokens` from 20 to 100 and expand slider range to 4000; modern models (GPT-5, etc.) need higher limits to avoid truncated summaries.

## [0.3.6] - 2026-02-10
- Add optional requirement for zones to be present before the initial notification.

## [0.3.5] - 2026-02-10
- Fix mobile notification action - use HA-recommended default handling for missing trigger payloads.

## [0.3.4] - 2026-02-10
- Add optional camera override map to match Frigate camera names when HA entity ids differ.

## [0.3.3] - 2025-10-27
- Reduce auto per-camera cooldown to 25 seconds so LLMVision summaries are not skipped by the generated silence window.

## [0.3.2] - 2025-10-06
- Trigger notification updates only if detection score improves by more than 2% - reduces update spam

## [0.3.1] - 2025-10-05
- Hardcoded 30s per-camera cooldown after a push - writes to silence table if set.
- Notification tags: initial + updates use `tag: camera` to collapse per camera; final END uses `tag: id` to retain one card per event.

## [0.3.0] - 2025-10-05
### Added
- **iOS HLS live view**: when *iOS Notification* is enabled, notifications use the `.m3u8` stream where possible. Falls back to snapshot if a signed clip URL isn't available.
- **“View Live” action**: opens the camera entity in the HA app (`entityId:camera.<slug>`). Included on initial, update, end, and LLMVision notifications.
- **Per-camera “Silence” action**:
  - Tap **Silence** and (optionally) enter minutes (default 5, min 1, max 120).
  - Uses an **Input Text** helper to store a JSON map `{camera_slug: silent_until_ts}`.
  - If the helper isn't configured, falls back to a **global mute** (temporarily turns off this automation).
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
- Update loop now cleanly exits on `end` and won't echo redundant updates.

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
