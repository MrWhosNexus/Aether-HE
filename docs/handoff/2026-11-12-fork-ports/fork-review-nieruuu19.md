# Fork review: nieruuu19 (2026-11-12)

Scope: `nieruuu19/aether-he-0.5.4-custom` (primary, 4 commits on v0.5.4) and `nieruuu19/main` (secondary). Compared against `origin/main` @ `f38e69a`. Read-only; nothing edited. Status: COMPLETE.

Abbreviations: `SP` = fork `protocol_sparkplay.py`, `PM` = upstream `protocol_magnet.py`, `DM` = upstream `drivers/magnet.py`.

## 1. Summary

- Upstream's experimental SOCD frame is wrong against the fork's Nov 5 code: the model sits in what is now the `bind` byte and is not zero-based. Only "Model 1" behaves correctly, by accident; Models 2-4 send an undefined `bind` and mode 0.
- Upstream's captured lighting write is byte-correct but blind: every write resets the board's sleep timer to 2, static slot to 0, colour slot to 0 and the palette to the capture's values. The fork reads the state first and preserves it.
- Upstream's experimental actuation write zeroes the advanced-key nibble of the mode property (drops SOCD/macro/MT bindings on that key) and never writes the dead band that the fork says decides Standard vs Continuous RT.
- Three board-neutral UI fixes are missing upstream and worth porting: phantom keys in Custom mode, dark preview when lights are off, and a free colour picker in Per-key Paint.
- No fork write path is captured beyond what upstream already has. The fork author's "works on my board" (issue #7, README, registry note "HARDWARE-VERIFIED 2026-11-04") is an unverified owner claim; he states Calibration was not tested.

## 2. Item table

