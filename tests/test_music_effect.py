"""Phase 7 "music" host effect: band levels -> column bars, beat pulse on the
background, idle state without audio, and the engine owning the capture
lifecycle. The generator is called directly with a fake clock and a fake
MusicSource. No audio device, no HID, no keyboard."""
import math
import time

import pytest

import device_state
import effects
import music

BG = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)


class FakeKM:
    """2 rows x 14 columns: row y=0 on top, y=1 at the bottom."""
    def __init__(self):
        self.by_index = {i: {"x": float(i % 14), "y": float(i // 14)} for i in range(28)}
        self.index_of_code = {}


class FakeSource:
    def __init__(self, levels=None, live=True, seq=0):
        self.levels = tuple(levels or (0.0,) * 14)
        self.live, self.seq = live, seq
        self.calls = []

    def snapshot(self):
        return music.MusicSnapshot(self.levels, self.seq, self.live)

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")


def _engine(src=None, km=None):
    eng = effects.PerKeyEffectEngine(km or FakeKM(), lambda frame: None)
    eng.music = src
    return eng


def _zone(eng, palette=(RED,), bg=BG, bright=1.0, speed=0.5):
    return effects.Zone(list(eng.indices), "music", list(palette), bg, speed, bright, 0)


def _frame(eng, z, t):
    frame = {}
    eng._g_music(z, t, frame)
    return frame


TOP, BOTTOM = 0, 14          # first index of each FakeKM row


# ---------------------------------------------------------------- bars ----
def test_band_level_sets_the_bar_height():
    lv = [0.0] * 14
    lv[0], lv[1], lv[2] = 1.0, 0.5, 0.25
    eng = _engine(FakeSource(lv))
    z = _zone(eng, palette=(RED, BLUE))
    f = _frame(eng, z, 0.0)
    assert f[BOTTOM + 0] == RED and f[TOP + 0] == BLUE      # full bar, gradient bottom->top
    assert f[BOTTOM + 1] == RED and f[TOP + 1] == BG        # half = the bottom row only
    assert f[BOTTOM + 2] == (127, 0, 0) and f[TOP + 2] == BG
    assert f[BOTTOM + 3] == BG                              # silent band


def test_attack_is_instant_and_release_follows_the_speed_slider():
    src = FakeSource([1.0] * 14)
    slow, fast = _engine(src), _engine(src)
    zs, zf = _zone(slow, speed=0.0), _zone(fast, speed=1.0)
    assert _frame(slow, zs, 0.0)[TOP] == RED                # instant
    _frame(fast, zf, 0.0)
    src.levels = (0.0,) * 14
    s = _frame(slow, zs, 0.1)[TOP]
    f = _frame(fast, zf, 0.1)[TOP]
    assert f[0] < s[0]                                      # faster speed falls faster
    exp_slow = math.exp(-0.1 / effects.MUSIC_RELEASE_SLOW_S)
    assert abs(s[0] - 255 * (exp_slow * 2 - 1)) <= 1          # top row = 2 * level - 1
    for k in range(1, 120):
        last = _frame(slow, zs, 0.1 + k / 60)
    assert all(c == BG for c in last.values())              # dark within 2 s, no endless tail


def test_wide_key_averages_its_columns():
    km = device_state.KeyMap()
    eng = _engine(FakeSource(), km=km)
    lay = eng._music_map()
    space = km.index_of_code["Space"]
    bands = lay[space][0]
    lv = [0.0] * 14
    lv[bands[0]] = 0.5                                       # one of its columns half full
    eng.music.levels = tuple(lv)
    z = _zone(eng)
    f = _frame(eng, z, 0.0)
    assert f[space] == effects._lerp(BG, RED, 5 * 0.5 / len(bands))   # 5 rows * mean level


def test_real_win60_bottom_to_top():
    km = device_state.KeyMap()
    eng = _engine(FakeSource([0.6] * 14), km=km)            # 0.6 * 5 rows = 3 rows lit
    z = _zone(eng)
    f = _frame(eng, z, 0.0)
    code = km.index_of_code
    assert f[code["Space"]] == RED and f[code["Z"]] == RED and f[code["A"]] == RED
    assert f[code["Q"]] == BG and f[code["1"]] == BG


def test_brightness_scales_the_bars():
    eng = _engine(FakeSource([1.0] * 14))
    z = _zone(eng, bright=0.5)
    assert _frame(eng, z, 0.0)[TOP] == (127, 0, 0)


# ---------------------------------------------------------------- beats ----
def test_a_new_beat_pulses_the_background_then_fades():
    src = FakeSource(seq=4)
    eng = _engine(src)
    z = _zone(eng, palette=(RED,), bg=(0, 0, 0))
    assert _frame(eng, z, 0.0)[TOP] == BG                   # first look: no pulse
    src.seq = 5
    hit = _frame(eng, z, 1 / 60)[TOP]
    assert hit == effects._lerp(BG, RED, effects.MUSIC_PULSE_MAX)
    later = _frame(eng, z, 1.0)[TOP]
    assert later == BG


def test_unchanged_beat_sequence_never_pulses():
    eng = _engine(FakeSource(seq=9))
    z = _zone(eng)
    for k in range(30):
        assert _frame(eng, z, k / 60)[TOP] == BG


# ----------------------------------------------------------------- idle ----
@pytest.mark.parametrize("src", [None, FakeSource([1.0] * 14, live=False)])
def test_no_audio_breathes_the_bottom_row_only(src):
    eng = _engine(src)
    z = _zone(eng)
    peak = _frame(eng, z, effects.MUSIC_IDLE_PERIOD_S / 2)
    assert peak[BOTTOM] == effects._lerp(BG, RED, effects.MUSIC_IDLE_MAX)
    assert peak[TOP] == BG
    assert _frame(eng, z, effects.MUSIC_IDLE_PERIOD_S)[BOTTOM] == BG


def test_a_failing_source_is_treated_as_no_audio():
    class Boom(FakeSource):
        def snapshot(self):
            raise RuntimeError("capture hiccup")
    eng = _engine(Boom())
    z = _zone(eng)
    f = _frame(eng, z, 0.0)
    assert set(f) == set(eng.indices)


def test_all_channel_values_stay_in_byte_range():
    src = FakeSource([1.0, 0.0] * 7, seq=1)
    eng = _engine(src, km=device_state.KeyMap())
    z = _zone(eng, palette=((255, 255, 255), (255, 0, 0)), bg=(255, 255, 255))
    for k in range(120):
        src.seq += k % 7 == 0
        src.levels = tuple((math.sin(k / 5 + b) + 1) / 2 for b in range(14))
        for c in _frame(eng, z, k / 60).values():
            assert all(isinstance(v, int) and 0 <= v <= 255 for v in c)


def test_frame_cost_is_well_under_the_budget():
    eng = _engine(FakeSource([0.5] * 14), km=device_state.KeyMap())
    z = _zone(eng, palette=(RED, BLUE))
    _frame(eng, z, 0.0)
    t0 = time.perf_counter()
    for k in range(1, 61):
        _frame(eng, z, k / 60)
    assert (time.perf_counter() - t0) / 60 < 0.004          # < 4 ms per 61-key frame


# ------------------------------------------------------------ lifecycle ----
def test_the_engine_starts_capture_only_for_music_and_stops_it_with_the_effect():
    src = FakeSource()
    eng = _engine(src)
    eng.start("wave", [RED], BG, 0.5, 1.0)
    assert src.calls == ["stop"]                             # not music: kept off
    eng.start_zones([{"indices": eng.indices[:14], "mode": "music", "palette": [RED]},
                     {"indices": eng.indices[14:], "mode": "wave", "palette": [RED]}])
    assert src.calls[-1] == "start"
    eng.stop()
    assert src.calls[-1] == "stop" and not eng.is_running()


def test_restarting_music_keeps_the_capture_running():
    src = FakeSource()
    eng = _engine(src)
    eng.start("music", [RED], BG, 0.5, 1.0)
    eng.start("music", [BLUE], BG, 0.9, 1.0)                 # palette/speed edit
    assert src.calls == ["start", "start"]                   # no stop in between
    eng.stop()
    assert src.calls[-1] == "stop"


def test_switching_away_from_music_stops_the_capture():
    src = FakeSource()
    eng = _engine(src)
    eng.start("music", [RED], BG, 0.5, 1.0)
    eng.start("rain", [RED], BG, 0.5, 1.0)
    assert src.calls == ["start", "stop"]
    eng.stop()


def test_a_dead_stream_releases_the_capture():
    src = FakeSource()

    def broken(frame):
        raise OSError("device gone")
    eng = effects.PerKeyEffectEngine(FakeKM(), broken)
    eng.music = src
    eng.start("music", [RED], BG, 0.5, 1.0)
    end = time.time() + 2.0
    while eng.is_running() and time.time() < end:
        time.sleep(0.01)
    assert src.calls == ["start", "stop"]


def test_a_raising_source_never_breaks_start_or_stop():
    class Bad(FakeSource):
        def start(self):
            raise RuntimeError("no COM")
        stop = start
    eng = _engine(Bad())
    eng.start("music", [RED], BG, 0.5, 1.0)
    assert eng.is_running()
    eng.stop()
    assert not eng.is_running()


def test_engines_without_a_source_are_unchanged():
    eng = _engine(None)
    eng.start("music", [RED], BG, 0.5, 1.0)
    eng.stop()
    assert eng.music is None
