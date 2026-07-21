# Per-Board Feature Parity Plan — Aula Win60 HE (A) vs Aula MINI 60 HE PRO (B)

> READ-ONLY audit output, 2026-07-20. No source files were edited; no hardware was touched.
>
> Evidence tags used throughout:
> - **CONFIRMED-BY-CAPTURE** — matches labeled frames in
>   `docs/context/issue-6-mini60-pro-raw/webhid-capture-2026-07-20.json` (457 frames, every OUT/IN
>   frame labeled with the vendor-UI action that caused it).
> - **SOURCE-ONLY** — read from vendor driver JS
>   (`docs/context/issue-6-mini60-pro-raw/driver_src/*` for board B; `driver_src/dec_agreement/deobfuscated.js`
>   for board A). Correct as a statement about what the driver *sends*, but not round-tripped on hardware.
> - **ASSUMED** — inference. Each one is flagged and has a verification task.
>
> Boards:
> - **A** = Aula Win60 HE, VID 0x2E3C PID 0xC365, `protocol.py`, report-ID-1 63-byte bodies.
> - **B** = Aula MINI 60 HE PRO (wired), VID 0x0C45 PID 0x80A2, `protocol_mini60.py` (in progress by
>   another agent — NOT edited here), 0xAA/0x55 64-byte frames, no report ID.

---

## 0. The one structural gap everything else hangs on

**Aether has no per-board protocol dispatch at all.** `app_web.py:21` does `import protocol` and every
Api method calls `protocol.build_*` directly — `set_light` (app_web.py:446), `_flush_triggers`
(app_web.py:525), `set_custom_colors` (app_web.py:589-591), `set_deadband_codes` (app_web.py:612),
`set_switch_codes` (app_web.py:627), `_flush_remaps` (app_web.py:638-650), `set_socd` (app_web.py:698-700),
`calibrate` (app_web.py:727-734), `_send_frame` (app_web.py:1027), `set_poll` (app_web.py:501),
`gamepad_mode` (app_web.py:749), `open_capture` re-arm (app_web.py:143,161).

The registry knows the protocol name per board (`boards.py:64` `protocol` field, `boards.py:77-80`
`drivable`), and `Api.__init__` detects the board (app_web.py:270-272) and opens the right interface via
`AulaDevice(self.board)` (app_web.py:276, aula_device.py:116-123) — but the *packet builders* are never
switched. With board B plugged in today, Aether opens the 0xFF68 vendor interface and writes **Win60
report-ID-1 frames** at it. (The registry note at `data/board_registry.json:37` records what happens:
the firmware echoes frames back and changes nothing.)

The UI is equally board-blind: `get_board` exists (app_web.py:330-354) and returns capabilities +
`drivable`, but **nothing in `ui/runtime_src/` ever calls it** (grep for `get_board|capabilities|drivable`
matches only an unrelated comment at `ui/runtime_src/src/sections.jsx:715`). Every workspace renders the
same Win60-shaped controls regardless of board.

**Task 0 (prerequisite for everything below):**
1. `app_web.py` — resolve the protocol module from `self.board.protocol` at connect
   (`importlib.import_module(self.board.protocol)` behind a small adapter), and route every Api method
   through a per-board driver object instead of module-level `protocol.*`. Suggested shape: a
   `drivers/` layer (`driver_win60.py`, `driver_mini60pro.py`) exposing a common interface
   (`set_light`, `set_actuation`, `read_actuation`, `set_keymap`, `set_macros`, `capabilities()`), with
   the existing `protocol.py` / `protocol_mini60.py` staying pure packet builders underneath.
2. Gate every Api method on capability: if the active board's driver lacks a feature, return
   `{"ok": False, "error": "not supported on <board>", "unsupported": True}` instead of writing
   Win60 bytes to a foreign board.
3. UI: call `get_board` once at startup (`ui/runtime_src/src/app.jsx`, next to the connect watchdog at
   app.jsx:866-887), stash `active.capabilities` in state, pass it into workspace `ctx`, and hide/disable
   controls per board (details per section below).

---

## 1. Animation / effect lists per board

### Where Aether's effect list lives today

- `ui/runtime_src/workspaces/lighting.jsx:16-36` — `LIGHT_MODES`, a **hardcoded** 19-entry list
  (wave, neon, radar, cross, breath, static, aurora, ripple, twinkle, reactive, striation, fireworks,
  frenzy, autorip, speedres, rain, comet, tide, custom). Also `ZONE_MODES` at lighting.jsx:38-46.
- `ui/runtime_src/src/app.jsx:78-96` — `FW_MODES`/`MODE_BYTE`: the *firmware* mode bytes for board A
  (static 0, breath 1, wave 2 … aurora 16), used only when the host engine is bypassed
  (app.jsx:908-918: firmware path only for Static or Full-RGB; everything else goes to
  `start_multicolor`, the host per-key engine).
- Both lists are **Win60-only**. Nothing selects a different list per board.

### `readLightList` (firmware reports supported modes)

- Defined at `protocol.py:48-58` (`build_read_light_list` cmd 10, `build_read_side_light_list` cmd 2)
  with parser `protocol.py:61-80`. This is board A's protocol (SOURCE-ONLY from the Win60 web driver;
  exercised on hardware only by the standalone tool `cycle_modes.py:66-69`).