| # | Item | Fork file:line | Upstream status | Evidence | Value | Risk | Recommendation |
|---|---|---|---|---|---|---|---|
| 1 | SOCD frame: `bind` at byte 7, zero-based mode at byte 8, delay u16 | SP:735, 1867-1895 | PARTIAL, wrong layout: PM:284-287, DM:167-173 | source-only + owner-claim | high | wrong SOCD behaviour today | PORT-EXPERIMENTAL: fix the frame behind the existing flag |
| 2 | SOCD clear-before-apply (firmware accumulates pairs) | SP:1905-1946 | MISSING | owner-claim | med | needs key-table read | PORT-EXPERIMENTAL with item 6 |
| 3 | Actuation keeps advanced-key nibble in prop 0x08 | SP:1549 | PARTIAL: PM:197-209 writes nibble 0 | source-only | high | upstream clobbers bindings | PORT-EXPERIMENTAL |
| 4 | Standard vs Continuous RT via press dead band 0x16; dead band 0x16/0x17 writes | SP:1533-1565, 1696-1731 | MISSING (PM docstring: "deliberately not ported") | owner-claim | med | per-key writes, uncaptured | PORT-EXPERIMENTAL |
| 5 | Global travel table write 0x29 and modes 98/99 | SP:1114-1120, 1462-1466, 1486-1527 | MISSING (read only, PM:235) | source-only | low | board-wide write | SKIP until captured |
| 6 | Connect handshake + read-back (sync, version, travel limits, 0x23 props, 0x18 state) | SP:1136-1157, 1173-1238, 1247-1279, 1607-1694 | PARTIAL: request builders exist (PM:135-240), no reply parsing, DM never reads | requests captured; replies source-only | high | reads only | PORT-EXPERIMENTAL (enables 2, 3, 7) |
| 7 | Lighting read-modify-write (keep palette, sleep, static slot, dyn id) | SP:1281-1288 | MISSING: PM:122-132 hardcodes `sleep_min=2`, slots 0, fixed block | write captured; reply layout source-only | high | low | PORT (echo the board's reply, fall back to today's frame) |
| 8 | Firmware effects 1-20 with names; static mode 0 with slot 0-6 / 7 = spectrum; dyn id 0 = spectrum, 1-7 = slots | fork `data/board_registry.json` win68 entry; `app_web.py`:112-135; SP:1299-1342 | PARTIAL: mode byte 0-21 captured (PM:66) but DM:97-102 refuses 0-20 | mode/slot/dyn bytes captured; names source-only + owner-claim | high | wrong label only | PORT: bytes ship on, names marked SOURCE-ONLY |
| 9 | Palette editing (7 slots, B,G,R,FF at payload 5..32) | SP:1122-1134, 1309-1319 | MISSING (PM:70 treats it as an opaque block) | layout captured (decodes to R,G,Y,B,M,C,W); non-default values owner-claim | med | low | PORT-EXPERIMENTAL |
| 10 | Snow Blossoms (mode 18) takes a colour | fork registry line 1383; commit `bcb79ae` | n/a until item 8 | owner-claim, and the fork contradicts its own earlier hardware note | low | none | fold into item 8 as `color: true`, flagged unverified |
| 11 | Batched per-key RGB write (14 keys per frame) | SP:1382-1389 | MISSING: PM:146 single key | source-only (vendor wrote all 68 keys one frame each in the capture) | med (5 frames instead of 68) | uncaptured | PORT-EXPERIMENTAL |
| 12 | Switch assignment 0x19 as an index into the CMD_SYS 118 axis list | SP:1734-1792 | MISSING | source-only + owner-claim | low | could store a bad switch id | SKIP until captured |
| 13 | Poll rate `CMD_SYS [80, idx, FF, FF]` | SP:738, 1794-1798 | MISSING | source-only; capture shows `50 07`, which is not one of the fork's indices | low | unknown semantics | SKIP |
| 14 | Key remap, prop 0x00 = hid or (mods << 8) | SP:1801-1832 | MISSING (constant only, PM:168) | source-only | med | uncaptured | SKIP until captured |
| 15 | Macros 0x20/0x21, MT 0x24, TGL 0x25, RS 0x2D | SP:1953-1985, 2097-2152 | MISSING | source-only; every slot writes address 256, so slots overwrite each other | low | flash writes | SKIP |
| 16 | Calibration `CMD_SYS 12/13` | SP:2009-2013 | MISSING | none (author: "haven't tested") | low | can wreck calibration | SKIP |
| 17 | Press-bitmap poll (0x12 sub 3) for firmware trigger state | SP:405-417 | MISSING (DM polls sub 2 only) | source-only | low | read only | SKIP for now |
| 18 | Phantom keys: Custom mode preview shows every sixth key lit | fork `lighting.jsx`:365 | MISSING: `ui/runtime_src/workspaces/lighting.jsx`:307-318 | n/a (UI) | med | low | PORT |
| 19 | Preview dark when lights off / unpaired | fork `app.jsx`:779 | MISSING: `ui/runtime_src/src/app.jsx`:933-960 | n/a | low | see conflicts | PORT the power-off half only |
| 20 | Per-key Paint: free colour picker + hex + saved colours | fork `lighting.jsx`:82, 1331-1480 | MISSING: upstream `lighting.jsx`:939-950 paints palette slots only, and the palette is hidden in Custom (line 841) | n/a | med | low | PORT (picker + hex; saved-colour library optional) |
| 21 | `set_custom_colors` writes the complete map, unlisted keys black, empty map allowed | fork `app_web.py`:1375-1400 | MISSING: `app_web.py`:1658-1679 | n/a | low | changes MINI 60 cumulative paint and the carrier path | SKIP |
| 22 | Updates disabled, WIN 68 default/fallback profile, Win60 HE Max (1CA2:1902) marked supported | fork `app_web.py`:68, 140-175; registry | n/a | none | none | contradicts upstream policy | SKIP |
| 23 | `nieruuu19/main` (2 commits) | all | superseded by the custom branch | n/a | none | n/a | SKIP; see section 5 |

## 3. Port specs

**A. SOCD frame (items 1, 2).** Target `protocol_magnet.py` `build_socd`, `drivers/magnet.py` `set_socd`, the `app_web.set_socd` docstring (it says the magnet driver takes N as is).
- New payload, 11 bytes: `[0x01, k1, k2, v1_lo, v1_hi, v2_lo, v2_hi, bind, mode, delay_lo, delay_hi]`.
- `mode = model - 1` (1 last input, 2 key 1 priority, 3 key 2 priority, 4 neutral). Refuse a model outside 1..4 before writing, as `Win60Driver` does.
- `bind = 0` (position binding) sends `v1 = v2 = 0`; `bind = 1` (key values) sends `v1 = k1`, `v2 = k2` unless given. Delay 0..50 ms.
- Default to `bind = 0`, `delay = 0`. The fork's UI defaults to `bind = 1`, `delay = 10`; the driver default is 0. Neither is captured.
- This layout is for firmware 1.0.7+. The fork has shorter frames for older firmware (SP:1889-1895); do not port those without the version read in spec C.
- Clearing: write `(key, 0x08, touch << 4)` for every key whose mode nibble reads 8, then the new pairs. Needs spec C.
- Tests: update `tests/test_protocol_magnet.py::test_socd_frame` and `tests/test_magnet_driver.py::test_experimental_actuation_and_socd_frames`. New: model 1..4 gives byte 8 = 0..3; `bind = 0` zeroes bytes 3..6; out-of-range model writes nothing. Expected vectors are in the fork's `tests/test_drivers.py`:1850-1880.
- Update the bring-up checklist line in `docs/HARDWARE_TEST_CHECKLIST.md`:203.

