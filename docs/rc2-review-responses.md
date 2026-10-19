# RC2 responses to the RC1 review

The [RC1 review](review-v1.0.0-rc.1.md) is preserved as submitted. These are the RC2 decisions and remaining installation checks.

| Review point | RC2 disposition |
| --- | --- |
| B1: candidate metadata | RC2 kept the candidate branch URL for testing. Stable v1.0.0 points the blueprint source and README import link at `main`. |
| B2: zone migration | Add a prominent breaking-change note and examples for both include and exclude patterns. Full-ID matching stays intentional; `*porch*` preserves substring behavior. |
| H1: live link | Use `/?more-info-entity-id=...` for both buttons and no-media taps. Android supports the old `entityId:` form, but iOS routing needs the shared URL. Test both platforms with mapped camera IDs. |
| H2: CI | Add minimum, pinned current and latest stable HA jobs, plus both Frigate 0.18 source checks. Weekly runs require the workflow on the default branch. |
| H3: early debug | Log camera, label, type and malformed-payload rejections before stopping. Include observed zone IDs and matching decisions. |
| M1: AI URL | Document HA URL selection and reachability. A manually configured URL is not always required: HA can also select a cloud URL or detected local address. Blueprint phone-link overrides do not control the analyzer's event resolver. |
| M2: obsolete AI keys | Remove `remember` and `temperature` from the call. Keep the deprecated Temperature input for saved automations. `store_in_timeline` persists events; `use_memory` is a separate contextual-memory feature. |
| M3: iOS re-alerts | Document the limitation. Keep active delivery because an update may be the event's first eligible alert. Android's `alert_once` does not control iOS. Live device testing remains required. |
| M4: HA minimum | Keep the user-approved 2026.3 support floor, matching the verified Frigate integration. It is a support decision, independent of the oldest HA syntax that could parse the file. |
| M5: README | Correct cooldown guidance, log timing and deprecated AI settings. |
| M6: labels | Allow custom values, including `truck` and custom-model labels; test selector acceptance and runtime filtering. |
| M7: camera map | Keep the JSON text input and mapping validation for saved-input compatibility. An object selector alone also accepts non-mapping values. |
| Editorial | Correct contributor URL guidance. Open Frigate intentionally opens the configured UI root. Keep valid HA aliases and the 2026.3 floor; newer `note` annotations are optional future work. |

The expanded tests use HA's actual local blueprint loader and input substitution, MQTT JSON parsing, a custom topic and mobile event routing. An overlapping-END scenario verifies that a second event waits while the busy helper is already held and retains its own event tag. The helper remains non-atomic when events arrive simultaneously.

The contract checker executes upstream Frigate MQTT serialization statements and validates every analyzer key actually sent by the blueprint. These checks do not verify URL-based blueprint downloading, a real broker, phone playback, provider authentication or recording availability. Maximum-run saturation and all possible concurrency interleavings remain outside the suite.
