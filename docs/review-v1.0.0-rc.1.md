# Review — v1.0.0-rc.1 (`codex/v1-candidate`)

- **Commit reviewed:** `baa271b4` — "Prepare v1.0.0-rc.1 for Home Assistant 2026 and Frigate 0.18"
- **Compared with:** `main` at `d5ae79cc` (0.3.9)
- **Reviewed:** 2026-10-18
- **Method:** static review of every changed file; the regression suite executed on
  Home Assistant 2026.3.0 and 2026.10.2 (Python 3.14); the upstream contract check executed
  against the pinned revisions; and a read of the upstream sources the blueprint actually calls
  (Frigate 0.18.0/0.18.2, `frigate-hass-integration`, LLMVision) at those commits.

This is an independent review of the branch, prepared with an AI review assistant at the repository
owner's request. Every automated result quoted below was executed on the reviewing machine. The
review did not use a live Frigate instance, phone, broker or AI provider.

## Verdict

The rewrite is a real improvement over 0.3.9. It removes the two defects that most damaged the old
behaviour — the `state_attr('homeassistant', ...)` "URL autodetection" that always returned empty, and
an LLMVision path that bypassed every quality filter and the cooldown. It also retires the
`wait_for_trigger` update loop, so an END message is now handled whenever it arrives instead of
being lost when an event went quiet for 30 seconds, and it fixes the nested Android `data` payload,
the per-device platform handling, the silence-table overflow, and the AI log length.

The default notification path now behaves as the README describes, and the test suite is
substantially better than anything the repository had before.

It is not ready to be labelled 1.0.0 without changes: one merge blocker, one silent breaking change,
one likely-broken tap target, and no CI. None of them needs a redesign; all are small.

## Verification results

| Check | Result |
| --- | --- |
| 42 regression tests, HA 2026.3.0, Python 3.14 | **pass** (42/42, 6.5 s) |
| 42 regression tests, HA 2026.10.2, Python 3.14 | **pass** (42/42, 5.1 s) |
| `tests/check_frigate_018.py` (0.18.2) | **pass** (7/7) |
| `tests/check_frigate_018.py --version 0.18.0` | **pass** (7/7) |
| Blueprint + automation schema validation | covered by the suite |
| Live Frigate, phone, AI provider | **not tested** (as the docs already say) |

```sh
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/work -w /work -e HOME=/tmp \
  python:3.14 sh -c "pip install -q -r requirements-test.txt && python -m unittest discover -s tests -v"
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/work -w /work -e HOME=/tmp \
  python:3.14 sh -c "pip install -q -r requirements-test-current.txt && python -m unittest discover -s tests -v"
python3 tests/check_frigate_018.py
python3 tests/check_frigate_018.py --version 0.18.0
```

The two claims in `docs/frigate-0.18-compatibility.md` about the automated checks hold as written.

`python:3.14-slim` is not sufficient: it has no compiler and `lru-dict` builds from source there.
The installation notes only mention `pip install`, so add the `python:3.14` image (or `build-essential`)
next to them.

## Blocking

### B1. Release metadata still points at the candidate branch

`frigate-ai-notification.yaml:7` (`source_url`) and `README.md:13` (the import badge) both reference
`codex/v1-candidate`. Home Assistant records `source_url` when a blueprint is imported and uses it
for update detection.

If the branch is merged as-is:

- every imported copy keeps tracking a feature branch, so a later fix on `main` is never offered as
  an update;
- the badge imports the branch file, not the released one;
- deleting the branch (normal after a merge) turns both into 404s and breaks update checks.

Fix in the merge commit: point `source_url` at `blob/main/...` and rebuild the badge's encoded
`blueprint_url`.

### B2. Zone patterns silently changed from substring to exact match

0.3.9 wrapped a pattern without `*`/`?` in `.*….*` (`main:frigate-ai-notification.yaml:458` and
`:472`), so `zones: porch` matched `front_porch` and `zones: drive` matched `driveway`. The
candidate always anchors the pattern (`^…$`, `frigate-ai-notification.yaml:501-520`).

The new behaviour is arguably the correct one, and a test pins it (`test_globs_and_literal_zone_names`
expects `drive` *not* to match `driveway`). But it is a silent alerting change for every existing
zone-filtered automation: no error, no log, notifications simply stop. The CHANGELOG mentions only
"anchor wildcard patterns to full zone IDs", and the README says nothing.

This is the one change in the branch that can quietly cost a user their alerts on upgrade, so it
must not ship unannounced. Pick one:

- keep 0.3.9 semantics for patterns without wildcards (least surprise), or
- declare it breaking: a `### Breaking` section in the CHANGELOG, a migration note in the README, and
  a debug line when an include pattern matches no zone in an event.

## High

### H1. The tap target for events without media is an action URI, not a URL

