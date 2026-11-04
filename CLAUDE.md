# Aether — Aula WIN60 HE Controller

Desktop app to control the **Aula Win60 HE** Hall-effect keyboard (VID `0x2E3C`,
PID `0xC365`) over raw HID. The UI is the exact "Claude Design" React/Tailwind
prototype rendered natively via **pywebview**; there is no WebHID, so a JS bridge
calls into a Python `Api` (exposed as `window.pywebview.api`).

Built and verified on **Linux/CachyOS**. A **Windows port** is in progress (see
"Porting to Windows" below). Detailed engineering notes are in `docs/context/`
(carried over from the dev sessions) — read those for protocol/effect specifics. Latest release
record: `docs/context/aula-win60-v0.5.0-tray-macros-review.md`; hardware checks still owed:
`docs/HARDWARE_TEST_CHECKLIST.md`.

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
  `CalibrationReader`. The LiveReader drains and DISCARDS every non-travel report, so any driver
  read-back (remap/switch/mode-0 actuation/macros) must run inside `Api._reader_paused()`.
  Calibration parks the shared reader (CalibrationReader must be the only drain).
- `telemetry.py` — key statistics (roadmap Phase 1): per-key, per-day aggregates from the live travel stream (`LiveReader.on_sample`), owner `"telemetry"` keeps the shared reader on while connected; files `<user_data_dir>/stats/YYYY-MM-DD.json`, 90 days; aggregates only, never sequences or timestamps. Each press is filed under the actuation its key had (day-file key "idx@act", "idx" = unknown); load_day/aggregate merge them, load_day_buckets/recent_buckets keep them apart.
- `analytics.py` — typing analytics + actuation auto-tune (roadmap Phase 4), pure functions over telemetry buckets. Bridge `get_analytics(days)` / `get_tune_suggestions()` (read-only). Suggestions use ONLY presses at each key's current read-back actuation (14 days, >= 200 presses per key or group; groups WASD / letters / mods / space by design code), shallow > 5 % -> p10 - 0.1 mm (>= 0.30), barely > 15 % on letters (not WASD) -> +0.1/0.2 mm. Never written automatically: the Analytics tab's Apply is app.jsx `writeActuation` (set_trigger_codes + verify_actuation). UI: `ui/runtime_src/workspaces/analytics.jsx` (tab gated on registry `keyStats`), reusable pieces on `window.AetherAnalytics`.
- `ui/runtime_src/workspaces/dashboard.jsx` — the Dashboard (roadmap Phase 5), first and landing tab (a remembered tab wins after one intro launch: settings `globals.dashboardIntro`). ONE composed page on the 1480 x 900 canvas (app.jsx renders `DASHBOARD_PAGE` instead of the widget desktop): hero keyboard (Heatmap = today's AetherAnalytics heat / Live depth = `ctx.setLiveView` holding the Travel Test stream / Actuation = read-back), rail (connection + poll, profile + `ctx.games`, actuation summary), band (today, `SuggestionList limit={3} compact`, lighting quick switch via `ctx.setPattern`). No new bridge; it calls only Phase 6's `get_overlays` / `set_overlay` and hides "Status on keys" until they exist. Pure helpers on `window.AetherDashboard` are tested in node.
- `effects.py` — host-driven **per-key** lighting engine (firmware effects only hold one
  fg+bg, so multi-color animations are streamed from the host via cmd 9). `FPS = 60`: a
  120 bump was tried and reverted because it saturated the USB pipe. Per-board caps come
  from `lighting.hostEngineMaxFps` in the registry (MINI 60 HE PRO measured at 28).
  Optional engine sources: `get_depths` and `get_actuation` (set by `Api._ensure_reactive`).
- `music.py` — Phase 7 music visualizer: WASAPI loopback of the default output (soundcard) -> 1024-pt FFT (numpy) -> 14 log bands 40 Hz-16 kHz -> auto-gain levels + energy-flux beats. Windows only; numpy/soundcard are imported lazily on the capture thread; without them `music_status()` says why and the effect idles. The engine starts/stops `MusicSource` with the zones (capture runs only while a `music` zone runs). Audio is processed in memory only, never recorded.
- `overlays.py` — "status on keys" (roadmap Phase 6): CPU bar (number row 1-0), RAM bar (Q-P), GPU bar (home row, `nvidia-smi` only), Pomodoro 25/5 progress (shift row, whole-board pulse at each phase change) and `flash(color, ms)`, composited by `effects.PerKeyEffectEngine.overlay` onto whatever the engine streams (fixed colours, opaque bars, no extra frame rate). 1 s sampler thread (ctypes `GetSystemTimes` / `GlobalMemoryStatusEx`, no psutil), only while a sensor overlay is on and the keyboard handle is open. Per-profile flags live in `settings.json` top-level `overlays` (Aether-owned; optional `pomodoro.workMin/breakMin`). Over firmware lighting (static / Full-RGB / per-key paint / off) `Api.set_light` / `set_custom_colors` record the UI's call and a host-engine "carrier" reproduces it; the last overlay going off re-sends the firmware lighting once. Bridges: `get_overlays` / `set_overlay` (the dashboard tile's contract), `flash`. Tests inject sensors and the `nvidia-smi` runner; nothing here touches HID.
- `gamepad.py` — Linux uinput virtual gamepad (LINUX ONLY; self-disables elsewhere).
- `tray.py` — tray residency (pystray, Windows): closing the window HIDES it and the effect
  engine keeps streaming; the Settings "Start minimized" toggle (settings.json `startMinimized`,
  or `--minimized`) starts hidden. Right-click menu: Open / Hide window / Mini mode / Exit. The
  icon opens a mini-mode panel (`ui/tray_panel.html`: Open / effect grid / speed slider / Exit). The panel
  never drives the board: it sets `pattern`/`speed` in the React app via `window.__aetherTraySet`
  and reads state from `Api.tray_sync` (pushed by app.jsx). Without pystray, close quits as before.
