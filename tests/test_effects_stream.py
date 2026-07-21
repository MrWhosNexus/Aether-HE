"""Tests for the host effect engine's per-board frame-rate cap.

The engine historically ran at one hardcoded rate for the Win60. Boards now
declare their measured sustainable host-stream rate in the registry
(lighting.hostEngineMaxFps: Win60 60, MINI 60 HE PRO 28 — the latter
HARDWARE-VERIFIED at 27.7 fps over cmd 0x32 on 2026-07-20), and the engine
paces each instance to min(module default, cap).

What is pinned here:
  * the Win60 pipeline is UNCHANGED: default pacing, default spawn
    normalisation, and identical per-frame color output — a cap above the
    engine default (60 == 60) must change nothing;
  * a 28 fps board gets 28 fps pacing AND rate-independent particle density
    (the _SPAWN_NORM normalisation re-derived per instance, so it gets the
    full intended spawn rate, not 28/60 of it);
  * the cap flows registry JSON -> app_web._host_engine_max_fps ->
    PerKeyEffectEngine, and the UI-facing lighting block carries the one
    uniform hostEngineMaxFps field.
"""
import threading
import types

import pytest

import boards
import effects
import app_web


class FakeKM:
    """Minimal KeyMap stand-in: 6 keys on a 3x2 grid."""

    def __init__(self, n=6):
        self.by_index = {i: {"x": float(i % 3), "y": float(i // 3)}
                         for i in range(n)}
        self.index_of_code = {}


def _engine(max_fps=None):
    return effects.PerKeyEffectEngine(FakeKM(), lambda frame: None,
                                      max_fps=max_fps)


# ------------------------------------------------------------ cap resolution ----
def test_win60_engine_defaults_unchanged():
    """No cap and a cap >= the engine default are byte-for-byte the same
    engine config (120 kept here deliberately to exercise cap > default): the
    module constants still rule, so the Win60 path is provably untouched."""
    default = _engine()
    win60 = _engine(max_fps=120)
    for eng in (default, win60):
        assert eng.fps == effects.FPS == 60
        assert eng._frame_interval == pytest.approx(1.0 / effects.FPS)
        assert eng._spawn_norm == pytest.approx(effects._SPAWN_NORM)
    assert effects._SPAWN_NORM == pytest.approx(30.0 / 60.0)


def test_capped_engine_paces_to_board_rate():
    eng = _engine(max_fps=28)
    assert eng.fps == 28
    assert eng._frame_interval == pytest.approx(1.0 / 28.0)
    # spawn density normalisation re-derived for the actual rate
    assert eng._spawn_norm == pytest.approx(30.0 / 28.0)


def test_cap_edge_values_fall_back_to_default():
    for bad in (None, 0, -5):
        eng = _engine(max_fps=bad)
        assert eng.fps == effects.FPS


# ------------------------------------------------------- registry -> app_web ----
def test_fps_cap_resolution_per_board_from_registry():
    reg = boards.load_registry()
    mini = reg.by_slug("aula-mini60he-pro")
    win60 = reg.by_slug("aula-win60-he")
    dongle = reg.by_slug("aula-mini60he-pro-24g")
    assert app_web._host_engine_max_fps(mini) == 28
    assert app_web._host_engine_max_fps(win60) == 60
    assert app_web._host_engine_max_fps(dongle) is None   # no lighting block
    assert app_web._host_engine_max_fps(None) is None


def test_lighting_block_carries_uniform_ui_field():
    """The JS-facing lighting block exposes hostEngineMaxFps on every board
    that declares one (the UI reads this exact field name)."""
    reg = boards.load_registry()
    mini_lt = app_web._lighting_block(reg.by_slug("aula-mini60he-pro"))
    assert mini_lt["hostEngine"] is True
    assert mini_lt["hostEngineMaxFps"] == 28
    win_lt = app_web._lighting_block(reg.by_slug("aula-win60-he"))
    assert win_lt["hostEngine"] is True
    assert win_lt["hostEngineMaxFps"] == 60
    # The MINI 60 HE PRO dongle (drivable since 2026-07-20) DOES declare a
    # lighting block — same firmware mode table as wired — but with
    # hostEngine FALSE (HARDWARE-VERIFIED: the RF bridge silently drops
    # 0x32 stream writes; the vendor never streams over 2.4GHz) and no
    # hostEngineMaxFps at all: there is no stream to cap, and the UI must
    # see hostEngine false and hide the host-effects surface.
    dongle_lt = app_web._lighting_block(reg.by_slug("aula-mini60he-pro-24g"))
    assert dongle_lt is not None
    assert dongle_lt["hostEngine"] is False
    assert "hostEngineMaxFps" not in dongle_lt
    # augmentation copies — the validated profile dict itself is not mutated
    assert "hostEngineMaxFps" not in reg.by_slug("aula-win60-he").lighting


def _api():
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.Lock()
    a._registry = None
    a.reader = None
    a.calib_reader = None
    a.fx = None
    a.pad = None
    a._pad_stop = threading.Event()
    a._pad_thread = None
    a.dev = types.SimpleNamespace(close=lambda: None, is_open=lambda: False)
    a.board = None
    a._remaps = {}
    a._trigger_state = {}
    a._deadband_state = {}
    a._fn_layer_raw = None
    return a


def test_select_board_wires_cap_into_engine():
    a = _api()
    r = a.select_board("aula-mini60he-pro")
    assert r["ok"] is True
    assert a.fx is not None and a.fx.fps == 28
    assert a.fx._spawn_norm == pytest.approx(30.0 / 28.0)
    # the select_board return carries the UI field too
    assert r["active"]["lighting"]["hostEngineMaxFps"] == 28

    r2 = a.select_board("aula-win60-he")
    assert r2["ok"] is True
    assert a.fx.fps == effects.FPS == 60          # cap == engine default, no change
    assert a.fx._spawn_norm == pytest.approx(effects._SPAWN_NORM)
    assert r2["active"]["lighting"]["hostEngineMaxFps"] == 60


# ------------------------------------------------------------ engine behavior ----
def test_spawn_density_is_rate_independent(monkeypatch):
    """The rain spawner's per-frame probability scales by the instance's
    spawn norm: with speed 0.5 the threshold is exactly 1.0 * norm, so a
    fixed random draw of 0.7 spawns at 28 fps (norm ~1.07) and does NOT at
    60 fps (norm 0.5) — per-SECOND density stays constant, per-frame does
    the scaling. This is the check that a 28 fps board gets the intended
    particle count rather than 28/60 of it."""
    monkeypatch.setattr(effects.random, "random", lambda: 0.7)

    def spawned(eng):
        z = effects.Zone(list(eng.indices), "rain", [(255, 0, 0)],
                         (0, 0, 0), 0.5, 1.0, 0)
        eng._g_rain(z, 0.0, {})
        return len(z.state.get("drops", []))

    assert spawned(_engine(max_fps=28)) == 1
    assert spawned(_engine()) == 0
    assert spawned(_engine(max_fps=120)) == 0     # Win60 behavior unchanged


def test_frame_colors_identical_regardless_of_cap():
    """The cap changes PACING only: for deterministic generators the
    rendered frame at a given t is byte-identical between a default engine
    and a capped one (same gamma, same palette math)."""
    palette = [(255, 165, 0), (0, 128, 255)]
    for mode in ("static", "wave", "breath", "comet"):   # deterministic gens
        frames = []
        for cap in (None, 28):
            eng = _engine(max_fps=cap)
            z = effects.Zone(list(eng.indices), mode, palette,
                             (10, 10, 10), 0.6, 0.9, 0)
            f = {}
            getattr(eng, "_g_" + mode)(z, 1.25, f)
            frames.append(f)
        assert frames[0] == frames[1], f"{mode} frame differs under cap"


def _run_one_frame(eng):
    """Start the engine, capture the first pacing sleep, stop. The sleep
    interval IS the pacing contract (1/fps)."""
    sleeps = []
    orig_stop = eng._stop

    def fake_sleep(s):
        sleeps.append(s)
        orig_stop.set()

    real_sleep = effects.time.sleep
    effects.time.sleep = fake_sleep
    try:
        eng.start("static", [(255, 0, 0)], (0, 0, 0), 0.5, 1.0)
        eng._thread.join(timeout=2.0)
    finally:
        effects.time.sleep = real_sleep
        eng.stop()
    return sleeps


def test_run_loop_sleep_matches_declared_rate():
    sent = []
    eng = effects.PerKeyEffectEngine(FakeKM(), lambda f: sent.append(f),
                                     max_fps=28)
    sleeps = _run_one_frame(eng)
    assert sent, "engine sent no frame"
    assert sleeps and sleeps[0] == pytest.approx(1.0 / 28.0)

    sent2 = []
    eng2 = effects.PerKeyEffectEngine(FakeKM(), lambda f: sent2.append(f))
    sleeps2 = _run_one_frame(eng2)
    assert sent2
    assert sleeps2 and sleeps2[0] == pytest.approx(1.0 / 60.0)  # Win60 pacing


# ======================== matrix geometry: the 22-stride assumption ========
# GAP CLOSED 2026-07-21: the engine is board-neutral everywhere it uses
# `_nx_map`/`_ny_map`, but Cross and Striation derive row/column
# ARITHMETICALLY as `idx // 22` / `idx % 22` — the Win60 device-index matrix
# — and no test pinned that. These tests pin BOTH halves of the audit
# finding as data:
#   * the Win60's own layout really is a 22-stride matrix, so its Cross and
#     Striation behaviour is correct and must stay byte-identical;
#   * the MINI 60 HE PRO's layout is NOT, so on that board (hostEngine true,
#     28 fps) those two generators group unrelated keys.
# A geometric fallback added later must keep the Win60 assertions below
# passing unchanged — that is what makes it provably additive.
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "tools"))