When an event has neither a clip nor a snapshot, `view_media_url` falls back to `live_deeplink`
(`frigate-ai-notification.yaml:620`), which is `entityId:{{ camera_entity }}` (`:577`), and that value
is used for `clickAction` and `url` (`:653-654`).

The Companion documentation lists the tap targets as a relative URL, a full URL, a More Info link
(`/?more-info-entity-id=<entity_id>`), and the Android-specific `app://`, `settings://` and
`deep-link://` schemes. `entityId:<entity_id>` is documented only for **action URI** buttons (and for
the `command` notification). It is the right value for the "View Live" *button* and the wrong one for
the *tap*, so tapping such a notification has no documented behaviour.

The existing test asserts the current value (`tests/test_blueprint.py:331`), so it would not catch
this. Fix: use `/?more-info-entity-id={{ camera_entity }}` for `clickAction`/`url` and keep
`entityId:` in the action list. Verify on one Android and one iOS device.

### H2. There is no CI

`.github/` contains only `copilot-instructions.md`. The suite is good but nothing runs it, and it is
not cheap to run by hand (Python 3.14 plus a full Home Assistant install, twice).

That matters more here than in a normal repository because the tests reach into HA internals that
move between releases — `bootstrap.async_load_base_functionality`, `ConfigEntry._entries`,
`ConfigEntry._async_set_state`, `hass.config_entries = ConfigEntries(...)`. The tests pass today on
2026.3.0 and 2026.10.2; without a scheduled run, the next HA release can break them and nobody will
know until a user does.

The two requirements files already give you a matrix. A small workflow with `python:3.14`, a pip
cache and `pip install -r requirements-…` is enough.

### H3. Debug mode cannot explain the most common silent failure

The camera/label gate (`frigate-ai-notification.yaml:494-498`) runs before the debug logger
(`:584-590`). So with `debug: true` there is **no output at all** for:

- a camera whose Frigate name does not match the selected entity and the override map (issue #1 —
  the most common installation problem this project has had);
- a label that is not in the selected list;
- a non-JSON payload or an unsupported `type`.

Everything up to the gate is silent by design, and the gate is exactly where misconfiguration lands.
Add one debug log before the gate with `trigger.id`, `event_type`, `camera`, `camera_key`,
`camera_entity` and the label decision.

## Medium

### M1. AI analysis needs a resolvable Home Assistant URL; notifications do not

LLMVision's `MediaProcessor.add_videos` calls `get_url(self.hass)` before resolving `event_id`
(`custom_components/llmvision/media_handlers.py:930` at `b81d6268`), and `get_url` raises when the
installation has no internal URL, external URL or cloud URL. The result is that AI analysis fails on
an installation whose notifications work fine with relative links — with only the generic
"AI analysis failed after N attempts" line.

Worth documenting next to the relative-URL paragraph in the README, and worth a clearer rejection
message when the analyzer errors (the call uses `continue_on_error`, so the actual exception only
appears in the HA log, not the logbook).

### M2. Two AI options are dead keys against current LLMVision

`frigate-ai-notification.yaml:742` sends `remember: true` and `:750` sends `temperature`. At the pinned
LLMVision revision:

- the service reads `use_memory` (`const.py:59`, `__init__.py:455`); `remember` does not exist, so
  memory is off;
- `ServiceCallData.temperature` is never read from the service data (`__init__.py:476`); the provider
  uses its own configuration (`providers.py:174`), so the Temperature slider does nothing.

HA does not reject the extra keys because LLMVision registers the service without a schema
(`__init__.py:947`), so calls still succeed — the options just have no effect. The upstream check
asserts only a subset of the field names (`tests/check_frigate_018.py:134`) and the mocked analyzer
accepts anything, so both tests are blind to this.

The README ("the blueprint temperature input remains available for older versions", `:148`) is
misleading: the key is sent unconditionally, so it cannot be version-dependent. Send `use_memory`,
drop `temperature` or label it as ignored, and make the contract check assert that **every** key the
blueprint sends exists in the upstream `services.yaml`.

### M3. Update notifications may be noisier on iOS than the README implies

`meaningful_update` now includes "the snapshot advanced and the object is not stationary"
(`frigate-ai-notification.yaml:556-560`). Frigate publishes an update on significant changes (zone,
`position_changes`, new attributes, active/stationary transitions — `tracked_object.py:326-352` at
0.18.0), so a moving visitor can produce several card updates during one event.

On Android this is quiet because `alert_once: true` is Android-only and suppresses re-alerts. The
Companion docs describe `alert_once` as Android behaviour; the iOS quiet-update control is
`silent: true`, which this payload does not set, so each replacement may alert again. Either verify on
an iPhone and document the expectation, or add a minimum interval / score delta for snapshot-triggered
updates.

### M4. `min_version: 2026.3.0` is inherited from the integration, not from the blueprint