**B. Lighting state preservation and effects (items 7, 8, 9, 10).** Target `protocol_magnet.py`, `drivers/magnet.py`, `data/board_registry.json`.
- On connect, send `build_lighting_read()` (captured) and read one report. Accept it only if `[0]` is 0x5C or 0xDC, `[2] & 0x7F == 0x18` and length byte >= 43. Keep reply payload bytes 1..36 (palette block), 41 (sleep), 42 (static slot), 43 (dyn id).
- `build_lighting` gains a `block=` argument and stops defaulting `sleep_min=2`. With no valid reply, send exactly today's frame.
- Field offsets in the reply are the fork's (SP:1247-1279): flags 37, brightness 38, mode 39, speed 40, sleep 41, static 42, dyn 43; palette slot i at `5 + 4i` as B, G, R, 0xFF.
- Registry: add modes 0-20 with the fork's names (byte: 1 Rippling Water, 2 Tide Flux, 3 Soft Ripples, 4 Spinning Storm, 5 Lucky Rainbow, 6 Glowing Rainbow, 7 Radiant Glow, 8 Shifting Panes, 9 Wave Shift, 10 Shape Shift, 11 Sine Wave, 12 Smooth Flow, 13 Blooming Flowers, 14 Colorful Pattern, 15 Heavy Rain, 16 Eternal Pulse, 17 Traceless Steps, 18 Snow Blossoms, 19 Laser Beam, 20 Water Ripples). Use upstream-style ids, not the fork's reuse of Win60 ids (`wave`, `neon`...). `_note`: bytes CONFIRMED-BY-CAPTURE, names SOURCE-ONLY.
- `DM.set_lighting`: stop refusing 1..20. Colour choice maps to captured values only: dyn id 0 = spectrum, 1..7 = stored slot. Keep static colour on mode 21 + per-key paint for arbitrary RGB.
- Palette editing (writing non-captured palette bytes) goes behind `AETHER_EXPERIMENTAL=magnet`.
- Tests: `test_lighting_writes_rebuild_byte_for_byte` already guards the frame. New: a fake reply with sleep 30 and a custom palette is echoed unchanged; a short or foreign reply falls back to the captured block; modes 1..20 build with the right byte 39.

**C. Read-back (item 6).** Target `drivers/magnet.py` (new `connect`, `device_info`, `read_actuation`), experimental only.
- Requests are already captured builders: `build_hello`, `build_sys_query(1 / 0x26 / 0x25)`, `build_key_config_read(prop)`. Use upstream's captured pad `(FF, FF, FF, 00)` and `KEY_ORDER`, not the fork's sorted ids and `(FF, FF, 00, 00)`.
- Reply parsing from the fork: body = report[4 : 4 + len]; 0x23 reply is 4-byte records `(key, prop, lo, hi)` from body[1]; skip key 0 / 0xFF. Version: `major = body[3] & 0x0F`, `minor = body[2] >> 4`, `patch = body[2] & 0x0F`. Travel limits (sub 37): `body[2]` precision um, `body[3:5]` min, `body[5:7]` max.
- Cache per key: touch mode (`prop 8 >> 4`), advanced type (`prop 8 & 0x0F`).
- Tests: fake device replies; a failed read must leave writes refusing rather than guessing.

**D. Actuation correctness (items 3, 4).** Target `protocol_magnet.actuation_records`, experimental only.
- Mode record becomes `(touch << 4) | adv`, with `adv` from spec C's cache; refuse the write if the cache is empty.
- Mode 12 (Standard RT): also write `(key, 0x16, travel_um - 10)` clamped to 50..3390. Mode 13 (Continuous): write the user's dead band to 0x16/0x17.
- Dead band API: `(key, 0x16, top_um)`, `(key, 0x17, bottom_um)`, 0..1000 um. Do not port the fork's `user_deadband_memory.json` side file; keep the value in profile state.
- Tests: extend `test_rapid_trigger_records`, `test_key_config_write_frames`; new test that a key with nibble 8 keeps it after an actuation write.

**E. Batched RGB (item 11).** `build_key_rgb_batch(records)`: `[0x01] + (key, r, g, b) x <=14`, length `1 + 4n`, fill 0xFF. Use it in `stream_frame` only when experimental; raise `hostEngineMaxFps` only after a tester measures it.

