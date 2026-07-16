# Frigate Home Assistant AI Notification Blueprint
---
<sup>Rewritten and improved version of the original by [@zacharyd3](https://github.com/zacharyd3/Frigate-Vision).</sup>

**Frigate AI Notification** is a clean, low-noise blueprint for smart multi-camera alerts powered by **Frigate** and (optionally) **LLMVision**. It focuses on fast, relevant notifications with the right links and the right amount of detail - no spam.

---

## Import the Blueprint

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fsam2kb%2Ffrigate-ai-notification-blueprint%2Fblob%2Fmain%2Ffrigate-ai-notification.yaml)

---

## ✨ Highlights

- **Multi-camera**: monitor one or many Frigate cameras from a single automation.
- **Multi-device notifications**: send to any number of mobile devices.
- **iOS-optimized playback**: uses **HLS (.m3u8)** for live/clip viewing on iOS when enabled.
- **Action buttons**:
  - **View Clip** opens the event clip
  - **View Live** deep-links to the camera in HA
  - **Open Frigate** jumps to Frigate's review page
  - **Silence** mute per-camera for X minutes, or globally if you don't set a table
- **Per-camera silence** (optional, recommended): provide an `input_text` helper to store a tiny JSON map of `{camera_slug: muted_until_epoch}`.
- **Thoughtful update loop**: sends updates on meaningful changes (new snapshot, sub-label change, clip becomes ready) - not for every tiny motion.
- **Zone filtering** with wildcards:
  - Include / Exclude lists
  - Match by **entered**, **current**, or **either**
  - Require **any** or **all** zones to match
- **Noise controls**:
  - Minimum detection score
  - Require “clip ready” (optional)
  - Ignore likely false positives (optional)
- **LLMVision summaries (optional)**: short, readable descriptions of what happened.
- **Auto URL detection**: uses your HA **internal/external URL** if set; you can override the **Frigate UI URL**.
- **Friendly titles & camera names**: quick options to expand “Cam → Camera” or append “Camera”.
- **Debug mode**: safe, verbose logging to validate logic while you fine-tune.

---

## ✅ Requirements

- **Frigate** set up with MQTT events
- **Home Assistant 2024.6+**
- **Home Assistant Companion App** on your phone (for notifications)

**Optional:**
- **LLMVision** provider (leave blank to disable AI entirely)
- **Input helpers** create in the same automation edit screen:
  - `input_datetime` for a **global cooldown** (optional, NOT recommended)
  - `input_text` for the **per-camera silence table** (optional, recommended)
  - `input_boolean` as a simple **LLM “busy” gate** when several cameras run in parallel (optional)
- **Camera name override map** (optional): JSON map to align HA camera entity ids with Frigate camera names.
- **Require zones on initial send** (optional): skip the first notification until zones are populated.

---

## 🚀 Quick Start

1. **Import** the blueprint and **create an automation** from it.  
2. **Pick your cameras** and **notification devices**.  
3. (Optional) Add **Camera name override map** if your HA camera entity ids do not match Frigate camera names.  
4. (Optional) Turn on **Require zones on initial send** if you want to avoid early notifications before zones populate.  
5. (Optional) Turn on **iOS Notification** if you send to iPhones/iPads - this enables the HLS stream path.  
6. (Optional) Add **zones** to include/exclude and set match type/logic.  
7. (Optional) Enable **LLMVision** by selecting a provider/model.
8. (Optional) Add **AI Description Log Helper**: select an `input_text` to persist LLM-generated descriptions for a scrollable log page on any dashboard.
9. (Optional) Add **Global cooldown** helper: choose an `input_datetime` so back-to-back alerts are throttled.
10. (Recommended) Add **Per-camera silence table** helper: select an `input_text`. The blueprint initializes it automatically.
11. **Save** and test.

---

## 📲 How the Notification Behaves

Every send uses the same tag: `{{ id }}` - the Frigate event id. On both Android and iOS the HA app treats a repeated tag as a replacement of the existing notification rather than a new one. We also set `alert_once: true`, so the updated notification won't ping/vibrate again.

The update loop only fires on meaningful changes (clip becomes ready, sub-label changes, zones list changes, or a truly new snapshot). It's not sending on every MQTT tick.

- **Initial alert** on new Frigate event if it passes your filters.
- **Update alerts** on important changes:
  - Clip becomes ready
  - Sub-label recognition changes
  - Zone match list changes - entered/current
  - New snapshot timestamp
- **End alert** when the event finishes (optional, depending on your filters).

**Buttons you'll see:**
- **View Clip** → opens the Frigate clip or HLS on iOS if enabled
- **View Live** → deep-links to the camera entity in HA
- **Open Frigate** → opens `/review?camera=...&id=...`
- **Silence** → mutes **just this camera** for X minutes (type a number);  
  if you *didn't* provide a silence table, it falls back to **global mute** (temporarily turns off this whole automation - all cameras!).

---

## 🎛️ Zones & Labels

- **Include list** supports `*` and `?`, blank = include all.
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
- **Global cooldown**: prevents rapid repeat notifications across the board (optional `input_datetime`).
- **Signal quality filters**:
  - **Minimum score** (default 0.6)
  - **Require clip ready**
  - **Ignore likely false positives**

---

## 🧠 LLMVision (Optional)

Enable the provider/model to get a **short, readable summary** of what happened.  
You can tweak:
- Number of frames analyzed
- Target width token/size trade-off
- Max tokens & temperature
- Whether to expose images for richer notifications

Leave the **Provider** blank to turn AI off.

### 📝 AI Description Log

When you configure the **AI Description Log Helper** (`input_text`) under LLMVision Tweaks, every LLM-generated summary is persisted to the helper — even after the notification is dismissed.

Each entry is prepended with a timestamp, camera name, and label:

```
[2026-07-16 01:43] Back Yard Camera — person: Person walking across driveway
A person was observed walking across the driveway carrying a package toward the front door.
---
[2026-07-16 01:35] Front Door — package: Delivery driver drops off package
A delivery driver in a blue uniform approached the front door and placed a package on the doorstep.
---
```

To display it, add a **Markdown card** to any dashboard pointing at the helper:

```yaml
type: markdown
content: "{{ states('input_text.frigate_ai_log') }}"
```

---

## 🔗 Links the Blueprint Builds for You

- `clip_url` - the event MP4 or HLS for iOS if toggled
- `clip_url_signed` - signed clip used on iOS when available
- `snapshot_url` / `thumbnail_url` - still images
- `frigate_review_url` - jumps to Frigate's review UI
- `live_deeplink` - opens your camera entity in HA

All URLs are auto-derived from your HA internal/external URL when possible. You can override the **Frigate UI URL** if it lives elsewhere (e.g., different host/port).

---

## 📜 Changelog

See **[CHANGELOG.md](./CHANGELOG.md)** for what's new.
