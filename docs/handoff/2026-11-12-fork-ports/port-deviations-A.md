# Port deviations: Agent A (nieruuu19 fork → WIN 68 HE Max)

Source: `nieruuu19/aether-he-0.5.4-custom@7de05f2` (`protocol_sparkplay.py`). Target: `protocol_magnet.py`, `drivers/magnet.py`. Covers commits `186e8b4` and `12f1d00`. UI items 18-20, the layout test and the docs are not ported yet (see `port-status-A.md`).

## Where the port differs from the fork, and why
| Area | Fork | Port | Why |
|---|---|---|---|
| Structure | One 2,256-line driver with I/O, caches and builders | Pure builders and parsers in `protocol_magnet.py`, I/O in `drivers/magnet.py` | Upstream's split; builders are testable against the capture. |
| Read requests | Lighting read carries the current palette; 0x23 pad `(FF, FF, 00, 00)`; sorted key ids | Upstream's captured frames: all-FF lighting read, pad `(FF, FF, FF, 00)`, `KEY_ORDER` | The capture is the stronger evidence. A test asserts every frame `connect()` sends is in the capture. |
| Reply matching | Drains the input queue before each query | No drain; a reply must match the command, and for 0x23 the first key and the property | Works with the shared handle and cannot eat another reader's reports. |
| Failed read | `clear_socd` swallows a read failure and writes from its cache; actuation uses `ADV_NONE` when a key is not cached | 0x23 and 0x2C writes raise `RuntimeError`, with no traffic, when the key table was not read at connect | Review spec: a failed read must leave writes refusing, not guessing. |
| Partial key table | Uses whatever records came back | All 68 keys or nothing | A half table would zero the nibble of the missing keys. |
| SOCD old firmware | Shorter frames for protocol < 1.0.7 | Not ported; SOCD refuses when the board reports < 1.0.7 | Review spec: do not port them. |
| SOCD model | Unknown model silently becomes index 0 | Model outside 1..4 raises before anything is written; so does a key not on the board or a key paired with itself | Same rule as `Win60Driver`. |
| SOCD defaults | UI default `bind = 1`, `delay = 10` | `bind = 0`, `delay = 0`; `bind` / `delay` accepted per pair but the bridge does not send them | Review spec. |
| SOCD cache | Marks partner keys in a session cache | Re-reads property 0x08 from the board before every apply | The board is the source of truth; pairs made by the vendor driver are cleared too. |
| Lighting fallback | Starts from its own default palette (R, O, Y, G, C, B, V) | With no usable reply sends exactly the captured frame | Captured bytes ship; the fork's default palette is not what the board held. |
| Lighting reply check | Length >= 43 | Same, plus magic and command check; a 43-byte state gets 43-byte writes | Echo the board's own shape. |
| Static colour | Mode 0 + palette slot (rewrites slot 0 for a new colour) | Registry `static` stays mode 21 + paint every key; mode 0 is accepted by the driver but not listed | Upstream's path is fully captured and edits no palette. |
| Effect ids | Reuses Win60 ids (`wave`, `neon`, ...) | Own ids `fw-...` in `LIGHT_EFFECTS` | Win60 ids would route to the host effect engine on this board. |
| Effect names | Presented as verified | Marked SOURCE-ONLY in code; registry flag `nameUnverified` | Bytes are captured, names are not. |
| Palette API | `palette=` and `color_slot=` arguments on `set_lighting` | Not ported; only the implicit slot-0 rewrite for an unknown colour | No UI for it; keeps the `BoardDriver.set_lighting` signature. |
| Dead band memory | `user_deadband_memory.json` side file, with an install-tree fallback | In-memory, seeded from the board at connect | Review spec and security finding. |
| Standard RT at connect | Known from the side file | Inferred: rapid trigger with 0x16 == actuation - 0.01 mm. Such a key's own top dead band is unknown, so 0.20 mm (the fork's default) is used when it leaves Standard RT | No side file. |
| Dead band on mode change | Rewrites 0x16/0x17 on every fixed / Continuous write | Only for keys leaving Standard RT | Fewer uncaptured writes; other keys already hold their value. |
| Dead band + board-wide table | Writes global table 0x29 when >= 60 keys change | Not ported | Item 5 is SKIP. |
| Trigger modes | 0, 2, 12, 13, 14, 98, 99 | 0, 12, 13 (`Api._TRIGGER_MODES`) | 98/99 need the global table write (SKIP). |
| Actuation clamp | Fixed range | The travel limits the board reported, else 0.10-3.40 mm | Uses the read-back. |
| Batched RGB | All per-key writes | `stream_frame` only; static paint keeps the captured single-key frame | Review spec E. `hostEngineMaxFps` unchanged. |
| Write pacing | 2 ms sleep between 0x23 frames | None | Upstream's `_send_all`; add back if a tester sees dropped frames. |
| Link probe | Version query as `probe_link` / `ping_link` | Not ported | A wrong reply layout would make a healthy link look dead. |
| Bootloader check, serial, build date | Parsed from the hello reply | Not ported | Not needed by any item. |
| Gating | Everything on | Owner-run paths on, labelled COMMUNITY-TESTED (nieruuu19); 0x12 live travel still behind `AETHER_EXPERIMENTAL=magnet` | Owner's instruction of 2026-11-12. |

## Removed as redundant
- `protocol_magnet.build_socd` old layout `[1, k1, k2, k1, 0, k2, 0, model, 0, 0, 0]`.
- `protocol_magnet.actuation_records(rapid=...)` and its mode record with nibble 0.
- `MagnetDriver.EXPERIMENTAL_FEATURES` entries `actuation` and `socd`, and the `_require_experimental` calls in `set_actuation` / `set_socd`.
- The refusal of firmware effect bytes 1..20 in `set_lighting`.
- The `sleep_min=2` default of `build_lighting` (now `None`, which sends the captured 2).
- Tests for the above: `test_unmapped_firmware_effect_is_refused_not_guessed`, `test_unverified_writes_are_off_unless_experimental`, `test_experimental_actuation_and_socd_frames`, `test_magnet_receives_the_model_number_unchanged` (each replaced by a test of the new behaviour).
