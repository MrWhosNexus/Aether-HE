# Port status: Agent A (nieruuu19 → WIN 68 HE Max)

Stopped on the orchestrator's instruction, 2026-11-12. Worktree `ah-forkA`, branch `port/nieruuu19-win68max`, nothing pushed, working tree clean. There is no `wip` commit: everything committed is finished and green.

## Commits
- `186e8b4` feat(magnet): WIN 68 HE Max read-back, state-preserving lighting, effects, actuation, dead band, SOCD
- `12f1d00` fix(magnet): refuse key writes without traffic when the key table was not read; SOCD contract tests

## Tests
Full suite at `12f1d00`: 1640 passed, 26 skipped, 2 failed. Both failures are `tests/test_service_guard.py` (port bind refused by the sandbox), which the brief lists as expected. Baseline magnet tests went from 27 to 92 (`test_magnet_driver.py` 59, `test_protocol_magnet.py` 33).

## Items
| # | Item | Status |
|---|---|---|
| 1 | SOCD frame (bind byte 7, zero-based mode byte 8, delay u16) | Done. On by default. |
| 2 | SOCD clear-before-apply | Done. Re-reads property 0x08, unbinds every key with nibble 8, then writes the pairs. |
| 3 | Actuation keeps the advanced-key nibble | Done. Refuses when the key table was not read. |
| 4 | Standard vs Continuous RT, dead band 0x16/0x17 | Done in protocol and driver. Needs the registry change below before the UI offers it. |
| 6 | Connect read-back | Done: version, travel limits, name, global travel, lighting state, per-key 0x08/0x04/0x16/0x17. Only captured read requests are sent. |
| 7 | Lighting read-modify-write | Done. Falls back to the captured frame with no usable reply. |
| 8 | Firmware effects 1-20 and static mode 0 | Driver done. Registry mode list and the UI "unverified name" label are NOT done. |
| 9 | Palette editing | Done in the driver only: a colour not in the palette rewrites slot 0. No palette editor UI. |
| 10 | Snow Blossoms takes a colour | Covered by 8 (every effect takes the colour slot). Registry flag not applied. |
| 11 | Batched per-key RGB | Done, used by `stream_frame` only. |
| 18 | Phantom keys in Custom preview | Not started. |
| 19 | Preview dark when lights off | Not started. |
| 20 | Per-key Paint colour picker + hex | Not started. |
| Owner update 1 | Drivable by default, COMMUNITY-TESTED labels | Done in code. Only `travel_stream` is still behind `AETHER_EXPERIMENTAL=magnet`. |
| Owner update 2 | Layout verified, pinned by a test | Verified, test NOT written (see below). |
| Owner update 3 | Remove redundant code | Done for the driver and protocol (list in `port-deviations-A.md`). |
| Docs | README rows, `docs/HARDWARE_TEST_CHECKLIST.md` | Not started. |

## Layout check result (no file changed)
`ui/layouts/aula-win68he-max.json` was compared against the fork's `AULA_WIN68_KEYS` table and the capture:
- all 68 indices and key ids match the fork's table exactly;
- the layout sorted by `index` gives exactly `protocol_magnet.KEY_ORDER` (the captured 0x23 / 0x2A read order);
- the 0x2A writes in the capture cover the same 68 ids;
- the only differences from the fork are display names (`1!` vs `1`, `Shift` vs `LShift`), which are cosmetic.

No key needs fixing. The `_meta` block is stale and wrong: it says `provisionalIndices: true` and "Indices beyond the 60% block are placeholders. No HID dump/captures yet."

## Next steps, in order
1. Layout: correct `_meta` in `ui/layouts/aula-win68he-max.json` (indices verified against the capture). Add a test that pins, for all 68 keys, `index` → `hidCode` → position in `pm.KEY_ORDER`, and `index == row * 21 + col`. A literal table of 68 `(index, key id)` pairs is the simplest pin.
2. UI (spec F), then `python ui/runtime_src/build_runtime.py`:
   - `lighting.jsx` `previewSimColor`: after the `static` line add `if (s.pattern === "custom") return s.bgColor || "#000000";`
   - `app.jsx` `ledMap`: when `!power` paint every key `#000000`; add `power` to the memo deps.
   - `PerKeyPaintWidget`: replace `activeSlot` with a `paintColor` state fed by the slot buttons, an `<input type="color">` and a hex field.
   - `modeGridFor`: carry `nameUnverified` from the registry mode into the grid entry; show a marker and one line under the grid saying the effect names come from the vendor driver's source.
   - No node harness imports `previewSimColor` today; add one modelled on `tests/test_dashboard_ui_sources.py`.
3. Registry change (below), then README and the checklist line at `docs/HARDWARE_TEST_CHECKLIST.md`:203 (SOCD byte 8 = model - 1; the experimental section now covers only live travel).
4. `tests/test_socd_model.py`:81 has a docstring that still says the magnet driver takes N unchanged. Wording only.

## Registry change needed (`data/board_registry.json`, entry `aula-win68he-max`; Agent B's file)
- `offerInUi`: `true`; drop `_offerNote`. `status`: owner's call (`supported` or keep `bringup`).
- `capabilities`: `"actuation": true, "rapidTrigger": true, "socd": true, "deadzone": true` (lighting and perKeyRgb stay true).
- Add an `actuation` block: `"deadzoneScope": "per-key", "travelRange": [0.1, 3.4], "rtRange": [0.01, 3.4], "deadzoneRange": [0.0, 1.0]`. Do not copy the fork's `switches` list (switch assignment is SKIP).
- `lighting.modes`: keep `static` and `custom` at byte 21 and append the 20 effects from `protocol_magnet.LIGHT_EFFECTS`, each as
  `{"id": "<id>", "byte": <n>, "name": "<name>", "nameUnverified": true, "color": true, "speed": true, "brightness": true, "direction": true}`.
  Ids are `fw-rippling-water` (1) … `fw-water-ripples` (20). `tests/test_magnet_driver.py::test_registry_effect_table_matches_the_protocol_table` checks id, byte, name and the `nameUnverified` flag as soon as they are present, and requires all 20 or none.
- `lighting._note` and the entry `_note`: bytes CONFIRMED-BY-CAPTURE, names SOURCE-ONLY; actuation / RT / dead band / SOCD COMMUNITY-TESTED (nieruuu19).
- `tests/test_wiring_matrix.py` runs each capability against a stub that never answers. With the capabilities set to `true` the driver raises `RuntimeError` having written nothing, which that test accepts. Check `KNOWN_OVERCLAIMS` and `tests/test_boards.py` for assertions on this entry's old values.

## Decisions for the orchestrator / owner
- Live travel (0x12) stays behind the flag. It was not in the owner's list of features the fork author ran, and the fork maps mirror matrix slots (75→76, 85→86, 108-110→111, 112→114, 113→115) that upstream's reader does not handle. Without it the Travel Test and Dashboard live depth do not work on this board.
- `probe_link` / `ping_link` are not implemented. If the fork's reply layout were wrong, a probe would report a healthy link as dead and cause reconnect loops.
- If the board's replies do not match the fork's layout, actuation, dead band and SOCD refuse with a clear error and lighting uses the captured frame. Nothing is written blind.
- An effect colour that is not in the board's 7-slot palette overwrites palette slot 0 on the board (the fork's behaviour).
