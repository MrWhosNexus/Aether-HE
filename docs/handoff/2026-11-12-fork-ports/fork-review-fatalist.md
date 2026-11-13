# Fork review: Fatalist0001 (PR #15 subtype-3 release) and feat/sayo-actuation-decode

Reviewed 2026-11-12 against `origin/main` @ `f38e69a` (v0.6.5). Read-only; no fork code was run.

## 1. Summary

- **PR #15 (`fix/subtype3-release-detection`, base `2179fd7`, 3 commits): port nothing.** Its headline claim (a "subtype-3 raw_adc = 0" frame signals release) has no recorded evidence, contradicts upstream's own decode of the same byte, and ships with zero tests for it. Upstream's direction-plus-silence rule (`839a076`) plus the later OS-key-state and tap-flash rules already fix the stuck-key symptom from a capture. The gamepad smoothing was a workaround for that same symptom and is no longer needed.
- **`feat/sayo-actuation-decode` (base `77ba8f1`, 2 commits, owner-authored): port only the field decode, reshaped.** Main has the captures and the analysis doc but not the builder. The app wiring (`protocol_adapter.py`, `app_web.py` routing, registry `actuation: true`) is superseded by `drivers/` and contradicts the 2026-07-21 decision to keep this board inert.
- One real hazard in the Sayo builder: it replays key 0x2F's bytes 0-11 into every key. The captures themselves show those bytes differ per key.
- One follow-up worth more than either branch: a committed raw travel-stream capture, which would settle the subtype-3 question in minutes.
- `gh pr view 15 --comments` holds only a Vercel bot notice and a Greptile summary (5/5, automated). No human review discussion, no capture attached.

## 2. Item table