from validate_keymap import load_keymap        # noqa: E402


WIN60_KEYMAP = os.path.join(_ROOT, "ui", "keymap.json")
MINI60_LAYOUT = os.path.join(_ROOT, "ui", "layouts", "aula-mini60he-pro.json")


class LayoutKM:
    """KeyMap stand-in built from a real layout file (only what the effect
    engine touches: by_index x/y and index_of_code)."""

    def __init__(self, path):
        self.by_index = {int(k["index"]): {"x": float(k["x"]),
                                           "y": float(k["y"])}
                         for k in load_keymap(path)["keys"]}
        self.index_of_code = {}


def _rows_by_stride(km, stride=22):
    rows = {}
    for i in km.by_index:
        rows.setdefault(i // stride, []).append(i)
    return rows


def test_win60_index_rows_are_exactly_its_physical_rows():
    """`idx // 22` on the Win60 selects a set of keys that all share ONE y —
    a real physical row — and the buckets ascend with y. This is why Cross
    and Striation look right on the shipped board."""
    km = LayoutKM(WIN60_KEYMAP)
    rows = _rows_by_stride(km)
    assert sorted(rows) == [1, 2, 3, 4, 5]            # row 0 is unpopulated
    ys = []
    for r in sorted(rows):
        distinct = {km.by_index[i]["y"] for i in rows[r]}
        assert len(distinct) == 1, "row %d spans %r" % (r, sorted(distinct))
        ys.append(distinct.pop())
    assert ys == sorted(ys) and len(set(ys)) == 5
    assert [len(rows[r]) for r in sorted(rows)] == [14, 14, 13, 12, 8]
    # within a row, `idx % 22` increases left-to-right: the arithmetic column
    # is a real column ordering, not an accident of index order.
    for r in sorted(rows):
        by_x = sorted(rows[r], key=lambda i: km.by_index[i]["x"])
        assert [i % 22 for i in by_x] == sorted(i % 22 for i in by_x)


def test_mini60_layout_is_not_a_22_stride_matrix():
    """The MINI 60 HE PRO's firmware indices are stride-16-ish (Esc=0, then
    17..28, Backspace=92): `idx // 22` mixes physical rows together, so the
    Win60 row arithmetic is wrong there. 3 of its 5 index-buckets span more
    than one y — Cross would light unrelated keys and Striation's shooting
    stars would fly across nonsense groupings."""
    km = LayoutKM(MINI60_LAYOUT)
    rows = _rows_by_stride(km)
    scrambled = [r for r in sorted(rows)
                 if len({km.by_index[i]["y"] for i in rows[r]}) > 1]
    assert scrambled, "MINI layout unexpectedly is a clean 22-stride matrix"
    assert len(scrambled) == 3
    # ...and the true geometry is 5 clean rows of 14/14/13/12/8, exactly the
    # Win60 shape — so a geometric row/col derivation has a correct answer
    # available for this board.
    geo = {}
    for i, k in km.by_index.items():
        geo.setdefault(round(k["y"]), []).append(i)
    assert sorted(len(v) for v in geo.values()) == [8, 12, 13, 14, 14]


def _cross_frame(km, pressed):
    eng = effects.PerKeyEffectEngine(km, lambda f: None)
    z = effects.Zone(list(eng.indices), "cross", [(255, 0, 0)], (0, 0, 0),
                     0.5, 1.0, 0)
    eng._depths = {pressed: 1.0}
    frame = {}
    eng._g_cross(z, 0.0, frame)
    return z, frame


def test_win60_cross_lights_exactly_the_pressed_row_and_column():
    """CLAUDE.md: "Cross = press lights that key's exact row+column". Pinned
    against the real shipped keymap for three different keys — the contract
    any board-aware row/col rework must preserve byte-for-byte."""
    km = LayoutKM(WIN60_KEYMAP)
    for pressed in (22, 69, 110):        # row 1 col 0, row 3 col 3, bottom row
        assert pressed in km.by_index
        z, frame = _cross_frame(km, pressed)
        lit = {i for i, c in frame.items() if c != (0, 0, 0)}
        expected = {i for i in z.indices
                    if i // 22 == pressed // 22 or i % 22 == pressed % 22}
        assert lit == expected, "pressed %d" % pressed
        assert pressed in lit
        # every unlit key is the zone background, not a stale colour
        assert all(frame[i] == (0, 0, 0) for i in z.indices if i not in lit)


def test_win60_striation_rows_are_the_five_physical_rows():
    """Striation buckets keys into rows once, at first frame. On the Win60
    those buckets are the five physical rows (row ids 1..5)."""
    km = LayoutKM(WIN60_KEYMAP)
    eng = effects.PerKeyEffectEngine(km, lambda f: None)
    z = effects.Zone(list(eng.indices), "striation", [(255, 0, 0)],
                     (0, 0, 0), 0.5, 1.0, 0)
    eng._g_striation(z, 0.0, {})
    rows = z.state["rows"]
    assert sorted(rows) == [1, 2, 3, 4, 5]
    assert rows == _rows_by_stride(km)
    assert sorted(len(v) for v in rows.values()) == [8, 12, 13, 14, 14]


def test_geometry_driven_generators_are_already_board_neutral():
    """Contrast: every OTHER generator positions keys through the
    normalised x/y maps, which are derived from the layout — so they render
    on the MINI's real geometry with no matrix assumption at all. This is
    the property Cross/Striation are missing, asserted so a future rework
    cannot quietly regress the rest."""
    for path in (WIN60_KEYMAP, MINI60_LAYOUT):
        km = LayoutKM(path)
        eng = effects.PerKeyEffectEngine(km, lambda f: None)
        assert set(eng._nx_map) == set(km.by_index)
        assert min(eng._nx_map.values()) == 0.0
        assert max(eng._nx_map.values()) == 1.0
        assert min(eng._ny_map.values()) == 0.0
        assert max(eng._ny_map.values()) == 1.0
        for mode in ("wave", "breath", "comet", "static"):
            z = effects.Zone(list(eng.indices), mode, [(255, 165, 0)],
                             (0, 0, 0), 0.6, 0.9, 0)
            frame = {}
            getattr(eng, "_g_" + mode)(z, 1.25, frame)
            assert set(frame) == set(km.by_index), (path, mode)