- **Aether the app never calls it** — no reference in `app_web.py` or any JSX; the UI ignores firmware
  mode reporting entirely.
- **Board B has no equivalent.** The HFD SDK command enum (`driver_src/hfd-sdk.es-CGV2WPaF.js`,
  enum at ~offset 3300: `GET_LED_EFFECT:19 … SET_LED_EFFECT:35`) contains no "list supported modes"
  command; the hub driver's mode list is **client-side static data**
  (`driver_src/light-BPRaNowv.js`, `lightExplicit.effectMode`: static=1, custom=20, dynamic1..18 = 2..19).
  SOURCE-ONLY. So a firmware-query strategy cannot work uniformly across boards.

### Board B's firmware modes vs Aether's existing effects

Board B mode bytes 0x01..0x13 (CONFIRMED-BY-CAPTURE: all 19 captured with menu labels, and
mode/brightness/speed round-trip read back via cmd 0x13). The hub driver's own English names
(`driver_src/index-BZJzwCAk.js`, i18n `lightEffectHfd` dict — SOURCE-ONLY) are much better than the
Chinglish menu labels and should be what Aether displays:

| Byte | Vendor English name | Chinese menu label seen in capture | Closest existing Aether effect |
|------|--------------------|--------------------------------------|-------------------------------|
| 0x01 | Static             | Static constant brightness           | `static` (firmware) — HAVE |
| 0x02 | Reactive Single    | Single-point lighting                | `reactive` (host) — HAVE (semantics: light on press) |
| 0x03 | Extinguish Single  | Single extinguish                    | MISSING (inverse reactive) |
| 0x04 | Starry Sky         | twinkling stars                      | `twinkle` (host) — HAVE |
| 0x05 | Snowfall           | Snowflakes flying everywhere         | `rain`-like — PARTIAL (Aether rain is Matrix-style) |
| 0x06 | Blossoming         | A riot of flowers                    | MISSING (random color, firmware forces colorful) |
| 0x07 | Dynamic Breathing  | Dynamic breathing                    | `breath` — HAVE |
| 0x08 | Spectrum Cycle     | Spectral Cycling                     | full-RGB `neon`-ish — PARTIAL (forced colorful) |
| 0x09 | Color Spring       | Colorful springs gushing forth       | MISSING |
| 0x0A | Colorful Cross     | Colorful and diverse                 | `cross` — PARTIAL (has direction ctrl) |
| 0x0B | Drifting           | Go with the flow                     | `wave` — HAVE (has direction ctrl) |
| 0x0C | Twisting Path      | A Twist of Fate                      | MISSING (has direction ctrl) |
| 0x0D | Reactive           | On the verge of exploding            | `reactive` — HAVE |
| 0x0E | Double Tap         | Kill two birds with one stone        | MISSING |
| 0x0F | Ripple Spread      | Ripple spread                        | `ripple`/`autorip` — HAVE |
| 0x10 | Flowing            | Flowing continuously                 | `wave`/`tide` — PARTIAL (direction ctrl) |
| 0x11 | Mountain Peaks     | Layer upon layer of mountains        | MISSING |
| 0x12 | Gentle Rain        | Slanting wind and drizzle            | `rain` — HAVE (direction ctrl) |
| 0x13 | Shuttle            | shuttling back and forth             | `comet`-ish — PARTIAL |
| 0x14 | Custom (per-key)   | 自定义                                | `custom` — HAVE (see per-key RGB below) |