| # | Item | Fork file:line | Upstream status | Evidence | Value | Risk | Recommendation |
|---|---|---|---|---|---|---|---|
| A1 | Treat cmd-33 frames with `r[5]==3` and bytes 9-10 == 0 as an instant release | `device_state.py:167-197`, `:242-269`; `aula_device.py:46-50` | MISSING (by design). Release handled at `device_state.py:166` (`RELEASE_SILENCE_S`), `:175` (`STALE_S` + `is_key_down`), `:287` | owner-claim only ("verified on physical hardware" in `PR_BODY.md`); not in any committed capture | med if true (cuts release latency from ~150 ms to one frame) | high: discriminator misread (see section 4); non-zero frames are booked as depth | **SKIP.** Request a capture instead (section 3, note) |
| A2 | `_released` set: ignore subtype-5 frames for a released key until a new subtype-3 | `device_state.py:127`, `:190-192`, `:278-279` | MISSING | none | low | A missed re-press frame mutes a key | SKIP (depends on A1) |
| A3 | Pre-commit pending depth before a subtype-3 release (commit `9536a9b`) | `device_state.py:175-180`, `:250-255` | HAVE (different mechanism): `TAP_HOLD_S` flash, `device_state.py:182`, `_cleared()` and `snapshot()` `:395` | none | low | n/a | SKIP: the short-tap visibility problem is already solved, and without A1 this code has no trigger |
| A4 | Trend + 3 s stuck-silence removal, 1 s absolute snapshot timeout, 200 ms re-arm | `device_state.py:122`, `:205-225`, `:309-335` | HAVE, better: 150 ms upward-silence, 1 s stale gated on OS key state; re-arm 0.8 s | fork: owner-claim; upstream: captured (2026-11-03, replayed in `tests/test_travel_release.py`) | low | 1 s timeout relies on timer refresh to keep held keys | SKIP: superseded |
| A5 | `_depth_lock` + batched updates for atomic snapshots | `device_state.py:124`, `:271-290`, `:309` | PARTIAL: `snapshot()` copies with `dict()` under the GIL, `device_state.py:395-405`; no torn read, but two keys cleared in one drain can still be seen one frame apart | none (synthetic test only) | low | Lock taken per report on the hot path | SKIP: one 8 ms frame of asymmetry on a stick axis is not a reported problem |
| A6 | Gamepad EMA smooth-decay (`_DECAY = 0.7`), instant zero | `gamepad.py:225-235`, `:338`, `:403-410` | MISSING | owner-claim | low | Conflicts with idle-skip `gamepad.py:310`; adds a release tail | SKIP |
| A7 | Analog depth gate `AXIS_GATE_MM = 1.5` (the PR text says 1 mm) | `gamepad.py:32`, `:283-286`, `:384-387` | MISSING; upstream floor is `TRAVEL_FLOOR_MM = 0.15`, `gamepad.py:36` | owner-claim | negative | Discards 44% of the 3.4 mm range; the PR body itself calls it a "bandaid" | SKIP |
| A8 | `self._pad.reset()` at the top of every vgamepad update | `gamepad.py:371` | MISSING | none | none | Extra per-frame state churn | SKIP |
| A9 | Debug logging: `aether_debug.log` in the CWD, DEBUG level on three loggers, per-frame log lines | `app_web.py:27-36`; `gamepad.py:194`; `device_state.py:226`, `:292` | MISSING | n/a | negative | Writes outside the data dir; per-frame logging at 120 Hz | SKIP (see section 5) |
| A10 | Gamepad thread traceback on death, `LiveReader.is_alive()` | `app_web.py:1370-1383`; `device_state.py:337` | HAVE: `LiveReader.alive()` `device_state.py:~389`; reader marks the device dead on failure | n/a | low | none | SKIP |
| A11 | `AetherHE.spec` comment stripping | `AetherHE.spec:1-50` | n/a | n/a | none | Owner-only path | SKIP |
| A12 | `PR_BODY.md` at repo root | `PR_BODY.md` | n/a | n/a | none | none | SKIP |
| A13 | `tests/test_depth_race.py` (3 tests, subtype-5 frames only) | `tests/test_depth_race.py:79,142,177` | PARTIAL: `tests/test_travel_release.py` covers release paths | none | low | Tests the fork's lock, not upstream's design | SKIP |
| B1 | `build_key_analog(key, press_mm, release_mm)`: press at payload 12-13, release at 14-15, LE16, 0.001 mm | `protocol_sayo.py:134-173` | PARTIAL: decode documented in `docs/context/issue-3-sayodevice-raw/actuation_decode_analysis.md`; code has only `build_key_analog_raw` `protocol_sayo.py:134` and still says "fields NOT decoded" (`:83-88`) | captured (bytes 12-15, keys 0x2F and 0x30, three values); bytes 0-11 template: none for other keys | med (keeps code in step with the doc) | high as written: clobbers per-key bytes 0-11 | **PORT, adapted, library-only** |
| B2 | Golden tests for 0.4 / 1.0 / 2.0 mm | `tests/test_protocol_sayo.py:89-119` | MISSING | captured, with a caveat (goldens use echo 0x12, capture has 0x13) | med | none | **PORT with B1**, corrected to the real captured bytes |
| B3 | `protocol_adapter.py` (`SayoAdapter`, `for_board`) | `protocol_adapter.py:1-89` | HAVE, superseded: `drivers/__init__.py:44-48`, `drivers/base.py:67` | n/a | none | Second dispatch layer beside `drivers/` | SKIP |
| B4 | `app_web.py` routing of connect / lighting / actuation through the adapter | `app_web.py:22`, `:281`, `:315-320`, `:457-461`, `:475-502`, `:514-518`, `:587-596`, `:619-620` | Superseded by the driver layer; Sayo maps to `NullDriver` on purpose (`drivers/__init__.py:16`) | none (no Aether frame has reached this board) | negative | Sends writes to an unowned board; uses provisional layout indices as key ids | SKIP |
| B5 | Registry: Pro `capabilities.actuation: true`, `_note` update | `data/board_registry.json:77,81` | Contradicts `data/board_registry.json:525-526` (`offerInUi: false`, `_offerNote`) and `:535` | none | negative | Advertises an unverified write | SKIP the flag; take only the `_note` wording (see spec) |
| B6 | `tests/test_protocol_adapter.py` | whole file | n/a | n/a | none | none | SKIP with B3 |

## 3. Port spec

### B1 + B2: SayoDevice cmd-0x1C field decode (library-only, not reachable from the app)

