# Phase 2: Pressure Lighting + Travel Test Actuation Marker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a host lighting effect `"pressure"` whose per-key colour follows live key depth (0 mm background, actuation point palette midpoint, bottom-out full, ~120 ms decay after release), and draw each key's actuation point on the Travel Test keyboard so the user can dial actuation in by eye.

**Architecture:** `effects.py` gets one new generator `_g_pressure` plus a pure helper `pressure_level(mm, act)`; it reads the same per-frame `engine._depths` snapshot the other press-reactive effects use (so it is simply added to `PRESS_REACTIVE`) and a per-key actuation map the engine pulls from a new optional `engine.get_actuation()` source. `Api` keeps that map (`_act_mm`) filled from the firmware read-back (`verify_actuation`) and from successful actuation writes. The UI lists gain the new effect id; the tester's `Key` component draws a 2 px line at the key's actuation height using the per-key value the UI already holds (`perKeyActuation`).

**Tech Stack:** Python 3 stdlib only (`statistics`, `math`), pytest, the existing React/Tailwind UI (precompiled by `ui/runtime_src/build_runtime.py`).

**Spec:** `docs/superpowers/specs/2026-11-04-win60-roadmap-design.md` (section "Phase 2"). Read it and `docs/superpowers/roadmap-status.md` (Phase 1 decisions: build readers only via `Api._make_live_reader`; the shared reader is kept alive by owner `"telemetry"`) before starting.

## Global Constraints

- Windows is the shipping target; nothing may break Linux (guard Windows-only code by `sys.platform`, degrade to "unavailable" elsewhere). Phase 2 is platform-neutral pure Python + JSX; add no platform code.
- **No HID writes during development or tests. Never run the app against the keyboard.** Fakes only (patterns: `tests/test_travel_release.py`, `tests/test_socd_clear.py`, `tests/test_stats_api.py`). Hardware checks are listed at the end of this plan for the orchestrator.
- No push, merge into other branches, tag, release, or install. No network during development or tests.
- Python: `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe` (written `<py>` below). Full suite: `<py> -m pytest -q -p no:cacheprovider` (766 passing, 12 skipped at the start of this phase); must stay green at every commit.
- JSX changes need `<py> ui\runtime_src\build_runtime.py`; commit the regenerated `ui/index_runtime.html` + only the `ui/runtime_src/build/*.js` files with real (non-line-ending) diffs. Check with `git diff --ignore-cr-at-eol --stat` and `git checkout --` every build file that shows only in plain `git diff --stat`.
- UI: edit `ui/runtime_src/src/*.jsx` / `ui/runtime_src/workspaces/*.jsx`, never `vendor/`. No raw-HTML sinks (`dangerouslySetInnerHTML`, `innerHTML`). Match the existing look (Tailwind classes, CSS vars `--text`, `--accent`, `--line`, `--ink`). Watch block comments: `tests/test_ui_sources.py` checks they close.
- New Python dependencies: **none** in Phase 2.
- **Privacy anti-goal:** Aether must never become a keylogger. This phase stores nothing: depth is used for the current frame only; no sequences, text, or per-keystroke timestamps are kept anywhere.
- Bridge methods return `{"ok": bool, ...}` and never raise to JS (follow `Api._fail`). Phase 2 adds no bridge methods.
- Do NOT touch `service/server.py`, `updater.py`, `Api.open_submission_url`, `.github/workflows/board-bot.yml`, or the Pillow pin.
- `git add` only the files you changed (other agents leave untracked files in this worktree). Never use `git stash`.
- Every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Working-tree sources are CRLF. If the Edit tool cannot match a multi-line `old_string`, do the same replacement with a short Python snippet (`open(p, newline="")`, replace on `\n`-normalised text, convert back to `\r\n` if the file had them).
- Context limit: if your context approaches ~400k tokens, stop: commit only what is green, append a status entry to `docs/superpowers/roadmap-status.md` saying exactly where you stopped, and return.

## Design decisions (resolved; do not re-decide)

