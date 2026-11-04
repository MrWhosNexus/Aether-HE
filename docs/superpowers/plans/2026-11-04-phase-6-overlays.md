# Phase 6: Status on Keys (Overlays) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the computer's state on the keyboard: a CPU load bar on the number row, a RAM bar on the QWERTY row, a GPU load bar on the home row (NVIDIA only), a Pomodoro progress bar on the shift row with a pulse at each phase change, and a generic `flash(color, ms)`. Each overlay is toggleable per profile and works over any lighting, including static and firmware modes.

**Architecture:** One new module `overlays.py` holds everything pure or host-side: bar maths and colours, the Pomodoro clock, `OverlayLayer` (composites onto the frame the effect engine is about to stream, through one new `engine.overlay` hook), the 1 s `Sampler` (CPU via ctypes `GetSystemTimes`, RAM via `GlobalMemoryStatusEx`, GPU via `nvidia-smi`), per-profile preferences in `settings.json`, and `OverlayManager` (toggles, availability, sampler lifecycle, the `get_overlays` rows). `app_web.Api` adds `get_overlays` / `set_overlay` (the Phase 5 contract), `flash`, and a "carrier": when an overlay is on but the UI's lighting is a firmware mode, the host engine is switched on to reproduce it, and switched off (firmware lighting re-sent once) when the last overlay goes off. The dashboard chip shows the Pomodoro countdown.

**Tech Stack:** Python 3 stdlib + ctypes (no psutil, no new dependency), pytest, the existing React/Tailwind UI (one helper in `dashboard.jsx`).

**Spec:** `docs/superpowers/specs/2026-11-04-win60-roadmap-design.md` ("Phase 6" and "Global constraints"). Also read `docs/superpowers/roadmap-status.md` (the Phase 5 entry defines the bridge contract) and `docs/superpowers/plans/2026-11-04-phase-5-dashboard.md` (the "Status on keys" tile).

**Prototype:** every code block and test below was run against the real tree on 2026-11-04 (full suite **1103 passed, 14 skipped**; `node --check` ok on the rebuilt `ws_dashboard.js`) and then reverted. Copy it verbatim; the only things left to the implementer are the small anchored edits that say so.

## Global Constraints

- Windows is the shipping target; nothing may break Linux. Windows-only code (`ctypes.windll`) is guarded by `sys.platform`; Linux gets optional `/proc` readers; anything unreadable degrades to "unavailable" (never an exception).
- **NEVER write to the keyboard, open HID, or run the app against it. Fakes only.** No test starts `nvidia-smi` or any other process: the GPU probe takes an injected `runner`, and every test file that builds an `Api` or a manager patches `overlays._run_nvidia_smi` to fail loudly.
- No push, merge into other branches, tag, release, or install. No network during development or tests.
- Python: `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe` (written `<py>` below). Full suite: `<py> -m pytest -q -p no:cacheprovider` (**1009 passed, 14 skipped** at the start of this phase); green at every commit.
- JSX changes need `<py> ui\runtime_src\build_runtime.py`; commit `ui/index_runtime.html` + only the `ui/runtime_src/build/*.js` files with real diffs (`git diff --ignore-cr-at-eol --stat`; `git checkout -- <file>` every build file that shows only in plain `git diff --stat`). `node --check` every touched build file.
- UI: edit `ui/runtime_src/src/*.jsx` / `ui/runtime_src/workspaces/*.jsx`, never `vendor/`. No raw-HTML sinks. Every `/*` must close (`tests/test_ui_sources.py`).
- Source files may be CRLF (core.autocrlf). If the Edit tool cannot match a multi-line `old_string`, apply the same replacement with a short Python snippet (`open(p, encoding="utf-8", newline="")`, replace on `\n`-normalised text, convert back to `\r\n` if the file had them, write with `newline=""`).
- No new Python dependencies (no psutil). New module `overlays.py` must be in the Flatpak `cp` list (`tests/test_packaging.py` enforces it); PyInstaller finds it through `import overlays`.
- **Privacy anti-goal:** never store or transmit key sequences, text, or per-keystroke timestamps. Overlays read system load and the clock only; the one new stored item is the per-profile on/off flags (and optional Pomodoro minutes) under the top-level `overlays` key of `settings.json`.
- Bridge methods return `{"ok": bool, ...}` and never raise to JS (`Api._fail`).
- Do NOT touch `service/server.py`, `updater.py`, `Api.open_submission_url`, `.github/workflows/board-bot.yml`, or the Pillow pin.
- Implementer: `git add` only the files you changed, never `git stash`, end every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The user is asleep: "If it doesn't require my intervention write the code save items that require me for later." Do not stop to ask; queue user items in the status file.
- Context limit: if your context approaches ~400k tokens, stop: commit only what is green, append a status entry to `docs/superpowers/roadmap-status.md` saying exactly where you stopped, and return.

## Design decisions (resolved; do not re-decide)

1. **Where it lives.** `overlays.py` (pure maths + threads, no HID). `effects.PerKeyEffectEngine` gains one attribute, `overlay` (None by default), and calls `overlay.apply(frame, t_start)` after the zones are drawn and before `last_frame` is set, inside `try/except`: a broken overlay can never stop the stream, and the in-app keyboard mirror shows the overlays too. The frame loop, pacing and `FPS` cap are untouched, so overlays cannot raise the frame rate; only colours change, and the driver's page diff cache sends only the pages that changed.
2. **Rows (design codes, left to right).** CPU = number row `1..0` (10 keys); RAM = `Q..P` (10); GPU = home row `A..;` (`A S D F G H J K L Semi`, 10); Pomodoro = the whole shift row (`LShift Z..Slash RShift`, 12). A bar is drawn **opaque** (it replaces the effect on those keys): lit keys in the load colour, unlit keys in a near-black track `(14, 14, 22)`. Blending over a busy effect was rejected: a half-transparent bar disappears into a rainbow wave. The boundary key lights partially (`bar_levels`), so ten keys give a smooth ten-step bar. No reading yet = all track.
3. **Colours are fixed, not the effect palette** (readable on every palette): CPU and GPU ramp green `(0,210,80)` -> amber `(255,170,0)` at 65 % -> red `(255,30,30)` at 90 %; RAM has its own ramp cyan `(0,170,255)` -> violet `(110,80,255)` at 75 % -> magenta-red `(255,40,120)` at 92 % because a normal desktop sits at 60-80 % RAM and an alarm colour there would be noise. Pomodoro: work `(255,80,40)`, break `(0,220,120)`; the fill is the elapsed fraction of the current phase.
4. **Compositing order (later wins):** effect frame -> CPU, RAM, GPU rows -> Pomodoro row -> flashes. Rows never overlap. A flash blends every key toward its colour with alpha `1 - age/ms` (linear fade); colour and duration are clamped (`50..5000` ms), at most 8 live flashes.
5. **Pomodoro** is on/off: turning it on starts a repeating 25 / 5 minute cycle (minutes overridable by hand-editing `settings.json` `overlays.pomodoro.workMin` / `breakMin`, clamped 1..180 / 1..60; no UI for that). No threads: `Pomodoro.state(now)` is a pure function of the clock. Turning it off and on restarts the cycle; switching to a profile that also has it on keeps it running. **Phase change = a whole-board flash in the new phase colour, 700 ms**, and only when the change is less than 1.5 s old (a laptop that slept through the change does not pulse on wake).
6. **Sampling.** `GetSystemTimes` (idle, kernel+user; kernel includes idle) and `GlobalMemoryStatusEx.dwMemoryLoad` via ctypes on Windows; `/proc/stat` and `/proc/meminfo` on Linux (optional, tested by parsers); anything else or any failure -> `None` -> the overlay is "unavailable: <reason>". One daemon thread, 1 s ticks, started only while a sensor overlay (cpu/ram/gpu) is on for the active profile, stopped otherwise. A tick is skipped entirely (nothing read, no process started) while the keyboard handle is closed (`gate`).
7. **GPU.** `shutil.which("nvidia-smi")` once at construction; absent -> the overlay is unavailable with reason "nvidia-smi not found (NVIDIA GPU only)" (the dashboard shows the chip disabled with that reason). Reads run `nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits` with `CREATE_NO_WINDOW`, a 1.5 s timeout, at most once per sampler tick, the busiest GPU wins. Three failed reads in a row switch it off for the session ("nvidia-smi is not answering"). Tests inject the runner.
8. **Overlays over firmware lighting: the "carrier".** On the Win60 every animated effect already runs on the host engine, so overlays simply ride on it. Only static / Full-RGB / per-key paint / lights-off are firmware (or one-shot table) writes, and those cannot show a bar. `Api.set_light` / `set_custom_colors` therefore **record** what the UI asked for (`_light_src`); while an overlay is on they do not write it to the board but start the host engine with `overlays.carrier_plan(...)` (static colour or per-key paint reproduced exactly per key, scaled by the firmware brightness step; Full-RGB approximated by a host rainbow wave; lights-off = black, so the bars still show). When the last overlay goes off, the engine stops and the recorded firmware lighting is re-sent **once** (the same `set_lighting` / `set_per_key_rgb` call the UI would have made). A host effect the UI started is never touched: the layer just draws over it and stops drawing. Turning an overlay on while the board is offline defers the carrier; the UI re-sends its lighting on connect and that call starts it. Side effect to know about: the host stream writes the board's per-key slot 0 like every host effect already does (documented in `Win60Driver.set_per_key_rgb`); the restore rewrites it.
9. **Persistence, per profile.** `settings.json` top-level key `overlays`: `{"profiles": {<profile id>: {"cpu": bool, "ram": bool, "gpu": bool, "pomodoro": bool}}, "pomodoro": {"workMin": .., "breakMin": ..}}`. Aether-owned: the UI's `save_settings` merges around unknown top-level keys, so UI saves never erase it. The active profile is whatever `games_sync` last reported (it already fires on every profile switch and at start-up), falling back to `settings.json` `activeProfile`, then `"p1"`. Switching profile applies that profile's flags (all off for a new profile). A stored choice for an overlay that is unavailable (GPU without nvidia-smi) is kept but not drawn and reported `on: false`.
10. **Bridge contract (Phase 5, exact).** `Api.get_overlays()` -> `{ok, supported, overlays: [{id: cpu|ram|gpu|pomodoro, label, row, on, available, reason, value 0..1|None}], pomodoro: {phase, remaining_s}}`; `Api.set_overlay(id, on)` -> `{ok, id, on}` (refusals are `{ok: False, error}`); neither raises. `supported` is false (and `overlays` empty, so the tile stays hidden) when there is no engine, the driver lacks `host_effects`, or the registry says `hostEngine: false` (the MINI 60 dongle). Additive fields only: the pomodoro row also carries `phase` and `remaining_s`; `value` for it is the phase progress. New bridge `flash(color, ms=600)` -> `{ok}` (needs the engine streaming: a host effect or an overlay).
11. **Out of scope** (spec): temperatures, Discord / notification pings. Not built: a Pomodoro start/pause UI or minutes UI (hand-edit `settings.json`), a lower frame rate while a static carrier is idle (queued as a follow-up; the driver diff cache means an unchanged static frame costs no HID writes).

## Review Focus

Failure modes the spec implies but a happy-path test would miss (each has a test in the task that owns the code):

1. `settings.json` missing, corrupt, hand-edited with junk, or rewritten by a UI save: choices must survive UI saves and junk must be ignored, never trusted or raised (Task 4 `test_malformed_prefs...`, Task 5 `test_the_uis_settings_saves_keep_the_overlay_choices`).
2. `nvidia-smi` absent, hanging, or failing: the overlay is simply unavailable, nothing blocks the sampler longer than the 1.5 s timeout, and a stored "GPU on" never traps the user in a disabled chip (Task 3 probe tests, Task 4 `test_a_probe_that_gives_up...`).
3. A laptop sleeping through a Pomodoro phase change, or the timer being toggled: no stale pulse, no restart on a no-op toggle (Task 2).
4. Keyboard unplugged / handle closed while overlays are on: no sensor reads, no process spawns, no exception; the carrier starts on the UI's next lighting call after reconnect (Task 3 `test_sampler_gate...`, Task 6 `test_offline_board_defers_the_carrier`).
5. A throwing overlay, a throwing sensor, or a profile switch to one with no overlays while the carrier runs: the stream keeps going; the firmware lighting is handed back exactly once (Task 2, Task 3, Task 6).
6. Lights turned off (power off) with an overlay on: the bars still show on black, and "off" is what gets restored (Task 6 `test_lights_off_still_shows_the_bars`).

## File Structure

- Create `overlays.py` — everything pure or host-side (Tasks 1-4, 6).
- Modify `effects.py` — the `overlay` attribute + 6-line hook in `_run` (Task 2).
- Modify `app_web.py` — import, `__init__`/`select_board` attach, `games_sync` follow, `get_overlays` / `set_overlay` / `flash`, carrier, `set_light` / `set_custom_colors` / `start_*` / `stop_multicolor` touch-ups, exit hook (Tasks 5-6).
- Modify `flatpak/io.github.mrwhosnexus.AetherHE.yml` — add `overlays.py` to the `cp` list (Task 5).
- Modify `ui/runtime_src/workspaces/dashboard.jsx` (+ rebuilt `build/ws_dashboard.js`, `ui/index_runtime.html`) — `overlayText` (Task 7).
- Create tests `tests/test_overlays_paint.py`, `_layer.py`, `_samplers.py`, `_manager.py`, `_api.py`, `_carrier.py`, `_ui_sources.py`; modify `tests/test_dashboard_ui_sources.py` (export set).
- Modify `CLAUDE.md` (Task 8).

---

### Task 1: `overlays.py` — layout, colours, bar painting

**Files:**
- Create: `overlays.py` (this task writes the head of the module: imports for the whole module, layout constants, colour and bar maths)
- Test: `tests/test_overlays_paint.py`

**Interfaces:**
- Produces (used by every later task): `IDS`, `LABELS`, `ROW_NAMES`, `ROW_CODES`, `SENSOR_IDS`, `TRACK`, `LOAD_STOPS`, `RAM_STOPS`, `POMO_WORK_RGB`, `POMO_BREAK_RGB`, `PHASE_FLASH_MS`, `PHASE_FLASH_WINDOW_S`, `FLASH_MIN_MS`, `FLASH_MAX_MS`, `FLASH_KEEP`, `RAINBOW`; `unit(v) -> float|None`, `mix(a, b, t) -> (r,g,b)`, `ramp(stops, v)`, `color_for(oid, value) -> (r,g,b)`, `bar_levels(value, n) -> list[float]`, `paint_bar(frame, indices, value, color) -> None`.

