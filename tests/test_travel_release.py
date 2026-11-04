"""Travel Test release detection, from a real WIN 60 HE capture (2026-11-03).

On release the firmware's LAST travel report is usually mid-travel
(0.07-0.98 mm in the capture; W ended on 0.45, 0.12, 0.50, 0.70, 0.51) and
then the stream goes silent — it almost never sends a final ~0 frame. A held
key also goes silent (the stream is event-driven), but its last motion was
DOWNWARD. The reader must tell the two apart: a key whose last report moved
up and then fell silent has been released; a key whose last report moved
down (or was its only report) is being held.
"""
import threading
import time
import types

import device_state


class _FakeHandle:
    def __init__(self, reports=None):
        self.reports = list(reports or [])

    def set_nonblocking(self, v):
        pass

    def read(self, n):
        return self.reports.pop(0) if self.reports else []


class _FakeDev:
    def __init__(self, reports=None):
        self._lock = threading.Lock()
        self._dev = _FakeHandle(reports)
        self.writes = []

    def write(self, payload):
        self.writes.append(list(payload))
        return len(payload)


def _travel_report(idx, mm):
    raw = int(round(mm * 100))
    r = [0] * 64
    r[1] = 33; r[5] = 5; r[7] = idx // 22; r[8] = idx % 22
    r[9] = raw & 0xFF; r[10] = raw >> 8
    return r


_KM = types.SimpleNamespace(indices=lambda: [46],
                            code_of_index={46: "W"},
                            code_of=lambda i: {46: "W"}.get(i))

# Captured W press + release (t=48.59 s segment): down to 3.25, back up,
# last frame 0.45 mm, then nothing.
_PRESS = [0.31, 1.02, 2.06, 3.25]
_RELEASE_TAIL = [2.42, 2.11, 1.72, 1.18, 0.45]


def _run(reports, wait_s):
    lr = device_state.LiveReader(_FakeDev(reports), _KM, indices=[46])
    lr.start()
    try:
        time.sleep(wait_s)
        return lr.snapshot()
    finally:
        lr.stop()


def test_release_that_ends_mid_travel_clears_the_key():
    frames = [_travel_report(46, mm) for mm in _PRESS + _RELEASE_TAIL]
    assert _run(frames, 0.6) == {}, "released key stuck partway down"


def test_key_held_at_the_bottom_stays_visible():
    # Captured hold (t=54.36 s): rising to 3.40, then silence while held.
    frames = [_travel_report(46, mm) for mm in (2.56, 2.79, 2.97, 3.18, 3.40)]
    assert _run(frames, 0.6) == {"W": 3.40}


def test_partial_press_held_still_stays_visible():
    # A single report (no motion history) is a hold, not a release.
    assert _run([_travel_report(46, 1.20)], 0.6) == {"W": 1.20}


def test_release_frame_under_noise_floor_still_clears_immediately():
    frames = [_travel_report(46, mm) for mm in (1.5, 3.0, 0.8, 0.01)]
    assert _run(frames, 0.1) == {}


def _run_hooked(reports, wait_s, hook):
    lr = device_state.LiveReader(_FakeDev(reports), _KM, indices=[46])
    lr.on_sample = hook
    lr.start()
    try:
        time.sleep(wait_s)
        return lr.snapshot()
    finally:
        lr.stop()


def test_on_sample_sees_every_report_then_the_release_clear():
    seen = []
    frames = [_travel_report(46, mm) for mm in _PRESS + _RELEASE_TAIL]
    assert _run_hooked(frames, 0.6, lambda i, mm, t: seen.append((i, mm))) == {}
    assert seen == [(46, mm) for mm in _PRESS + _RELEASE_TAIL] + [(46, 0.0)]


def test_a_held_key_gets_no_clear():
    seen = []
    frames = [_travel_report(46, mm) for mm in (2.56, 3.40)]
    _run_hooked(frames, 0.6, lambda i, mm, t: seen.append(mm))
    assert seen == [2.56, 3.40]


def test_a_failing_hook_does_not_stop_the_reader():
    def boom(i, mm, t):
        raise RuntimeError("hook bug")
    frames = [_travel_report(46, mm) for mm in _PRESS + _RELEASE_TAIL]
    assert _run_hooked(frames, 0.6, boom) == {}


def test_reader_feeds_telemetry_one_press(tmp_path):
    import telemetry
    tel = telemetry.Telemetry(str(tmp_path), board="aula-win60-he",
                              today=lambda: "2026-11-04", flush_interval_s=None)
    tel.set_actuation({46: 0.80})
    frames = [_travel_report(46, mm) for mm in _PRESS + _RELEASE_TAIL]
    _run_hooked(frames, 0.6, tel.feed)
    agg = tel.aggregate(1)[46]
    assert agg["presses"] == 1 and agg["hist"][32] == 1 and agg["unrated"] == 0