1. **Where depth state lives, and how it is fed.** No new store, no new thread. Every frame `PerKeyEffectEngine._run` sets `self._depths = get_depths()`; for press-reactive effects `Api._ensure_reactive` makes `get_depths` = `LiveReader.snapshot_by_index()` (`{device index: mm}`, one `dict()` copy, atomic under the GIL, key absent = released). `_g_pressure` reads `self._depths` only. Its own smoothing state is `z.state["lvl"]` (`{idx: level 0..1}`, written only by the engine thread, one entry per key of the zone), `z.state["ramp"]` (colour LUT, built once per zone run) and `z.state["t"]`.
2. **Grouped with the press-reactive effects.** `"pressure"` is appended to `effects.PRESS_REACTIVE` (single source of truth; `app_web._ensure_reactive` and `play_effect.py` both read it). `_ensure_reactive` therefore acquires owner `"reactive"` on the shared reader through `_make_live_reader` (Phase 1: the same reader also feeds telemetry; owners coexist). It also now sets `fx.get_actuation`. Zone mode lists get it too (`_ensure_reactive` already receives every zone's mode).
3. **Level mapping** (`effects.pressure_level(mm, act, max_mm=3.40)`): `mm < 0.05` (LiveReader noise floor, also NaN/negative) -> 0.0; `mm >= 3.40` -> 1.0; with `act` clamped to `[0.08, 3.30]`: `mm < act` -> `0.5 * mm / act`, else `0.5 + 0.5 * (mm - act) / (3.40 - act)`. So 0 = released, 0.5 = exactly at that key's actuation point, 1.0 = bottomed out, linear in between.
4. **Colour ramp.** Per zone, a 65-entry LUT: entry `k` (`u = k/64`) = `_scale(_lerp(bg, G(u), u), bright)` where `G` is the palette as a NON-looping gradient (first colour at `u=0`, last at `u=1`; a single colour is constant). So level 0 is exactly `_scale(bg, bright)` ("0 -> background"), level 1 is exactly the last palette colour ("full"), level 0.5 is the palette midpoint `G(0.5)` blended halfway from the background. The palette is already gamma-corrected by `Zone`; the background stays linear (same as every other effect). The per-key lookup is `ramp[int(level * 64 + 0.5)]`.
5. **Decay.** Instant attack (a deeper level is taken the same frame); the level may FALL by at most `dt / 0.12 s` per frame (`PRESSURE_DECAY_S`), so a full-scale release is dark in 120 ms, a partial ease-off follows the finger down smoothly, and the result is frame-rate independent (uses the engine clock `t`, like `_g_reactive`). `dt = 0` or a backwards clock decays nothing; a long stall drops straight to the target. A key can never stick: any key absent from the depth snapshot has target 0 and falls to the background within 120 ms. Real-world note: the firmware often stops reporting mid-travel on release and `LiveReader` clears the key only after `RELEASE_SILENCE_S = 0.15`, so the worst case from physical release to dark is about 0.27 s. `LiveReader` timing is NOT changed (Phase 1 telemetry depends on it).
6. **"Actuation point" per key, and the fallback.** The engine's source is `fx.get_actuation() -> {device index: mm}`. `Api` provides `_actuation_snapshot()` over `Api._act_mm`, filled from (a) `verify_actuation`'s whole-board firmware read-back (the UI already calls it on connect and after every Apply; it reads every key whatever `codes` says) and (b) a SUCCESSFUL `set_trigger_codes` / `set_trigger_all` (the written, clamped travel; corrected by the UI's follow-up read-back). A failed write leaves it alone; `select_board` clears it. Values that are not finite numbers in `(0, 100)` are never stored (and the engine re-validates). Fallback when a key has no value: the MEDIAN of the known keys' values (a half-finished read-back must not skew), and when nothing is known at all: **1.70 mm** (`PRESSURE_DEFAULT_ACT_MM`, the factory actuation in the spec's ground truth; the user's real 0.80 mm arrives with the read-back on connect, before an effect is normally chosen). The engine re-reads the map at most every 0.5 s (`PRESSURE_ACT_REFRESH_S`), per zone, not per frame.
7. **Frame-time cost at 60 fps.** Per key per frame: two dict lookups, one `pressure_level` call (a few float ops), one list lookup. About 0.1 ms for 61 keys against a 16.7 ms frame; the actuation refresh is 2 Hz; the ramp is built once. A test pins `< 4 ms` per 64-key frame (about 25x headroom, not a tight bound). It adds no HID traffic beyond what any host effect already streams (the driver diff cache sends only changed pages).
8. **Which UI lists need the effect.** `ui/runtime_src/workspaces/lighting.jsx`: `LIGHT_MODES` (the mode grid, which the tray panel's effect grid is built from via `modeGridFor`, so `ui/tray_panel.html` needs NO change), `ZONE_MODES`, `HOST_FX_IDS` (dispatch: without it the id would fall back to firmware Static), `HOST_FX_FAST` (the low-fps "≈" marker), `previewKindFor` (preview glyph kind `"react"`) and the comment listing the press-reactive set. `ui/runtime_src/src/sections.jsx`: the legacy copies `LIGHT_MODES` and `ZONE_MODES`, kept in step. NOT needed: `data/board_registry.json` `modes` (host-only effects such as rain/comet/tide are not listed there), `app.jsx` `FW_MODES` (firmware bytes only; `pressure` has none and falls back to the board's Static in Full RGB / power-off exactly like rain), `play_effect.py` (reads `PRESS_REACTIVE`; it has no actuation source, so it uses the 1.70 default). The effect ignores the speed slider (the decay is fixed at 120 ms by the spec).
9. **Tester marker.** The Travel Test keyboard is `KeyboardPanel` -> `Key` in `ui/runtime_src/src/keyboard.jsx` (Actuation workspace). `Key` already fills from the bottom to `depth / 4` of its height. New shared constant `TRAVEL_SCALE_MM = 4` replaces that literal and also positions the marker: a 2 px line at `bottom: (actuationPoint / 4) * 100 %` (clamped 0..100) with `data-act-tick`, drawn only in `mode === "actuation"` and `actuationPoint > 0`. Because fill and line share one scale, the fill crosses the line exactly when `depth >= actuationPoint` (the existing `actuated` rule); the line turns white and glows at that moment. Data source: the per-key `override.actuation` that `ActuationKeyboardWidget` builds from `perKeyActuation` (firmware read-back, `app.jsx`), falling back to the slider value for keys not yet read; no new bridge call. It is drawn whether or not Travel Test is streaming (it then simply shows where each key will fire). The widget header gains the legend text `line = actuation point`.

## Review Focus

- **Key released but the firmware never sends a ~0 frame** (mid-travel last report, then silence): the key must fade to the background, never stay lit. Tests: Task 1 `test_release_decays_in_about_120_ms_and_never_sticks`, `test_stalled_loop_and_frozen_clock_are_safe`.
- **No live depth at all** (reader missing, `UnsupportedFeature` on a board without a travel stream, analog-tab reader swap returning `{}`): all keys sit at the background, nothing raises. Tests: Task 1 `test_no_depth_source_means_everything_stays_background`, Task 2 `test_actuation_source_survives_a_missing_reader`.
- **Actuation values missing, zero, NaN, a string, or at the range extremes**: no `ZeroDivisionError`, no NaN colours, channels stay integers 0..255. Tests: Task 1 `test_level_survives_degenerate_actuation_points`, `test_garbage_actuation_values_are_ignored_not_fatal`, `test_all_channel_values_stay_in_byte_range`; Task 2 `test_garbage_values_never_enter_the_map`.
- **Corrupt or out-of-range depth report** (`> 3.40`, negative, NaN): clamped to the ramp ends. Test: Task 1 `test_level_is_clamped_for_corrupt_depths`.
- **Actuation changed while the effect is running** (user clicks Apply): the next 0.5 s refresh uses the new value; a failed write must not poison the map. Tests: Task 1 `test_actuation_source_is_polled_at_most_every_half_second`; Task 2 `test_successful_write_updates_the_map_immediately`, `test_failed_write_leaves_the_map_alone`.

## File Structure

- Modify `effects.py`: `import statistics`; constants + `pressure_level`; `PerKeyEffectEngine.get_actuation`, `_pressure_acts`, `_g_pressure`; `PRESS_REACTIVE`; `_gens["pressure"]`.
- Modify `app_web.py`: `Api._act_mm`, `_note_actuation`, `_actuation_snapshot`; edits in `__init__`, `select_board`, `verify_actuation`, `set_trigger_codes`, `set_trigger_all`, `_ensure_reactive`.
- Modify `ui/runtime_src/workspaces/lighting.jsx`, `ui/runtime_src/src/sections.jsx` (effect lists); `ui/runtime_src/src/keyboard.jsx`, `ui/runtime_src/workspaces/actuation.jsx` (tester marker). Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/{ws_lighting,sections,keyboard,ws_actuation}.js` (only those with real diffs).
- Modify `CLAUDE.md` (effects notes).
- Tests (all new): `tests/test_pressure_effect.py`, `tests/test_pressure_api.py`, `tests/test_pressure_ui_sources.py`, `tests/test_travel_tick_sources.py`.

---

### Task 1: The `pressure` generator, `pressure_level`, and engine wiring

**Files:**
- Modify: `effects.py`
- Test: `tests/test_pressure_effect.py` (create)

**Interfaces:**
- Produces (module level in `effects.py`): `PRESSURE_DECAY_S = 0.12`, `PRESSURE_DEFAULT_ACT_MM = 1.70`, `PRESSURE_MAX_MM = 3.40`, `PRESSURE_NOISE_MM = 0.05`, `PRESSURE_RAMP_STEPS = 64`, `PRESSURE_ACT_REFRESH_S = 0.5`, `pressure_level(mm: float, act: float, max_mm: float = PRESSURE_MAX_MM) -> float`.
- Produces (engine): `PerKeyEffectEngine.get_actuation: Callable[[], dict[int, float]] | None` (default `None`, set by `Api._ensure_reactive`, Task 2), `_pressure_acts(z, t) -> (dict[int, float], float)`, `_g_pressure(z, t, frame)`, `_gens["pressure"]`, and `"pressure"` in `PRESS_REACTIVE`.

- [ ] **Step 1: Write the failing tests** — `tests/test_pressure_effect.py`:

```python
"""Phase 2 "pressure" host effect: each key's colour follows its live depth
(0 -> background, actuation point -> palette midpoint, bottom-out -> full) and
decays ~120 ms after release. Pure engine tests: generators are called
directly with a fake clock and a fake depth source. No HID, no keyboard."""
import math
import time

import pytest

import effects

N_KEYS = 6
BG = (10, 20, 30)
RED = (255, 0, 0)       # gamma 1.6 leaves pure 0/255 channels unchanged
BLUE = (0, 0, 255)


class FakeKM:
    def __init__(self, n=N_KEYS):
        self.by_index = {i: {"x": float(i % 8), "y": float(i // 8)}
                         for i in range(n)}
        self.index_of_code = {}


def _engine(n=N_KEYS, acts=None, max_fps=None):
    eng = effects.PerKeyEffectEngine(FakeKM(n), lambda frame: None,
                                     max_fps=max_fps)
    if acts is not None:
        eng.get_actuation = lambda: dict(acts)
    return eng


def _zone(eng, palette=(RED,), bg=(0, 0, 0), bright=1.0):
    return effects.Zone(list(eng.indices), "pressure", list(palette), bg,
                        0.5, bright, 0)


def _frame(eng, z, t, depths):
    eng._depths = depths
    frame = {}
    eng._g_pressure(z, t, frame)
    return frame


# ---------------------------------------------------------------- wiring ----
def test_pressure_is_registered_and_press_reactive():
    assert "pressure" in effects.PRESS_REACTIVE
    assert "pressure" in _engine()._gens


# ------------------------------------------------------- depth -> level ----
def test_level_anchors_for_actuation_0_80():
    lv = effects.pressure_level
    assert lv(0.0, 0.80) == 0.0
    assert lv(0.04, 0.80) == 0.0                       # under the noise floor
    assert lv(0.40, 0.80) == pytest.approx(0.25)
    assert lv(0.80, 0.80) == pytest.approx(0.5)        # actuation = midpoint
    assert lv(2.10, 0.80) == pytest.approx(0.75)
    assert lv(3.40, 0.80) == pytest.approx(1.0)        # bottom-out = full


def test_level_is_clamped_for_corrupt_depths():
    lv = effects.pressure_level
    assert lv(9.99, 0.80) == 1.0
    assert lv(-1.0, 0.80) == 0.0
    assert lv(float("nan"), 0.80) == 0.0


def test_level_survives_degenerate_actuation_points():
    lv = effects.pressure_level
    for act in (0.0, -3.0, 0.01, 3.4, 99.0, float("nan")):
        for mm in (0.06, 1.0, 3.39, 3.4):
            v = lv(mm, act)
            assert 0.0 <= v <= 1.0 and not math.isnan(v), (act, mm)
    assert lv(3.4, 99.0) == 1.0


# ------------------------------------------------------- frame colours ----
def test_released_keys_are_exactly_the_scaled_background():
    eng = _engine()
    z = _zone(eng, bg=BG, bright=0.5)
    f = _frame(eng, z, 0.0, {})
    assert set(f) == set(eng.indices)
    assert all(c == effects._scale(BG, 0.5) for c in f.values())


def test_actuation_point_is_half_way_and_bottom_out_is_full():
    eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
    z = _zone(eng)
    f = _frame(eng, z, 0.0, {0: 0.80, 1: 3.40, 2: 0.0})
    assert f[0] == (127, 0, 0)                  # lerp(black, red, 0.5)
    assert f[1] == RED
    assert f[2] == (0, 0, 0)


def test_two_colour_palette_walks_the_gradient():
    eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
    z = _zone(eng, palette=(RED, BLUE))
    f = _frame(eng, z, 0.0, {0: 0.80, 1: 3.40})
    assert f[0] == (63, 0, 63)                  # lerp(black, mid(red, blue), 0.5)
    assert f[1] == BLUE                         # last palette colour = full


def test_zone_brightness_scales_the_ramp():
    eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
    z = _zone(eng, bright=0.5)
    f = _frame(eng, z, 0.0, {0: 3.40})
    assert f[0] == (127, 0, 0)


def test_each_key_uses_its_own_actuation_point():
    eng = _engine(acts={0: 0.50, 1: 2.00})
    z = _zone(eng)
    f = _frame(eng, z, 0.0, {0: 1.0, 1: 1.0})
    assert f[0][0] > f[1][0]                    # past a low point vs before a high one


def test_unknown_actuation_uses_the_median_of_the_known_keys():
    eng = _engine(acts={0: 0.80, 1: 0.80, 2: 0.80})     # keys 3-5 unknown
    z = _zone(eng)
    f = _frame(eng, z, 0.0, {0: 0.80, 4: 0.80})
    assert f[4] == f[0] == (127, 0, 0)


def test_no_actuation_source_falls_back_to_factory_1_70():
    eng = _engine()
    assert eng.get_actuation is None
    assert effects.PRESSURE_DEFAULT_ACT_MM == 1.70
    z = _zone(eng)
    f = _frame(eng, z, 0.0, {0: 1.70})
    assert f[0] == (127, 0, 0)


def test_garbage_actuation_values_are_ignored_not_fatal():
    eng = _engine(acts={0: "x", 1: -2.0, 2: float("nan"), 3: float("inf"), 4: 0.80})
    z = _zone(eng)
    f = _frame(eng, z, 0.0, {0: 0.80, 4: 0.80})
    assert f[4] == (127, 0, 0)
    assert f[0] == (127, 0, 0)                  # unknown -> median of the valid {0.80}


def test_failing_actuation_source_does_not_break_the_frame():
    eng = _engine()

    def boom():
        raise RuntimeError("bridge hiccup")
    eng.get_actuation = boom
    z = _zone(eng)
    f = _frame(eng, z, 0.0, {0: 1.70})
    assert f[0] == (127, 0, 0)


def test_actuation_source_is_polled_at_most_every_half_second():
    calls = []
    eng = _engine()
    eng.get_actuation = lambda: calls.append(1) or {0: 0.80}
    z = _zone(eng)
    for k in range(66):                         # 1.1 s at 60 fps
        _frame(eng, z, k / 60.0, {})
    assert len(calls) == 3                      # t = 0, 0.5, 1.0
    eng.get_actuation = lambda: {0: 2.0}
    _frame(eng, z, 1.2, {0: 0.80})
    assert _frame(eng, z, 1.6, {0: 0.80})[0] != (127, 0, 0)   # refreshed value used


# ------------------------------------------------------ attack and decay ----
def test_attack_is_instant():
    eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
    z = _zone(eng)
    _frame(eng, z, 0.0, {})
    assert _frame(eng, z, 1 / 60, {0: 3.40})[0] == RED


def test_release_decays_in_about_120_ms_and_never_sticks():
    eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
    z = _zone(eng)
    assert _frame(eng, z, 0.0, {0: 3.40})[0] == RED
    half = _frame(eng, z, 0.06, {})[0]          # reader cleared the key
    assert 100 <= half[0] <= 155
    assert _frame(eng, z, 0.121, {})[0] == (0, 0, 0)
    assert _frame(eng, z, 5.0, {})[0] == (0, 0, 0)


def test_easing_off_a_key_follows_it_down_not_instantly():
    eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
    z = _zone(eng)
    _frame(eng, z, 0.0, {0: 3.40})
    f = _frame(eng, z, 0.03, {0: 0.80})          # target 0.5, fall allowed 0.25
    assert 185 <= f[0][0] <= 195


def test_held_key_stays_lit():
    eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
    z = _zone(eng)
    first = _frame(eng, z, 0.0, {0: 2.0})[0]
    for k in range(1, 120):
        assert _frame(eng, z, k / 60.0, {0: 2.0})[0] == first


def test_decay_is_frame_rate_independent():
    def after(fps, seconds):
        eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
        z = _zone(eng)
        _frame(eng, z, 0.0, {0: 3.40})
        f = None
        for k in range(1, round(fps * seconds) + 1):
            f = _frame(eng, z, k / fps, {})
        return f[0][0]
    a, b = after(60, 0.06), after(28, 0.06)
    assert 100 <= a <= 155
    assert abs(a - b) <= 12


def test_stalled_loop_and_frozen_clock_are_safe():
    eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
    z = _zone(eng)
    _frame(eng, z, 1.0, {0: 3.40})
    assert _frame(eng, z, 1.0, {})[0] == RED            # dt = 0: nothing decays
    assert _frame(eng, z, 1.0 - 5.0, {})[0] == RED      # clock went backwards
    assert _frame(eng, z, 600.0, {})[0] == (0, 0, 0)    # long stall: fully off


def test_no_depth_source_means_everything_stays_background():
    eng = _engine()
    z = _zone(eng, bg=BG)
    for k in range(5):
        f = _frame(eng, z, k / 60.0, effects._NO_DEPTHS)
        assert all(c == BG for c in f.values())


def test_state_is_bounded_by_key_count_and_ramp_is_built_once():
    eng = _engine()
    z = _zone(eng)
    _frame(eng, z, 0.0, {0: 1.0})
    ramp = z.state["ramp"]
    assert len(ramp) == effects.PRESSURE_RAMP_STEPS + 1
    for k in range(1, 400):
        _frame(eng, z, k / 60.0, {k % N_KEYS: 0.5 + (k % 7) * 0.4})
    assert z.state["ramp"] is ramp
    assert len(z.state["lvl"]) <= len(eng.indices)


def test_all_channel_values_stay_in_byte_range():
    eng = _engine(acts={i: 0.80 for i in range(N_KEYS)})
    z = _zone(eng, palette=((255, 255, 255), (1, 2, 3)), bg=(255, 255, 255))
    for k in range(60):
        f = _frame(eng, z, k / 60.0, {i: (k * 0.1 + i) % 4.0 for i in range(N_KEYS)})
        for c in f.values():
            assert all(isinstance(v, int) and 0 <= v <= 255 for v in c)


def test_frame_cost_stays_far_below_the_16ms_budget():
    eng = _engine(n=64, acts={i: 0.80 for i in range(64)})
    z = _zone(eng, palette=(RED, BLUE))
    depths = {i: 0.2 + (i % 9) * 0.35 for i in range(64)}
    t0 = time.perf_counter()
    for k in range(200):
        _frame(eng, z, k / 60.0, depths)
    per_frame = (time.perf_counter() - t0) / 200
    assert per_frame < 0.004, per_frame         # ~25x headroom over the expected ~0.1 ms


# ------------------------------------------------------ engine end to end ----
def test_running_engine_streams_pressure_frames():
    frames = []
    eng = effects.PerKeyEffectEngine(FakeKM(), frames.append)
    eng.get_depths = lambda: {0: 3.40}
    eng.get_actuation = lambda: {i: 0.80 for i in range(N_KEYS)}
    eng.start("pressure", [RED], (0, 0, 0), 0.5, 1.0)
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not any(f.get(0) == RED for f in frames):
            time.sleep(0.02)
    finally:
        eng.stop()
    assert any(f.get(0) == RED for f in frames)
    assert all(f.get(1) == (0, 0, 0) for f in frames)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_pressure_effect.py -q -p no:cacheprovider`
Expected: FAIL (`AttributeError: module 'effects' has no attribute 'pressure_level'`, `'PerKeyEffectEngine' object has no attribute '_g_pressure'`, the registration test fails on `PRESS_REACTIVE`).

- [ ] **Step 3: Implement in `effects.py`**

1. Add `import statistics` to the imports (alphabetical, between `random` and `threading`).
2. Change `PRESS_REACTIVE` to `("reactive", "ripple", "speedres", "cross", "fireworks", "pressure")`.
3. Insert, between `_palette_at` and `class Zone`, exactly:

```python
# ---- "pressure" effect constants (Phase 2) ----
PRESSURE_DECAY_S = 0.12          # full-scale fall time after the key rises
PRESSURE_DEFAULT_ACT_MM = 1.70   # factory actuation, used until a read-back exists
PRESSURE_MAX_MM = 3.40           # bottom-out
PRESSURE_NOISE_MM = 0.05         # LiveReader.NOISE_MM: below this = released
PRESSURE_RAMP_STEPS = 64         # colour ramp resolution (65 entries)
PRESSURE_ACT_REFRESH_S = 0.5     # how often the engine re-reads the actuation map


def pressure_level(mm, act, max_mm=PRESSURE_MAX_MM):
    """Depth -> 0..1 along the ramp: 0 = released, 0.5 = at the key's actuation
    point, 1.0 = bottomed out. Linear on both sides of the actuation point."""
    if not mm >= PRESSURE_NOISE_MM:          # also catches NaN and negatives
        return 0.0
    if mm >= max_mm:
        return 1.0
    if not act == act:                       # NaN
        act = PRESSURE_DEFAULT_ACT_MM
    act = min(max(act, 0.08), max_mm - 0.10)
    if mm < act:
        return 0.5 * mm / act
    return 0.5 + 0.5 * (mm - act) / (max_mm - act)
```

4. In `PerKeyEffectEngine.__init__`, next to `self.get_depths = None`, add `self.get_actuation = None  # optional () -> {device_index: mm} for pressure`; in the `self._gens` table add `"pressure": self._g_pressure` (beside `"reactive"`).
5. Add these two methods to the class (put them right after `_g_reactive`):

```python
    def _pressure_acts(self, z, t):
        """({idx: actuation mm}, default mm) for the pressure effect, refreshed
        at most every PRESSURE_ACT_REFRESH_S. Unknown keys use the median of
        the known ones, or PRESSURE_DEFAULT_ACT_MM when nothing is known."""
        st = z.state
        if t - st.get("act_t", -1e9) >= PRESSURE_ACT_REFRESH_S:
            st["act_t"] = t
            acts = {}
            src = self.get_actuation
            if src is not None:
                try:
                    raw = src() or {}
                except Exception:
                    raw = {}
                for i, v in raw.items():
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        continue
                    if v == v and 0.0 < v < 100.0:
                        acts[i] = v
            st["acts"] = acts
            st["act_default"] = (statistics.median(acts.values()) if acts
                                 else PRESSURE_DEFAULT_ACT_MM)
        return st["acts"], st["act_default"]

    def _g_pressure(self, z, t, frame):
        # Each key's colour follows its live depth along a background -> palette
        # ramp (pressure_level). Attack is instant; the level falls at most
        # 1/PRESSURE_DECAY_S per second, so a released key is dark ~120 ms later
        # even if the reader never reports a ~0 frame.
        st = z.state
        ramp = st.get("ramp")
        if ramp is None:
            pal, n, steps = z.palette, len(z.palette), PRESSURE_RAMP_STEPS
            ramp = []
            for k in range(steps + 1):
                u = k / steps
                if n == 1:
                    g = pal[0]
                else:
                    p = u * (n - 1)
                    i = min(int(p), n - 2)
                    g = _lerp(pal[i], pal[i + 1], p - i)
                ramp.append(_scale(_lerp(z.bg, g, u), z.bright))
            st["ramp"] = ramp
        lvl = st.setdefault("lvl", {})
        last_t = st.get("t")
        fall = 0.0 if last_t is None else max(0.0, t - last_t) / PRESSURE_DECAY_S
        st["t"] = t
        acts, default_act = self._pressure_acts(z, t)
        depths = self._depths
        top = len(ramp) - 1
        for idx in z.indices:
            target = pressure_level(depths.get(idx, 0.0), acts.get(idx, default_act))
            cur = lvl.get(idx, 0.0)
            cur = target if target >= cur else max(target, cur - fall)
            lvl[idx] = cur
            frame[idx] = ramp[int(cur * top + 0.5)]
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_pressure_effect.py tests/test_effects_stream.py -q -p no:cacheprovider`
Expected: all pass (`25` in `test_pressure_effect.py`).

- [ ] **Step 5: Commit**

```bash
git add effects.py tests/test_pressure_effect.py
git commit -m "feat(effects): pressure host effect (depth -> colour, 120 ms decay)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Api actuation map and the engine's actuation source

**Files:**
- Modify: `app_web.py`
- Test: `tests/test_pressure_api.py` (create)

**Interfaces:**
- Consumes: `PerKeyEffectEngine.get_actuation` (Task 1); Phase 1's `tests/test_stats_api.py::_api(tmp_path, enabled=True, slug="aula-win60-he")` helper (fake driver/reader/device, real `KeyMap`) and its `FakeDriver.detail` read-back hook.
- Produces (Api): `self._act_mm: dict[int, float]` (device index -> mm), `_note_actuation(mm_by_idx: dict) -> None` (drops anything not a finite float in `(0, 100)`), `_actuation_snapshot() -> dict[int, float]` (a copy). `_ensure_reactive` sets `fx.get_actuation = self._actuation_snapshot` for press-reactive modes and `None` otherwise (also `None` when no reader could be built). No bridge method is added.

- [ ] **Step 1: Write the failing tests** — `tests/test_pressure_api.py`:

```python
"""Phase 2: the Api keeps a per-key actuation map for the pressure effect, fed
by the firmware read-back (verify_actuation) and by successful writes, and
hands it to the engine as fx.get_actuation. Fakes only: no HID, no keyboard."""
import types

import pytest

import app_web
from test_stats_api import _api


def _with_engine(a):
    a.fx = types.SimpleNamespace(get_depths=None, get_actuation=None)
    return a


def _read_back(a, mm=0.80):
    w = a.km.index_of_code["W"]
    a.driver.detail = {a.km.by_index[w]["name"]: {"travel_mm": mm, "mode": 0}}
    assert a.verify_actuation([])["ok"]
    return w


def test_read_back_feeds_the_pressure_effect(tmp_path):
    a = _with_engine(_api(tmp_path))
    w = _read_back(a, 0.80)
    a._ensure_reactive(["pressure"])
    assert a.fx.get_depths is not None
    assert a.fx.get_actuation()[w] == 0.80


def test_non_reactive_effect_detaches_the_actuation_source(tmp_path):
    a = _with_engine(_api(tmp_path))
    a._ensure_reactive(["pressure"])
    assert a.fx.get_actuation is not None
    a._ensure_reactive(["wave"])
    assert a.fx.get_actuation is None and a.fx.get_depths is None


def test_actuation_source_survives_a_missing_reader(tmp_path):
    a = _with_engine(_api(tmp_path))
    a.driver.make_live_reader = lambda km, indices=None: (_ for _ in ()).throw(
        app_web.UnsupportedFeature("Test board", "travel_stream"))
    a._ensure_reactive(["pressure"])
    assert a.fx.get_depths is None             # effect stays dark, no exception


def test_snapshot_is_a_copy_the_engine_may_keep(tmp_path):
    a = _api(tmp_path)
    a._note_actuation({46: 0.8})
    snap = a._actuation_snapshot()
    a._note_actuation({47: 1.0})
    assert snap == {46: 0.8}


def test_garbage_values_never_enter_the_map(tmp_path):
    a = _api(tmp_path)
    a._note_actuation({1: "x", 2: -1.0, 3: float("nan"), 4: float("inf"),
                       5: 0.0, 6: 0.9})
    assert a._actuation_snapshot() == {6: 0.9}


def test_successful_write_updates_the_map_immediately(tmp_path):
    a = _with_engine(_api(tmp_path))
    w = _read_back(a, 0.80)
    assert a.set_trigger_codes(["W"], 1.2)["ok"]
    assert a._actuation_snapshot()[w] == pytest.approx(1.2)


def test_failed_write_leaves_the_map_alone(tmp_path):
    a = _with_engine(_api(tmp_path))
    w = _read_back(a, 0.80)

    def boom(*args, **kw):
        raise RuntimeError("link lost")
    a._flush_triggers = boom
    assert a.set_trigger_codes(["W"], 1.2)["ok"] is False
    assert a._actuation_snapshot()[w] == 0.80


def test_whole_board_write_updates_every_key(tmp_path):
    a = _api(tmp_path)
    assert a.set_trigger_all(1.0)["ok"]
    snap = a._actuation_snapshot()
    assert set(snap) == set(a.km.indices())
    assert set(snap.values()) == {1.0}


def test_selecting_another_board_forgets_the_map(tmp_path):
    a = _api(tmp_path)
    a._note_actuation({46: 0.8})
    a._registry = None
    a._remaps, a._deadband_state, a._fn_layer_raw = {}, {}, None
    assert a.select_board("aula-mini60he-pro")["ok"] is True
    assert a._actuation_snapshot() == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_pressure_api.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: 'Api' object has no attribute '_note_actuation'` and `'types.SimpleNamespace' object has no attribute 'get_actuation'`-style assertion errors.

- [ ] **Step 3: Implement in `app_web.py`**

Make exactly these edits (no other behaviour changes):
- `__init__`, directly after `self._deadband_state = {}`: `self._act_mm = {}` with a comment that it is filled by `verify_actuation` and successful writes and read lock-free (engine takes `dict()` copies).
- `select_board`, in the per-board cache reset next to `self._deadband_state = {}`: `self._act_mm = {}`.
- New methods next to `_stats_actuation`: `_note_actuation(mm_by_idx)` (creates `self._act_mm` lazily when missing, because tests build `Api.__new__` objects; `float()` each value, skip `TypeError`/`ValueError`, keep only `mm == mm and 0.0 < mm < 100.0`) and `_actuation_snapshot()` (`dict(getattr(self, "_act_mm", None) or {})`).
- `verify_actuation`: right after `self._stats_actuation(act_by_idx)` add `self._note_actuation(act_by_idx)`.
- `set_trigger_codes`: after the `if mode == 0: ... else: ...` flush block and BEFORE `return {"ok": True, ...}` (so a raising flush skips it) add `self._note_actuation({i: travel_mm for i in idxs})` (`travel_mm` is already clamped there).
- `set_trigger_all`: after the `if mode == 0: ... else: ...` write block, before its `return {"ok": True, ...}`, add `self._note_actuation({i: float(travel_mm) for i in idxs})`.
- `_ensure_reactive`: in the `self.reader is None` early-return add `self.fx.get_actuation = None`; after `self.fx.get_depths = get_depths` add `self.fx.get_actuation = self._actuation_snapshot` (comment: the pressure effect also needs each key's actuation point); in the `else:` branch add `self.fx.get_actuation = None` next to `self.fx.get_depths = None`.

- [ ] **Step 4: Run the tests and the suites that touch this code**

Run: `<py> -m pytest tests/test_pressure_api.py tests/test_stats_api.py tests/test_effects_stream.py tests/test_actuation_readback.py tests/test_drivers.py tests/test_win60_settings_fixes.py -q -p no:cacheprovider`
Expected: all pass (`9` in `test_pressure_api.py`).

- [ ] **Step 5: Commit**

```bash
git add app_web.py tests/test_pressure_api.py
git commit -m "feat(api): per-key actuation map for the pressure effect" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Offer the effect in the UI

**Files:**
- Modify: `ui/runtime_src/workspaces/lighting.jsx`, `ui/runtime_src/src/sections.jsx`
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/ws_lighting.js`, `ui/runtime_src/build/sections.js`
- Test: `tests/test_pressure_ui_sources.py` (create)

**Interfaces:**
- Consumes: `effects.PRESS_REACTIVE` and the engine `_gens` table (Task 1) through the new source test.
- Produces: effect id `"pressure"` (label `Pressure`, icon `▮`) selectable in the Lighting mode grid, in Effect Zones, and in the tray panel's effect grid; dispatched to `start_multicolor("pressure", ...)` on the Win60 like every host effect.

- [ ] **Step 1: Write the failing tests** — `tests/test_pressure_ui_sources.py`:

```python
"""Phase 2 UI wiring guards. The lighting lists are hand-kept JS copies of the
engine's tables, so a new effect can be half-wired (engine knows it, UI never
offers it, or the other way round). These read the JSX sources as text."""
import os
import re

import effects
from test_pressure_effect import _engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


def _set_ids(text, name):
    m = re.search(r"const %s = new Set\(\[(.*?)\]\)" % name, text, re.S)
    assert m, name
    return set(re.findall(r'"([a-z0-9_]+)"', m.group(1)))


def _list_ids(text, name):
    m = re.search(r"const %s = \[(.*?)\n\];" % name, text, re.S)
    assert m, name
    return set(re.findall(r'id: "([a-z0-9_]+)"', m.group(1)))


def test_host_fx_ids_equal_the_engine_generators():
    gens = set(_engine()._gens) - {"static", "calibrate"}
    assert _set_ids(_read("workspaces", "lighting.jsx"), "HOST_FX_IDS") == gens


def test_host_fx_fast_equals_the_press_reactive_set():
    assert _set_ids(_read("workspaces", "lighting.jsx"), "HOST_FX_FAST") \
        == set(effects.PRESS_REACTIVE)


def test_pressure_is_offered_in_every_effect_list():
    for rel in (("workspaces", "lighting.jsx"), ("src", "sections.jsx")):
        text = _read(*rel)
        assert "pressure" in _list_ids(text, "LIGHT_MODES"), rel
        assert "pressure" in _list_ids(text, "ZONE_MODES"), rel


def test_pressure_previews_like_the_other_press_reactive_effects():
    text = _read("workspaces", "lighting.jsx")
    assert re.search(r'pattern === "pressure"\) return "react"', text)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_pressure_ui_sources.py -q -p no:cacheprovider`
Expected: 4 FAIL (`HOST_FX_IDS` lacks `pressure`, `HOST_FX_FAST` lacks it, the lists lack it, the preview regex finds nothing).

- [ ] **Step 3: Edit the sources**

In `ui/runtime_src/workspaces/lighting.jsx`:
- `LIGHT_MODES`: insert `{ id: "pressure", label: "Pressure",      icon: "▮" },` after the `speedres` entry (before `rain`).
- `ZONE_MODES`: insert `{ id: "pressure", label: "Pressure" },` on its own line after the `fireworks`/`aurora` line.
- The block comment above `HOST_ENGINE_TARGET_FPS`: change the line `press-reactive: reactive, ripple, speedres, cross, fireworks` to end with `, pressure`.
- `HOST_FX_FAST`: add `"pressure"` to the Set.
- `HOST_FX_IDS`: add `"pressure"` (after `"speedres",`).
- `previewKindFor`: extend the react line to `if (pattern === "reactive" || pattern === "cross" || pattern === "speedres" || pattern === "pressure") return "react";`.

In `ui/runtime_src/src/sections.jsx`: the same `LIGHT_MODES` and `ZONE_MODES` insertions (this file's copies are legacy; keep them in step).

- [ ] **Step 4: Build and keep only real diffs**

Run: `<py> ui\runtime_src\build_runtime.py`
Expected: ends with `Wrote ...index_runtime.html  (NNN KB)`, no Babel error.
Run: `git diff --ignore-cr-at-eol --stat` — expected files: the two `.jsx`, `ui/index_runtime.html`, `ui/runtime_src/build/sections.js`, `ui/runtime_src/build/ws_lighting.js`. Run plain `git diff --stat`; any build file listed there but not above is a line-ending-only change: `git checkout -- <file>`.

- [ ] **Step 5: Run the tests**

Run: `<py> -m pytest tests/test_pressure_ui_sources.py tests/test_ui_sources.py tests/test_tray.py -q -p no:cacheprovider`
Expected: all pass (`4` new). Run `git grep -n "dangerouslySetInnerHTML\|innerHTML" -- ui/runtime_src/workspaces/lighting.jsx ui/runtime_src/src/sections.jsx`; expected: nothing.

- [ ] **Step 6: Commit**

```bash
git add ui/runtime_src/workspaces/lighting.jsx ui/runtime_src/src/sections.jsx ui/index_runtime.html ui/runtime_src/build/ws_lighting.js ui/runtime_src/build/sections.js tests/test_pressure_ui_sources.py
git commit -m "feat(ui): offer the Pressure effect (mode grid, zones, host dispatch)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Travel Test actuation marker

**Files:**
- Modify: `ui/runtime_src/src/keyboard.jsx`, `ui/runtime_src/workspaces/actuation.jsx`
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/keyboard.js`, `ui/runtime_src/build/ws_actuation.js`
- Test: `tests/test_travel_tick_sources.py` (create)

**Interfaces:**
- Consumes: the per-key `actuationPoint` prop `Key` already receives (`override.actuation ?? actuationPoint` in `KeyboardPanel`, where `override` comes from `ActuationKeyboardWidget`'s `perKeyOverride`, built from `perKeyActuation`).
- Produces: `TRAVEL_SCALE_MM = 4` and `tickPct(mm) -> number` (0..100) at the top of `keyboard.jsx`; a `<span data-act-tick>` inside `Key`.

- [ ] **Step 1: Write the failing tests** — `tests/test_travel_tick_sources.py`:

```python
"""Phase 2 Travel Test polish: each key draws its actuation point. The Key
component is JSX, so these pin the wiring in the sources and the built bundle."""
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_fill_and_tick_share_one_travel_scale():
    kb = _read("src", "keyboard.jsx")
    assert re.search(r"const TRAVEL_SCALE_MM = 4;", kb)
    assert "Math.min(1, depth / TRAVEL_SCALE_MM)" in kb
    assert "(mm / TRAVEL_SCALE_MM) * 100" in kb
    assert "depth / 4)" not in kb          # the old literal must not creep back


def test_tick_is_per_key_and_only_in_actuation_mode():
    kb = _read("src", "keyboard.jsx")
    m = re.search(r'\{mode === "actuation" && actuationPoint > 0 && \(\s*'
                  r"<span aria-hidden data-act-tick.*?bottom: tickPct\(actuationPoint\)", kb, re.S)
    assert m, "tick must be gated on actuation mode and use the key's own actuationPoint"
    # per-key value reaches Key from perKeyOverride (the firmware read-back)
    assert "actuationPoint={override.actuation ?? actuationPoint}" in kb


def test_actuation_header_explains_the_line():
    assert "line = actuation point" in _read("workspaces", "actuation.jsx")


def test_built_bundle_contains_the_tick():
    with open(os.path.join(SRC, "build", "keyboard.js"), encoding="utf-8") as fh:
        built = fh.read()
    assert "data-act-tick" in built and "TRAVEL_SCALE_MM" in built
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_travel_tick_sources.py -q -p no:cacheprovider`
Expected: 4 FAIL (`TRAVEL_SCALE_MM` not found, no `data-act-tick`, no legend, built bundle lacks it).

- [ ] **Step 3: Edit `keyboard.jsx`**

- Above the `ufrac` helper add (with a block comment saying the fill and the tick share one scale so the fill crosses the tick exactly when the key would actuate):

```jsx
const TRAVEL_SCALE_MM = 4;
const tickPct = (mm) => Math.max(0, Math.min(100, (mm / TRAVEL_SCALE_MM) * 100));
```

- In `Key`: `const progress = Math.min(1, depth / TRAVEL_SCALE_MM);` (replaces `depth / 4`).
- In `Key`'s JSX, immediately before the `{/* Label */}` block, add a short comment and this element (it renders above the travel fill, below the label which is `z-10`):

```jsx
{mode === "actuation" && actuationPoint > 0 && (
  <span aria-hidden data-act-tick className="absolute inset-x-0 h-[2px] pointer-events-none z-[5]"
        style={{
          bottom: tickPct(actuationPoint) + "%",
          background: actuated ? "#ffffff" : "var(--accent)",
          opacity: actuated ? 0.95 : 0.75,
          boxShadow: actuated ? "0 0 6px var(--accent-glow)" : "none",
        }}/>
)}
```

- Do not touch the `React.memo` comparator (`depth`, `actuationPoint`, `mode` are already compared) or the existing 3 px bar.

In `ui/runtime_src/workspaces/actuation.jsx`, `ActuationKeyboardWidget` header: after the `live travel` span line add `{" · "}<span className="text-[var(--text)]/80">line = actuation point</span>`.

- [ ] **Step 4: Build and keep only real diffs**

Run: `<py> ui\runtime_src\build_runtime.py`, then the same `git diff --ignore-cr-at-eol --stat` / `git checkout --` routine as Task 3. Expected real diffs: the two `.jsx`, `ui/index_runtime.html`, `ui/runtime_src/build/keyboard.js`, `ui/runtime_src/build/ws_actuation.js`.

- [ ] **Step 5: Run the tests**

Run: `<py> -m pytest tests/test_travel_tick_sources.py tests/test_ui_sources.py tests/test_keyboard_review.py -q -p no:cacheprovider`
Expected: all pass (`4` new). `git grep -n "dangerouslySetInnerHTML\|innerHTML" -- ui/runtime_src/src/keyboard.jsx ui/runtime_src/workspaces/actuation.jsx` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add ui/runtime_src/src/keyboard.jsx ui/runtime_src/workspaces/actuation.jsx ui/index_runtime.html ui/runtime_src/build/keyboard.js ui/runtime_src/build/ws_actuation.js tests/test_travel_tick_sources.py
git commit -m "feat(ui): draw each key's actuation point on the Travel Test board" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Docs, full suite, status

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/roadmap-status.md` (append)

- [ ] **Step 1: CLAUDE.md**

In "## Effects": change `Press-reactive (need live travel): **reactive, ripple, speedres, cross, fireworks**.` to include `**pressure**`, and append a sentence: `**Pressure** = each key's colour follows its live depth (background -> palette midpoint at that key's actuation point -> full at bottom-out), instant attack, 120 ms fall; per-key actuation comes from \`Api._act_mm\` (read-back + successful writes), unknown keys use the median, else 1.70 mm.` In the `effects.py` Architecture bullet add: `Optional engine sources: \`get_depths\` and \`get_actuation\` (set by \`Api._ensure_reactive\`).`

- [ ] **Step 2: Full suite**

Run: `<py> -m pytest -q -p no:cacheprovider`
Expected: `808 passed, 12 skipped` (766 + 25 + 9 + 4 + 4), zero failures, zero errors.

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: record the pressure effect in the architecture notes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Status entry**

Append to `docs/superpowers/roadmap-status.md`, ABOVE `## Waiting on the user`, a dated implementer entry in the file's format (≤15 lines): the commits landed, the decisions later phases must respect (`PRESS_REACTIVE` includes `pressure`; `Api._act_mm` / `_actuation_snapshot` is the per-key actuation source for the engine and any later feature, filled by read-back and successful writes; `fx.get_actuation`; `Key` draws `data-act-tick` at `TRAVEL_SCALE_MM = 4`), gotchas, and the hardware checks below pointing at this plan. Add one bullet inside `## Waiting on the user`: `- [Phase 2] Run the 9 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-2-pressure.md (pressure feel, 120 ms fade, actuation lines on the tester).` Commit it alone:

```bash
git add docs/superpowers/roadmap-status.md
git commit -m "docs(status): phase 2 pressure lighting done" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Hardware checks (for the orchestrator → `docs/HARDWARE_TEST_CHECKLIST.md` under `## Roadmap 2026-11-04`)

1. Lighting -> Pressure with a two-colour palette and a dark background: resting keys show only the background; pressing a key slowly makes it brighten and shift colour smoothly with depth (no steps, no flicker).
2. With the 0.80 mm actuation setting: a key pressed exactly to its actuation point (the moment the character types) shows about the palette midpoint at half strength; bottoming out shows the last palette colour at full strength.
3. Release a key quickly from bottom-out: it is dark within roughly a quarter second (120 ms fade plus the reader's 150 ms release window). No key stays lit after ten rapid taps on different keys, including keys released very lightly (stopping mid-travel).
4. Hold a key halfway: it stays at a constant glow (no pulsing or decay while held).
5. Change a few keys' actuation in the Actuation tab (Apply, read-back matches) while Pressure is running: those keys' midpoint shifts to the new actuation within about a second.
6. Switch Pressure <-> Ripple/Reactive <-> a non-reactive effect 10 times: the board follows the last choice, typing and the Travel Test still work, nothing lingers.
7. Typing feel and CPU: type normally for 5 minutes on Pressure; no missed or doubled keys; AetherHE CPU similar to Ripple (the effect itself is about 0.1 ms/frame). Also run it in an Effect Zone (select some keys -> Pressure in Custom): only those keys react.
8. Actuation tab, Travel Test ON: every key shows a short accent line at its own actuation height (lower lines for lower actuation, e.g. the user's 0.80 mm keys near the bottom fifth); pressing a key, its fill rises through the line at the instant the key types, and the line turns white. Travel Test OFF: lines still show. Change one key's actuation: only that key's line moves after Apply/Re-read.
9. Tray panel effect grid shows Pressure; selecting it from the tray switches the board's effect.