Per-mode control rules from the vendor UI (`light-BPRaNowv.js` `lightDisabled()`, SOURCE-ONLY):
speed disabled for modes 1 and 20; color picker disabled for 6 and 8 (firmware forces random color);
direction control only for modes **10, 11, 12, 16, 18**; mode 0 = lights off. Max brightness **5**, max
speed **5** (`lightExplicit.maxLightly/maxSpeed` — note Aether's `briByte`/`spdByte` at app.jsx:70-71
clamp to **4**, the Win60 scale; the capture's BRIGHTNESS_DEC went 5→4, consistent with a 1..5 scale).

### Full 0x23 frame decode (supersedes the partial decode in protocol_mini60.py's docstring)

From `hfd-sdk.es-CGV2WPaF.js` `ye`/`Te` (SET/GET_LED_EFFECT, payload offset = frame byte − 8),
SOURCE-ONLY except where noted:

| Payload off | Frame byte | Field | Note |
|---|---|---|---|
| 0 | 8  | mode | CONFIRMED-BY-CAPTURE |
| 1..3 | 9..11 | R,G,B | CONFIRMED-BY-CAPTURE |
| 4 | 12 | 0xFF constant | the "alpha" byte |
| 5..7 | 13..15 | secondary R,G,B | a second color — untested on hardware |
| 8 | 16 | **colorMode** (1 = random/colorful, 0 = use chosen color) | the byte protocol_mini60.py:16-17 hardcodes to 1. All 21 captured frames carried 1 because the driver state had colorMode=1 throughout; it is NOT a magic must-be-1 byte. **ASSUMED consequence: with colorMode hardcoded 1, user-chosen colors are ignored by firmware — needs a hardware test with colorMode=0.** |
| 9 | 17 | brightness (0..5) | CONFIRMED-BY-CAPTURE |
| 10 | 18 | speed (0..5) | CONFIRMED-BY-CAPTURE |
| 11 | 19 | direction (0/1) | boolean in vendor UI |
| 12 | 20 | effectModeType | always 0 in driver |
| 14..15 | 22..23 | 0xAA 0x55 marker | CONFIRMED-BY-CAPTURE |

### Does board B support per-key RGB? — YES (static custom); host-driven animation UNPROVEN

- The SDK has `GET_CUSTOM_LED_DATA:20` (0x14) / `SET_CUSTOM_LED_DATA:36` (0x24)
  (`hfd-sdk.es-CGV2WPaF.js` enum). The writer `_e` (at ~offset 12867) builds a **504-byte table =
  126 slots × 4 bytes `[slotIndex, R, G, B]`** and sends it under cmd 0x24. SOURCE-ONLY.
- The vendor light page exposes it as mode **20 = Custom** with per-key painting
  (`light-BPRaNowv.js` `setCustomLight()`/`resetCustomLight()`), keyed by `keyValue` (matrix slot).
  SOURCE-ONLY.
- The init sequence in the capture reads the 0x14 table (0x1F8 = 504 bytes — the table
  protocol_mini60.py:106 calls "unknown"; it is the custom-LED table, all zeros because no custom
  colors were set). CONFIRMED-BY-CAPTURE that the table exists and pages correctly; the *write* path
  0x24 was never captured.
- **So: static per-key colors (Aether's "Per-key Paint", app_web.py:577 `set_custom_colors`) are
  portable to board B.** What is NOT established is whether streaming 0x24 frames ~30-60×/s works as an
  animation channel the way board A's cmd 9 does (effects.py engine, `_send_frame` app_web.py:1013-1035,
  FPS at effects.py:20). Risks: 10 frames per full update (504/56); unknown latch/flash-wear behavior.
  The SDK also has `SET_MUSIC_DATA:53`, `SET_TEMPORARY_COMMAND_DATA:52`, `SET_LED_DATA:66`,
  `SET_LED_USER_ANIMATION:65` — one of these is likely the intended high-rate channel (the hub has a
  music-rhythm and GIF-light feature, `gifLight-Bulkc0-I.js`). SOURCE-ONLY, undecoded payloads.
- **Plan statement, plainly: do NOT promise host-driven animated effects (rain/frenzy/striation/etc.)
  on board B in this milestone.** Ship (a) the 19 firmware modes with correct per-mode controls, and
  (b) static per-key Custom via 0x24. Add a spike task to bench 0x24 streaming; only if it sustains
  ≥20fps without artifacts, port the effects.py engine (which itself is board-agnostic — it just needs
  a `send_frame` that emits 0x24 pages instead of cmd-9 pages).

### Data model recommendation: registry-driven per-board effect tables (hybrid-ready)

Firmware query is impossible on board B (no list command) and unused on board A, so:

1. **Extend `data/board_registry.json`** with a per-board `lighting` block:
   ```json
   "lighting": {
     "brightnessMax": 5, "speedMax": 5,
     "modes": [ {"id":"static","byte":1,"speed":false,"color":true,"direction":false}, ... ],
     "customModeByte": 20,
     "hostEngine": false
   }
   ```
   Board A gets its existing FW_MODES content (`app.jsx:78-95`) moved here verbatim, plus
   `"hostEngine": true`. Board B gets the 20-mode table above.
2. `get_board` (app_web.py:330) already ships capabilities to the UI — add the `lighting` block to that
   payload. The UI builds `LIGHT_MODES` from it instead of the hardcoded list
   (lighting.jsx:16-36) and clamps sliders with `brightnessMax`/`speedMax` instead of app.jsx:70-71.
3. **Hybrid hook:** keep `readLightList` as an optional *validator* on board A only (log a warning if
   firmware disagrees with the registry); never a UI source.

### Tasks (Section 1)

1. [Task 0 first.]
2. `data/board_registry.json` — add `lighting` blocks for `aula-win60-he` and `aula-mini60he-pro`
   (mode tables above; B's per-mode rules from `lightDisabled()`).
3. `app_web.py` — `set_light` routed per board; for B call `protocol_mini60.build_light` extended with
   `color_mode`, `direction`, `secondary_rgb` params (coordinate with the agent writing
   protocol_mini60.py — its `build_light` currently hardcodes `[16]=0x01` = colorMode 1 and has no
   direction parameter, protocol_mini60.py:284-308).
4. `ui/runtime_src/workspaces/lighting.jsx` + `src/app.jsx` — mode grid, sliders, direction control,
   Full-RGB toggle (→ colorMode on B) all driven by the registry block; hide host-engine-only modes
   (rain, frenzy, striation, comet, tide, zones panel) when `hostEngine` is false.
5. `app_web.py:set_custom_colors` — per-board: A = cmd 9 pages (protocol.py:98-121); B = one 0x24
   504-byte table write keyed by matrix slot (needs the new layout file, Section 2).
6. HW test task (owner has board B): colorMode=0 + chosen RGB on a dynamic mode; secondary color
   bytes; direction byte on modes 10/11/12/16/18; custom mode 20 + 0x24 write.
7. Spike (time-boxed): 0x24 streaming rate test → decide on porting effects.py to B. Until then the
   Lighting workspace on B shows firmware modes + static per-key only.

---

## 2. Actuation

### Board A (works today)

- `protocol.build_trigger` (protocol.py:125-147): cmd 33 sub 24, **22-byte column-major keymask**
  (`_keymask` protocol.py:39-44: `mask[i%22] |= 1<<(i//22)`), travel/RT LE16-split high bytes at
  sub[27..30], units 0.01 mm. Matrix stride **22**: device index = `row*22 + col`
  (device_state.py:157-160 travel stream, device_state.py:239-243 calibration mask,
  protocol.py:176-177 `build_remap` index split). Verified on hardware per CLAUDE.md cheat-sheet.
- Modes: 0 = fixed actuation, 12 = RT single, 13 = RT separate press/release (CLAUDE.md; UI sends
  via `set_trigger_codes` app.jsx:983, app_web.py:531-547).
- Read-back: `verify_actuation` (app_web.py:549-575) via cmd-33 sub-5 per-key query.

### Board B

- Table write cmd 0x27 / read 0x17: 0x3F0 = 1008 bytes = **126 records × 8 bytes**, paged 0x38 per
  frame, 18 pages at offsets 0x0000..0x03B8. CONFIRMED-BY-CAPTURE (18-page 0x17 sweeps under
  `NAV: Trigger settings` and before every write pass; 73-frame read+write passes for each of
  TRIP_INCREASE / TRIP_SET / RT_PRESS / RT_RELEASE).
- **Record layout — one-byte correction to protocol_mini60.py.** The SDK reader `Ne`
  (GET_MAGNETIC_AXIS_RT, `hfd-sdk.es-CGV2WPaF.js` ~offset 20200) assembles the table from
  `reply.slice(8)` — payload starts at **frame byte 8**, giving clean 56-byte pages = exactly 7
  records, **no truncated 7th record**. Record fields (SOURCE-ONLY, and byte-consistent with the
  capture):
  - `[0]` **axisType** — per-key magnetic-switch/axis id (trigger page `setAxisInfo()` writes it,
    `trigger-t6lqQxHu.js`). 0 for every key in the capture.
  - `[1]` **flags bitfield**: bit0 `isWholeFast` = RT enable, bit1 `isRampageMode`
    (CONFIRMED-BY-CAPTURE for bit0: raw offset-0 write frame is `AA 27 38 00 | 00 00 00 00 | 00 01 2C 01 7D 00 4B 00`
    → frame[8]=axisType 0, frame[9]=flags 1, trip 0x012C=3.00mm, press 0x7D=1.25mm, release 0x4B=0.75mm).
  - `[2..3]` trip LE16, `[4..5]` RT press LE16, `[6..7]` RT release LE16 — 0.01 mm units.
  - protocol_mini60.py:75-88 uses base 9 with `[0]=RT flag` and a "reserved trailing byte". This emits
    **byte-identical frames** while axisType=0 (which is why its golden tests pass) but mislabels the
    fields: its "reserved byte" is the *next record's axisType*, and its "[0] RT flag" is the flags
    bitfield. Fix the docstring/parse before axis-type or rampage features land — this is exactly the
    class of off-by-one that bit this project before. (Do not edit while the other agent owns the file;
    file it as a review note for them.)
- **Matrix mapping: keyValue = matrix slot, stride 16** (`slot = matrixRow*16 + col`).
  CONFIRMED-BY-CAPTURE: with all keys selected, exactly **61** record slots are populated —
  {0, 17-28, 32-44, 48-60, 64-76, 80-87, 92} — all at 16-aligned row boundaries. The full key→slot
  table is in the vendor bundle `driver_src/HFD-D07mGRx8.js` (`const o=[...]`, 61 entries, exported as
  the MINI 60 HE PRO layout; selected per PID in `info-Ce0byjrM.js` `initDeviceLayout`):
  Esc=0; 1!..=+ =17-28; Backspace=92; Tab..]=32-44; \\=60; Caps..;=48-59; Enter=76; LShift../=64-75;
  RShift=75; LCtrl=80, LWin=81, LAlt=82, Space=83, RAlt=84, Fn=85, App=86, RCtrl=87. SOURCE-ONLY
  (but its populated-slot set matches the capture exactly, which is strong cross-confirmation).
- **Aether's layout file for board B is wrong.** `ui/layouts/aula-mini60he-pro.json` is a scaffold with
  `"provisionalIndices": true` and Win60-style indices (Esc = "22"), plus a stale `_meta.pid` of FEFE
  and a falsified protocol note. Must be regenerated from the vendor table above.
- **Dead zones are global on B, not per-key.** Top/bottom dead zone live in the 64-byte game-mode/config
  table (cmd 0x11 read / 0x21 write) at payload offsets 8/9 (frame bytes 16/17), 0.01 mm:
  SDK `J`/`Q` field map `{[1] gameMode, [3] sleepTime, [4] keyDelay, [5] reportRate, [7] tftDisplayTime,
  [8] topDeadZone, [9] bottomDeadZone, [11] stabilityMode, [14] autoCalibration}`. The captured page-0
  bytes land on this map perfectly: sleepTime=1, reportRate=6, stabilityMode=1, autoCalibration=1, and
  the DEADZONE_TOP_0.42mm write patched exactly payload[8]=0x2A. **CONFIRMED-BY-CAPTURE** for
  topDeadZone position; the rest of the field map is SOURCE-ONLY with byte-level consistency. This
  fully decodes the table protocol_mini60.py:57-65 treats as opaque (its offset-7-with-base-9 equals
  the same frame byte 16). Note the vendor driver does NOT read-modify-write — `Q` rebuilds the table
  from page state and zeroes everything else; Aether's read-patch-write plan is safe and strictly better.
- Ranges (vendor `Trigger_Data`, `trigger-t6lqQxHu.js`, SOURCE-ONLY): travel 0.1..3.4 step 0.01
  (max adjusted down by the active axis's `maxTravel`), RT 0.01..3.4, dead zone 0..0.5.
  Aether's actuation sliders (actuation.jsx:74 travel 0.1..3.4; actuation.jsx:100-101 RT 0.05..2.0;
  actuation.jsx:135-136 dead band 0..0.5) are compatible; RT min/max differ per board (A vs B) and
  should come from the registry.

### Status table

| Feature | Board A | Board B |
|---|---|---|
| Fixed actuation point per key | WORKS (cmd 33, app_web.py:531) | MISSING in app; protocol ready (0x27 records, flags bit0=0) — CONFIRMED-BY-CAPTURE |
| Rapid trigger press/release | WORKS (modes 12/13) | MISSING in app; protocol ready (flags bit0=1 + press/release LE16) — CONFIRMED-BY-CAPTURE |
| Per-key different values | WORKS (grouped packets, app_web.py:506-529) | Native (table is inherently per-key) — needs full read-modify-write flow like the vendor (0x17 sweep, patch slots, 0x27 sweep) |
| Read-back / verify | WORKS (app_web.py:549) | MISSING; use 0x17 sweep + `parse_actuation_records` |
| Dead band | WORKS per-key (cmd 38, app_web.py:598) | Global only (0x11/0x21 table) — per-key UI semantics IMPOSSIBLE-ON-THIS-HARDWARE; apply globally & say so in UI |
| Switch/axis profile | WORKS (cmd 37 table, app_web.py:619; hardcoded 4-switch list actuation.jsx:152-161) | Different mechanism: per-key `axisType` byte in the 0x27 record (SOURCE-ONLY); axis list comes from vendor config (`axisMap`, HFD-D07mGRx8.js) — needs its own list for B |
| Travel test / live depth | WORKS (cmd 33 sub 5, device_state.py:157) | MISSING; SDK: `GET_MAGNETIC_AXIS_KEY_STATUS:96` (0x60) + calibration stream `GET_MAGNETIC_AXIS_CALIBRATION_DATA:251` input reports `{keyValue, status, max, min, current, keyStroke, maxStroke}` (SDK `V`, SOURCE-ONLY) |
| Calibration | WORKS (cmd 33 revise, app_web.py:721) | MISSING; SDK: `SET_CALIBRATION_ON:100/OFF:101`, `CLEAR_CALIBRATION:5` via factory-reset cmd (SOURCE-ONLY) |
| Matrix stride | 22 (device_state.py:160) | 16 (CONFIRMED-BY-CAPTURE via populated-slot boundaries) |

### Tasks (Section 2)

1. Regenerate `ui/layouts/aula-mini60he-pro.json` from the HFD layout table (61 keys, real `keyValue`
   slots, HID codes from `keyboardMap` `browserValue` — e.g. `"41-KEYBOARD"` = HID 0x29 Escape;
   fix `_meta` pid → 80A2, drop the falsified sonix note).
2. Driver B actuation: implement vendor flow — read 0x17 sweep → patch selected slots (preserve
   axisType and other keys' values) → write 0x27 sweep with final flag. Wire into `set_trigger_codes`
   / `verify_actuation` per-board.
3. Dead band on B: `set_deadband_codes` becomes global-apply (read 0x11, patch payload[8]/[9], write
   0x21); UI copy in `actuation.jsx` DeadBandWidget switches to "whole board" wording when
   `capabilities.deadbandScope === "global"`.
4. Switch widget: registry-driven switch/axis list per board; B writes `axisType` into 0x27 records
   (needs a hardware test — axis ids for this board are in the hub's device config, not yet captured:
   mark axis-id values ASSUMED until read back from a board with non-default axes).
5. Polling widget (actuation.jsx:212-236, 1/2/4/8 KHz → `set_poll` app_web.py:499, cmd 33 sub 9):
   Win60-only. B's `reportRate` lives in the game-mode table (payload[5], =6 in capture; meaning of the
   value UNDECODED — the vendor perf page doesn't even expose it). Hide the widget on B until decoded.
6. Travel test / calibration on B: implement 0x60 status polling + 100/101 calibration; until then hide
   the Travel Test toggle (actuation.jsx:55) and Calibration widget (actuation.jsx:239) on B.
7. Review note to protocol_mini60.py owner: record base is frame byte 8 (axisType byte), flags is a
   bitfield; config-table field map is fully decoded above; custom-LED table 0x14 and key tables
   0x12/0x16 are known commands (GET_KEY / GET_FN_KEY / GET_CUSTOM_LED_DATA), not "unknown".

---

## 3. Macros

### Current Aether state

- **No macros workspace**: `ui/runtime_src/workspaces/` = actuation, gamepad, keymap, lighting,
  settings, socd only. The old section removed macro/combo tabs as "duplicates of Remap Key"
  (`ui/runtime_src/src/sections.jsx:115-116`). Legacy Tk UI had a placeholder tab (`main.py:286`).
- `docs/MACROS_PROPOSAL.md` (v0.4 draft) proposes **host-side** macros (play back from the app), with
  firmware macros explicitly out of scope pending protocol decode. That decode now exists for both boards.

### Board A firmware macros (SOURCE-ONLY, `driver_src/dec_agreement/deobfuscated.js` `setMacroValue`)

- Cmd **25 (0x19)**: 10 macro slots, each a 256-byte blob paged in 58-byte chunks under
  `[25, slot, pageHi, pageLo, len, ...]`. Blob: `[0]`=index (+bit7 reuse flag), `[1]`=trigger type,
  `[3]`=stepCount*4, `[4..5]`=repeat count BE; steps from byte 8, 4 bytes each:
  `[hidCode, state<<4|type, delayHi, delayLo]`. Read-back uses the same cmd (`initMacroValue` wait loop).
- Binding to a key goes through the keymap table (cmd 24) — code values for macro keys are in the
  driver's key tables (not yet extracted; ASSUMED that `code1`/type byte selects macro binding —
  verification task).

### Board B firmware macros (SOURCE-ONLY, `hfd-sdk.es-CGV2WPaF.js` SET_MACRO writer ~offset 19978)

- `GET_MACRO:21` (0x15) / `SET_MACRO:37` (0x25). Layout: a **400-byte header** written first at
  `addrStart 0` — 100 × LE32 byte-offsets, one per macro id — then each macro's data appended from
  `addrStart 400`. Per-macro blob: `[0..1]` step count-ish header (`u[2]=0,u[3]=0`), steps from byte 4,
  4 bytes each: `[delayLo, delayHi, keyCode, actionByte]` where actionByte = press?0x90:0x10 for
  keyboard/mouse types, press?0xB0:0x30 otherwise. `macroSpaceSize: 512` hardcoded in device info.
- Binding: key-table record with pageType **MACRO = 6** (enum in SDK), with trigger behavior
  (`behaviorMode`, clickCount, clickInterval — `high-B56jYPrN.js` `highDefaultData.MACRO`), plus a rich
  macro editor in the key page (`keySet` i18n: recording, press/release events, Fire Key, Combo Key,
  repeat modes "Play Once / Fixed Count / Stop on next press / Stop on release").
- The macro pages were **not exercised in the capture** (NAV: Key remapping settings is a MARK with no
  frames) — everything here is SOURCE-ONLY and needs one capture session on the vendor UI recording a
  macro before Aether writes macros to hardware.

### Status table

| | Board A | Board B |
|---|---|---|
| Firmware macro storage | 10 × 256 B, cmd 0x19 (SOURCE-ONLY) | 100-entry offset header + blobs in 512-byte space, cmds 0x15/0x25 (SOURCE-ONLY) |
| Macro→key binding | via cmd-24 keymap table (ASSUMED encoding) | key record pageType 6 + behavior params (SOURCE-ONLY) |
| Aether UI | MISSING | MISSING |
| Aether protocol builders | MISSING | MISSING |

### Tasks (Section 3)

1. New `ui/runtime_src/workspaces/macros.jsx` workspace (recorder/editor + slot list), added to
   `WIDGETS`/`NAV` in app.jsx:40-47,150-157. Data model per MACROS_PROPOSAL.md's step schema, but
   target = firmware storage, not host playback.
2. Api methods `get_macros` / `set_macros` / `bind_macro`, dispatched per board driver.
3. Board B first (owner has hardware): capture one macro-record session in the hub driver to upgrade
   the SET_MACRO layout from SOURCE-ONLY to CONFIRMED, then implement builders in the B driver.
4. Board A second: implement cmd-0x19 builders; extract the macro key-binding code path from
   `dec_agreement/deobfuscated.js` (setKeyValue with macro key codes) before writing.
5. Until protocol confirmed per board, the workspace renders read-only/disabled with a "protocol not
   yet verified for this board" banner (capability flag `macros: "wip"`).

---

## 4. Missing sections per board

Vendor page inventory. Board B (hub.aulacn.com, `info-Ce0byjrM.js` `deviceRoute`):
`lightSet, triggerSet, masterSet, keySet, highSet, perfSet, versionSet` (+ `liveGifLightSet` for
TFT/GIF boards). Board A (hed.aulacn.com): lighting (+side light, music), trigger, key remap + macros +
combos, PRCS/SOCD, performance (win-lock etc.), switch, dead band, calibration.

| Vendor section | Contents | Aether workspace | Board A status | Board B status |
|---|---|---|---|---|
| Lighting (`light-*.js`) | modes, brightness/speed, color, direction, custom per-key | `lighting.jsx` | WORKS (host engine + fw modes) | BROKEN (sends Win60 frames; wrong mode list; wrong slider scale) → Section 1 |
| Trigger (`trigger-*.js`) | travel, RT, dead zone, axis, travel test, calibration | `actuation.jsx` | WORKS | MISSING/BROKEN → Section 2 |
| Expert (`masterSet`) | "Pro Presets" — cloud preset browse/apply (index-BZJzwCAk.js i18n `master:{title:"Pro Presets"…}`) | none | N/A (cloud service, not hardware) — optional future "community presets" feature, low priority | same |
| Key remap (`key-*.js`) | remap (KEYBOARD/MOUSE/CONSUMER/SYSTEM/FUNC types), macro list/editor, combo key, Fn layer | `keymap.jsx` (remap only) | Remap WORKS (cmd 24 both layers, app_web.py:634-683); macros/combos MISSING | Remap MISSING — needs SET_KEY 0x22 (126×4 `[pageType,p1,p2,p3]`, KEYBOARD type 2 with HID in param2 — SOURCE-ONLY) + SET_FN_KEY 0x26; macros MISSING |
| Advanced keys (`high-*.js`) | DKS, SOCD, MPT, MT (hold/tap), TGL (toggle), END (release trigger), RS (rapid SOCD / snap-tap) | `socd.jsx` (SOCD only) | SOCD WORKS (cmd 36 PRCS, app_web.py:686-703); DKS/MT/TGL/snap-tap: NOT PRESENT in the Win60 driver source → treat as IMPOSSIBLE-ON-THIS-HARDWARE unless new evidence | ALL MISSING in Aether; protocol known SOURCE-ONLY: bindings are key-table records (pageType 9=MT, 10=TGL, 11=SOCD, 12=RS, 13=FUNC, 6=MACRO — `high-B56jYPrN.js` type switch) + DKS via `SET_MAGNETIC_AXIS_DKS_DATA:40` (0x28), 63 slots |
| Performance (`perf-*.js`) | stabilityMode, adaptiveCalibration, sleepTime (game-mode table) | none (settings.jsx is app-prefs only: autostart/updates/profiles) | Win60 equivalents: win-lock/sleep/reset exist in protocol.py:348-361 but NO Api method / UI — MISSING | MISSING; trivially reachable via the 0x11/0x21 table (payload[11], [14], [3]) once driver lands |
| Version (`version-*.js`) | firmware version display, factory reset | none | MISSING (protocol.build_reset_keyboard exists protocol.py:359, unused; version via cmd 1 heartbeat/info undecoded) | MISSING (version from GET_DEVICE_INFO 0x10 reply bytes [8..9] per SDK `H` — SOURCE-ONLY; reset via `SET_FACTORY_RESET:15` / `RESET_ALL:255`) |
| Gamepad | n/a in vendor apps | `gamepad.jsx` | WORKS (board-side cmd 20 sub 3 + host uinput/ViGEm) | board-side gamepad mode: NO EVIDENCE in HFD SDK — hide the "board gamepad mode" toggle on B (host-side analog capture also impossible until live travel (0x60) lands) |

### SOCD detail (`socd.jsx` vs both boards)

- Aether UI collects pairs + model and calls `set_socd` (app.jsx:842 → app_web.py:686), which writes
  Win60 cmd 36 (protocol.py:317-338). On board B this is wrong at every level: B's SOCD is a
  **key-table binding** — two keys each get a record `{pageType:11, param1:behaviorMode,
  param2:key1HID, param3:key2HID}` written via SET_KEY 0x22 (`high-B56jYPrN.js` `setSOCDToDevice`,
  SOURCE-ONLY). Additionally B has **RS ("Rapid SOCD" — deeper press wins, i.e. snap-tap)** with
  pageType 12, which board A lacks.
- MT on B: `{pageType:9, param1:tapHID, param2:holdHID, param3:time/10}` (mtMin 10ms, mtMax 1000ms);
  TGL: `{pageType:10, value:HID}`; DKS: key record pageType 4 (`case 4` renders DKS)… DKS params live
  in the separate 0x28 table (up to 63 entries, 4 trip points 0.1..3.4mm with per-point press/release
  action masks — writer at hfd-sdk ~offset 22795). All SOURCE-ONLY; none captured.

### Tasks (Section 4)

1. Rename/expand `socd.jsx` → "Advanced Keys" workspace with per-board tabs: A shows SOCD (cmd 36
   models) only; B shows SOCD/RS/MT/TGL/DKS (DKS last — biggest payload risk).
2. B key remap: implement SET_KEY/GET_KEY (0x22/0x12) + Fn layer (0x26/0x16) in the B driver; wire
   `set_remap`/`reset_remap` per board. The 0x12 init read in the capture confirms the read side pages
   correctly (all-zero = no remaps set).
3. New "Board" settings widget (in settings.jsx or actuation): per-board performance fields — A:
   win-lock family (needs new Api around protocol.py:348); B: stabilityMode/adaptiveCalibration/
   sleepTime via 0x11/0x21.
4. Version/about widget: A: decode info reply (task); B: GET_DEVICE_INFO parse + factory reset with
   confirm dialog.
5. Gamepad workspace: hide board-mode toggle for B (capability flag).

---

## 5. Broken things (wired wrong today)

1. **Win60 packets sent to any detected board** — the Section 0 gap. Every Api write path
   (app_web.py:446,525,589,612,627,638,698,727,1027) emits `protocol.py` frames regardless of
   `self.board.protocol`. With B connected: writes go to the 0xFF68 interface as report-ID-1 frames,
   firmware echo-loops them, nothing works, and the UI happily reports success toasts
   (e.g. actuation.jsx:47 "Wrote …mm" fires without checking the promise result).
2. **UI ignores capabilities entirely** — `get_board` (app_web.py:330) has zero JSX consumers. Boards
   with `protocol: null` / `capabilities: false` still render full Lighting/Actuation/SOCD controls.
3. **`ui/layouts/aula-mini60he-pro.json` has fabricated indices** (Win60 stride-22 numbers, Esc="22",
   `"provisionalIndices": true`) and stale meta (pid FEFE, "sonix-aa assumed" — a hypothesis the
   registry note at board_registry.json:37 records as *falsified on hardware*). Any keymap-based
   feature on B (per-key paint, remap, per-key actuation, SOCD) will address the wrong keys until it's
   regenerated from the vendor table (Section 2 Task 1). This is the current live instance of the
   "assumption carried between boards" failure mode.
4. **Brightness/speed byte scale hardcoded to Win60's 1..4** (app.jsx:70-71) — B is 0..5; sending 4 as
   max means B never reaches full brightness, and 0-vs-off semantics differ (B mode 0 = light off).
5. **protocol_mini60.py semantic drift (byte-compatible today, wrong tomorrow):** record base off by
   one / axisType mislabeled as reserved; `[16]` hardcoded 1 is actually colorMode (user color likely
   ignored while 1); config-table treated as opaque though fully field-mapped; 0x12/0x14 tables labeled
   "unknown" though they are GET_KEY / GET_CUSTOM_LED_DATA. Hand to the owning agent as review input,
   with the SDK citations above.
6. **Registry entries for B still `protocol: null`, all capabilities false**
   (board_registry.json:40-41) — correct *right now* (protocol_mini60.py isn't wired), but flipping
   them is part of Task 0's definition of done, and the dongle entry (0xFEFE, board_registry.json:45-58)
   must stay null — the capture is wired-only; nothing here validates the 2.4G transport.
7. **SWITCHES list hardcoded in actuation.jsx:152-161** (four Win60-era switch profiles) feeding
   `set_switch_codes` → cmd 37 — meaningless ids on B (B uses axisType in the 0x27 record with
   board-specific axis ids).
8. **Gamepad board-mode toggle** (gamepad workspace → `gamepad_mode` app_web.py:747, cmd 20 sub 3) —
   no such command exists in the HFD SDK; on B it's a no-op write dressed as a feature.
9. **Success-blind UI toasts** (actuation.jsx:43-48,124-128 and similar) — flash "Wrote …" without
   awaiting the API result; with per-board gating landing, these must key off `res.ok` so unsupported
   features fail loudly, not silently.

---

## Ordered implementation sequence (cross-section)

| # | Task | Files | Blocked by |
|---|------|-------|-----------|
| 1 | Protocol dispatch layer + capability gating in Api | app_web.py (+ new drivers/*.py) | protocol_mini60.py landing (other agent) |
| 2 | Regenerate B layout from vendor table (61 keys, keyValue slots, HID codes) | ui/layouts/aula-mini60he-pro.json | — |
| 3 | Registry: lighting blocks, capability flags, slider scales, deadband scope, switch/axis lists | data/board_registry.json, boards.py (accept new fields) | — |
| 4 | UI board-awareness: fetch get_board, ctx.capabilities, hide/disable per board; honest toasts | app.jsx, all workspaces/*.jsx | 3 |
| 5 | B lighting: 20-mode list, 1..5 scales, direction/colorMode/secondary params; HW test colorMode=0 | app_web.py, protocol_mini60.py (owner), lighting.jsx | 1,3,4 |
| 6 | B actuation read-modify-write (0x17→patch→0x27), verify path, global deadband via 0x11/0x21 | drivers, actuation.jsx | 1,2 |
| 7 | B static per-key custom (mode 20 + 0x24 table) | drivers, lighting.jsx | 2,5 |
| 8 | B remap: SET_KEY/GET_KEY + Fn layer | drivers, keymap.jsx | 1,2 |
| 9 | Advanced-keys workspace: A=SOCD; B=SOCD/RS/MT/TGL (DKS later) | socd.jsx → advanced.jsx, drivers | 8 |
| 10 | Macros: capture session on hub driver → B builders → workspace; A cmd-0x19 after | new macros.jsx, drivers, app_web.py | 1; capture session |
| 11 | B travel-test/calibration (0x60, 100/101, 0xFB stream) | drivers, device_state.py analog readers | 1 |
| 12 | Perf/version widgets per board (A win-lock+reset; B game-mode fields + device info) | settings.jsx or new widget, drivers | 1 |
| 13 | Spike: 0x24 streaming benchmark → go/no-go on porting effects.py host engine to B | drivers, effects.py | 7 |

**Hardware-verification checklist for board B before shipping each feature** (owner has the board):
colorMode=0 color rendering; secondary-color bytes; direction on modes 10/11/12/16/18; mode 20 + 0x24
write visible; 0x22 remap of one key + read-back; SET_MACRO round-trip after a fresh capture;
axisType write acceptance; 0x60 live-status stream shape. Everything listed above as SOURCE-ONLY stays
gated behind `"wip"` capability flags until its line item here is checked off.
