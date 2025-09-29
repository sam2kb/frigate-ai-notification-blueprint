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
* **🧠 Integrates with LLMVision** to enrich notifications with event summaries
* **🕒 Enforces per-camera cooldowns** so you’re not spammed when a squirrel does laps in your yard
* **📱 Pushes mobile notifications** with custom text, camera names, and optional sublabels (e.g., who or what was recognized)
* **🧩 Uses input helpers** so you can easily reuse this blueprint across cameras without editing YAML
* **🌐 Auto-detects your Home Assistant URLs** for clip links and Frigate shortcuts, with overrides for the Frigate host and port when you need them
* **🎛️ Multiple notification devices** now available
* **🐛 Debug mode** lets you preview all variables and logic without sending notifications

---

### 🎯 Zone Filters

You can now restrict notifications to specific Frigate zones. In the blueprint, set "Zones to Notify On" to a comma-separated list like:

- `driveway`
- `porch, sidewalk`

Leave it blank to notify on all zones. Zone filters apply to:

- The initial notification when the event starts
- Subsequent update notifications (loitering/sublabel changes)
- Optional LLMVision analysis step

Zones are matched case-insensitively against Frigate's `entered_zones` for the event.

---

### ⚙️ Requirements:

* [Frigate installed](https://docs.frigate.video/integrations/home-assistant/) with MQTT events enabled
* [LLMVision](https://llmvision.org/) installed and configured
* Home Assistant mobile app (for push notifications)
* An input_boolean helper for multi-camera queuing
* A dashboard to use as a landing page ( LLMVision event summary suggested )

---

## Changelog

See the full change history in [CHANGELOG.md](./CHANGELOG.md).