- `games.py` — game detection (Windows; ctypes Toolhelp32, no dependency): Discord's public detectable list
  (HTTPS, 5 MB wire cap, cached `<user_data_dir>/games/detectable.json`, weekly) + user-added programs, matched by
  trailing path segments; `GameSwitcher` debounces 5 s and reverts on exit; `GameService` owns settings.json `games`
  and the 3 s poll thread (`main()` starts/stops it via `Api._start_games/_stop_games`; private `Api._games`). Python
  decides, `app.jsx` polls `games_status()` and switches the profile, then `Api.apply_profile_to_board` writes
  actuation/RT to all keys + SOCD (skipped when `_act_mm`/`_trig_mode`/`_socd_last` show the board already has it;
  deferred to the next connect while offline). Only candidate processes are opened; nothing about other processes
  is kept or sent. Tray tooltip names the detected game.
- `single_instance.py` — Windows named mutex + "show" event: a second launch pokes the running
  instance (window comes up) and exits. main() also gives WebView2 its OWN profile folder
  (`%LOCALAPPDATA%\AetherHE\webview`): the pywebview default is shared by every build, and a
  second process holding it → WebView2 init fails with HRESULT 0x8007139F (blank window).
- `ui/runtime_src/src/{app,sections,keyboard}.jsx` — the edited UI; `vendor/` is unmodified.