Nothing in the blueprint obviously requires 2026.3: it uses `from_json` with a default (present in
2026.3), `config_entry_attr`, `!input` inside an MQTT topic, and standard template helpers. The
`2026.3.0` floor comes from the Frigate integration's `hacs.json`, which is a different product with a
different release cadence.

That hard-gates the import dialog on 2026.1/2026.2 installations that would probably run the
blueprint fine. Decide whether this is a support statement ("tested on 2026.3+, may work on older
versions") or a real gate; if it is a gate, say so in the README so users know why the import is
refused.

### M5. README statements that do not match the code

- `README.md:152` — "stores a short preview after the notification is dismissed". The log is written
  **before** the AI push (`:781` precedes `:805`), immediately after analysis.
- `README.md:148` — the temperature claim (see M2).
- `README.md:55` calls the global cooldown "NOT recommended", while `README.md:73` (Quick Start step 9)
  tells users to add it. Pick one position.
- `README.md:11` ("Import the v1 Candidate") and the badge need rewriting at merge (see B1).

## Low / editorial

- `.github/copilot-instructions.md:47` still says "ensure both internal/external HA URL fallbacks …
  continue to work". That rule describes the removed design and will push future changes (human or
  agent) back toward the bug this branch fixed.
- "Open Frigate" now opens the Frigate root (`frigate-ai-notification.yaml:578`) because the old
  proxied `/review?…` path was fictional. Event-level landing is probably still possible from
  `frigate_url`, but the 0.18 route needs verifying (`/review?cameras=` appears in the UI command
  menu) before restoring it. Not a blocker; just note the intentional downgrade.
- `alert_once: true` is Android-only, but the README states the replacement behaviour as if it were
  cross-platform (`README.md:82`).
- `test_blueprint_and_automation_schemas` compares the *installed* HA version with `min_version`
  (`tests/test_blueprint.py:220`) — true by construction in the pinned environment. It does not show
  older versions would work.

## Test-coverage gaps

The suite is the strongest part of the branch, but it does not cover:

- **the trigger path.** `run_event` builds a synthetic trigger dict and runs the action sequence
  through `Script`; the MQTT trigger, the custom topic input and the `mobile_app_notification_action`
  wiring are only schema-validated, never executed. A wrong topic or trigger id would pass.
- **blueprint import.** Loading the file through the blueprint platform (URL import, `!input`
  materialisation) is not exercised.
- **concurrency.** `mode: parallel` / `max` and the cooldown's context-id exemption are not tested
  under simultaneous runs; the "other event" in `test_other_event_cooldown_during_ai_delay_is_respected`
  is a synthetic write.
- **the update payload contract.** `check_frigate_018.py` asserts that the literals `new`, `update`,
  `end` exist in `object_processing.py`, but not that `update` carries `before` and `after` — which is
  what `meaningful_update` is built on. (It does today: `object_processing.py:120-139` at 0.18.0.)
  Assert the payload shape.
- **AI service fields.** The check validates a hardcoded subset of `services.yaml`, not the set of
  keys the blueprint sends (see M2).
- **`mqtt_topic`** with a non-default prefix.
- **AI options.** `max_tokens`, `temperature`, `generate_title` values are only checked against a mock.

## What is good

- The `new`/`update`/`end` handling removes the old loop's two failure modes (END lost after 30 s of
  silence; a run wedged waiting for messages).
- Quality, zone and face filters are now shared by notifications and AI, and END evaluates its own
  `after` data — the 0.3.9 defects are genuinely gone.
- Per-device delivery handles deleted/unloaded devices, failed services, mixed Apple/Android, and the
  three-button Android limit.
- Silence handling prunes expired entries, clamps the requested duration, and reports a full table
  instead of failing silently.
- The AI log respects the helper's maximum and uses real newlines.
- `has_clip` is correctly documented as retention eligibility, not download readiness.
- The documentation is unusually honest about the busy-helper race, restart behaviour and missing
  live testing.
- The contract check's pinned blob hashes are a good pattern.

## Release checklist

- [ ] B1: `source_url` and the import badge point at `main` (do it in the merge commit).
- [ ] B2: keep substring zone matching, or add a `### Breaking` changelog entry plus README migration
      note and a debug line for unmatched include patterns.
- [ ] H1: tap URL for events without media uses `/?more-info-entity-id=…`.
- [ ] H2: CI workflow over `requirements-test.txt` and `requirements-test-current.txt`.
- [ ] H3: debug log before the camera/label gate.
- [ ] M2: `use_memory`; drop or document `temperature`; assert every sent AI key upstream.
- [ ] M5: README fixes.
- [ ] Live test: one Android and one iOS device, Wi-Fi and mobile data; a real AI summary; a Silence
      tap; a camera-override install; a zone-filtered event.
- [ ] At merge: `[1.0.0-rc.1]` → `[1.0.0]` in `blueprint.description` and a `1.0.0` CHANGELOG entry.
