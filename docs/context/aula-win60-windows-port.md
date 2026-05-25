---
name: aula-win60-windows-port
description: Repo + open work queue for the Aula WIN60 HE app (Windows port planned)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 2613a36f-e3c5-4c8d-9874-805854a9bc78
---

User plans a **Windows version** of the WIN60 HE app. Repo (USER'S OWN — MrWhosNexus IS the user):
https://github.com/MrWhosNexus/WIN60-HE-Mod.git
The Linux app (~/Projects/aula-win60-app) is now a git repo (committed on branch `aether-linux-app`, remote `origin` = that URL, .gitignore excludes venv-web/__pycache__). No GitHub auth in this env — user must `git push -u origin aether-linux-app` from their own shell.

- TRAVEL-TEST live animation FIX: actuation/dead-band config writes (cmd 33) stop the travel-test stream (also cmd 33), so live depth died right after entering the Actuation tab. LiveReader._run now RE-ARMS the stream (re-sends build_open_trigger_test) every 0.8s. open_trigger_test packet confirmed byte-identical to driver openTriggerTest (cmd33 [4]=24 [5]=2 mask[6:28]); read parse r[1]==33 r[5]==5 idx=r[7]*22+r[8] depth=(r[9]|r[10]<<8)/100. NOTE: couldn't verify with a physical keypress from agent side — user must confirm. Travel Test is a TOGGLE on the actuation Travel sub-tab (must be ON for live animation).
- ACTUATION "types at wrong point" FIX: code→device-index alignment VERIFIED correct (W→46 etc). Real cause = selection scope: default selection was WASD so actuation only hit WASD. Changed default selectedKeys to EMPTY (set_trigger_codes empty=ALL keys), added "Applying to: ALL keys / N selected" scope indicator in ActuationSection travel tab. Note triggerUnit=0.01mm, min actuation 0.08mm (so 0.10mm is near floor — suggest ≥0.3mm).

Work queue for `~/Projects/aula-win60-app` (see [[aula-win60-webview-ui]]). Status as of 2026-05-24:

DONE this session (user order 7,6,5,2,1 — built clean, app boots errors:[]):
- #7 Three new lighting modes: **Rain** (`_g_rain` Matrix drops), **Comet** (`_g_comet`), **Tide** (`_g_tide` waterline) in effects.py; registered in gens map + both UI lists (sections.jsx LIGHT_MODES & ZONE_MODES) + MODE_BYTE fallback. Host-driven via start_multicolor string passthrough.
- #6 Actuation audit: Python treats empty selection as ALL keys (correct). Fixed dead-band effect to re-push on `selectedKeys` change (parity with trigger).
- #5 Background themes already fully wired (theme.jsx Theme btn→Background tab→6 SVG presets+upload+opacity→`#__bg-image-layer`); bumped default imageOpacity 0.35→0.6 so backdrops show.
- #2 Keymap REMAP real: protocol.build_keymap_table (cmd 24, full 528B table, 4B/key [code1,hid,c3,c4], 56B pages — matches driver setKeyValue). Api.set_remap/reset_remap track accumulated `_remaps`. JS HID_BY_LABEL (app.jsx) maps picker label→USB HID; Apply/Default wired+toast. NOT yet flashed to HW (persistent — user tests live). Combo/Macro tabs still cosmetic.
- #1 Calibration highlight: handleCalibrate polls live depth; keys ≥3.0mm → calibratedKeys Set → green on board (keyboard.jsx Key calibrated/calibrating props). Switch info: switch tab shows per-switch spec readout.

- #3 DONE: Striation orientation v/h/both — Zone.orient threaded through start_multicolor/start_zones (orient param) + effects.py _g_striation rewritten (axis by orient); UI selector in LightingSection shows only when pattern==="striation" (striOrient state, persisted). Speed Respond rewritten (_g_speedres) as press-rate row fill: each press bumps a fill `level` that decays; keys under level light up, leading edge brighter; uses existing Direction control (_flow) for all 4 directions.

- #4 DONE: Gamepad now its own nav section (GamepadSection in sections.jsx, IZap icon). Capture toggle (set_gamepad_capture), editable key→control mapping rows (key/axis/direction/threshold) with driving-defaults + add/remove. Backend: Api.set_gamepad_map builds gamepad.KeyMap list into self._pad_map, VirtualGamepad(self._pad_map), live re-open on change; gamepad_status() reports capturing/evdev. gamepadMap persisted per profile.
- PERSISTENCE verified (code audit): save obj ⇄ applySettings symmetric, deps match, load-before-save race handled by applyingRef so switching never clobbers; covers Lighting/Actuation/SOCD/Gamepad/layer. App boots errors:[] with all sections.

- CALIBRATION (current state): firmware reports calibrated keys via cmd-33 response (hidapi r[1]==33, r[6] in {8,15}, r[7]==1, bitmask r[8:30]; index = bit*22 + col; r[7]==0 => done). device_state.CalibrationReader decodes → design codes, uses BLOCKING read (timeout_ms=40, no busy-spin — busy-spin on dev._lock had FROZEN the UI since AulaDevice.write shares dev._lock). app_web.calibrate(start): stops fx + LiveReader so reader is SOLE device owner, starts CalibrationReader. BOARD LED feedback DISABLED for now (was not visibly lighting — unresolved: either wrong byte offset OR firmware blocks LED writes in calibration mode; _render_calib method left unused). On-screen: JS polls read_calibrated()→green highlight. Auto-finish: firmware done OR 3s idle after ≥1 key (JS interval). handleCalibrate(false) chains apiCall().then(()=>lightNonce++) so lighting reverts AFTER reader torn down (fixed revert race). TODO when back at HW: dump one raw cmd-33 calibration packet to confirm offsets, then re-enable board LEDs.

- LIGHTING = HOST ENGINE (REVERTED firmware-native switch — user wants multi-color striation/twinkle + custom zones KEPT). Animated effects route through start_multicolor (host per-key engine, full palette); only Static/Full-RGB use firmware set_light. Rain/Comet/Tide + striOrient control + custom zones all RESTORED. effects.py gens cover every LIGHT_MODES id.
  FIRMWARE DATA (reference, to make host effects accurate — driver decoded/deobfuscated.js refreshColorView ~2138, setLightValue dec_agreement ~1366): cmd-7 packet = [0]=7,[4]=14,[5]=mode,[6]=bri,[7]=speed,[8-10]=fg,[11-13]=bg,[14]=dir,[15]=fullColor,[16]=power. Mode bytes: static0 breath1 wave2 neon3 radar4 reactive6 cross7 ripple8 twinkle9 custom10 fireworks11 speedres12 autorip14 striation15 aurora16. Dir bytes (index.html 881): right0 left1 up2 down3 spread4 gather5. Per-mode caps kept as FW_MODES (app.jsx) / MODE_CAPS+DIR_OPTS (sections.jsx) for reference, NOT gating UI. NOTE: actual effect ANIMATION lives in keyboard MCU firmware, not the driver JS — can't byte-copy it; host engine reproduces by name. TODO: tune host generators per-effect for fidelity (ask user which look off).

- ACTUATION BUG FIXED (half-presses didn't register): trigger packet (build_trigger) byte layout was correct & matches driver setAnyTriggerValue, BUT the app hardcoded trigger mode=2 which is INVALID → board ignored the whole packet. Correct trigger modes (driver decoded ~3163): 0=fixed actuation point (no RT), 12=rapid trigger single sens, 13=RT separate press/release. Fix: app.jsx sends mode = rtEnabled?13:0; app_web set_trigger_codes default mode=0. VERIFIED on hardware via read-back (cmd33/sub5, parse_trigger_read): set 0.5mm→travel=50 mode0; set RT 1.0mm/0.2/0.3→travel100 i1=20 i2=30 mode13. Trigger unit CONFIRMED 0.01mm (queried cmd33[4]=24[5]=4: unit_num=1, maxTravel=340=3.4mm, minTravel=8). TRIGGER_UNIT_MM=0.01 correct.
- EFFECTS verified frame-by-frame (host engine): all 17 animate+multicolor+valid. Fixed striation (step rate 0.4→2.0+speed*5, was too slow to animate) and fireworks (spawn 0.04→0.22+speed*0.35 + seed first burst, was rendering empty frames). reactive/static intentionally static (press-driven).

- EFFECTS REVIEW (live, on hardware via play_effect.py — kept as a tool: `venv-web/bin/python play_effect.py <effect> [speed] [dir] [orient]`, close app_web first). Outcomes in effects.py:
  - FPS = 120 (board sustains ~1200fps writes, 0.14ms/write — HID not the bottleneck; motion is time-based so unaffected).
  - CROSS = press-reactive, lights exactly the pressed key's ROW+COLUMN (idx//22, idx%22) then fades.
  - FIREWORKS = press-reactive explosion (burst expands from pressed key). FRENZY = NEW mode = the old automatic-burst fireworks (added to LIGHT_MODES, MODE_CAPS, FW_MODES byte 11).
  - STRIATION = shooting stars: bright heads fly horizontally across rows w/ fading trails, random palette colors over bg (dir 1 = R→L). (NOT the old stripes/slopewave.)
  - AUTORIP = auto ripple: vertical wavefronts born at CENTER travel outward both sides across board, wide (~9-key band) + slow by default ("rock in pond"); dir picks axis/origin (0 h-out,1 h-in,2 v-out,3 v-in).
  - TIDE = _g_slopewave (diagonal wave). SPEEDRES = press/click-rate fill, builds fast per press, recedes when idle; dir sets origin (↑ = from bottom up).
  - Press-reactive modes (need live travel via _ensure_reactive + play_effect reader): reactive, ripple, speedres, cross, fireworks.
  - PALETTE: default colors ~2 tones darker (app default #a6143a; addSlot seeds #663390/#009fa6/#a62848/#a66e14); palette is CLEARABLE to empty ("Clear all" btn) + persists per profile.
  - CALIBRATION: lighting now KEPT running during calibration (no longer killed); calib_reader (blocking read) coexists with fx engine.

STILL TODO:
- #8 (DEFERRED by user) FINAL: package AppImage named **"Aether"** (NOT "Aether HE Keyboard Hub") with icon.
