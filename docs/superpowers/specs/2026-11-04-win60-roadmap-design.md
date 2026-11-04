# WIN60 "Take It Up a Notch" Roadmap — Design

Date: 2026-11-04. Owner: the user (MrWhosNexus). Decisions come from the user's
answers on 2026-11-03 ("we know what we want done") plus calls made by Claude,
marked **[Claude's call]**. This is the spec every phase plan argues from.

## Intent

The Aula WIN60 HE streams how deep every key is pressed (0.01 mm steps, 0–3.40 mm).
Aether only uses that for the tester and press-reactive effects. The user wants the
keyboard to *do more* with it, and wants Aether to feel like a central dashboard for
the board rather than a settings panel. Typing analytics is the user's stated priority.

## Ground truth (verified on the user's board, 2026-11-03)

- Board: Aula Win60 HE, 2E3C:C365, vendor interface 2, usage page 0xFF1B, 61 keys,
  60% layout (**no F-row**: number row, QWERTY, home, shift, bottom).
- Info report: is_dead_band, is_custom_light, is_music_rhythm, is_any_key_calibration
  true; is_gamepad, is_rs, is_rkrt, is_high_precision false. Travel 0.08–3.40 mm.
- Travel stream: event-driven; on release the last report is usually mid-travel
  (handled in `device_state.LiveReader`, commit 839a076: a key whose last report moved
  up is cleared after `RELEASE_SILENCE_S = 0.15`). Frames arrive in bursts; gaps up to
  ~140 ms between frames of one moving key.
- The user's setting: fixed actuation 0.80 mm on all keys, dead band 0.04/0.05. They
  found 0.10 mm too sensitive and 1.70 mm (factory) too stiff.
- Host effect engine: `effects.py`, 60 fps cap (USB saturation above that).

## Global constraints (every phase)

- Windows is the shipping target; nothing may break Linux (guard Windows-only code by
  `sys.platform`, degrade to "unavailable" elsewhere).
- **No HID writes during development or tests.** Never run the app against the
  keyboard. Use fakes (patterns: `tests/test_travel_release.py`, `tests/test_socd_clear.py`).
  Hardware checks go into `docs/HARDWARE_TEST_CHECKLIST.md` under a new
  `## Roadmap 2026-11-04` heading, for the user.
- No push, merge into other branches, tag or release. Work only on the overnight
  session's own branch/worktree.
- Python: `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe`. Full suite:
  `<python> -m pytest -q -p no:cacheprovider` (683 passing at branch start); must pass
  after every phase. JSX changes need `<python> ui\runtime_src\build_runtime.py`; commit
  regenerated `ui/index_runtime.html` + `ui/runtime_src/build/*.js` only in phases that
  changed JSX (line-ending-only diffs must not be committed).
- UI: edit `ui/runtime_src/src/*.jsx` / `ui/runtime_src/workspaces/*.jsx`; never `vendor/`.
  No raw-HTML sinks (CI guard in `validate-submissions.yml`). Match the existing look
  (Tailwind classes, CSS vars `--text`, `--accent`, `--line`, `--ink`).
- New Python dependencies only where a phase names them; add to `requirements.txt` with
  a platform marker and to `AetherHE.spec` hidden imports if needed.
- Capability gating through `data/board_registry.json` like `macros`/`advancedKeys`;
  enabled for `aula-win60-he`; host-only features may be board-agnostic.
- **Privacy anti-goal:** Aether must never become a keylogger. No phase may store or
  transmit key *sequences*, text, or per-keystroke timestamps. Aggregates only.
- Bridge methods return `{"ok": bool, ...}` and never raise to JS (follow `Api._fail`).
- Do not touch the security-fix targets (a separate scheduled run owns them on branch
  `claude/missing-broken-audit-cda685`): `service/server.py`, `updater.py`,
  `Api.open_submission_url`, `.github/workflows/board-bot.yml`, the Pillow pin.

## Phases (in order; each depends only on earlier ones)

### Phase 1 — Live-depth telemetry foundation
Always-on (while connected) consumer of the travel stream keeping **per-key aggregates**.
- New `telemetry.py`: per device index — press count, bottom-out count (peak ≥ 3.30 mm),
  peak-depth histogram in 0.1 mm bins (0–3.4), "shallow attempts" (peak > 0.15 mm but
  below the key's actuation point: a press the board did not register), "barely-over"
  presses (peak within 0.10 mm above actuation), running mean time-to-peak. A press = a
  rising run of reports ending when LiveReader clears the key.
- Daily aggregates in `<user_data_dir>/stats/YYYY-MM-DD.json`, written at most once a
  minute and on disconnect/exit; keep 90 days. Settings toggle "Collect key statistics"
  (default ON) + "Clear statistics". [Claude's call]
- A LiveReader owner `"telemetry"` (see `Api._reader_users`) so the reader stays on while
  connected; coexists with `_reader_paused()` read-backs, the analog tab, reactive effects
  and the gamepad. Fed from the reader thread via a cheap hook — never a second HID reader.
- Bridge: `get_stats(days=1)`, `clear_stats()`, `set_stats_enabled(on)`.

### Phase 2 — Pressure lighting
- New host effect `"pressure"`: each key's colour/brightness follows its live depth
  (0 → background, actuation point → palette midpoint, bottom-out → full), ~120 ms decay
  after release so it never sticks. Grouped with the press-reactive effects.
- Travel Test polish: draw each key's actuation point on the tester so the user can dial
  in actuation visually (from `perKeyActuation`).

### Phase 3 — Game detection + per-game profiles (Discord-style)
- New `games.py`. Detection = running processes matched against (a) Discord's public
  detectable list `https://discord.com/api/v9/applications/detectable` (HTTPS, cached in
  `<user_data_dir>/games/detectable.json`, refreshed weekly; works offline with the cache
  or none; cap 5 MB, validate shape, render names as text only), using each entry's
  `win32` executables (match trailing path segments case-insensitively, e.g.
  `valorant/valorant.exe`), and (b) user-added executables. Enumerate processes via
  ctypes Toolhelp32 + `QueryFullProcessImageNameW` — **no new dependency** [Claude's call].
  Poll every 3 s; the foreground game wins when several run (`GetForegroundWindow` → PID).
- Per-game profile = game id → existing `settings.json` profile id. On a mapped game
  starting/gaining focus: switch to that profile and **apply it to the board** (actuation/
  RT to all keys, SOCD pairs, lighting) through existing Api paths; on exit, revert to the
  previous profile. Debounce 5 s so alt-tab doesn't hammer the flash. Toggle "Auto-switch
  profiles for games" (default ON once any game is mapped).
- Settings section "Games": detected-now indicator, mapped games, add from running
  processes, map to profile. Tray tooltip shows the active game.
- Bridge: `games_status()`, `list_running_games()`, `set_game_profile(game_id, profile_id|None)`,
  `add_custom_game(exe_path, name)`, `refresh_detectable()`.

### Phase 4 — Typing analytics + actuation auto-tune (PRIORITY)
- Views from Phase 1 data: presses per key (heatmap on the on-screen board), presses per
  day (14 days), bottom-out %, average peak depth, shallow attempts / barely-over per key.
- Auto-tune = **suggestions only**, never automatic writes. Per key or group (WASD/arrows,
  letters, mods, space): if shallow attempts > 5 % of presses, suggest shallower actuation
  toward the 10th-percentile peak minus 0.1 mm; if barely-over > 15 % on letter keys, flag
  likely accidental presses and suggest 0.1–0.2 mm deeper. Clamp to 0.08–3.40 and never
  below 0.30 mm [Claude's call]. Need ≥ 200 presses before suggesting. "Apply suggestion"
  uses the normal Actuation Apply path with read-back.
- Bridge: `get_analytics(days)`, `get_tune_suggestions()`.

### Phase 5 — Central dashboard
- New default landing workspace "Dashboard" (first in the nav; all existing tabs stay).
  Hero keyboard with a toggle: today's heatmap / live depth / actuation map. Tiles:
  connection + poll rate, active profile + detected game, actuation summary (read-back),
  today's presses / bottom-out % / shallow attempts, top-3 auto-tune suggestions with
  Apply, current lighting effect with quick switch, status-on-keys toggles (Phase 6).
  Fits the existing minimum window (1160×800).
- Design-heavy: the plan author picks the layout, but it must read as one coherent page
  in the existing visual language, not a grid of unrelated widgets.

### Phase 6 — Status on keys
- An **overlay layer** in the effect engine composited over any effect (or static):
  CPU load bar on the number row (1–0, ten steps), RAM bar on the QWERTY row, GPU load on
  the home row when `nvidia-smi` exists (else hidden), Pomodoro (25/5 default, progress on
  the shift row, pulse at phase change), and a generic `flash(color, ms)`. CPU via ctypes
  `GetSystemTimes`, RAM via `GlobalMemoryStatusEx` (no psutil) [Claude's call]; 1 s samples.
- Out of scope (follow-ups): temperatures (admin sensors) and Discord/notification pings
  (Windows notification-listener permission).
- Each overlay toggleable; persisted per profile.

### Phase 7 — Aether's own music visualizer
- Not the vendor's "Musical Rhythm". Windows WASAPI **loopback** capture of the default
  output via `soundcard`, FFT with `numpy` [Claude's call — the only phase adding
  dependencies]. 14 log-spaced bands → 14 columns, height across 5 rows, effect palette,
  background pulse on beats (energy flux). New effect `"music"`; graceful "no audio
  device" state. Target < 60 ms audio→LED, < 5 % of one core at 60 fps.

### Phase 8 — Integration
- Full suite, UI rebuild, PyInstaller + Inno Setup build into the session worktree's
  `dist\` (do NOT install), pip-audit of the build venv from a throwaway venv, and a
  whole-branch review (correctness, the privacy anti-goal, no HID writes in tests).

## Research track (parallel, read-only) — WIN60 DKS / Mod-Tap / Toggle decode
- Source-only decode of the vendor driver in `docs/context/hed-aulacn-raw/driver_deobf/`
  (UI: `wmIndex.deobf.js` — `curDksKey`, `curMtKey`, `curTglKey`, `dksEdit`,
  `dksTriggerDiv`; packet layer: `agreement.deobf.js`) into
  `docs/context/aula-win60-advanced-keys-decode.md`: command bytes, table layout, paging,
  which info-report feature bit gates it (this board reports is_rs/is_rkrt false — say
  whether DKS depends on either), and a comparison with the MINI 60 HE PRO path in
  `protocol_mini60.py`.
- A hardware capture checklist for the user (what to click in the vendor web driver,
  which frames to capture) and proposed `protocol.py` builder signatures with golden-frame
  tests marked SOURCE-ONLY. **No device writes. Nothing wired into the drive path** —
  builders may land only behind a `"wip"` capability.

## Backlog (scheduled later, not built now)
- **Analog stick / mouse from keys** (user: "a project we can schedule"): software analog
  movement (WASD depth → stick or mouse speed) via ViGEm / uinput; needs its own design
  pass; adds latency, so single-player first.
- **What reset the board to factory actuation** (1.70 mm): suspect the poll-rate restart.
  Hardware test with the user (write one key, change poll rate, read back).
- Smoother effects above 60 fps (dirty-page streaming) — not selected yet.

## Coordination ("shared memory")
- `docs/superpowers/roadmap-status.md` is the team's shared notes. Every agent reads it
  first and appends a dated entry when done (≤ 15 lines): commits, decisions later phases
  must respect, gotchas, items for the user.
- Every agent keeps its task bounded; if its context approaches ~400k tokens it stops,
  commits what is green, writes its status entry saying exactly where it stopped, and reports.
