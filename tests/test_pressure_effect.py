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