- [ ] **Step 1: Write the failing test** — create `tests/test_overlays_paint.py`:

```python
"""Phase 6 / Task 1: overlay layout, colours and bar painting (pure maths)."""
import pytest

import device_state
import overlays


def test_rows_resolve_on_the_win60_keymap():
    km = device_state.KeyMap()
    for oid, n in (("cpu", 10), ("ram", 10), ("gpu", 10), ("pomodoro", 12)):
        idx = km.indices_for_codes(overlays.ROW_CODES[oid])
        assert len(idx) == n == len(set(idx)), oid
        ys = {round(km.by_index[i]["y"] / 10) for i in idx}
        assert len(ys) == 1, f"{oid} must be one physical row"
    rows = [{round(km.by_index[i]["y"] / 10) for i in km.indices_for_codes(overlays.ROW_CODES[o])}.pop()
            for o in ("cpu", "ram", "gpu", "pomodoro")]
    assert rows == sorted(rows) and len(set(rows)) == 4      # number, QWERTY, home, shift


def test_ids_labels_and_row_names_line_up():
    assert overlays.IDS == ("cpu", "ram", "gpu", "pomodoro")
    assert overlays.LABELS["gpu"] == "GPU" and overlays.ROW_NAMES["pomodoro"] == "shift row"
    assert set(overlays.ROW_CODES) == set(overlays.LABELS) == set(overlays.ROW_NAMES)


def test_unit_rejects_garbage():
    assert overlays.unit(0.5) == 0.5
    assert overlays.unit(-3) == 0.0 and overlays.unit(7) == 1.0
    for bad in (None, "x", float("nan")):
        assert overlays.unit(bad) is None


def test_load_ramp_goes_green_amber_red():
    assert overlays.color_for("cpu", 0.0) == (0, 210, 80)
    assert overlays.color_for("cpu", 0.65) == (255, 170, 0)
    assert overlays.color_for("gpu", 0.9) == (255, 30, 30)
    assert overlays.color_for("cpu", 1.0) == (255, 30, 30)
    mid = overlays.color_for("cpu", 0.325)
    assert mid == (128, 190, 40)                              # halfway green -> amber


def test_ram_uses_its_own_ramp_and_is_not_red_at_ordinary_use():
    assert overlays.color_for("ram", 0.0) == (0, 170, 255)
    assert overlays.color_for("ram", 0.75) == (110, 80, 255)
    r, g, b = overlays.color_for("ram", 0.75)
    assert b > r and b > g                                    # still blue at 75 %
    assert overlays.color_for("ram", 1.0) == (255, 40, 120)


def test_bar_levels_give_ten_steps_with_a_soft_edge():
    assert overlays.bar_levels(0.0, 10) == [0.0] * 10
    assert overlays.bar_levels(1.0, 10) == [1.0] * 10
    half = overlays.bar_levels(0.5, 10)
    assert half[:5] == [1.0] * 5 and half[5:] == [0.0] * 5
    soft = overlays.bar_levels(0.35, 10)
    assert soft[:3] == [1.0] * 3 and soft[3] == pytest.approx(0.5) and soft[4:] == [0.0] * 6
    assert overlays.bar_levels(None, 4) == [0.0] * 4
    assert overlays.bar_levels(float("nan"), 4) == [0.0] * 4


def test_paint_bar_replaces_the_row_and_leaves_other_keys_alone():
    frame = {i: (9, 9, 9) for i in range(6)}
    overlays.paint_bar(frame, [1, 2, 3, 4], 0.5, (200, 100, 0))
    assert frame[1] == frame[2] == (200, 100, 0)              # lit keys: the fill colour
    assert frame[3] == frame[4] == overlays.TRACK             # unlit keys: opaque track, not the effect
    assert frame[0] == frame[5] == (9, 9, 9)


def test_paint_bar_with_no_reading_shows_only_the_track():
    frame = {}
    overlays.paint_bar(frame, [5, 6], None, (255, 0, 0))
    assert frame == {5: overlays.TRACK, 6: overlays.TRACK}


def test_bar_edge_key_is_a_blend_of_track_and_fill():
    frame = {}
    overlays.paint_bar(frame, [0, 1], 0.25, (214, 14, 22))
    assert frame[0] == overlays.mix(overlays.TRACK, (214, 14, 22), 0.5)
    assert frame[1] == overlays.TRACK
```

- [ ] **Step 2: Run it to see it fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_paint.py`
Expected: collection error `ModuleNotFoundError: No module named 'overlays'`.

- [ ] **Step 3: Create `overlays.py` with exactly this head** (later tasks append further sections below it; the imports are for the whole module, leave them even though some are unused until then):

```python
"""Status on keys (roadmap Phase 6): CPU / RAM / GPU bars and a Pomodoro timer
painted over the live lighting frame, plus a generic flash(color, ms).

Everything here is host-side and stateless towards the keyboard: `OverlayLayer`
mutates the per-key frame the effect engine is about to stream (no HID, no
extra frame rate), `Sampler` reads system load once a second, and
`OverlayManager` ties them to per-profile toggles in settings.json. It never
sees a keystroke: the only inputs are CPU / memory / GPU load and the clock.
"""
import ctypes
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import namedtuple

IDS = ("cpu", "ram", "gpu", "pomodoro")
LABELS = {"cpu": "CPU", "ram": "RAM", "gpu": "GPU", "pomodoro": "Pomodoro"}
ROW_NAMES = {"cpu": "number row", "ram": "QWERTY row", "gpu": "home row",
             "pomodoro": "shift row"}
# Design codes (device_state.DESIGN_CODES) of each overlay's keys, left to right.
ROW_CODES = {
    "cpu": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    "ram": ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
    "gpu": ["A", "S", "D", "F", "G", "H", "J", "K", "L", "Semi"],
    "pomodoro": ["LShift", "Z", "X", "C", "V", "B", "N", "M", "Comma", "Dot",
                 "Slash", "RShift"],
}
SENSOR_IDS = ("cpu", "ram", "gpu")

TRACK = (14, 14, 22)                 # unlit part of a bar (near black, readable on any effect)
LOAD_STOPS = ((0.0, (0, 210, 80)), (0.65, (255, 170, 0)), (0.9, (255, 30, 30)))
RAM_STOPS = ((0.0, (0, 170, 255)), (0.75, (110, 80, 255)), (0.92, (255, 40, 120)))
POMO_WORK_RGB = (255, 80, 40)
POMO_BREAK_RGB = (0, 220, 120)
PHASE_FLASH_MS = 700
PHASE_FLASH_WINDOW_S = 1.5           # no pulse for a phase change older than this
FLASH_MIN_MS, FLASH_MAX_MS, FLASH_KEEP = 50, 5000, 8
RAINBOW = [(255, 0, 0), (255, 160, 0), (255, 255, 0), (0, 220, 0), (0, 120, 255), (160, 0, 255)]


# ---- colour + bar maths (pure) ----------------------------------------------
def unit(v):
    """float in [0, 1], or None for None / NaN / non-numbers."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return min(1.0, max(0.0, f))


def mix(a, b, t):
    t = min(1.0, max(0.0, t))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def ramp(stops, v):
    v = unit(v) or 0.0
    if v <= stops[0][0]:
        return stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if v <= p1:
            return mix(c0, c1, (v - p0) / (p1 - p0))
    return stops[-1][1]


def color_for(oid, value):
    return ramp(RAM_STOPS if oid == "ram" else LOAD_STOPS, value)


def bar_levels(value, n):
    """Per-key fill 0..1 for an n-key bar: whole keys light fully, the key at
    the boundary lights partially, so ten keys give a smooth ten-step bar."""
    v = unit(value)
    if v is None:
        return [0.0] * n
    return [min(1.0, max(0.0, v * n - i)) for i in range(n)]


def paint_bar(frame, indices, value, color):
    for idx, lv in zip(indices, bar_levels(value, len(indices))):
        frame[idx] = mix(TRACK, color, lv)
```

- [ ] **Step 4: Run it to see it pass**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_paint.py`
Expected: `9 passed`.

- [ ] **Step 5: Full suite, then commit**

Run: `<py> -m pytest -q -p no:cacheprovider` — expected `1018 passed, 14 skipped`.

```bash
git add overlays.py tests/test_overlays_paint.py
git commit -m "feat(overlays): layout, load colours and bar painting" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Pomodoro, `OverlayLayer`, `flash`, and the engine hook

**Files:**
- Modify: `overlays.py` (append the Pomodoro and layer sections)
- Modify: `effects.py` (`PerKeyEffectEngine.__init__` and `_run`)
- Test: `tests/test_overlays_layer.py`

**Interfaces:**
- Consumes: Task 1 (`IDS`, `SENSOR_IDS`, `unit`, `mix`, `color_for`, `paint_bar`, `POMO_*`, `PHASE_FLASH_*`, `FLASH_*`).
- Produces: `PomoState(phase, remaining_s, progress, elapsed_s)`; `Pomodoro(work_s=1500.0, break_s=300.0)` with `.running`, `.start(now)`, `.stop()`, `.state(now) -> PomoState|None`; `phase_color(phase)`; `OverlayLayer(rows, all_indices, pomodoro=None, clock=time.monotonic)` with `.set_enabled(oid, on, now=None)`, `.enabled(oid)`, `.any_enabled()`, `.set_value(oid, v)`, `.value(oid)`, `.flash(rgb, ms, now=None)`, `.pomodoro_state(now=None)`, `.apply(frame, now=None)`; `PerKeyEffectEngine.overlay` (None or any object with `apply(frame, now)`).

- [ ] **Step 1: Write the failing tests** — create `tests/test_overlays_layer.py`:

```python
"""Phase 6 / Task 2: Pomodoro cycle, the compositing layer, flash(), and the
effect engine's overlay hook. Fakes only: no HID, no keyboard."""
import threading

import pytest

import effects
import overlays

ROWS = {"cpu": [0, 1, 2, 3], "ram": [4, 5, 6, 7], "gpu": [8, 9], "pomodoro": [10, 11, 12, 13]}
ALL = list(range(16))
BASE = {i: (50, 60, 70) for i in ALL}


def _layer(work=100, brk=20):
    return overlays.OverlayLayer(ROWS, ALL, overlays.Pomodoro(work, brk))


def _frame():
    return dict(BASE)


def test_pomodoro_cycles_work_then_break_then_work():
    p = overlays.Pomodoro(100, 20)
    assert p.state(5) is None and not p.running
    p.start(1000)
    s = p.state(1000)
    assert (s.phase, s.remaining_s, s.progress, s.elapsed_s) == ("work", 100, 0.0, 0.0)
    s = p.state(1025)
    assert s.phase == "work" and s.remaining_s == 75 and s.progress == pytest.approx(0.25)
    s = p.state(1110)
    assert s.phase == "break" and s.remaining_s == 10 and s.progress == pytest.approx(0.5)
    assert s.elapsed_s == 10
    assert p.state(1120).phase == "work"                       # 120 s cycle wraps
    p.stop()
    assert p.state(1130) is None


def test_pomodoro_defaults_are_25_and_5_minutes_and_never_zero():
    p = overlays.Pomodoro()
    assert (p.work_s, p.break_s) == (1500.0, 300.0)
    q = overlays.Pomodoro(0, -4)
    assert q.work_s == 1.0 and q.break_s == 1.0


def test_nothing_enabled_leaves_the_frame_untouched():
    lay, f = _layer(), _frame()
    lay.apply(f, 0.0)
    assert f == BASE and not lay.any_enabled()


def test_cpu_bar_paints_only_the_number_row():
    lay = _layer()
    lay.set_enabled("cpu", True)
    lay.set_value("cpu", 0.5)
    f = _frame()
    lay.apply(f, 0.0)
    assert [f[i] for i in (0, 1)] == [overlays.color_for("cpu", 0.5)] * 2
    assert [f[i] for i in (2, 3)] == [overlays.TRACK] * 2
    assert all(f[i] == BASE[i] for i in range(4, 16))


def test_each_sensor_uses_its_own_row_and_ramp():
    lay = _layer()
    for oid in ("cpu", "ram", "gpu"):
        lay.set_enabled(oid, True)
        lay.set_value(oid, 1.0)
    f = _frame()
    lay.apply(f, 0.0)
    assert f[0] == overlays.color_for("cpu", 1.0) and f[4] == overlays.color_for("ram", 1.0)
    assert f[8] == overlays.color_for("gpu", 1.0) and f[10] == BASE[10]


def test_a_sensor_without_a_reading_shows_the_dim_track():
    lay = _layer()
    lay.set_enabled("ram", True)
    f = _frame()
    lay.apply(f, 0.0)
    assert [f[i] for i in ROWS["ram"]] == [overlays.TRACK] * 4


def test_disabling_clears_the_stored_value():
    lay = _layer()
    lay.set_enabled("cpu", True)
    lay.set_value("cpu", 0.9)
    lay.set_enabled("cpu", False)
    assert lay.value("cpu") is None and not lay.any_enabled()


def test_bad_values_and_unknown_ids_are_ignored():
    lay = _layer()
    lay.set_value("cpu", "x")
    lay.set_value("nope", 0.5)
    lay.set_enabled("nope", True)
    assert lay.value("cpu") is None and not lay.any_enabled()


def test_pomodoro_progress_fills_the_shift_row_in_the_phase_colour():
    lay = _layer()
    lay.set_enabled("pomodoro", True, now=1000.0)
    f = _frame()
    lay.apply(f, 1050.0)                                       # half way through work
    assert [f[i] for i in (10, 11)] == [overlays.POMO_WORK_RGB] * 2
    assert [f[i] for i in (12, 13)] == [overlays.TRACK] * 2
    f = _frame()
    lay.apply(f, 1110.0)                                       # half way through break
    assert f[10] == f[11] == overlays.POMO_BREAK_RGB


def test_phase_change_pulses_the_whole_board_once_and_fades():
    lay = _layer()
    lay.set_enabled("pomodoro", True, now=1000.0)
    lay.apply(_frame(), 1099.9)                                 # last moment of work
    f = _frame()
    lay.apply(f, 1100.0)                                        # break begins: pulse at full strength
    assert f[0] == overlays.POMO_BREAK_RGB and f[15] == overlays.POMO_BREAK_RGB
    f = _frame()
    lay.apply(f, 1100.35)                                       # half faded
    assert f[0] == overlays.mix(BASE[0], overlays.POMO_BREAK_RGB, 0.5)
    f = _frame()
    lay.apply(f, 1101.0)                                        # over
    assert f[0] == BASE[0]


