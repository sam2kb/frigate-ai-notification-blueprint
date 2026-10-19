# Frigate Home Assistant AI Notification Blueprint
---
<sup>Rewritten and improved version of the original by [@zacharyd3](https://github.com/zacharyd3/Frigate-Vision).</sup>

**Frigate AI Notification** sends multi-camera alerts from **Frigate**, with optional **LLMVision** summaries. Detection, zone and face filters help you control which events produce notifications.

---

## Import the Blueprint

Version `1.0.0` is available on `main` and requires Home Assistant 2026.3+. It includes the fixes tested in RC2. See the [compatibility notes and known limits](docs/frigate-0.18-compatibility.md) for automated coverage and installation checks, and the [RC1 review responses](docs/rc2-review-responses.md) for the review decisions.

[![Open your Home Assistant instance and import the blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fsam2kb%2Ffrigate-ai-notification-blueprint%2Fblob%2Fmain%2Ffrigate-ai-notification.yaml)

---

## Upgrading from 0.3.x

**Zone matching changed in v1.** Include and exclude patterns now match the full zone ID. Previously, `porch` could match `front_porch`; use `*porch*` to keep that substring behavior, or enter `front_porch` for an exact match. Review both lists before importing, especially privacy exclusions. Exclusions now take precedence reliably, and `all` requires every include pattern to match.

Home Assistant 2026.3+ is the supported minimum. Existing input IDs are preserved. The Temperature input is deprecated and ignored; configure temperature in your LLMVision provider instead.

---

## ✨ Highlights

- **Multi-camera**: monitor one or many Frigate cameras from a single automation.
- **Multi-device notifications**: send to any number of mobile devices.
- **iOS playback**: uses **HLS (.m3u8)** for recorded events on Apple devices when enabled. View Live opens the camera entity in HA.
- **Action buttons**:
  - **View Clip** opens the event clip
  - **View Live** deep-links to the camera in HA
  - **Open Frigate** opens your configured Frigate UI URL on Apple devices
  - **Silence** mute per-camera for X minutes, or globally if you don't set a table
- **Per-camera silence** (optional, recommended): provide an `input_text` helper to store a tiny JSON map of `{camera_slug: muted_until_epoch}`.
- **Event updates**: notify when an event becomes eligible, its recording flag or zones change, a name is recognized, or a moving object gets a new snapshot.
- **Zone filtering** with wildcards:
  - Include / Exclude lists
  - Match by **entered**, **current**, or **either**
  - Require **any** or **all** zones to match
- **Noise controls**:
  - Minimum detection score
  - Require event recording (optional)
  - Ignore likely false positives (optional)
- **LLMVision summaries (optional)**: short, readable descriptions of what happened.
- **Notification URLs**: relative links use the sending HA server in the Companion app. You can supply an explicit HA base URL and a separate Frigate UI URL.
- **Friendly titles & camera names**: quick options to expand “Cam → Camera” or append “Camera”.
- **Debug mode**: logs rejected events, filter decisions and observed zones while you fine-tune.

---

## ✅ Requirements

- **Frigate** set up with MQTT events and the **Frigate Home Assistant integration**
- **Home Assistant 2026.3+** (matches the verified Frigate integration's minimum)
- **Home Assistant Companion App** on your phone (for notifications)

Frigate 0.18 event fields and notification media routes are covered by the [compatibility checks](docs/frigate-0.18-compatibility.md). Enable Frigate recording retention if you want event clips and LLMVision video analysis.

**Optional:**
- **LLMVision** provider (leave blank to disable AI entirely)
- **Input helpers** create in the same automation edit screen:
  - `input_datetime` for a **global cooldown** (optional; enable only if you want to skip alerts during the cooldown)
  - `input_text` for the **per-camera silence table** (optional, recommended)
  - `input_boolean` as a simple **LLM “busy” gate** when several cameras run in parallel (optional)
- **Camera name override map** (optional): JSON map to align HA camera entity ids with Frigate camera names.
- **Require zone data** (optional): wait for zone data before sending notifications or AI analysis.

---

## 🚀 Quick Start

1. **Import** the blueprint and **create an automation** from it.
2. **Pick your cameras** and **notification devices**.
3. (Optional) Add **Camera name override map** if your HA camera entity ids do not match Frigate camera names.
4. (Optional) Turn on **Require Zone Data** if you want to wait for zones to populate.
5. (Optional) Turn on **iOS Notification** for HLS event playback on Apple devices. Android recipients keep MP4 links and three action buttons.
6. (Optional) Add **zones** to include/exclude and set match type/logic.
7. (Optional) Enable **LLMVision** by selecting a provider. Leave Model blank to use that provider's configured default.
8. (Optional) Add **AI Description Log Helper**: select an `input_text` with maximum length 255 for a short dashboard preview. Use the LLMVision timeline for longer history.
9. (Optional) Add a **Global cooldown** helper and duration if you want to throttle alerts across all cameras. Events during that interval can be skipped.
10. (Recommended) Add **Per-camera silence table** helper: select an `input_text`, set its maximum length to 255, and initialize its value to `{}`.
11. If Frigate uses a custom MQTT `topic_prefix`, set **Frigate MQTT event topic** to `<prefix>/events`.
12. **Save** and test.

---

## 📲 How the Notification Behaves

Initial and update notifications use the normalized Frigate camera ID as their tag. The final END card uses the Frigate event ID, and the AI summary replaces that final card. Repeated tags replace the corresponding notification. `alert_once: true` keeps Android replacements from alerting again.

On iOS, updates and AI replacements may alert again according to the phone's notification settings. Android's `alert_once` option does not control iOS sounds or banners.

The blueprint handles each MQTT `new`, `update`, and `end` message directly. An event no longer depends on a waiting loop being active when END arrives. Updates notify when an event becomes eligible, its recording flag changes, its recognized name or zones change, or a moving object gets a new snapshot.

- **Initial alert** on new Frigate event if it passes your filters.
- **Update alerts** on important changes:
  - The event's recording flag becomes true
  - Sub-label recognition changes
  - Zone match list changes - entered/current
  - New snapshot timestamp
- **End alert** when the event finishes and its final data passes your filters.
- **AI summary** after END, subject to the same filters, manual silence, and global cooldown. The event's own final card does not block its summary; another event's cooldown can.

**Buttons you'll see:**
- **View Clip** → opens the Frigate clip or HLS on iOS if enabled; events without a recording offer View Snapshot or View Live
- **View Live** → deep-links to the camera entity in HA
- **Open Frigate** → opens your configured Frigate UI URL on iOS
- **Silence** → mutes **just this camera** for X minutes (type a number);
  if you *didn't* provide a silence table, it falls back to **global mute** (temporarily turns off this whole automation - all cameras!).

Android supports three action buttons: View Clip, View Live, and Silence. If a summary dashboard URL is configured, View Summary replaces View Live. With iOS Notification enabled, Apple devices also receive View Live and Open Frigate when configured. The device registry's manufacturer identifies Apple recipients, so one automation can send to both platforms.

---

## 🎛️ Zones & Labels

- **Labels**: choose the suggested labels or type any Frigate label, including `truck` and custom model labels. Leave the list empty to accept all labels.
- **Include list** matches full zone IDs, supports `*` and `?`, blank = include all. Use `*porch*` to match IDs containing `porch`.
- **Exclude list**: use to carve out small “privacy” areas inside larger includes. If an event matches both an include and an exclude, the **exclude overrides** and the notification for that step is suppressed.

**Example:** `include=front_yard_*`, `exclude=porch_privacy` → activity in `front_yard_driveway` not blocked; stepping into `porch_privacy` suppresses that tick.

- **Zone Match Type**: which zone list to check from Frigate:
  - `entered` → only `after.entered_zones` (crossings)
  - `current` → only `after.current_zones` (currently inside)
  - `either` → union of entered + current

- **Zone Logic**: when include zones are set, require `any` or `all` of the listed zones to match.
  - Example: `include=driveway, porch` + `logic=all` → object must be in **both** zones.

---

## 🔕 Silence, Cooldowns & Noise Controls

- **Silence button**: per-camera mute for X minutes - requires the optional `input_text` table.
- The global mute fallback uses a running delay to turn the automation back on. Restarting HA or reloading automations during that delay cancels it and can leave the automation off. Use the silence table for mutes that survive restarts.
- **Global cooldown**: throttles sends across cameras (optional `input_datetime`, configured with both date and time). There is no hardcoded per-camera auto-mute.
- **Signal quality filters**:
  - **Minimum score** (default 0.6)
  - **Require Event Recording** (`has_clip=true`; this indicates retention, not that a clip has finished writing)
  - **Ignore likely false positives**

---

## 🧠 LLMVision (Optional)

Enable the provider/model to get a **short, readable summary** of what happened.
You can tweak:
- Number of frames analyzed
- Target width token/size trade-off
- Maximum output tokens
- Whether to save analyzed frames in LLMVision

Leave the **Provider** blank to turn AI off.

Analysis starts 30 seconds after END and retries failed requests using Retry Attempts and Retry Timing. Manual silence, cooldown and provider readiness are checked again after waiting. Generated titles use LLMVision's `title` field, with `response_title` accepted for older integrations. Missing or empty response text never produces an AI card.

The busy helper is released after each analyzer call, including reported service failures. It is a shared flag, so simultaneous events can still race. A restart or automation reload can interrupt cleanup; if the flag remains on after analysis has stopped, turn it off before retrying.

Set temperature in the LLMVision provider configuration. The blueprint keeps its deprecated Temperature input so saved automations still load, but does not send it to the analyzer. Timeline storage uses `store_in_timeline`; it does not enable LLMVision's separate contextual memory feature.

LLMVision resolves event clips using Home Assistant's own URL selection. HA must be able to select a URL and reach its notification proxy through it. This can use configured network URLs, a cloud URL, or a detected local address. The blueprint's External/Internal Base URL inputs affect phone links only. If analysis cannot fetch a clip, check HA's network URL settings and proxy access.

### 📝 AI Description Log

The **AI Description Log Helper** (`input_text`) stores a short preview when analysis succeeds. It remains available after the notification is dismissed. Set its maximum length to 255 characters. New entries are prepended, and the combined text is truncated to the helper's configured limit. A single description may fill the entire helper.

Entries include a timestamp and camera name:

```
[2026-10-17 21:43] Front Door: Delivery
A person leaves a parcel at the door.
---
```

For longer history, use the LLMVision timeline. To display the helper preview, add a Markdown card:

```yaml
type: markdown
content: "{{ states('input_text.frigate_ai_log') }}"
```

---

## 🔗 Links the Blueprint Builds for You

- `clip_url` - the event MP4
- `video_ios` - the event HLS playlist
- `snapshot_url` / `thumbnail_url` - still images
- `frigate_review_url` - opens the configured Frigate UI URL
- `live_deeplink` - opens your camera entity in HA using `/?more-info-entity-id=camera.example`, for both notification taps and View Live buttons

With both HA base URL inputs empty, media links remain relative and the Companion app resolves them against the sending server. An explicit External Base URL takes precedence over Internal Base URL. Use a URL reachable by every receiving device. The Frigate UI URL is independent and controls the Open Frigate action; it does not change HA's media proxy URLs.

---

Enable **Debugging** to see rejected camera, label, event-type and malformed-payload reasons in the logbook. Zone diagnostics show the observed IDs, configured patterns and whether an include failed or an exclusion matched. Debug output includes camera and recognized face names; leave it off during normal use.

## 📜 Changelog

See **[CHANGELOG.md](./CHANGELOG.md)** for what's new.