**F. UI (items 18, 19, 20).** Sources only; rebuild with `ui/runtime_src/build_runtime.py`.
- `lighting.jsx` `previewSimColor`: after the `static` line add `if (s.pattern === "custom") return s.bgColor || "#000000";`.
- `app.jsx` `ledMap`: when `!power`, paint every key `#000000`; add `power` to the memo deps.
- `PerKeyPaintWidget`: replace `activeSlot` with a `paintColor` state fed by the slot buttons, an `<input type="color">` and a hex field validated by the existing hex helper; `assignToSelection` paints `paintColor`.
- Tests: the UI verification harness that imports `previewSimColor`; add a case for `custom`.

## 4. Conflicts with upstream decisions

| Topic | Upstream | Fork | Better evidenced |
|---|---|---|---|
| SOCD byte 7/8 | model (1..4) at byte 7, byte 8 = 0, bytes 3 and 5 = keys | bind at 7, zero-based mode at 8, bytes 3..6 are key values (zero for position binding) | Fork. Newer (Nov 5 vs October), carries the author's hardware note that the old table made Model 1 act as Neutral, and matches upstream's own checklist semantics. Still uncaptured. |
| Lighting read request | all-FF palette, zeros (captured) | current palette, lum 4, speed 4, sleep 30 | Upstream (byte-for-byte capture). |
| 0x23 read padding / key order | `(FF, FF, FF, 00)`, vendor order | `(FF, FF, 00, 00)`, sorted | Upstream (captured). |
| 0x2B frames in the capture | reads (`payload[0] = 0`) | PR comment calls them remap writes | Upstream. |
| Palette block | opaque 36 bytes | 4 zeros, 7 x (B, G, R, FF), 4 zeros | Fork: decodes the captured bytes to exactly R, G, Y, B, M, C, W. |
| Per-key colour write | one key per frame | 14 per frame | Upstream (the vendor wrote 68 single frames). |
| Static colour | mode 21 + paint every key | mode 0 + palette slot (rewrites slot 0 for a new colour) | Both captured as frames; upstream's avoids palette writes. |
| Snow Blossoms colour | not listed | first "colour-locked on hardware", then "takes the palette" one commit later | Neither; unverified. |
| Preview while unpaired | previews the selected mode | dark | Upstream's is a deliberate choice (`previewSimColor` comment covers "disconnected"); keep it. |
| Updates, default board, 1CA2:1902 as supported | policy | personal-build choices | Upstream. |

## 5. Security findings

No network, process-spawn, credential or workflow changes in either branch (`git diff` of all `.py`/`.yml` against the merge base: no `subprocess`, `urllib`, `socket`, `requests`, `eval`, `exec`, `ctypes`; no `.github/` changes).

- SECURITY (low) `protocol_sparkplay.py`:959-965. `_dz_memory_path` falls back to the module directory when `boot.user_data_dir()` fails, so it can write `user_deadband_memory.json` into the install tree. `nieruuu19/main` committed that file at the repo root.
- SECURITY (low) `protocol_sparkplay.py`:2049-2053. Macro store goes to `%LOCALAPPDATA%/AetherHE` or `~/.local/share/AetherHE`, bypassing `boot.user_data_dir()` (wrong directory on macOS).
- SECURITY (low) `protocol_sparkplay.py`:2033-2047. `send_raw` re-checksums and sends any 0x5C frame except commands 8..14. Calibration, macro and flash-table writes are reachable through it.
- SECURITY (info) `app_web.py`:68. `UPDATES_DISABLED = True` removes the update path entirely. Not harmful, but it must not be ported.
- SECURITY (med, do not port) `nieruuu19/main`: `aether_ui_only.js` (834,655 bytes), `aether_workspaces.js` (333,003), `aether_app_only.js` (88,991). They are `<script data-mod>` sections cut out of `ui/index_runtime.html`, re-encoded (mojibake such as `â€"`).
  - `aether_workspaces.js` and `aether_app_only.js` are readable Babel output. Zero uses of `fetch(`, `XMLHttpRequest`, `WebSocket`, `sendBeacon`, `eval(`, `new Function`, `atob(`, `innerHTML`, `window.open`, dynamic `import(`. The only URLs are the upstream issue links and the SVG namespace.
  - `aether_ui_only.js` line 9 is a 273 KB minified Tailwind browser 4.3.0 bundle. Its hash does not match upstream's copy (the re-encoding alone could explain that), so it cannot be verified as the genuine library. Same zero counts for the APIs above.
  - Also on that branch: `protocol_sparkplay.py.old` (dead code).

Not checked: the fork's built `ui/index_runtime.html` and `ui/runtime_src/build/*` (regenerated, never ported), and nothing was run on hardware.