def test_starting_the_timer_does_not_pulse_and_a_stale_change_is_skipped():
    lay = _layer()
    lay.set_enabled("pomodoro", True, now=1000.0)
    f = _frame()
    lay.apply(f, 1000.0)
    assert f[0] == BASE[0]                                      # no pulse at start
    lay.apply(_frame(), 1050.0)
    f = _frame()
    lay.apply(f, 1119.0)                                        # slept through the change: 19 s into break
    assert f[0] == BASE[0]


def test_turning_pomodoro_off_and_on_restarts_the_cycle():
    lay = _layer()
    lay.set_enabled("pomodoro", True, now=0.0)
    lay.set_enabled("pomodoro", True, now=50.0)                 # already on: keep running
    assert lay.pomodoro_state(60.0).elapsed_s == 60.0
    lay.set_enabled("pomodoro", False, now=60.0)
    assert lay.pomodoro_state(61.0) is None
    lay.set_enabled("pomodoro", True, now=500.0)
    assert lay.pomodoro_state(510.0).elapsed_s == 10.0


def test_flash_blends_every_key_and_expires():
    lay = _layer()
    lay.flash((255, 0, 0), 1000, now=10.0)
    f = _frame()
    lay.apply(f, 10.0)
    assert all(f[i] == (255, 0, 0) for i in ALL)
    f = _frame()
    lay.apply(f, 10.5)
    assert f[3] == overlays.mix(BASE[3], (255, 0, 0), 0.5)
    f = _frame()
    lay.apply(f, 11.0)
    assert f == BASE


def test_flash_sits_on_top_of_a_bar_and_is_clamped():
    lay = _layer()
    lay.set_enabled("cpu", True)
    lay.set_value("cpu", 1.0)
    lay.flash((300, -5, 0), 99999, now=0.0)                     # colour and duration clamped
    f = _frame()
    lay.apply(f, 0.0)
    assert f[0] == (255, 0, 0)
    f = _frame()
    lay.apply(f, 4.9)                                           # still alive: capped at 5 s, not 99 s
    assert f[4] != BASE[4]
    f = _frame()
    lay.apply(f, 5.1)
    assert f[4] == BASE[4]


def test_flash_list_is_bounded():
    lay = _layer()
    for _ in range(50):
        lay.flash((1, 2, 3), 1000, now=0.0)
    assert len(lay._flashes) == overlays.FLASH_KEEP


