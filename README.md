# Frigate Home Assistant AI Notification Blueprint
---
<sup>Rewritten and improved version of the original by [@zacharyd3](https://github.com/zacharyd3/Frigate-Vision).</sup>

Frigate AI Notification is a concise Home Assistant blueprint for smart, low‑noise camera notifications powered by Frigate + LLMVision: real‑time alerts with AI summaries, per‑camera cooldowns, multi‑device push, and reliable clip/Frigate links. It auto‑detects your HA internal/external URLs, lets you set the Frigate host/port, uses signed clip links for iOS live view, and includes a debug mode for safe testing.

---

### Get the Blueprint

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fsam2kb%2Ffrigate-ai-notification-blueprint%2Fblob%2Fmain%2Ffrigate-ai-notification.yaml)

---
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/sam2kb)
#### 💡 What Frigate AI Notification Does

* **🚨 Listens for new Frigate detection events** from any camera you choose using MQTT
* **🧠 Integrates with LLMVision (optional)** to enrich notifications with event summaries
* **🕒 Enforces per‑camera cooldowns** so you’re not spammed when a squirrel does laps in your yard
* **📱 Pushes mobile notifications** with custom text, camera names, and optional sublabels (e.g., who or what was recognized)
* **🧩 Uses input helpers** so you can easily reuse this blueprint across cameras without editing YAML
* **🌐 Auto-detects your Home Assistant URLs** for clip links and Frigate shortcuts, with overrides for the Frigate host and port when you need them
* **🎛️ Multiple notification devices**
* **📹 Multiple cameras in one automation**
* **🐛 Debug mode** lets you preview all variables and logic without sending notifications
* **🧭 Zone filtering controls** include/exclude modes, match by entered/current/either zones, and any/all logic — applied to initial, update, and LLMVision steps
* **🔐 iOS live view** uses signed clip URLs when enabled
* **🔗 Resilient URL handling** with derived `clip_url`, `clip_url_signed`, `snapshot_url`, `thumbnail_url`, `thumbnail_android_url`, and `frigate_review_url` (no hardcoded `:8123`)
* **📉 Reduced noise**: for stationary objects, update notifications only fire on new snapshots or sublabel changes

---

### 🎯 Zone Filters with wildcards

Precisely control when notifications are sent based on Frigate zones:

- Zones to Notify On (`zones`): comma‑separated list like `driveway` or `porch, sidewalk` (blank = all zones). Supports wildcards `*` and `?` (full‑name match). Examples: `*_near`, `front_*`, `zone_?`.
- Zone Filter Mode (`zone_filter_mode`): `include` (only notify on listed zones) or `exclude` (ignore listed zones)
- Zone Match Type (`zone_match_type`): match by `entered`, `current`, or `either` zone lists
- Zone Logic (`zone_logic`): when mode is `include`, require `any` or `all` of the listed zones to match

Filtering is applied to:
- Initial notifications (event start)
- Update notifications (e.g., sublabel changes)
- Optional LLMVision analysis

Matching is case‑insensitive.

Examples:
- `driveway` → notify only when the event intersects the Driveway zone
- `porch, sidewalk` with mode `include` and logic `any` → notify when either zone matches
- `*_far` with mode `exclude` → suppress notifications in any zone ending with `_far`
- `front_* , *_near` with mode `include` and logic `all` → requires a zone matching each pattern (a single `front_near` zone satisfies both)

---

### ⚙️ Requirements & optional integrations

Required:
* [Frigate installed](https://docs.frigate.video/integrations/home-assistant/) with MQTT events enabled
* Home Assistant mobile app (for push notifications)
* Home Assistant 2024.6.0 or newer

Optional:
* [LLMVision](https://llmvision.org/) — leave the Provider input blank to disable AI entirely
* input_boolean helper — only used to gate LLM across multiple cameras; not needed if LLM is disabled
* A dashboard to use as a landing page (recommended for LLMVision summaries)

---

### 🔗 Helper Variables in templates and notifications

- `clip_url` → Derived URL to the event MP4 clip
- `clip_url_signed` → Signed clip URL (used for iOS live view)
- `snapshot_url` → URL to the event snapshot (JPG)
- `thumbnail_url` → URL to the event thumbnail (JPG)
- `thumbnail_android_url` → Android‑optimized thumbnail URL
- `frigate_review_url` → Link to Frigate UI /review for the camera/event
- `camera_name` → Human‑friendly camera name (after expand/append options)
- `id` → Frigate event ID
- `icon` → MDI icon selected based on detected label
- `base_url` / `local_url` → Resolved Home Assistant base URLs (auto from config if blank)
- `event_zones_entered` / `event_zones_current` → Zones reported by the event (lowercased)
- `zone_match` → True/false indicating if the event passes the zone filter

### 🧰 Multi‑camera usage notes
- Select multiple camera entities in the Camera input; the automation subscribes to all Frigate events via MQTT and filters to your selected camera IDs.
- The event must be of type `new` to trigger notifications; updates are handled by an internal loop per event.
- Execution mode is `parallel` (max 25) so multiple events/cameras can process concurrently.

---

## Changelog

See the full change history in [CHANGELOG.md](./CHANGELOG.md).