## HID protocol cheat-sheet (verified on hardware)
- **Lighting (cmd 7)**: `[0]=7,[4]=14,[5]=mode,[6]=bri,[7]=speed,[8-10]=fg,[11-13]=bg,[14]=dir,[15]=fullColor,[16]=power`.
  Mode bytes (VENDOR-CORRECT, from hed.aulacn.com `config__language.json` lightMode<N>
  + the board's own readLightList): static0 breath1 wave2 neon3 radar4 reactive6
  **aurora7** ripple8 twinkle9 custom10 **cross11** speedres12 autorip14 striation15
  **fireworks16** (5 and 13 unused; 100 = vendor's host-side Musical Rhythm, not ported).
  An earlier table had 7/11/16 swapped (cross7 fireworks11 aurora16) — that was wrong.
  Direction bytes: right0 left1 up2 down3 spread4 gather5. Side-light channel = same
  layout on **cmd 8** (list via cmd 2); the Win60 reports an EMPTY side list (no side LEDs).
- **Per-key RGB (cmd 9)**: 396-byte table streamed in 54-byte pages (host effect engine).
- **Actuation/trigger (cmd 33)**: travel/RT. Trigger MODE: **0 = fixed actuation point**,
  12 = rapid-trigger single, 13 = RT separate press/release. Unit = **0.01 mm**, min 0.08, max 3.4 mm.
  Travel-test stream = cmd33 frames with body[5]==0x01 (`r[1]==33,r[6]==1`; the `r[5]==5` the reader
  matches is the payload LENGTH byte, not a sub-command — sub 0x05 is the per-key config read;
  `idx=r[7]*22+r[8],depth=(r[9]|r[10]<<8)/100` — offsets confirmed correct by capture).
- **Calibration**: cmd33 sub `r[6]∈{8,15}`; `r[7]==1` → bitmask `r[8:30]` (idx=bit*22+col) of
  calibrated keys; `r[7]==0` → complete.
- **Macros (cmd 25)**: 10 slots x 256 B, paged 4x58+24 (`[1]=slot` write, `slot|0x80` read; never-
  written slot reads all 0xFF, vendor writes all-0x00 for unused). Header `[slot, playMode, lenBE16,
  countBE16, 0, 0]` — byte 1 is the vendor macroType (0 once, 1 repeat N; 2 toggle / 3 hold UNVERIFIED),
  NOT the slot repeated. Events `[hid, 0x10 down|0x00 up, delayAfterBE16]`; Aether/base-driver tuples are
  `(delay_BEFORE_ms, hid, is_down)` and protocol.py shifts by one at the wire (deobfuscated.js L1244/L505).
  A key fires a macro via base-keymap entry `[0x10, default_hid, slot, 0]` (cmd 24) — `Win60Driver.bind_macro`
  is a base-layer RMW (`protocol.compose_base_keymap`: zero read-back = firmware default) + Fn replay.
  Api: `list_macros/read_macro/save_macro/delete_macro/bind_macro/unbind_macro`; names live in
  settings.json `macroNames`. UI: `ui/runtime_src/workspaces/macros.jsx` (tab gated on registry `macros`).
- **Device interface**: prefer usage_page `0xFF1B`; Linux reports 0x0 so it falls back to the
  highest interface_number (iface 2). Windows usually reports the usage page correctly.

## Effects (host engine, all multi-color over a background, time-based motion @60fps)
Press-reactive (need live travel): **reactive, ripple, speedres, cross, fireworks, pressure**.
Notable behaviors set during review: **Cross** = press lights that key's exact row+column;
**Fireworks** = press-triggered explosion; **Frenzy** = the old automatic bursts;
**Striation** = shooting stars across rows w/ fading trails; **Auto-Ripple** = wavefronts
from center outward, wide+slow ("rock in pond"); **Speed-Respond** = click-rate fill;
**Pressure** = each key's colour follows its live depth (background -> palette midpoint at that
key's actuation point -> full at bottom-out), instant attack, 120 ms fall; per-key actuation
comes from `Api._act_mm` (read-back + successful writes), unknown keys use the median, else
1.70 mm.
**Music** = 14 band columns, height over the rows, palette bottom->top, background pulse on beats (not press-reactive: not in `PRESS_REACTIVE`/`HOST_FX_FAST`).
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
