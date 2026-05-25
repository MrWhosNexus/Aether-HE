# Aether — Aula WIN60 HE Controller

Desktop app to control the **Aula Win60 HE** Hall-effect keyboard (VID `0x2E3C`,
PID `0xC365`) over raw HID. The UI is the exact "Claude Design" React/Tailwind
prototype rendered natively via **pywebview**; there is no WebHID, so a JS bridge
calls into a Python `Api` (exposed as `window.pywebview.api`).

Built and verified on **Linux/CachyOS**. A **Windows port** is in progress (see
"Porting to Windows" below). Detailed engineering notes are in `docs/context/`
(carried over from the dev sessions) — read those for protocol/effect specifics.

## Run
```
python -m venv venv-web && venv-web/bin/pip install -r requirements.txt   # (Win: venv-web\Scripts\pip)
venv-web/bin/python app_web.py                                            # the app
```
`app_web.py` is the real app. `main.py` is a legacy CustomTkinter UI (ignore unless asked).
The UI is prebuilt into `ui/index_runtime.html` by `ui/runtime_src/build_runtime.py`
(React precompiled offline with bundled Babel). Rebuild after editing `ui/runtime_src/src/*.jsx`:
```
venv-web/bin/python ui/runtime_src/build_runtime.py
```

## Architecture
- `app_web.py` — pywebview shell + `Api` HID bridge (connect, set_light, set_trigger_codes,
  set_socd, calibrate, open_analog/read_live, start_multicolor, set_custom_colors, gamepad…).
- `protocol.py` — HID packet builders, reverse-engineered from the official driver
  (`driver_src/dec_agreement/deobfuscated.js`). Report ID 1; 64-byte reports.
- `device_state.py` — `KeyMap` (key index↔design-code↔xy), `LiveReader` (travel-test stream),
  `CalibrationReader`.
- `effects.py` — host-driven **per-key** lighting engine (firmware effects only hold one
  fg+bg, so multi-color animations are streamed from the host via cmd 9, ~120fps).
- `gamepad.py` — Linux uinput virtual gamepad (LINUX ONLY; self-disables elsewhere).
- `ui/runtime_src/src/{app,sections,keyboard}.jsx` — the edited UI; `vendor/` is unmodified.

## HID protocol cheat-sheet (verified on hardware)
- **Lighting (cmd 7)**: `[0]=7,[4]=14,[5]=mode,[6]=bri,[7]=speed,[8-10]=fg,[11-13]=bg,[14]=dir,[15]=fullColor,[16]=power`.
  Mode bytes: static0 breath1 wave2 neon3 radar4 reactive6 cross7 ripple8 twinkle9
  custom10 fireworks11 speedres12 autorip14 striation15 aurora16. Direction bytes:
  right0 left1 up2 down3 spread4 gather5.
- **Per-key RGB (cmd 9)**: 396-byte table streamed in 54-byte pages (host effect engine).
- **Actuation/trigger (cmd 33)**: travel/RT. Trigger MODE: **0 = fixed actuation point**,
  12 = rapid-trigger single, 13 = RT separate press/release. Unit = **0.01 mm**, min 0.08, max 3.4 mm.
  Travel-test stream = cmd33 sub5 (`r[1]==33,r[5]==5,idx=r[7]*22+r[8],depth=(r[9]|r[10]<<8)/100`).
- **Calibration**: cmd33 sub `r[6]∈{8,15}`; `r[7]==1` → bitmask `r[8:30]` (idx=bit*22+col) of
  calibrated keys; `r[7]==0` → complete.
- **Device interface**: prefer usage_page `0xFF1B`; Linux reports 0x0 so it falls back to the
  highest interface_number (iface 2). Windows usually reports the usage page correctly.

## Effects (host engine, all multi-color over a background, time-based motion @120fps)
Press-reactive (need live travel): **reactive, ripple, speedres, cross, fireworks**.
Notable behaviors set during review: **Cross** = press lights that key's exact row+column;
**Fireworks** = press-triggered explosion; **Frenzy** = the old automatic bursts;
**Striation** = shooting stars across rows w/ fading trails; **Auto-Ripple** = wavefronts
from center outward, wide+slow ("rock in pond"); **Speed-Respond** = click-rate fill;
**Rain** = Matrix curtain (dense columns, bright heads, long tails). Per-frame spawners
(rain/twinkle/frenzy) scale by `_SPAWN_NORM` so density is FPS-independent.

## Porting to Windows (current focus)
Reference repo for the Windows build: https://github.com/MrWhosNexus/WIN60-HE-Mod.git
- `requirements.txt` is already cross-platform safe (evdev is `sys_platform=="linux"` only;
  pywebview added). `pip install` works on Windows.
- **Gamepad** (`gamepad.py`) is Linux uinput — needs a port to **vgamepad + ViGEmBus** on Windows.
  It already degrades gracefully (feature disabled) when evdev is absent, so the app still launches.
- **udev rules** (`99-*.rules`) are Linux-only — not used on Windows.
- **HID interface selection** (`aula_device.find_vendor_interface`) should work on Windows via the
  `0xFF1B` usage-page match, but verify it opens the vendor collection (not the keyboard HID).
- Lighting + actuation + effects are pure Python and should be portable as-is.
