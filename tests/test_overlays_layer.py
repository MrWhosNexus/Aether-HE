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
    # blank_base=False: these tests check painting over a visible base.
    return overlays.OverlayLayer(ROWS, ALL, overlays.Pomodoro(work, brk), blank_base=False)


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
    lay = overlays.OverlayLayer(ROWS, ALL, blank_base=False)
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
    eng.overlay = overlays.OverlayLayer(ROWS, ALL, blank_base=False)
    assert eng._frame_interval == before and eng.fps == 28


def test_a_repeated_enable_does_not_swallow_the_phase_change_pulse():
    lay = _layer()
    lay.set_enabled("pomodoro", True, now=1000.0)
    lay.apply(_frame(), 1099.9)                                 # last moment of work
    lay.set_enabled("pomodoro", True, now=1099.95)              # a status poll re-asserts "on"
    f = _frame()
    lay.apply(f, 1100.0)                                        # break begins: the pulse must still fire
    assert f[0] == overlays.POMO_BREAK_RGB and f[15] == overlays.POMO_BREAK_RGB


def test_any_overlay_switches_the_lighting_underneath_off():
    lay = overlays.OverlayLayer(ROWS, ALL, overlays.Pomodoro(100, 20))
    f = _frame(); lay.apply(f, now=0.0)
    assert f == BASE                                   # nothing on: untouched
    lay.set_enabled("cpu", True, now=0.0)
    lay.set_value("cpu", 0.0)
    f = _frame(); lay.apply(f, now=0.0)
    cpu = set(ROWS["cpu"])
    assert all(f[i] == (0, 0, 0) for i in ALL if i not in cpu)