**Target files:** `protocol_sayo.py`, `tests/test_protocol_sayo.py`, `data/board_registry.json` (`_note` text only). No change to `drivers/`, `app_web.py`, `boards.py`, capabilities, `offerInUi`, or any workspace.

**What to take:** the field map and range check from the fork's `build_key_analog` (`protocol_sayo.py:134-173` on the branch): press actuation = payload bytes 12-13, release = bytes 14-15, both LE16 in 0.001 mm; `release_mm=None` copies press; reject values outside 0.08-3.4 mm with `ValueError`.

**What to adapt:**

1. **Do not default bytes 0-11 and 16-23.** The fork hardcodes `_ANALOG_DEFAULT_HEAD = 6d8403006b84969e50020000` and `_ANALOG_DEFAULT_TAIL = e7000a0f64009001` for every key. The captures show these are per-key and change over time: in `actuation_0.4mm.pcapng`, key 0x2F appears with heads `6d84 0300 6b84 969e…`, `b081 0000 b581 259e…`, `b981 0300 b481 259e…`; key 0x30 with `b781 0500 b381 259e 5002…` and `e47c 0000 da7c 5829 5000…`, the latter with tail `dc05 0a0f c800 9001`. Make the base payload a required argument: `build_key_analog(key_idx, press_mm, release_mm=None, *, base_payload, echo=DEFAULT_ECHO)`, where `base_payload` is the 24 bytes last seen for that key. The function overwrites only bytes 12-15. Add a pure `parse_key_analog(payload) -> {"press_mm", "release_mm"}` for the inverse.
2. Keep the two captured payloads as named fixtures (`CAPTURED_ANALOG_FIXED_2F`), next to the existing `CAPTURED_ANALOG_PAYLOAD`, and update that constant's comment (`protocol_sayo.py:83-88` on main), which still says the fields are unverified.
3. Keep the module inside submission rule 2: imports stay `struct` only, no I/O.
4. Registry: update the Pro's `_note` to say the cmd-0x1C press/release fields are decoded and golden-tested but bytes 0-11 are per-key and no write path exists. Leave `"actuation": false`.

**Existing tests that guard it:** `tests/test_protocol_sayo.py` (framing, checksum, length guard), `tests/test_boards.py` and `tests/test_wiring_matrix.py` (Pro stays `NullDriver`, not offered), `tests/test_packaging.py`.

**New tests:**

- Goldens against the real wire bytes. The fork's constants start `2212 2000…`; the capture has `2213 2001…` (echo 0x13, checksum 0x0120). Use `echo=0x13` and the captured checksum: 0.4 mm `22132001 1c001c2f 6d8403006b84969e50020000 90019001 e7000a0f64009001`; 1.0 mm `2213d005 … e803e803 …`; 2.0 mm `2213a00d … d007d007 …`. I confirmed all three bodies occur once each in the pcapng files and that the checksum delta equals the echo delta.
- Asymmetric mid-drag frame from the capture: press 1.0 / release 0.4 (`e8039001`, checksum `7803`).
- `parse_key_analog` round-trip on all captured payloads, including key 0x30.
- `base_payload` is required (TypeError without it) and must be 24 bytes; bytes outside 12-15 are returned unchanged.
- Out-of-range press or release raises.
- A test asserting `drivers.get_driver(<Pro profile>)` is still `NullDriver` already exists in spirit; add an explicit one if `test_wiring_matrix.py` does not name the Pro.

### Not a port, but the useful follow-up from PR #15

Commit a raw travel-stream capture (the 2026-11-03 one is quoted in `839a076` and the test, but is not in the repo). Use the in-app capture (`app_web.py:296-312` keeps non-travel frames keyed by full hex) with Travel Test on while tapping and holding W. Then count cmd-33 frames by `r[5]` and `r[6]`. If length-3 frames exist and line up with releases, A1 becomes CONFIRMED-BY-CAPTURE and can be added as an *additional* early clear inside upstream's existing loop (roughly ten lines at `device_state.py:287`, clearing through `_cleared()` and `on_sample`), with direction-plus-silence kept as the fallback.

