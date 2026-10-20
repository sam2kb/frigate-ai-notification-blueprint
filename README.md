# Frigate Home Assistant AI Notification Blueprint
---
<sup>Rewritten and improved version of the original by [@zacharyd3](https://github.com/zacharyd3/Frigate-Vision).</sup>

**Frigate AI Notification** sends multi-camera alerts from **Frigate**, with optional **LLMVision** summaries. Detection, zone and face filters help you control which events produce notifications.

---

## Import the Blueprint

Version `1.1.0` is available on `main` and requires Home Assistant 2026.3+. It adds per-camera activity windows, helper pickers and clip context. See the [compatibility notes and known limits](docs/frigate-0.18-compatibility.md) for verification and installation checks.

[![Open your Home Assistant instance and import the blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fsam2kb%2Ffrigate-ai-notification-blueprint%2Fblob%2Fmain%2Ffrigate-ai-notification.yaml)

---

## Upgrading from 0.3.x

**Zone matching changed in v1.** Include and exclude patterns now match the full zone ID. Previously, `porch` could match `front_porch`; use `*porch*` to keep that substring behavior, or enter `front_porch` for an exact match. Review both lists before importing, especially privacy exclusions. Exclusions now take precedence reliably, and `all` requires every include pattern to match.

Home Assistant 2026.3+ is the supported minimum. Existing input IDs are preserved. The Temperature input is deprecated and ignored; configure temperature in your LLMVision provider instead.

---

## ✨ Highlights

- **Multi-camera**: monitor one or many Frigate cameras from a single automation.
- **Multi-device notifications**: send to any number of mobile devices.
- **iOS playback**: uses MP4 with added clip context. With context set to zero and iOS Notification enabled, Apple devices use HLS. View Live opens the camera entity in HA.
- **Action buttons**:
  - **View Clip** opens the event clip
  - **View Live** deep-links to the camera in HA
  - **Open Frigate** opens your configured Frigate UI URL on Apple devices
  - **Silence** mute per-camera for X minutes, or globally if you don't set a table
- **Per-camera silence** (optional, recommended): provide an `input_text` helper to store a tiny JSON map of `{camera_slug: muted_until_epoch}`.
- **Camera activity windows**: use one timer per camera to group nearby detections into one notification, even when Frigate changes tracking IDs.
- **Quiet updates**: clip availability, final event data and AI summaries replace the camera card. Snapshot and face-label changes alone do not resend it.
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
- **Input helpers** select or create in the grouped helper sections:
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
5. (Optional) Turn on **iOS Notification** for extra Apple actions and HLS playback when Clip context is zero. With context enabled, both platforms use MP4. Android recipients keep three action buttons.
6. (Optional) Add **zones** to include/exclude and set match type/logic.
7. (Optional) Enable **LLMVision** by selecting a provider. Leave Model blank to use that provider's configured default.
8. (Optional) Add **AI description preview** under Optional helpers: select or create a Text helper with maximum length 255 for a short dashboard preview. Use the LLMVision timeline for longer history.
9. (Optional) Add a **Global cooldown** helper and duration if you want to throttle alerts across all cameras. Events during that interval can be skipped.
10. (Recommended) Add **Per-camera silence helper** under Camera activity and silence: select or create a Text helper with maximum length 255. An empty value is ready to use.
11. If Frigate uses a custom MQTT `topic_prefix`, set **Frigate MQTT event topic** to `<prefix>/events`.
12. **Save** and test.

---

## Helper setup

The form keeps **Camera activity and silence** together, followed by a collapsed **Optional helpers and global cooldown** section. Use each helper picker's **Create helper** option to create and select a helper without leaving the automation editor. Typing a new entity ID alone does not create it. A standard blueprint cannot create these helpers automatically when imported.

| Helper | When to use it | Setup |
| --- | --- | --- |
| Camera activity timer | One per camera for quiet-window grouping | Add a camera/timer row. Select or create a Timer and enable Restore. |
| Per-camera silence | Recommended for the Silence button | Select or create a Text helper, maximum length 255. Empty is fine. |
| Global cooldown timestamp | Only with a nonzero global cooldown | Select or create a Date and time helper with both enabled. |
| AI busy flag | Optional when coordinating AI analysis | Select or create a Toggle. Leave blank when AI is off. |
| AI description preview | Optional short AI dashboard history | Select or create a Text helper, maximum length 255. |

For independent camera alerts, leave Global cooldown at zero. Changing its duration does not change the per-camera quiet period. The AI helpers can stay blank when no provider is selected.

Existing `activity_timers` mappings remain supported under **Previous timer setup**. New rows take precedence for the same camera. To move an existing setup into the form, add its camera/timer pairs as rows, then clear the previous mapping. Reuse the existing helpers.

---

## 📲 How the Notification Behaves

Every stage uses the same automation-and-camera notification tag, including END and AI summaries. A completed object no longer creates a second card. Different cameras and different automations have separate tags.

For one alert per camera until it has been quiet for two minutes, open **Camera activity and silence** and add a row under **Camera activity timers**. Pick a camera, select or create its Timer helper, and enable Restore. Repeat for each monitored camera. Set **Camera quiet period** to 120 seconds.

The form saves the following blueprint inputs under `use_blueprint.input`:

```yaml
activity_timer_rows:
  - camera: camera.front
    timer: timer.frigate_activity_front
  - camera: camera.doorbell
    timer: timer.frigate_activity_doorbell
activity_quiet_seconds: 120
```

Use a different helper for every camera and automation. A missing, unavailable or shared timer, or a repeated camera row, stops the run and writes a configuration message to the logbook. Cameras without a timer keep direct event notifications.

The first eligible detection alerts. Every eligible Frigate message renews that camera's timer, including updates that produce no notification. A changed tracking ID does not start a new window. Once the timer expires, the next eligible detection alerts again, even if the old notification is still on the phone. The window tracks attempted alerts; it cannot confirm phone delivery.

With activity timers enabled, a newly eligible detection updates the camera card quietly to its own media, even during an existing window. It does not wait for END. Clip availability and END messages also update the existing card quietly. Android replacements use `alert_once`; Apple replacements use the passive interruption level. Face-label and snapshot changes alone do not resend the card. A new activity window uses an active notification. Phone settings still control how notifications appear and sound.

Cameras without an activity timer keep direct event notifications, with the same stable camera tag and fewer update sends. Android uses alert-once for those replacements; Apple event updates can still alert. Configure activity timers for the quiet-window behavior. Existing zone, quality and optional known-face filters still determine eligibility. Known-face suppression trusts Frigate's label and can hide a real alert if recognition is wrong; leave it empty when recognition is unreliable. Recognition labels are displayed as Frigate metadata, not a confirmed identity.

Optional AI analysis still uses object IDs to fetch clips. With activity timers enabled, later camera activity supersedes pending analysis and prevents an older result from replacing newer activity. This limits the summary to the latest clip; it does not combine the whole walk or all tracked objects into one video. A result that arrives after its activity timer expires is also skipped.

The blueprint handles MQTT `new`, `update` and `end` messages directly. Grouping uses camera activity and timing, not face names or tracked-object identity. Activity grouping is available from v1.1.0. Configure a timer for each camera to enable its quiet window.

**Buttons you'll see:**
- **View Clip** → opens the Frigate clip (HLS on iOS when enabled and Clip context is zero); events without a recording offer View Snapshot or View Live
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
- **Camera quiet period**: defaults to 120 seconds when activity timers are mapped. It restarts on each eligible message and affects only that camera. A continuous false detection can keep a window open, and missing MQTT messages can let it expire.
- **Global cooldown**: optionally throttles sends across all cameras using an `input_datetime` with both date and time. Leave it at zero to keep the camera windows independent.
- **Signal quality filters**:
  - **Minimum score** (default 0.6)
  - **Require Event Recording** (`has_clip=true`; this indicates retention, not that a clip has finished writing)
  - **Ignore likely false positives**

---

## Clip coverage

MP4 links include 10 seconds before the tracked event and 10 seconds after it ends, when Frigate has those recordings. Adjust **Clip context (seconds)** under Advanced Options, or set it to zero for the original event boundaries. Alerts still arrive immediately; opening an ongoing event plays only the footage available at that moment.

Frigate can split one walk into short object tracks. The camera card opens the latest eligible track with this added context; it does not combine the whole activity window into one video. Apple and Android use MP4 when context is enabled. Event HLS playback does not reliably apply padding, so Apple uses HLS only with context set to zero and iOS Notification enabled. LLMVision's event-ID analysis keeps its existing boundaries. Keep recording retention long enough to preserve the lead-in you want to see.

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

The **AI description preview** helper (`input_text`) stores a short preview when analysis succeeds. It remains available after the notification is dismissed. Set its maximum length to 255 characters. New entries are prepended, and the combined text is truncated to the helper's configured limit. A single description may fill the entire helper.

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
- `video_ios` - the padded MP4, or the event HLS playlist when Clip context is zero
- `snapshot_url` / `thumbnail_url` - still images
- `frigate_review_url` - opens the configured Frigate UI URL
- `live_deeplink` - opens your camera entity in HA using `/?more-info-entity-id=camera.example`, for both notification taps and View Live buttons

With both HA base URL inputs empty, media links remain relative and the Companion app resolves them against the sending server. An explicit External Base URL takes precedence over Internal Base URL. Use a URL reachable by every receiving device. The Frigate UI URL is independent and controls the Open Frigate action; it does not change HA's media proxy URLs.

---

Enable **Debugging** to see rejected camera, label, event-type and malformed-payload reasons in the logbook. Zone diagnostics show the observed IDs, configured patterns and whether an include failed or an exclusion matched. Debug output includes camera and recognized face names; leave it off during normal use.

## 📜 Changelog

See **[CHANGELOG.md](./CHANGELOG.md)** for what's new.