# ---- the engine hook -------------------------------------------------------
class _KM:
    def __init__(self, n=16):
        self.by_index = {i: {"x": float(i % 4), "y": float(i // 4)} for i in range(n)}
        self.index_of_code = {}


def _run_engine(overlay, frames=3):
    got, done = [], threading.Event()

    def send(frame):
        got.append(dict(frame))
        if len(got) >= frames:
            done.set()

    eng = effects.PerKeyEffectEngine(_KM(), send)
    eng.overlay = overlay
    eng.start_zones([], global_bg=(1, 2, 3), base={})
    assert done.wait(2.0)
    eng.stop()
    return got


def test_engine_without_an_overlay_streams_the_plain_frame():
    assert effects.PerKeyEffectEngine(_KM(), lambda f: None).overlay is None
    got = _run_engine(None)
    assert all(v == (1, 2, 3) for v in got[0].values())


def test_engine_composites_the_overlay_onto_every_streamed_frame():
    lay = overlays.OverlayLayer(ROWS, ALL)
    lay.set_enabled("cpu", True)
    lay.set_value("cpu", 1.0)
    got = _run_engine(lay)
    for frame in got:
        assert frame[0] == overlays.color_for("cpu", 1.0)
        assert frame[8] == (1, 2, 3)


def test_a_broken_overlay_cannot_stop_the_stream():
    class Boom:
        def apply(self, frame, now):
            raise RuntimeError("x")
    got = _run_engine(Boom())
    assert len(got) >= 3


def test_overlay_does_not_change_the_frame_rate_cap():
    eng = effects.PerKeyEffectEngine(_KM(), lambda f: None, max_fps=28)
    before = eng._frame_interval
    eng.overlay = overlays.OverlayLayer(ROWS, ALL)
    assert eng._frame_interval == before and eng.fps == 28
```

- [ ] **Step 2: Run to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_layer.py`
Expected: failures `AttributeError: module 'overlays' has no attribute 'Pomodoro'` (and `OverlayLayer`).

- [ ] **Step 3: Append to `overlays.py`** (directly after `paint_bar`):

```python
# ---- Pomodoro ----------------------------------------------------------------
PomoState = namedtuple("PomoState", "phase remaining_s progress elapsed_s")


class Pomodoro:
    """Repeating work / break cycle (default 25 / 5 min), driven by the clock
    passed in: no thread. `start(now)` begins a cycle; `state(now)` is pure."""

    def __init__(self, work_s=1500.0, break_s=300.0):
        self.work_s = max(1.0, float(work_s))
        self.break_s = max(1.0, float(break_s))
        self._start = None

    @property
    def running(self):
        return self._start is not None

    def start(self, now):
        self._start = float(now)

    def stop(self):
        self._start = None

    def state(self, now):
        if self._start is None:
            return None
        cycle = self.work_s + self.break_s
        pos = max(0.0, float(now) - self._start) % cycle
        if pos < self.work_s:
            return PomoState("work", self.work_s - pos, pos / self.work_s, pos)
        el = pos - self.work_s
        return PomoState("break", self.break_s - el, el / self.break_s, el)


def phase_color(phase):
    return POMO_BREAK_RGB if phase == "break" else POMO_WORK_RGB


# ---- the compositing layer the effect engine calls -----------------------------
class OverlayLayer:
    """`apply(frame, now)` paints the enabled overlays and live flashes onto the
    engine's per-frame dict. Called on the engine thread; everything else
    (Api threads, the sampler) goes through the lock."""

    def __init__(self, rows, all_indices, pomodoro=None, clock=time.monotonic):
        self.rows = {k: list(v) for k, v in rows.items()}
        self.all = list(all_indices)
        self.pomodoro = pomodoro or Pomodoro()
        self._clock = clock
        self._lock = threading.Lock()
        self._on = {k: False for k in IDS}
        self._val = {k: None for k in SENSOR_IDS}
        self._flashes = []            # (rgb, start, ms)
        self._last_phase = None

    def set_enabled(self, oid, on, now=None):
        if oid not in self._on:
            return
        now = self._clock() if now is None else now
        on = bool(on)
        with self._lock:
            was, self._on[oid] = self._on[oid], on
            if oid == "pomodoro":
                if on and not was:
                    self.pomodoro.start(now)
                if not on:
                    self.pomodoro.stop()
                self._last_phase = None
            elif not on:
                self._val[oid] = None

    def enabled(self, oid):
        return self._on.get(oid, False)

    def any_enabled(self):
        return any(self._on.values())

    def set_value(self, oid, value):
        if oid in self._val:
            with self._lock:
                self._val[oid] = unit(value)

    def value(self, oid):
        return self._val.get(oid)

    def flash(self, rgb, ms, now=None):
        now = self._clock() if now is None else now
        rgb = tuple(min(255, max(0, int(c))) for c in rgb[:3])
        ms = min(FLASH_MAX_MS, max(FLASH_MIN_MS, int(ms)))
        with self._lock:
            self._add_flash(rgb, now, ms)

    def _add_flash(self, rgb, now, ms):
        self._flashes = (self._flashes + [(rgb, now, ms)])[-FLASH_KEEP:]

    def pomodoro_state(self, now=None):
        if not self._on["pomodoro"]:
            return None
        return self.pomodoro.state(self._clock() if now is None else now)

    def apply(self, frame, now=None):
        now = self._clock() if now is None else now
        with self._lock:
            on, vals = dict(self._on), dict(self._val)
            st = self.pomodoro.state(now) if on["pomodoro"] else None
            if st is not None:
                if (self._last_phase is not None and st.phase != self._last_phase
                        and st.elapsed_s < PHASE_FLASH_WINDOW_S):
                    self._add_flash(phase_color(st.phase), now, PHASE_FLASH_MS)
                self._last_phase = st.phase
            self._flashes = [f for f in self._flashes if now - f[1] < f[2] / 1000.0]
            flashes = list(self._flashes)
        for oid in SENSOR_IDS:
            if on[oid] and self.rows.get(oid):
                paint_bar(frame, self.rows[oid], vals[oid], color_for(oid, vals[oid]))
        if st is not None and self.rows.get("pomodoro"):
            paint_bar(frame, self.rows["pomodoro"], st.progress, phase_color(st.phase))
        for rgb, t0, ms in flashes:
            a = 1.0 - (now - t0) / (ms / 1000.0)
            for idx in self.all:
                frame[idx] = mix(frame.get(idx, (0, 0, 0)), rgb, a)
```

- [ ] **Step 4: Add the engine hook in `effects.py`.** In `PerKeyEffectEngine.__init__`, right after the `self.get_calibrated = None ...` line add:

```python
        self.overlay = None       # optional object with apply(frame, now): status-on-keys layer
```

In `_run`, replace the line `            self.last_frame = frame   # for the in-app keyboard mirror` with:

```python
            ov = self.overlay
            if ov is not None:
                try:
                    ov.apply(frame, t_start)    # same monotonic clock as `_now`
                except Exception:
                    pass                        # a broken overlay must never stop the stream
            self.last_frame = frame   # for the in-app keyboard mirror
```

- [ ] **Step 5: Run to see them pass**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_layer.py`
Expected: `19 passed`.

- [ ] **Step 6: Full suite, then commit**

Run: `<py> -m pytest -q -p no:cacheprovider` — expected `1037 passed, 14 skipped` (the existing effects tests must be unchanged).

```bash
git add overlays.py effects.py tests/test_overlays_layer.py
git commit -m "feat(overlays): Pomodoro, compositing layer, flash and the engine overlay hook" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Samplers — CPU, RAM, GPU

**Files:**
- Modify: `overlays.py` (append the samplers section)
- Test: `tests/test_overlays_samplers.py`

**Interfaces:**
- Consumes: Task 2 (`OverlayLayer.enabled/set_value`), Task 1 (`unit`).
- Produces: `parse_proc_stat(text) -> (idle, total)|None`, `parse_meminfo(text) -> float|None`, `cpu_load(prev, cur) -> float|None`, `read_cpu_counters() -> (idle, total)|None`, `read_memory_load() -> float|None`, `parse_gpu_output(text) -> float|None`, `_run_nvidia_smi(exe) -> str`, `GPU_TIMEOUT_S = 1.5`, `GpuProbe(which=shutil.which, runner=None)` with `.available`, `.reason`, `.read() -> float|None`; `Sampler(layer, cpu=None, mem=None, gpu=None, gate=None, interval=1.0)` with `.sample_once()`, `.start()`, `.stop()`, `.running`. Readers passed as `None` resolve to the module functions at construction time (so tests can monkeypatch them).

- [ ] **Step 1: Write the failing tests** — create `tests/test_overlays_samplers.py`:

```python
"""Phase 6 / Task 3: CPU / RAM / GPU samplers. The GPU probe only ever runs an
INJECTED runner here: no test starts nvidia-smi or any other process."""
import sys
import time

import pytest

import overlays

ROWS = {"cpu": [0], "ram": [1], "gpu": [2], "pomodoro": [3]}


@pytest.fixture(autouse=True)
def _never_spawn_nvidia_smi(monkeypatch):
    def boom(exe):
        raise AssertionError("a test tried to run the real nvidia-smi")
    monkeypatch.setattr(overlays, "_run_nvidia_smi", boom)


def test_cpu_load_from_two_counter_samples():
    assert overlays.cpu_load((100, 1000), (150, 1200)) == pytest.approx(0.75)   # 50 idle of 200
    assert overlays.cpu_load((100, 1000), (300, 1200)) == 0.0                   # all idle
    assert overlays.cpu_load((100, 1000), (100, 1100)) == 1.0                   # no idle
    for prev, cur in ((None, (1, 2)), ((1, 2), None), ((5, 10), (5, 10)), ((5, 10), (4, 9))):
        assert overlays.cpu_load(prev, cur) is None                              # first sample / no time passed


def test_proc_stat_parser():
    text = "cpu  100 5 50 800 20 3 2 0 0 0\ncpu0 1 1 1 1 1 1 1 1\nintr 5\n"
    assert overlays.parse_proc_stat(text) == (820, 980)          # idle + iowait, sum of first 8
    assert overlays.parse_proc_stat("") is None
    assert overlays.parse_proc_stat("cpu  a b c d") is None
    assert overlays.parse_proc_stat("cpu 1 2") is None


def test_meminfo_parser():
    text = "MemTotal:       16000000 kB\nMemFree: 1 kB\nMemAvailable:    4000000 kB\n"
    assert overlays.parse_meminfo(text) == pytest.approx(0.75)
    assert overlays.parse_meminfo("MemTotal: 5 kB") is None
    assert overlays.parse_meminfo("") is None


def test_gpu_output_parser_takes_the_busiest_gpu():
    assert overlays.parse_gpu_output("37\n") == pytest.approx(0.37)
    assert overlays.parse_gpu_output("12\n80\n") == pytest.approx(0.8)
    assert overlays.parse_gpu_output("[N/A]\n 5 \n") == pytest.approx(0.05)
    assert overlays.parse_gpu_output("250") == 1.0
    for junk in ("", "N/A", "No devices were found", None):
        assert overlays.parse_gpu_output(junk) is None


def test_gpu_probe_is_located_once_and_hidden_without_nvidia_smi():
    calls = []
    probe = overlays.GpuProbe(which=lambda n: calls.append(n) or None, runner=lambda e: "50")
    assert calls == ["nvidia-smi"]
    assert not probe.available and probe.read() is None
    assert "not found" in probe.reason and calls == ["nvidia-smi"]       # never looked again


def test_gpu_probe_reads_through_the_injected_runner():
    seen = []
    probe = overlays.GpuProbe(which=lambda n: "C:/x/nvidia-smi.exe",
                              runner=lambda exe: seen.append(exe) or "42\n")
    assert probe.available and probe.reason is None
    assert probe.read() == pytest.approx(0.42) and seen == ["C:/x/nvidia-smi.exe"]


def test_gpu_probe_gives_up_after_three_failures_in_a_row():
    answers = iter(["", "oops", "7", "", "", ""])
    probe = overlays.GpuProbe(which=lambda n: "x", runner=lambda e: next(answers))
    assert probe.read() is None and probe.read() is None
    assert probe.read() == pytest.approx(0.07)                  # a good read resets the count
    assert probe.read() is None and probe.read() is None and probe.available
    assert probe.read() is None
    assert not probe.available and probe.reason == "nvidia-smi is not answering"


def test_gpu_probe_survives_a_runner_that_raises():
    def runner(exe):
        raise OSError("gone")
    probe = overlays.GpuProbe(which=lambda n: "x", runner=runner)
    assert probe.read() is None


def test_nvidia_smi_is_started_without_a_console_window_and_with_a_timeout(monkeypatch):
    got = {}

    class R:
        returncode, stdout = 0, "9\n"

    def fake_run(cmd, **kw):
        got["cmd"], got["kw"] = cmd, kw
        return R()
    monkeypatch.undo()                                          # restore the real _run_nvidia_smi
    monkeypatch.setattr(overlays.subprocess, "run", fake_run)
    assert overlays._run_nvidia_smi("smi") == "9\n"
    assert got["cmd"] == ["smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]
    assert got["kw"]["timeout"] == overlays.GPU_TIMEOUT_S == 1.5
    assert got["kw"]["creationflags"] == getattr(overlays.subprocess, "CREATE_NO_WINDOW", 0)
    assert got["kw"]["capture_output"] is True


def _sampler(layer, cpu=None, mem=None, gpu=None, gate=None):
    return overlays.Sampler(layer, cpu=cpu or (lambda: None), mem=mem or (lambda: None),
                            gpu=gpu, gate=gate, interval=0.01)


def test_sampler_reads_only_the_enabled_sensors():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    reads = []
    s = _sampler(lay, cpu=lambda: reads.append("cpu") or (0, 1), mem=lambda: reads.append("ram") or 0.4,
                 gpu=type("G", (), {"read": lambda self: reads.append("gpu") or 0.2})())
    s.sample_once()
    assert reads == []                                          # nothing enabled: nothing read
    lay.set_enabled("ram", True)
    s.sample_once()
    assert reads == ["ram"] and lay.value("ram") == 0.4


def test_sampler_cpu_needs_two_samples_and_forgets_when_switched_off():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    seq = iter([(0, 100), (50, 200), (60, 300), (0, 1000)])
    s = _sampler(lay, cpu=lambda: next(seq))
    lay.set_enabled("cpu", True)
    s.sample_once()
    assert lay.value("cpu") is None                             # first sample: no delta yet
    s.sample_once()
    assert lay.value("cpu") == pytest.approx(0.5)               # 50 idle of 100
    lay.set_enabled("cpu", False)
    s.sample_once()
    lay.set_enabled("cpu", True)
    s.sample_once()                                             # fresh start: not a delta against a stale sample
    assert lay.value("cpu") is None


def test_sampler_gate_skips_the_whole_tick():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    lay.set_enabled("ram", True)
    open_ = {"v": False}
    s = _sampler(lay, mem=lambda: 0.9, gate=lambda: open_["v"])
    s.sample_once()
    assert lay.value("ram") is None
    open_["v"] = True
    s.sample_once()
    assert lay.value("ram") == 0.9


def test_sampler_thread_starts_ticks_and_stops():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    lay.set_enabled("ram", True)
    s = _sampler(lay, mem=lambda: 0.25)
    assert not s.running
    s.start()
    s.start()                                                   # second start is a no-op
    deadline = time.time() + 2
    while lay.value("ram") is None and time.time() < deadline:
        time.sleep(0.01)
    assert s.running and lay.value("ram") == 0.25
    s.stop()
    assert not s.running
    s.stop()                                                    # idempotent


def test_sampler_thread_survives_a_reader_that_raises():
    lay = overlays.OverlayLayer(ROWS, [0, 1, 2, 3])
    lay.set_enabled("ram", True)
    n = {"c": 0}

    def mem():
        n["c"] += 1
        if n["c"] == 1:
            raise RuntimeError("boom")
        return 0.5
    s = _sampler(lay, mem=mem)
    s.start()
    deadline = time.time() + 2
    while lay.value("ram") is None and time.time() < deadline:
        time.sleep(0.01)
    s.stop()
    assert lay.value("ram") == 0.5


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows kernel32 readers")
def test_windows_readers_answer_in_range_without_psutil():
    a = overlays.read_cpu_counters()
    assert a is not None and a[1] > a[0] >= 0
    time.sleep(0.05)
    b = overlays.read_cpu_counters()
    load = overlays.cpu_load(a, b)
    assert load is None or 0.0 <= load <= 1.0
    mem = overlays.read_memory_load()
    assert mem is not None and 0.0 < mem <= 1.0
    assert "psutil" not in sys.modules


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc readers")
def test_linux_readers_answer_from_proc():
    assert overlays.read_cpu_counters() is not None
    assert 0.0 < overlays.read_memory_load() <= 1.0
```

- [ ] **Step 2: Run to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_samplers.py`
Expected: failures `AttributeError: module 'overlays' has no attribute 'cpu_load'` (etc.).

- [ ] **Step 3: Append to `overlays.py`** (after the carrier-free layer section; the carrier section is added by Task 6, so for now this follows `OverlayLayer`):

```python
# ---- samplers ----------------------------------------------------------------
class _FILETIME(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


class _MEMSTATUS(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64)]


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def parse_proc_stat(text):
    """First 'cpu' line of /proc/stat -> (idle, total) jiffies, or None."""
    for line in (text or "").splitlines():
        parts = line.split()
        if parts and parts[0] == "cpu":
            try:
                nums = [int(x) for x in parts[1:9]]
            except ValueError:
                return None
            if len(nums) < 4:
                return None
            return (nums[3] + (nums[4] if len(nums) > 4 else 0), sum(nums))
    return None


def parse_meminfo(text):
    """/proc/meminfo -> used fraction 0..1, or None."""
    vals = {}
    for line in (text or "").splitlines():
        k, _, rest = line.partition(":")
        bits = rest.split()
        if bits and bits[0].isdigit():
            vals[k.strip()] = int(bits[0])
    total, avail = vals.get("MemTotal"), vals.get("MemAvailable")
    if not total or avail is None:
        return None
    return unit(1.0 - avail / total)


def cpu_load(prev, cur):
    """Load 0..1 between two (idle, total) counter samples, or None."""
    if not prev or not cur:
        return None
    dt = cur[1] - prev[1]
    if dt <= 0:
        return None
    return unit(1.0 - (cur[0] - prev[0]) / dt)


def read_cpu_counters():
    """(idle, total) system CPU counters: GetSystemTimes on Windows, /proc/stat
    on Linux, None elsewhere or on any failure."""
    try:
        if sys.platform.startswith("win"):
            idle, kern, user = _FILETIME(), _FILETIME(), _FILETIME()
            if not ctypes.windll.kernel32.GetSystemTimes(
                    ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
                return None
            ft = lambda f: (f.hi << 32) | f.lo
            return (ft(idle), ft(kern) + ft(user))   # kernel time includes idle
        if sys.platform.startswith("linux"):
            return parse_proc_stat(_read_text("/proc/stat"))
    except Exception:
        pass
    return None


def read_memory_load():
    """Physical memory in use 0..1: GlobalMemoryStatusEx / /proc/meminfo, else None."""
    try:
        if sys.platform.startswith("win"):
            m = _MEMSTATUS()
            m.dwLength = ctypes.sizeof(m)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return None
            return unit(m.dwMemoryLoad / 100.0)
        if sys.platform.startswith("linux"):
            return parse_meminfo(_read_text("/proc/meminfo"))
    except Exception:
        pass
    return None


NVIDIA_SMI_ARGS = ("--query-gpu=utilization.gpu", "--format=csv,noheader,nounits")
GPU_TIMEOUT_S = 1.5


def parse_gpu_output(text):
    """nvidia-smi csv (one utilization % per GPU) -> busiest GPU 0..1, or None."""
    vals = []
    for line in (text or "").splitlines():
        try:
            vals.append(float(line.strip()))
        except ValueError:
            continue
    return unit(max(vals) / 100.0) if vals else None


def _run_nvidia_smi(exe):
    res = subprocess.run([exe, *NVIDIA_SMI_ARGS], capture_output=True, text=True,
                         timeout=GPU_TIMEOUT_S,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return res.stdout if res.returncode == 0 else ""


class GpuProbe:
    """nvidia-smi, located ONCE with `which`; `runner(exe) -> csv text` is
    injectable (tests never start a process). Three failed reads in a row
    switch it off for the session."""
    MAX_FAILS = 3

    def __init__(self, which=shutil.which, runner=None):
        self._exe = which("nvidia-smi")
        self._runner = runner or _run_nvidia_smi
        self._fails = 0

    @property
    def available(self):
        return bool(self._exe) and self._fails < self.MAX_FAILS

    @property
    def reason(self):
        if not self._exe:
            return "nvidia-smi not found (NVIDIA GPU only)"
        if self._fails >= self.MAX_FAILS:
            return "nvidia-smi is not answering"
        return None

    def read(self):
        if not self.available:
            return None
        try:
            v = parse_gpu_output(self._runner(self._exe))
        except Exception:
            v = None
        self._fails = 0 if v is not None else self._fails + 1
        return v


class Sampler:
    """One-second sampling of the ENABLED sensors into the layer. `gate()`
    (e.g. "the keyboard is open") skips a tick entirely, so nothing is read
    and no process starts while there is nothing to draw on."""

    def __init__(self, layer, cpu=None, mem=None, gpu=None, gate=None, interval=1.0):
        self.layer = layer
        self._cpu = cpu if cpu is not None else read_cpu_counters
        self._mem = mem if mem is not None else read_memory_load
        self._gpu = gpu
        self._gate = gate
        self._interval = float(interval)
        self._prev_cpu = None
        self._stop = threading.Event()
        self._stop.set()
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def sample_once(self):
        if self._gate is not None and not self._gate():
            return
        lay = self.layer
        if lay.enabled("cpu"):
            cur = self._cpu()
            lay.set_value("cpu", cpu_load(self._prev_cpu, cur))
            self._prev_cpu = cur
        else:
            self._prev_cpu = None
        if lay.enabled("ram"):
            lay.set_value("ram", self._mem())
        if lay.enabled("gpu") and self._gpu is not None:
            lay.set_value("gpu", self._gpu.read())

    def start(self):
        if self.running:
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        th = self._thread
        if th is not None and th is not threading.current_thread():
            th.join(timeout=2.0)
        self._thread = None

    def _run(self, stop_ev):
        while not stop_ev.is_set():
            t0 = time.monotonic()
            try:
                self.sample_once()
            except Exception:
                pass
            stop_ev.wait(max(0.01, self._interval - (time.monotonic() - t0)))
```

- [ ] **Step 4: Run to see them pass**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_samplers.py`
Expected: `15 passed, 1 skipped` on Windows (the skip is the Linux-only `/proc` test; on Linux the Windows one skips instead).

- [ ] **Step 5: Full suite, then commit**

Run: `<py> -m pytest -q -p no:cacheprovider` — expected `1052 passed, 15 skipped`.

```bash
git add overlays.py tests/test_overlays_samplers.py
git commit -m "feat(overlays): CPU/RAM/GPU samplers (ctypes, no psutil; nvidia-smi probe is injectable)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Per-profile preferences and `OverlayManager`

**Files:**
- Modify: `overlays.py` (append preferences + manager)
- Test: `tests/test_overlays_manager.py`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: `PREFS_KEY = "overlays"`, `MAX_PROFILE_ID = 64`, `load_prefs(path) -> {"profiles": {...}, "pomodoro": {...}}`, `toggles_for(prefs, pid) -> {id: bool}`, `pomodoro_seconds(prefs) -> (work_s, break_s)`, `save_toggle(path, lock, pid, oid, on)`; `OverlayManager(rows, all_indices, settings_path, lock, cpu=None, mem=None, gpu=None, gate=None, clock=time.monotonic, interval=1.0)` with `.layer`, `.sampler`, `.gpu`, `.pid`, `.availability(oid) -> (bool, reason|None)`, `.follow_profile(pid)`, `.set(oid, on) -> {"ok", "id", "on"} | {"ok": False, "error"}`, `.any_on()`, `.status() -> {"overlays": [...], "pomodoro": {...}}`, `.close()`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_overlays_manager.py`:

```python
"""Phase 6 / Task 4: per-profile toggles in settings.json and the OverlayManager
(availability, sampler lifecycle, the get_overlays rows). Fakes only."""
import json
import threading

import pytest

import overlays

ROWS = {"cpu": list(range(0, 10)), "ram": list(range(10, 20)), "gpu": list(range(20, 30)),
        "pomodoro": list(range(30, 42))}
ALL = list(range(42))


@pytest.fixture(autouse=True)
def _never_spawn_nvidia_smi(monkeypatch):
    def boom(exe):
        raise AssertionError("a test tried to run the real nvidia-smi")
    monkeypatch.setattr(overlays, "_run_nvidia_smi", boom)


class FakeGpu:
    def __init__(self, available=True, value=0.3):
        self.available, self.value = available, value
        self.reason = None if available else "nvidia-smi not found (NVIDIA GPU only)"

    def read(self):
        return self.value


def _mgr(tmp_path, rows=ROWS, cpu=lambda: (0, 1), mem=lambda: 0.5, gpu=None, **kw):
    path = str(tmp_path / "settings.json")
    m = overlays.OverlayManager(rows, ALL, path, threading.Lock(), cpu=cpu, mem=mem,
                                gpu=gpu or FakeGpu(), interval=0.01, **kw)
    return m, path


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---- preferences ---------------------------------------------------------------
def test_missing_or_corrupt_settings_mean_everything_off(tmp_path):
    p = tmp_path / "settings.json"
    assert overlays.load_prefs(str(p)) == {"profiles": {}, "pomodoro": {}}
    p.write_text("{not json", encoding="utf-8")
    assert overlays.load_prefs(str(p)) == {"profiles": {}, "pomodoro": {}}
    assert overlays.toggles_for({"profiles": {}}, "p1") == {k: False for k in overlays.IDS}


def test_save_toggle_keeps_every_other_setting(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"profiles": [{"id": "p1"}], "activeProfile": "p1", "autoUpdate": True}),
                 encoding="utf-8")
    overlays.save_toggle(str(p), threading.Lock(), "p1", "cpu", True)
    overlays.save_toggle(str(p), threading.Lock(), "p2", "gpu", True)
    data = _read(str(p))
    assert data["autoUpdate"] is True and data["activeProfile"] == "p1"
    assert data["overlays"]["profiles"] == {"p1": {"cpu": True}, "p2": {"gpu": True}}
    prefs = overlays.load_prefs(str(p))
    assert overlays.toggles_for(prefs, "p1") == {"cpu": True, "ram": False, "gpu": False, "pomodoro": False}


def test_malformed_prefs_are_dropped_not_trusted(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"overlays": {"profiles": {"p1": "yes", "x" * 65: {"cpu": True},
                                                       "": {"cpu": True}, "ok": {"cpu": 1, "evil": True}},
                                          "pomodoro": {"workMin": "lots", "breakMin": True}}}),
                 encoding="utf-8")
    prefs = overlays.load_prefs(str(p))
    assert list(prefs["profiles"]) == ["ok"] and prefs["profiles"]["ok"] == {
        "cpu": True, "ram": False, "gpu": False, "pomodoro": False}
    assert prefs["pomodoro"] == {}


def test_pomodoro_length_comes_from_settings_with_sane_limits():
    assert overlays.pomodoro_seconds({}) == (1500.0, 300.0)
    assert overlays.pomodoro_seconds({"pomodoro": {"workMin": 50, "breakMin": 10}}) == (3000.0, 600.0)
    assert overlays.pomodoro_seconds({"pomodoro": {"workMin": 0, "breakMin": 999}}) == (60.0, 3600.0)


# ---- manager -------------------------------------------------------------------
def test_a_new_profile_starts_with_everything_off_and_no_sampler(tmp_path):
    m, _ = _mgr(tmp_path)
    m.follow_profile("p1")
    assert not m.any_on() and not m.sampler.running
    st = m.status()
    assert [o["id"] for o in st["overlays"]] == ["cpu", "ram", "gpu", "pomodoro"]
    assert all(o["on"] is False and o["available"] for o in st["overlays"])
    assert st["pomodoro"] == {"phase": None, "remaining_s": None}


def test_set_persists_per_profile_and_follows_the_profile(tmp_path):
    m, path = _mgr(tmp_path)
    m.follow_profile("p1")
    assert m.set("cpu", True) == {"ok": True, "id": "cpu", "on": True}
    assert m.sampler.running                                   # sampler runs while a sensor is on
    m.follow_profile("p2")                                     # another profile: all off, sampler stops
    assert not m.any_on() and not m.sampler.running
    m.set("pomodoro", True)
    m.follow_profile("p1")
    assert m.layer.enabled("cpu") and not m.layer.enabled("pomodoro")
    assert _read(path)["overlays"]["profiles"] == {"p1": {"cpu": True}, "p2": {"pomodoro": True}}
    m.close()
    fresh, _ = _mgr(tmp_path)                                  # a restart reads the same file
    fresh.follow_profile("p1")
    assert fresh.layer.enabled("cpu")
    fresh.close()


def test_pomodoro_alone_needs_no_sampler(tmp_path):
    m, _ = _mgr(tmp_path)
    m.follow_profile("p1")
    m.set("pomodoro", True)
    assert m.any_on() and not m.sampler.running
    st = m.status()
    pomo = [o for o in st["overlays"] if o["id"] == "pomodoro"][0]
    assert pomo["on"] and pomo["phase"] == "work" and pomo["remaining_s"] == 1500
    assert st["pomodoro"]["phase"] == "work"
    m.set("pomodoro", False)
    assert not m.any_on()


def test_pomodoro_length_is_read_from_settings(tmp_path):
    (tmp_path / "settings.json").write_text(
        json.dumps({"overlays": {"pomodoro": {"workMin": 50, "breakMin": 10}}}), encoding="utf-8")
    m, _ = _mgr(tmp_path)
    assert (m.layer.pomodoro.work_s, m.layer.pomodoro.break_s) == (3000.0, 600.0)


def test_gpu_without_nvidia_smi_is_unavailable_with_a_reason(tmp_path):
    m, _ = _mgr(tmp_path, gpu=FakeGpu(available=False))
    m.follow_profile("p1")
    gpu = [o for o in m.status()["overlays"] if o["id"] == "gpu"][0]
    assert gpu["available"] is False and "nvidia-smi" in gpu["reason"] and gpu["on"] is False
    res = m.set("gpu", True)
    assert res["ok"] is False and "nvidia-smi" in res["error"]
    assert not m.any_on()
    assert not (tmp_path / "settings.json").exists()           # a refused toggle is never saved


def test_a_stored_gpu_choice_is_not_drawn_while_unavailable(tmp_path):
    m, _ = _mgr(tmp_path, gpu=FakeGpu(available=False))
    (tmp_path / "settings.json").write_text(
        json.dumps({"overlays": {"profiles": {"p1": {"gpu": True, "cpu": True}}}}), encoding="utf-8")
    m.follow_profile("p1")
    assert m.layer.enabled("cpu") and not m.layer.enabled("gpu")
    m.close()


def test_a_probe_that_gives_up_turns_the_overlay_off_in_the_next_status(tmp_path):
    gpu = FakeGpu()
    m, _ = _mgr(tmp_path, gpu=gpu)
    m.follow_profile("p1")
    m.set("gpu", True)
    assert m.layer.enabled("gpu")
    gpu.available, gpu.reason = False, "nvidia-smi is not answering"
    st = m.status()
    row = [o for o in st["overlays"] if o["id"] == "gpu"][0]
    assert row["on"] is False and row["available"] is False and not m.layer.enabled("gpu")
    m.close()


def test_cpu_and_ram_are_unavailable_when_the_platform_cannot_read_them(tmp_path):
    m, _ = _mgr(tmp_path, cpu=lambda: None, mem=lambda: None)
    m.follow_profile("p1")
    rows = {o["id"]: o for o in m.status()["overlays"]}
    assert rows["cpu"]["available"] is False and "CPU" in rows["cpu"]["reason"]
    assert rows["ram"]["available"] is False and "RAM" in rows["ram"]["reason"]
    assert rows["pomodoro"]["available"] is True
    assert m.set("cpu", True)["ok"] is False


def test_a_layout_without_the_row_is_unavailable(tmp_path):
    rows = dict(ROWS, pomodoro=ROWS["pomodoro"][:5])
    m, _ = _mgr(tmp_path, rows=rows)
    row = [o for o in m.status()["overlays"] if o["id"] == "pomodoro"][0]
    assert row["available"] is False and "shift row" in row["reason"]


def test_unknown_overlay_id_is_refused_without_raising(tmp_path):
    m, _ = _mgr(tmp_path)
    assert m.set("fan", True)["ok"] is False


def test_status_rows_carry_the_dashboard_contract_fields(tmp_path):
    m, _ = _mgr(tmp_path)
    m.follow_profile("p1")
    m.set("cpu", True)
    m.layer.set_value("cpu", 0.42)
    row = m.status()["overlays"][0]
    assert set(row) == {"id", "label", "row", "on", "available", "reason", "value"}
    assert row["label"] == "CPU" and row["row"] == "number row" and row["value"] == 0.42
    m.close()
```

- [ ] **Step 2: Run to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_manager.py`
Expected: failures `AttributeError: module 'overlays' has no attribute 'load_prefs'` / `OverlayManager`.

- [ ] **Step 3: Append to `overlays.py`** (after the samplers section):

```python
# ---- per-profile preferences (settings.json top-level key "overlays") ---------
PREFS_KEY = "overlays"
MAX_PROFILE_ID = 64


def _read_settings(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_prefs(path):
    """{"profiles": {profile id: {overlay id: bool}}, "pomodoro": {...}} with
    anything malformed dropped. The key is Aether-owned: the UI's own settings
    saves merge around it (Api.save_settings keeps unknown top-level keys)."""
    raw = _read_settings(path).get(PREFS_KEY)
    out = {"profiles": {}, "pomodoro": {}}
    if not isinstance(raw, dict):
        return out
    profs = raw.get("profiles")
    if isinstance(profs, dict):
        for pid, tog in profs.items():
            if isinstance(pid, str) and 0 < len(pid) <= MAX_PROFILE_ID and isinstance(tog, dict):
                out["profiles"][pid] = {k: bool(tog.get(k)) for k in IDS}
    pomo = raw.get("pomodoro")
    if isinstance(pomo, dict):
        out["pomodoro"] = {k: pomo[k] for k in ("workMin", "breakMin")
                           if isinstance(pomo.get(k), (int, float)) and not isinstance(pomo.get(k), bool)}
    return out


def toggles_for(prefs, pid):
    return dict({k: False for k in IDS}, **(prefs.get("profiles", {}).get(pid) or {}))


def pomodoro_seconds(prefs):
    """(work_s, break_s): settings workMin / breakMin clamped to 1..180 / 1..60, default 25 / 5."""
    p = prefs.get("pomodoro") or {}
    work = min(180.0, max(1.0, float(p.get("workMin", 25))))
    brk = min(60.0, max(1.0, float(p.get("breakMin", 5))))
    return work * 60.0, brk * 60.0


def save_toggle(path, lock, pid, oid, on):
    """Read-modify-write ONE toggle of one profile; every other settings key is kept."""
    with lock:
        data = _read_settings(path)
        block = data.get(PREFS_KEY) if isinstance(data.get(PREFS_KEY), dict) else {}
        profs = block.get("profiles") if isinstance(block.get("profiles"), dict) else {}
        tog = profs.get(pid) if isinstance(profs.get(pid), dict) else {}
        tog[oid] = bool(on)
        profs[pid] = tog
        block["profiles"] = profs
        data[PREFS_KEY] = block
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


# ---- manager -------------------------------------------------------------------
class OverlayManager:
    """Toggles (per profile, persisted), availability, the sampler lifecycle and
    the get_overlays payload."""

    def __init__(self, rows, all_indices, settings_path, lock, cpu=None, mem=None,
                 gpu=None, gate=None, clock=time.monotonic, interval=1.0):
        self._path, self._lock = settings_path, lock
        work, brk = pomodoro_seconds(load_prefs(settings_path))
        self.layer = OverlayLayer(rows, all_indices, Pomodoro(work, brk), clock)
        self.gpu = gpu if gpu is not None else GpuProbe()
        cpu = cpu if cpu is not None else read_cpu_counters
        mem = mem if mem is not None else read_memory_load
        self._sensor_ok = {"cpu": cpu() is not None, "ram": mem() is not None}
        self.sampler = Sampler(self.layer, cpu, mem, self.gpu, gate, interval)
        self.pid = None
        self._pref = {k: False for k in IDS}

    def availability(self, oid):
        if len(self.layer.rows.get(oid, [])) != len(ROW_CODES[oid]):
            return False, f"This keyboard has no complete {ROW_NAMES[oid]}"
        if oid in self._sensor_ok and not self._sensor_ok[oid]:
            return False, f"{LABELS[oid]} load is not available on this system"
        if oid == "gpu" and not self.gpu.available:
            return False, self.gpu.reason
        return True, None

    def _apply(self):
        for oid in IDS:
            self.layer.set_enabled(oid, self._pref[oid] and self.availability(oid)[0])
        if any(self.layer.enabled(k) for k in SENSOR_IDS):
            self.sampler.start()
        else:
            self.sampler.stop()

    def follow_profile(self, pid):
        self.pid = pid
        self._pref = toggles_for(load_prefs(self._path), pid)
        self._apply()

    def set(self, oid, on):
        if oid not in IDS:
            return {"ok": False, "error": f"unknown overlay {oid!r}"}
        on = bool(on)
        ok, reason = self.availability(oid)
        if on and not ok:
            return {"ok": False, "error": reason}
        self._pref[oid] = on
        save_toggle(self._path, self._lock, self.pid or "p1", oid, on)
        self._apply()
        return {"ok": True, "id": oid, "on": self.layer.enabled(oid)}

    def any_on(self):
        return self.layer.any_enabled()

    def status(self):
        self._apply()                       # picks up a probe that gave up
        st = self.layer.pomodoro_state()
        rows = []
        for oid in IDS:
            ok, reason = self.availability(oid)
            e = {"id": oid, "label": LABELS[oid], "row": ROW_NAMES[oid],
                 "on": self.layer.enabled(oid), "available": ok, "reason": reason,
                 "value": self.layer.value(oid) if oid in SENSOR_IDS
                 else (st.progress if st else None)}
            if oid == "pomodoro" and st:
                e["phase"], e["remaining_s"] = st.phase, int(math.ceil(st.remaining_s))
            rows.append(e)
        return {"overlays": rows,
                "pomodoro": {"phase": st.phase if st else None,
                             "remaining_s": int(math.ceil(st.remaining_s)) if st else None}}

    def close(self):
        self.sampler.stop()
```

- [ ] **Step 4: Run to see them pass**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_manager.py`
Expected: `15 passed`.

- [ ] **Step 5: Full suite, then commit**

Run: `<py> -m pytest -q -p no:cacheprovider` — expected `1067 passed, 15 skipped`.

```bash
git add overlays.py tests/test_overlays_manager.py
git commit -m "feat(overlays): per-profile toggles in settings.json and the OverlayManager" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Api bridge — `get_overlays`, `set_overlay`, `flash`, profile follow

**Files:**
- Modify: `app_web.py` (import; `Api.__init__`; `Api.select_board`; `Api.games_sync`; new methods before `# ---- host-driven multi-color effects`; `main()` exit)
- Modify: `flatpak/io.github.mrwhosnexus.AetherHE.yml` (cp list)
- Test: `tests/test_overlays_api.py` (also un-skips the Phase 5 contract test `test_phase6_overlay_bridge_matches_the_dashboard_contract`)

**Interfaces:**
- Consumes: Task 4 `OverlayManager`, Task 2 `engine.overlay`, existing `Api._fail`, `Api._settings_path()`, `_SETTINGS_LOCK`, `drivers` `.supports("host_effects")`.
- Produces: `Api.get_overlays()`, `Api.set_overlay(overlay_id, on)`, `Api.flash(color, ms=600)`; private `Api._ov_attach()`, `_ov_profile_id()`, `_ov_follow(state)`, `_ov_supported()`, `_stop_overlays()`, `_overlay_sync()` (a stub here; Task 6 makes it real); attributes `_overlays`, `_ov_profile`, `_carrier_on`, `_light_src`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_overlays_api.py` (its `_api(tmp_path)` builds an `Api` with `Api.__new__`, a real Win60 `KeyMap`, a real engine whose `send` collects frames, and a fake driver that records calls; Task 6 reuses `_api`, `_teardown`, `_wait` and the autouse `_fake_sensors` fixture from this file):

```python
"""Phase 6 / Task 5: the Api bridge for status-on-keys (get_overlays,
set_overlay, flash), per-profile follow, wiring to the engine. Fakes only: no
HID, no keyboard, no nvidia-smi."""
import json
import threading
import time

import pytest

import app_web
import boards
import device_state
import effects
import overlays


@pytest.fixture(autouse=True)
def _fake_sensors(monkeypatch):
    class Probe:
        available, reason = True, None
        def read(self): return 0.3
    monkeypatch.setattr(overlays, "GpuProbe", Probe)
    ticks = {"n": 0}

    def busy_cpu():                    # never idle: the load reads 100 % from the 2nd sample on
        ticks["n"] += 10
        return (0, ticks["n"])
    monkeypatch.setattr(overlays, "read_cpu_counters", busy_cpu)
    monkeypatch.setattr(overlays, "read_memory_load", lambda: 0.5)
    monkeypatch.setattr(overlays, "_run_nvidia_smi",
                        lambda exe: (_ for _ in ()).throw(AssertionError("real nvidia-smi")))


class FakeDev:
    dead_events = 0
    def __init__(self): self.open = True
    def is_open(self): return self.open
    def close(self): self.open = False


class FakeDriver:
    FEATURES = frozenset({"host_effects", "lighting"})

    def __init__(self):
        self.calls = []

    def supports(self, f): return f in self.FEATURES
    def begin_host_stream(self): self.calls.append(("begin",))
    def end_host_stream(self): self.calls.append(("end",))
    def stream_frame(self, colors, force=False): self.calls.append(("frame",))

    def set_lighting(self, mode, fg, bg=(0, 0, 0), brightness=4, speed=4, direction=0,
                     full_color=0, power_on=True):
        self.calls.append(("light", mode, tuple(fg), tuple(bg), brightness, speed, direction,
                           full_color, power_on))

    def set_per_key_rgb(self, colors, brightness=4, speed=4):
        self.calls.append(("paint", dict(colors), brightness, speed))

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


def _api(tmp_path, slug="aula-win60-he"):
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.board = boards.load_registry().by_slug(slug)
    a.km = device_state.KeyMap()
    a.dev = FakeDev()
    a.driver = FakeDriver()
    a.frames = []
    a.fx = effects.PerKeyEffectEngine(a.km, lambda f: a.frames.append(dict(f)))
    a._settings_path = lambda: str(tmp_path / "settings.json")
    a.reader = a.calib_reader = None
    a._reader_users = set()
    a._overlays = None
    a._ov_profile = None
    a._carrier_on = False
    a._light_src = None
    a._ov_attach()
    return a


def _wait(pred, secs=2.0):
    end = time.time() + secs
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def _teardown(a):
    a.fx.stop()
    a._stop_overlays()


def test_get_overlays_matches_the_dashboard_contract(tmp_path):
    a = _api(tmp_path)
    r = a.get_overlays()
    assert r["ok"] is True and r["supported"] is True
    assert [o["id"] for o in r["overlays"]] == ["cpu", "ram", "gpu", "pomodoro"]
    for o in r["overlays"]:
        assert {"id", "label", "row", "on", "available", "reason", "value"} <= set(o)
        assert o["on"] is False and o["available"] is True and o["reason"] is None
    assert r["pomodoro"] == {"phase": None, "remaining_s": None}
    _teardown(a)


def test_set_overlay_returns_the_contract_and_persists_for_the_active_profile(tmp_path):
    a = _api(tmp_path)
    assert a.set_overlay("cpu", True) == {"ok": True, "id": "cpu", "on": True}
    row = a.get_overlays()["overlays"][0]
    assert row["on"] is True
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["overlays"]["profiles"] == {"p1": {"cpu": True}}      # no profile known yet -> p1
    assert a.set_overlay("cpu", False) == {"ok": True, "id": "cpu", "on": False}
    _teardown(a)


def test_bad_arguments_and_unknown_ids_never_raise(tmp_path):
    a = _api(tmp_path)
    assert a.set_overlay("fan", True)["ok"] is False
    assert a.set_overlay(None, None)["ok"] is False
    assert a.set_overlay({"x": 1}, [])["ok"] is False
    _teardown(a)


def test_the_activated_profile_follows_games_sync(tmp_path):
    a = _api(tmp_path)
    a.games_sync({"activeProfile": "fps", "profiles": []})
    assert a.set_overlay("pomodoro", True)["ok"]
    a.games_sync({"activeProfile": "desk", "profiles": []})            # switch: all off
    rows = {o["id"]: o["on"] for o in a.get_overlays()["overlays"]}
    assert rows == {"cpu": False, "ram": False, "gpu": False, "pomodoro": False}
    a.set_overlay("cpu", True)
    a.games_sync({"activeProfile": "fps", "profiles": []})             # back: its own choice returns
    rows = {o["id"]: o["on"] for o in a.get_overlays()["overlays"]}
    assert rows["pomodoro"] is True and rows["cpu"] is False
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["overlays"]["profiles"] == {"fps": {"pomodoro": True}, "desk": {"cpu": True}}
    _teardown(a)


def test_games_sync_garbage_is_ignored_by_the_overlay_follow(tmp_path):
    a = _api(tmp_path)
    for bad in (None, "x", {}, {"activeProfile": 5}, {"activeProfile": ""}, {"activeProfile": "x" * 99}):
        a._ov_follow(bad)
    assert a._ov_profile is None
    _teardown(a)


def test_start_up_profile_comes_from_settings_json(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({
        "activeProfile": "fps",
        "overlays": {"profiles": {"fps": {"ram": True}}}}), encoding="utf-8")
    a = _api(tmp_path)
    rows = {o["id"]: o["on"] for o in a.get_overlays()["overlays"]}
    assert rows["ram"] is True and rows["cpu"] is False
    _teardown(a)


def test_a_board_without_host_effects_reports_unsupported(tmp_path):
    a = _api(tmp_path)
    a.driver.FEATURES = frozenset()
    assert a.get_overlays() == {"ok": True, "supported": False, "overlays": [],
                                "pomodoro": {"phase": None, "remaining_s": None}}
    assert a.set_overlay("cpu", True)["ok"] is False
    _teardown(a)


def test_the_2_4ghz_dongle_that_drops_stream_writes_is_unsupported(tmp_path):
    a = _api(tmp_path, slug="aula-mini60he-pro-24g")
    assert a.get_overlays()["supported"] is False
    _teardown(a)


def test_no_engine_means_unsupported_not_an_error(tmp_path):
    a = _api(tmp_path)
    a.fx = None
    a._ov_attach()
    assert a.get_overlays()["supported"] is False
    assert a.flash([1, 2, 3])["ok"] is False


def test_the_engine_gets_the_layer(tmp_path):
    a = _api(tmp_path)
    assert a.fx.overlay is a._overlays.layer
    old = a._overlays
    a._ov_attach()                                  # board switch: rebuilt, old sampler stopped
    assert a._overlays is not old and a.fx.overlay is a._overlays.layer
    _teardown(a)


def test_flash_needs_a_running_engine_and_validates_its_arguments(tmp_path):
    a = _api(tmp_path)
    assert a.flash([255, 0, 0])["ok"] is False                           # nothing streaming
    a.fx.start_zones([], global_bg=(0, 0, 0), base={})
    assert _wait(lambda: a.frames)
    assert a.flash([255, 0, 0], 800) == {"ok": True}
    assert _wait(lambda: any(max(v[0] for v in f.values()) > 200 for f in a.frames))
    for bad in (None, "red", [1, 2], ["a", "b", "c"]):
        assert a.flash(bad)["ok"] is False
    assert a.flash([1, 2, 3], "soon")["ok"] is False
    _teardown(a)


def test_pomodoro_state_is_reported_while_on(tmp_path):
    a = _api(tmp_path)
    a.set_overlay("pomodoro", True)
    r = a.get_overlays()
    assert r["pomodoro"]["phase"] == "work" and 1495 <= r["pomodoro"]["remaining_s"] <= 1500
    row = [o for o in r["overlays"] if o["id"] == "pomodoro"][0]
    assert row["on"] and row["phase"] == "work"
    _teardown(a)


def test_the_uis_settings_saves_keep_the_overlay_choices(tmp_path):
    a = _api(tmp_path)
    a.set_overlay("cpu", True)
    assert a.save_settings({"profiles": [{"id": "p1", "name": "Default", "state": {}}],
                            "activeProfile": "p1", "globals": {}})["ok"]
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["overlays"]["profiles"] == {"p1": {"cpu": True}}
    assert saved["activeProfile"] == "p1"
    _teardown(a)
```

- [ ] **Step 2: Run to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_api.py`
Expected: errors `AttributeError: ... has no attribute '_ov_attach'` (from the `_api` helper).

- [ ] **Step 3: Edit `app_web.py`** (five small anchored edits plus one new block):

3a. After `import analytics` add `import overlays`.

3b. In `Api.__init__`, directly after the line `        self.telemetry = self._make_telemetry()` add:

```python
        # Status on keys (overlays.py): the layer rides on the effect engine.
        self._overlays = None
        self._ov_profile = None     # active profile id, fed by games_sync
        self._carrier_on = False    # engine running ONLY to carry overlays
        self._light_src = None      # last firmware-lighting call, for the carrier
        self._ov_attach()
```

3c. In `Api.select_board`, directly after the statement that builds the new `self.fx` (the `... if self.km else None)` line that ends the `self.fx = (effects.PerKeyEffectEngine(` expression) and before the `# per-board caches must not leak across boards` comment, add `            self._ov_attach()`.

3d. In `Api.games_sync`, make the first statement of the method (right after its docstring) `        self._ov_follow(state)      # overlays are per profile; never raises`.

3e. In `main()`'s `finally:` block, after `        api._stop_games()` add `        api._stop_overlays()`.

3f. Insert this block immediately before the line `    # ---- host-driven multi-color effects (per-key, driver stream) ----`, followed by the stub shown after it (Task 6 replaces the stub):

```python
    # ---- status on keys: CPU / RAM / GPU bars, Pomodoro, flash (overlays.py) ----
    #
    # The layer is composited by the effect engine onto whatever it streams
    # (`fx.overlay`), so it works over every host effect. When the active
    # lighting is a FIRMWARE mode (static / Full-RGB / per-key paint / off) the
    # host engine is switched on as a "carrier" that reproduces it (see
    # overlays.carrier_plan) and switched off again, restoring the firmware
    # lighting with one write, when the last overlay goes off.
    def _ov_attach(self):
        """(Re)build the overlay manager for the current keymap + engine."""
        old = getattr(self, "_overlays", None)
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        self._overlays = None
        self._carrier_on = False
        try:
            if not (getattr(self, "fx", None) and getattr(self, "km", None)):
                return
            rows = {oid: self.km.indices_for_codes(codes)
                    for oid, codes in overlays.ROW_CODES.items()}
            mgr = overlays.OverlayManager(
                rows, self.fx.indices, self._settings_path(), _SETTINGS_LOCK,
                gpu=overlays.GpuProbe(), gate=lambda: self.dev.is_open())
            self._overlays = mgr
            self.fx.overlay = mgr.layer
            mgr.follow_profile(self._ov_profile_id())
        except Exception as e:
            log.warning("status-on-keys unavailable: %s", e)
            self._overlays = None

    def _ov_profile_id(self):
        pid = getattr(self, "_ov_profile", None)
        if isinstance(pid, str) and pid:
            return pid
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                pid = json.load(f).get("activeProfile")
        except Exception:
            pid = None
        return pid if isinstance(pid, str) and 0 < len(pid) <= overlays.MAX_PROFILE_ID else "p1"

    def _ov_follow(self, state):
        """games_sync calls this on every profile change (and at start-up)."""
        try:
            pid = state.get("activeProfile") if isinstance(state, dict) else None
            if (not isinstance(pid, str) or not 0 < len(pid) <= overlays.MAX_PROFILE_ID
                    or pid == getattr(self, "_ov_profile", None)):
                return
            self._ov_profile = pid
            mgr = getattr(self, "_overlays", None)
            if mgr is not None:
                mgr.follow_profile(pid)
                self._overlay_sync()
        except Exception as e:
            log.warning("overlay profile follow failed: %s", e)

    def _ov_supported(self):
        """Overlays need the host engine: a keymap, a driver that streams
        per-key frames, and a board whose registry does not forbid it."""
        try:
            if getattr(self, "_overlays", None) is None or not getattr(self, "fx", None):
                return False
            if not self.driver.supports("host_effects"):
                return False
            lt = getattr(self.board, "lighting", None) or {}
            return lt.get("hostEngine") is not False
        except Exception:
            return False

    def _stop_overlays(self):
        """main(): stop the sampler thread on the way out."""
        mgr = getattr(self, "_overlays", None)
        if mgr is not None:
            mgr.close()

    def get_overlays(self):
        """Dashboard "Status on keys" tile. -> {ok, supported, overlays:[{id,
        label, row, on, available, reason, value}], pomodoro:{phase,
        remaining_s}}; unsupported boards answer supported:false."""
        try:
            if not self._ov_supported():
                return {"ok": True, "supported": False, "overlays": [],
                        "pomodoro": {"phase": None, "remaining_s": None}}
            return dict(self._overlays.status(), ok=True, supported=True)
        except Exception as e:
            return self._fail(e)

    def set_overlay(self, overlay_id, on):
        """Turn one overlay on/off for the ACTIVE profile (persisted).
        -> {ok, id, on}."""
        try:
            if not self._ov_supported():
                return {"ok": False, "error": "status on keys needs a board with host effects"}
            res = self._overlays.set(str(overlay_id), bool(on))
            if not res.get("ok"):
                return res
            self._overlay_sync()
            return {"ok": True, "id": res["id"], "on": res["on"]}
        except Exception as e:
            return self._fail(e)

    def flash(self, color, ms=600):
        """Flash the whole board `color` ([r, g, b]) fading out over `ms`
        (50..5000). Needs the host engine to be streaming (a host effect or an
        overlay); firmware-only lighting answers ok:false."""
        try:
            if not (isinstance(color, (list, tuple)) and len(color) >= 3):
                return {"ok": False, "error": "color must be [r, g, b]"}
            rgb = tuple(int(c) for c in color[:3])
            fx = getattr(self, "fx", None)
            if not (self._ov_supported() and fx is not None and fx.is_running()):
                return {"ok": False, "error": "flash needs a host effect or a status overlay running"}
            self._overlays.layer.flash(rgb, int(ms))
            return {"ok": True}
        except (TypeError, ValueError) as e:
            return {"ok": False, "error": f"bad flash arguments: {e}"}
        except Exception as e:
            return self._fail(e)
```

```python
    def _overlay_sync(self):
        """Reconcile the engine with the toggles (Task 6 makes this real)."""
        return None

```

3g. In `flatpak/io.github.mrwhosnexus.AetherHE.yml` add `overlays.py` after `analytics.py` in the `cp -r ...` line.

- [ ] **Step 4: Run to see them pass**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_api.py tests/test_dashboard_ui_sources.py tests/test_packaging.py`
Expected: all pass; `test_phase6_overlay_bridge_matches_the_dashboard_contract` now runs (no longer skipped).

- [ ] **Step 5: Full suite, then commit**

Run: `<py> -m pytest -q -p no:cacheprovider` — expected `1081 passed, 14 skipped`.

```bash
git add app_web.py flatpak/io.github.mrwhosnexus.AetherHE.yml tests/test_overlays_api.py
git commit -m "feat(overlays): get_overlays / set_overlay / flash bridges, per-profile follow" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The carrier — overlays over static, per-key paint and lights-off

**Files:**
- Modify: `overlays.py` (add `carrier_plan` between the layer and the samplers sections)
- Modify: `app_web.py` (replace the `_overlay_sync` stub; `set_light`, `set_custom_colors`, `start_multicolor`, `start_zones`, `stop_multicolor`)
- Test: `tests/test_overlays_carrier.py`

**Interfaces:**
- Consumes: Task 5 (`_ov_supported`, `_overlays`, `_light_src`, `_carrier_on`), Task 2 (`PerKeyEffectEngine.start_zones(zones, global_bg, base)`), existing driver calls `begin_host_stream()`, `end_host_stream()`, `set_lighting(mode, fg, bg=, brightness=, speed=, direction=, full_color=, power_on=)`, `set_per_key_rgb(colors, brightness=, speed=)`.
- Produces: `overlays.carrier_plan(src, indices, bright_max=4) -> {"zones", "bg", "base"}`; `Api._overlay_active()`, `_bright_max()`, real `_overlay_sync()`, `_carrier_start()`, `_carrier_stop()`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_overlays_carrier.py`:

```python
"""Phase 6 / Task 6: overlays over firmware lighting. While an overlay is on
and the UI's lighting is a firmware mode (static / Full-RGB / per-key paint /
off), the host engine runs as a "carrier"; turning the last overlay off stops it
and re-sends the firmware lighting once. Fakes only: no HID, no keyboard."""
import time

import overlays
import pytest

# _fake_sensors is autouse: importing it registers it here (no real sensors / nvidia-smi).
from test_overlays_api import _api, _fake_sensors, _teardown, _wait  # noqa: F401


# ---- carrier_plan (pure) ---------------------------------------------------
IDX = [3, 4, 5]


def _light(**kw):
    p = {"mode": 0, "fg": (200, 100, 0), "bg": (0, 0, 20), "brightness": 4, "speed": 4,
         "direction": 0, "full_color": 0, "power_on": True}
    p.update(kw)
    return ("light", p)


def test_no_known_lighting_carries_black():
    assert overlays.carrier_plan(None, IDX) == {"zones": [], "bg": (0, 0, 0), "base": {}}


def test_static_firmware_colour_is_reproduced_per_key():
    plan = overlays.carrier_plan(_light(), IDX, bright_max=4)
    assert plan["zones"] == [] and plan["base"] == {i: (200, 100, 0) for i in IDX}
    assert plan["bg"] == (0, 0, 20)


def test_firmware_brightness_steps_scale_the_colour():
    plan = overlays.carrier_plan(_light(brightness=2), IDX, bright_max=4)
    assert plan["base"][3] == (100, 50, 0)
    plan = overlays.carrier_plan(_light(brightness=5), IDX, bright_max=5)      # MINI-style scale
    assert plan["base"][3] == (200, 100, 0)
    assert overlays.carrier_plan(_light(brightness=99), IDX, 4)["base"][3] == (200, 100, 0)


def test_lights_off_carries_black_so_the_bars_still_show():
    assert overlays.carrier_plan(_light(power_on=False), IDX) == {
        "zones": [], "bg": (0, 0, 0), "base": {}}


def test_full_rgb_firmware_mode_becomes_a_rainbow_wave():
    plan = overlays.carrier_plan(_light(full_color=1, brightness=4), IDX, 4)
    z = plan["zones"][0]
    assert z["mode"] == "wave" and z["indices"] == IDX and z["palette"] == overlays.RAINBOW
    assert z["bright"] == 1.0 and plan["base"] == {}


def test_per_key_paint_is_reproduced_and_other_keys_are_dark():
    src = ("custom", {3: (255, 0, 0), 4: (0, 255, 0)}, 4, 4)
    plan = overlays.carrier_plan(src, IDX, 4)
    assert plan["base"] == {3: (255, 0, 0), 4: (0, 255, 0)} and plan["zones"] == []
    half = overlays.carrier_plan(("custom", {3: (255, 0, 0)}, 2, 4), IDX, 4)
    assert half["base"] == {3: (128, 0, 0)}


# ---- the Api carrier ---------------------------------------------------------
LIGHT = (0, 200, 100, 0, 4, 4, 0, 0, 20, 0, True, 0)       # set_light positional args


def test_without_overlays_set_light_goes_straight_to_the_firmware(tmp_path):
    a = _api(tmp_path)
    assert a.set_light(*LIGHT) == {"ok": True}
    assert a.driver.named("light") == [("light", 0, (200, 100, 0), (0, 0, 20), 4, 4, 0, 0, True)]
    assert a.driver.named("begin") == [] and not a.fx.is_running() and a._carrier_on is False
    _teardown(a)


def test_turning_an_overlay_on_over_static_starts_the_carrier(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.driver.calls.clear()
    assert a.set_overlay("cpu", True)["ok"]
    assert a.fx.is_running() and a._carrier_on is True
    assert a.driver.named("begin") == [("begin",)]
    assert a.driver.named("light") == []                           # firmware not touched
    assert _wait(lambda: a.frames)
    f = a.frames[-1]
    row = a.km.indices_for_codes(overlays.ROW_CODES["cpu"])
    other = a.km.index_of_code["Space"]
    assert f[other] == (200, 100, 0)                                # static colour carried
    assert all(f[i] == overlays.TRACK for i in row)                 # bar track (no reading yet)
    _teardown(a)


def test_last_overlay_off_stops_the_carrier_and_restores_the_firmware_once(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.set_overlay("cpu", True)
    a.set_overlay("ram", True)
    a.driver.calls.clear()
    a.set_overlay("cpu", False)
    assert a.fx.is_running()                                        # ram still on
    assert a.driver.named("light") == []
    a.set_overlay("ram", False)
    assert not a.fx.is_running() and a._carrier_on is False
    assert a.driver.named("light") == [("light", 0, (200, 100, 0), (0, 0, 20), 4, 4, 0, 0, True)]
    assert a.driver.named("end") == [("end",)]
    _teardown(a)


def test_ui_lighting_changes_while_overlays_are_on_are_carried_not_written(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.set_overlay("gpu", True)
    a.driver.calls.clear()
    a.stop_multicolor()                                             # the UI's usual first step
    assert a._carrier_on is False and not a.fx.is_running()
    a.set_light(0, 0, 0, 255, 4, 4, 0, 0, 0, 0, True, 0)           # then the new colour
    assert a._carrier_on is True and a.fx.is_running()
    assert a.driver.named("light") == []
    assert _wait(lambda: a.frames and a.frames[-1][a.km.index_of_code["Space"]] == (0, 0, 255))
    a.set_overlay("gpu", False)
    assert a.driver.named("light") == [("light", 0, (0, 0, 255), (0, 0, 0), 4, 4, 0, 0, True)]
    _teardown(a)


def test_a_host_effect_started_by_the_ui_is_never_touched_by_the_toggles(tmp_path):
    a = _api(tmp_path)
    assert a.start_multicolor("wave", [[255, 0, 0]], [0, 0, 0], 80, 60, 0, "v")["ok"]
    assert a._carrier_on is False
    a.driver.calls.clear()
    a.set_overlay("cpu", True)
    assert a.fx.is_running() and a._carrier_on is False
    assert a.driver.named("begin") == []                            # no restart, no extra write
    a.set_overlay("cpu", False)
    assert a.fx.is_running() and a.driver.named("light") == []      # the wave keeps going
    _teardown(a)


def test_overlays_draw_over_a_host_effect(tmp_path):
    a = _api(tmp_path)
    a.start_multicolor("wave", [[255, 0, 0]], [0, 0, 0], 80, 60, 0, "v")
    a.set_overlay("cpu", True)
    row = a.km.indices_for_codes(overlays.ROW_CODES["cpu"])
    assert _wait(lambda: a.frames and all(a.frames[-1][i] == overlays.color_for("cpu", 1.0) for i in row))
    _teardown(a)


def test_per_key_paint_is_carried_and_restored(tmp_path):
    a = _api(tmp_path)
    q = a.km.index_of_code["Q"]
    assert a.set_custom_colors({"Q": [255, 0, 0]}, 4, 4)["ok"]
    assert a.driver.named("paint") == [("paint", {q: (255, 0, 0)}, 4, 4)]
    a.driver.calls.clear()
    a.set_overlay("pomodoro", True)
    assert a._carrier_on and a.driver.named("paint") == []
    a.set_overlay("pomodoro", False)
    assert a.driver.named("paint") == [("paint", {q: (255, 0, 0)}, 4, 4)]
    _teardown(a)


def test_lights_off_still_shows_the_bars(tmp_path):
    a = _api(tmp_path)
    a.set_light(0, 255, 255, 255, 4, 4, 0, 0, 0, 0, False, 0)      # power off
    a.set_overlay("cpu", True)
    assert _wait(lambda: a.frames)
    other = a.km.index_of_code["Space"]
    assert a.frames[-1][other] == (0, 0, 0)
    a.set_overlay("cpu", False)
    assert a.driver.named("light")[-1][-1] is False                 # off is restored as off
    _teardown(a)


def test_no_known_lighting_restores_nothing(tmp_path):
    a = _api(tmp_path)
    a.set_overlay("cpu", True)
    assert a._carrier_on
    a.driver.calls.clear()
    a.set_overlay("cpu", False)
    assert a.driver.named("light") == [] and a.driver.named("paint") == []
    _teardown(a)


def test_offline_board_defers_the_carrier(tmp_path):
    a = _api(tmp_path)
    a.dev.open = False
    assert a.set_overlay("cpu", True)["ok"]
    assert not a.fx.is_running() and a._carrier_on is False
    a.dev.open = True
    a.set_light(*LIGHT)                                             # the UI re-sends on connect
    assert a.fx.is_running() and a._carrier_on is True
    _teardown(a)


def test_switching_profiles_to_one_without_overlays_hands_the_firmware_back(tmp_path):
    a = _api(tmp_path)
    a.games_sync({"activeProfile": "fps"})
    a.set_light(*LIGHT)
    a.set_overlay("cpu", True)
    assert a._carrier_on
    a.driver.calls.clear()
    a.games_sync({"activeProfile": "desk"})                         # desk has no overlays
    assert not a.fx.is_running()
    assert len(a.driver.named("light")) == 1
    _teardown(a)


def test_disconnect_style_stop_leaves_no_carrier_flag(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.set_overlay("cpu", True)
    a.stop_multicolor()
    assert a._carrier_on is False and not a.fx.is_running()
    _teardown(a)


def test_carrier_frame_rate_is_the_engines_normal_cap(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a.set_overlay("cpu", True)
    t0 = time.time()
    n0 = len(a.frames)
    time.sleep(0.5)
    rate = (len(a.frames) - n0) / (time.time() - t0)
    assert rate <= a.fx.fps + 5                                     # never above the existing cap
    _teardown(a)
```

- [ ] **Step 2: Run to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_carrier.py`
Expected: failures `AttributeError: module 'overlays' has no attribute 'carrier_plan'` and carrier assertions failing.

- [ ] **Step 3: Add `carrier_plan` to `overlays.py`**, a new section between `OverlayLayer` and `# ---- samplers`:

```python
# ---- carrier: a host rendering of the firmware lighting the overlays sit on ----
def carrier_plan(src, indices, bright_max=4):
    """What the host engine should stream while overlays are on but the UI's
    lighting is a firmware mode (static / Full-RGB / per-key paint / off).
    `src` is what Api.set_light / set_custom_colors last saw:
      ("light", {fg, bg, brightness, speed, power_on, full_color, ...}),
      ("custom", {device index: rgb}, brightness) or None.
    Returns {"zones": [...], "bg": rgb, "base": {index: rgb}}."""
    black = {"zones": [], "bg": (0, 0, 0), "base": {}}
    if not src:
        return black
    scale = lambda v: min(1.0, max(0.0, float(v) / float(bright_max or 1)))
    if src[0] == "custom":
        s = scale(src[2])
        return {"zones": [], "bg": (0, 0, 0),
                "base": {int(i): mix((0, 0, 0), tuple(c[:3]), s) for i, c in src[1].items()}}
    p = src[1]
    if not p.get("power_on", True):
        return black
    s = scale(p.get("brightness", bright_max))
    if p.get("full_color"):
        zone = {"indices": list(indices), "mode": "wave", "palette": list(RAINBOW),
                "bg": (0, 0, 0), "speed": 0.5, "bright": s, "direction": 0}
        return {"zones": [zone], "bg": (0, 0, 0), "base": {}}
    fg = mix((0, 0, 0), tuple(p["fg"][:3]), s)
    return {"zones": [], "bg": mix((0, 0, 0), tuple(p.get("bg", (0, 0, 0))[:3]), s),
            "base": {int(i): fg for i in indices}}
```

- [ ] **Step 4: Edit `app_web.py`.** Replace the `_overlay_sync` stub from Task 5 with these methods (same place):

```python
    def _overlay_active(self):
        """Overlays on AND drawable (supported board, at least one toggle on)."""
        mgr = getattr(self, "_overlays", None)
        return bool(mgr is not None and mgr.any_on() and self._ov_supported())

    def _bright_max(self):
        lt = getattr(self.board, "lighting", None) or {}
        return int(lt.get("brightnessMax", 4) or 4)

    def _overlay_sync(self):
        """Reconcile the engine with the toggles. Overlays on and nothing
        streaming -> start the carrier; every overlay off while the carrier
        runs -> stop it and give the firmware lighting back. A host effect the
        UI started is never touched: the layer simply stops drawing."""
        try:
            fx = getattr(self, "fx", None)
            if fx is None or getattr(self, "_overlays", None) is None:
                return
            if self._overlay_active():
                if not fx.is_running() and self.dev.is_open():
                    self._carrier_start()
            elif getattr(self, "_carrier_on", False):
                self._carrier_stop()
        except Exception as e:
            log.warning("overlay carrier sync failed: %s", e)

    def _carrier_start(self):
        """Stream a host rendering of the last firmware lighting (black when
        none is known) with the overlay layer on top."""
        plan = overlays.carrier_plan(getattr(self, "_light_src", None), self.fx.indices,
                                     self._bright_max())
        self.driver.begin_host_stream()
        self.fx.start_zones(plan["zones"], global_bg=plan["bg"], base=plan["base"])
        self._carrier_on = True

    def _carrier_stop(self):
        """Stop the carrier and re-send the firmware lighting the UI last asked
        for: one set_lighting (or per-key table) write, the same bytes the UI
        itself would have sent."""
        self._carrier_on = False
        self.fx.stop()
        try:
            self.driver.end_host_stream()
        except Exception:
            pass
        src = getattr(self, "_light_src", None)
        if not src or not self.dev.is_open():
            return
        if src[0] == "light":
            p = src[1]
            self.driver.set_lighting(p["mode"], p["fg"], bg=p["bg"], brightness=p["brightness"],
                                     speed=p["speed"], direction=p["direction"],
                                     full_color=p["full_color"], power_on=p["power_on"])
        elif src[0] == "custom":
            self.driver.set_per_key_rgb(dict(src[1]), brightness=src[2], speed=src[3])
```

Then four touch-ups:

4a. `Api.set_light` — record the call, and while overlays are on let the carrier hold it instead of writing the firmware. Replace the body of the `try:` (everything from `self.driver.set_lighting(` through `return {"ok": True}`) with:

```python
            p = {"mode": int(mode), "fg": (int(r), int(g), int(b)),
                 "bg": (int(bg_r), int(bg_g), int(bg_b)),
                 "brightness": int(brightness), "speed": int(speed),
                 "direction": int(direction), "full_color": int(full_color),
                 "power_on": bool(power_on)}
            self._light_src = ("light", p)
            if self._overlay_active():
                # Status overlays are on: the host engine carries this lighting
                # (the firmware gets it back when the overlays go off).
                self._carrier_start()
                return {"ok": True}
            self.driver.set_lighting(
                p["mode"], p["fg"], bg=p["bg"], brightness=p["brightness"],
                speed=p["speed"], direction=p["direction"],
                full_color=p["full_color"], power_on=p["power_on"])
            return {"ok": True}
```

4b. `Api.set_custom_colors` — directly after the `if not colors_by_index: return {"ok": False, "error": "no colors"}` guard, as the first statements inside the following `try:` (before `self.driver.set_per_key_rgb(`), add:

```python
            self._light_src = ("custom", dict(colors_by_index), int(brightness), int(speed))
            if self._overlay_active():
                self._carrier_start()
                return {"ok": True, "keys": len(colors_by_index)}
```

4c. `Api.start_multicolor` and `Api.start_zones` — a UI host effect takes the engine over from the carrier: after the `self.fx.start(...)` call and after the `self.fx.start_zones(norm, global_bg=gbg)` call respectively, add `            self._carrier_on = False` (before the `return {"ok": True, ...}`).

4d. `Api.stop_multicolor` — first statement of the method: `        self._carrier_on = False      # the engine (carrier or not) goes down`.

- [ ] **Step 5: Run to see them pass**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_carrier.py tests/test_overlays_api.py`
Expected: `19 passed` + `13 passed`. Run the carrier file three times to catch timing flakes (all waits are 2 s polls, the sampler tick is 1 s).

- [ ] **Step 6: Full suite, then commit**

Run: `<py> -m pytest -q -p no:cacheprovider` — expected `1100 passed, 14 skipped` (existing `set_light` / lighting tests in `test_wiring_matrix.py` and `test_drivers.py` must be unchanged: with no overlay on, `set_light` writes exactly what it wrote before).

```bash
git add overlays.py app_web.py tests/test_overlays_carrier.py
git commit -m "feat(overlays): carrier - overlays over static, per-key paint and lights-off, firmware lighting restored once" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Dashboard chip shows the Pomodoro countdown

**Files:**
- Modify: `ui/runtime_src/workspaces/dashboard.jsx` (`overlayText` helper, chip, export)
- Modify: `tests/test_dashboard_ui_sources.py` (export set)
- Modify (rebuilt): `ui/index_runtime.html`, `ui/runtime_src/build/ws_dashboard.js`
- Test: `tests/test_overlays_ui_sources.py`

**Interfaces:**
- Consumes: the `get_overlays` rows from Task 5 (the pomodoro row carries `phase` and `remaining_s` when on).
- Produces: `window.AetherDashboard.overlayText(o) -> string`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_overlays_ui_sources.py`:

```python
"""Phase 6 / Task 7: the Dashboard's "Status on keys" chips show the Pomodoro
phase + countdown (pure helper, run in node when installed)."""
import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")
NODE = shutil.which("node")

HARNESS = r"""
const fs = require("fs");
global.window = { AetherKeyboard: { KB_ROWS: [], KeyboardPanel() {} } };
global.React = { useState() {}, useEffect() {}, useMemo() {}, createElement() {} };
global.localStorage = { getItem() { return null; }, setItem() {} };
require("vm").runInThisContext(fs.readFileSync(process.argv[2], "utf8"), { filename: process.argv[2] });
const T = window.AetherDashboard.overlayText;
console.log(JSON.stringify([
  T({ id: "cpu", label: "CPU", on: true, value: 0.234 }),
  T({ id: "cpu", label: "CPU", on: false, value: null }),
  T({ id: "gpu", label: "GPU", on: false, available: false, value: null }),
  T({ id: "pomodoro", label: "Pomodoro", on: true, value: 0.4, phase: "work", remaining_s: 754 }),
  T({ id: "pomodoro", label: "Pomodoro", on: true, phase: "break", remaining_s: 59 }),
  T({ id: "pomodoro", label: "Pomodoro", on: false, value: 0.4, phase: "work", remaining_s: 754 }),
  T({ id: "pomodoro", label: "Pomodoro", on: true, value: 0.4 }),
]));
"""


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_chip_uses_the_helper_and_the_helper_is_exported():
    dash = _read("workspaces", "dashboard.jsx")
    assert "{overlayText(o)}" in dash
    assert "overlayView, overlayText," in dash
    assert "const overlayText = (o) => {" in dash


def test_built_dashboard_carries_the_helper():
    assert "overlayText" in _read("build", "ws_dashboard.js")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_chip_text(tmp_path):
    h = tmp_path / "h.cjs"
    h.write_text(HARNESS, encoding="utf-8")
    out = subprocess.run([NODE, str(h), os.path.join(SRC, "build", "ws_dashboard.js")],
                         check=True, capture_output=True, text=True, encoding="utf-8")
    assert json.loads(out.stdout) == ["CPU 23%", "CPU", "GPU", "Focus 12:34", "Break 0:59",
                                      "Pomodoro", "Pomodoro"]
```

and in `tests/test_dashboard_ui_sources.py` change the expected export set in `test_dashboard_exports_the_page_and_helpers` to end `"overlayView", "overlayText"}`.

- [ ] **Step 2: Run to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_ui_sources.py tests/test_dashboard_ui_sources.py`
Expected: the new tests and the export-set test fail.

- [ ] **Step 3: Edit `dashboard.jsx`.** Directly above `const readHero = () =>` add:

```js
// Chip text: a running Pomodoro shows its phase and countdown, the sensors their load.
const overlayText = (o) => {
  if (o.id === "pomodoro" && o.on && typeof o.remaining_s === "number") {
    const sec = Math.max(0, Math.floor(o.remaining_s));
    return `${o.phase === "break" ? "Break" : "Focus"} ${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
  }
  return `${o.label}${typeof o.value === "number" && o.id !== "pomodoro" ? ` ${Math.round(o.value * 100)}%` : ""}`;
};

```

In `OverlaysPanel`, replace the chip body `{o.label}{typeof o.value === "number" ? ` ${Math.round(o.value * 100)}%` : ""}` with `{overlayText(o)}`. In the `window.AetherDashboard = {...}` export add `overlayText,` after `overlayView,`.

- [ ] **Step 4: Rebuild and verify**

Run: `<py> ui\runtime_src\build_runtime.py`, then `git diff --ignore-cr-at-eol --stat` (expect only `ui/index_runtime.html`, `ui/runtime_src/build/ws_dashboard.js`, `dashboard.jsx` and the test), `git checkout -- <any other build file>`, then `node --check ui/runtime_src/build/ws_dashboard.js`.
Run: `<py> -m pytest -q -p no:cacheprovider tests/test_overlays_ui_sources.py tests/test_dashboard_ui_sources.py tests/test_ui_sources.py`
Expected: all pass (the node test is skipped without node).

- [ ] **Step 5: Full suite, then commit**

Run: `<py> -m pytest -q -p no:cacheprovider` — expected `1103 passed, 14 skipped`.

```bash
git add ui/runtime_src/workspaces/dashboard.jsx ui/runtime_src/build/ws_dashboard.js ui/index_runtime.html tests/test_overlays_ui_sources.py tests/test_dashboard_ui_sources.py
git commit -m "feat(ui): dashboard Status-on-keys chip shows the Pomodoro phase and countdown" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Docs, full suite, status

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/roadmap-status.md`

- [ ] **Step 1: `CLAUDE.md`.** In the Architecture list add after the `effects.py` bullet:

```text
- `overlays.py` — "status on keys" (roadmap Phase 6): CPU bar (number row 1-0), RAM bar (Q-P), GPU bar (home row, `nvidia-smi` only), Pomodoro 25/5 progress (shift row, whole-board pulse at each phase change) and `flash(color, ms)`, composited by `effects.PerKeyEffectEngine.overlay` onto whatever the engine streams (fixed colours, opaque bars, no extra frame rate). 1 s sampler thread (ctypes `GetSystemTimes` / `GlobalMemoryStatusEx`, no psutil), only while a sensor overlay is on and the keyboard handle is open. Per-profile flags live in `settings.json` top-level `overlays` (Aether-owned; optional `pomodoro.workMin/breakMin`). Over firmware lighting (static / Full-RGB / per-key paint / off) `Api.set_light` / `set_custom_colors` record the UI's call and a host-engine "carrier" reproduces it; the last overlay going off re-sends the firmware lighting once. Bridges: `get_overlays` / `set_overlay` (the dashboard tile's contract), `flash`. Tests inject sensors and the `nvidia-smi` runner; nothing here touches HID.
```

- [ ] **Step 2: Full suite**

Run: `<py> -m pytest -q -p no:cacheprovider`
Expected: `1103 passed, 14 skipped`, zero failures.

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: record the Phase 6 status-on-keys overlays in the architecture notes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Status entry.** Insert into `docs/superpowers/roadmap-status.md`, ABOVE `## Waiting on the user`, a dated implementer entry in the file's format (<= 15 lines): commits; decisions later phases must respect (`engine.overlay` hook and its `apply(frame, now)` contract, the carrier and `Api._light_src`, the `overlays` settings key, `flash`, the bridge contract unchanged plus the additive pomodoro fields); gotchas (Phase 7's `music` effect also streams through the engine, so overlays will draw over it automatically); pointer to the hardware checks below. Do not duplicate user bullets the planner already queued. Commit it alone:

```bash
git add docs/superpowers/roadmap-status.md
git commit -m "docs(status): phase 6 status on keys done" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Hardware checks (for the orchestrator → `docs/HARDWARE_TEST_CHECKLIST.md` under `## Roadmap 2026-11-04`)

1. Dashboard, WIN60 connected, lighting = **Static** colour: tick **CPU**. The number row `1`..`0` becomes a bar (dim track + load colour), the rest of the board keeps the static colour at the same brightness. Run a CPU stress (e.g. a few `python -c "while 1: pass"`): the bar climbs within ~2 s, green -> amber -> red. Untick: the board returns to exactly the static colour (compare brightness before/after).
2. Same with **RAM** (Q..P, blue/violet at normal use, magenta-red only near full) and **GPU** on an NVIDIA machine (home row; load a game or a GPU benchmark). On a machine without `nvidia-smi` the GPU chip is disabled with the reason, and a hand-edited "gpu: true" does nothing.
3. Lighting = a busy effect (Wave / Rain / Fireworks): the bars sit on top, opaque, readable; the rest of the effect keeps animating at its usual smoothness. Press-reactive effects (Reactive / Pressure) still react on the other rows. Typing feel and the Dashboard's CPU use are unchanged with CPU+RAM+GPU all on (check Task Manager for Aether and for `nvidia-smi.exe` flicker: no console window may ever appear).
4. **Pomodoro**: tick it; the shift row fills left to right over 25 min (to test quicker, set `"overlays": {"pomodoro": {"workMin": 1, "breakMin": 1}}` in `%LOCALAPPDATA%\AetherHE\settings.json` while Aether is closed). At the work -> break change the whole board pulses green for ~0.7 s, then the row restarts in green; break -> work pulses orange-red. The chip reads `Focus 24:30` / `Break 0:45`. Untick and tick again: the cycle restarts.
5. **Per profile**: with two profiles, tick CPU on one only; switch profiles from the profile menu: the bar appears/disappears with the profile and the tile chips follow within 2 s. A game-profile auto-switch (Phase 3) does the same. Restart Aether: choices are remembered.
6. Lighting **off** (power toggle) with CPU on: the board is dark except the bar. Untick: still off.
7. Lighting = **Custom** (per-key paint, no zones): tick CPU, the paint stays on the other keys; untick: the paint is back exactly (re-check a few colours).
8. Change lighting while an overlay is on (colour, brightness, effect -> static -> effect): each change applies immediately; no flicker to a stale colour; switching to a host effect and back keeps the bar.
9. Unplug the keyboard with overlays on, plug it back in: after reconnect the bar returns (the UI re-sends lighting); while unplugged `nvidia-smi.exe` is not being started (Process Explorer).
10. Kill Aether (end task) with an overlay on: the keyboard keeps showing the last frame (same as any host effect today); relaunch restores normal lighting. Note whether the board kept the bar after a power cycle (the host stream writes per-key slot 0, like every host effect).
11. `flash`: from a Python console attached to the running app (or a throwaway script calling `Api.flash([255,0,0], 800)`), the whole board flashes red and fades in ~0.8 s over a host effect and over a running overlay; with plain Static and no overlay it answers `ok: false`.
12. Leave CPU+RAM on for 30 minutes: Aether's own CPU stays near the Dashboard idle baseline; no memory growth; no stuck pulse after the machine sleeps and wakes in the middle of a Pomodoro phase.