## 4. Conflicts with upstream decisions

1. **What `r[5]` is.** The PR treats `r[5]` as a subtype and bytes 9-10 of a "subtype-3" frame as a raw ADC value. Upstream established from the vendor driver source and a capture that `r[5]` is the payload **length**; the live frame is length 5 with sub-command 1 at `r[6]` (`CLAUDE.md:78`, `WIN60_CAPTURE_NOTES.md:149-156` and `:593`), and `tests/test_vendor_spec_socd_calibration.py:494-501` pins this. A length-3 frame has payload bytes 6-8 only, so bytes 9-10 are padding and read as 0 for *every* such frame. "raw_adc == 0" is therefore not a measurement. The PR never checks `r[6]`. **Upstream has the better evidence.**
2. **Internal contradiction in the PR.** `aula_device.py:36` (fork) documents the value as "~2535 rest .. ~1431 bottomed", taken from the early note in `docs/context/aula-win60-protocol-capture.md:30`. A Hall ADC at rest would then read ~2535, not 0. And the reader books any non-zero subtype-3 value as depth (`device_state.py:193`, `:266`: `depth = val16 / 100.0`), so 2535 would become 25.35 mm.
3. **Does subtype-3 exist on the Win60 per upstream's captures?** Not shown. `docs/context/hed-aulacn-raw/webhid-capture-win60.json` (8,089 frames) contains no travel stream at all; its cmd-0x21 IN frames have length bytes 1, 2, 6 and 12 only. `tests/fixtures` has no Win60 stream. The only mention is the pre-capture note above, which describes a calibration detail report, not a release signal.
4. **Complement or conflict with direction-plus-silence?** As written, conflict: it replaces upstream's loop wholesale (base is 160+ commits old), drops `_depths_idx`, `on_sample` telemetry, `is_key_down`, tap flash, `note_rx` and `mark_dead`, and its `_released` gate can suppress valid travel frames. In principle, a verified release frame would complement the silence rule as a faster path. That needs the capture first.
5. **"The firmware never sends 0."** Both sides agree on the symptom. Upstream's fix is derived from a capture and replayed in tests; the fork's is asserted.
6. **Gamepad.** Upstream's `VirtualGamepad.update` skips unchanged frames (`gamepad.py:304-313`, commit `ab5ef69`). An EMA needs a tick every frame, so a decay would freeze mid-tail the moment inputs stop changing. The 1.5 mm gate contradicts upstream's 0.15 mm floor and commit `7ceb7d3`, which widened the usable range on purpose. With released keys now cleared at the reader, the drift the gate and EMA were added for no longer reaches the gamepad. No capture shows held-key jitter large enough to need filtering.
7. **Sayo.** The branch (2026-07-06) turns actuation on for the Pro. Upstream decided on 2026-07-21 (`data/board_registry.json:525`) that the board stays detected but inert because nobody on the project owns one. The later decision stands; the README states the same.

## 5. Security findings

No network access, process spawning, credential handling, workflow changes or minified blobs in either branch.

- **SECURITY (low), PR #15 `app_web.py:27-36`:** adds `logging.FileHandler("aether_debug.log", mode="w")` with a relative path, so the file lands in the process working directory (the install directory for a frozen build, possibly unwritable), outside the app's data dirs. Combined with DEBUG level and per-frame lines (`gamepad.py:194`, `device_state.py:226`, `:292`, `aula_device.py:47`) it records every key's travel continuously: a keystroke-timing log on disk. Not ported.
- **Policy, PR #15 `AetherHE.spec`:** touches an owner-only path (submission rule 6). Comment removal only; no behaviour change. Not ported.
- **Hardware-safety, Sayo `protocol_sayo.py:143-144` + `app_web.py:475-502`:** `set_trigger_all` would write key 0x2F's calibration-looking bytes to every key, then save (`cmd 0x0D`). Not a security issue, but a plausible way to de-calibrate a board nobody can test. Addressed by the `base_payload` requirement in the port spec.
- Sandbox note: the `gh` call failed TLS verification inside the sandbox proxy and was re-run once outside it; it was the read-only command the task allowed.
