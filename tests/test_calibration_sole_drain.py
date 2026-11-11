"""Calibration owns the HID stream: nothing may start a LiveReader or do a
read-back until it ends (a press-reactive effect re-sent as calibration
starts used to start one and swallow every calibration report). Fakes only."""
import pytest

from test_stats_api import _api


def _live(a):
    return [r for r in a.driver.readers if r.started and not r.stopped]


def test_reactive_reader_deferred_while_calibrating(tmp_path):
    a = _api(tmp_path, enabled=False)
    assert a.calibrate(True)["ok"]
    assert a._acquire_reader("reactive", a._make_live_reader) is None
    assert a.reader is None and not _live(a)
    assert "reactive" in a._reader_users
    assert a.calibrate(False)["ok"]
    assert a.reader is not None and len(_live(a)) == 1   # restored for its owner


def test_analog_open_deferred_while_calibrating(tmp_path):
    a = _api(tmp_path, enabled=False)
    a.calibrate(True)
    r = a.open_analog_codes([])
    assert r["ok"] and r.get("deferred") == "calibrating"
    assert a.reader is None and not _live(a)
    a.calibrate(False)
    assert len(_live(a)) == 1


def test_read_back_refused_while_calibrating(tmp_path):
    a = _api(tmp_path, enabled=False)
    a.calibrate(True)
    with pytest.raises(RuntimeError):
        with a._reader_paused():
            pass
    a.calibrate(False)
    with a._reader_paused():
        pass


def test_failed_arm_clears_flag(tmp_path):
    a = _api(tmp_path, enabled=False)
    def boom(*_a, **_k):
        raise OSError("write failed")
    a.driver.set_calibration = boom
    assert a.calibrate(True)["ok"] is False
    assert a._calibrating is False


# ---- transient read errors (the board throws one entering calibration) ----
import threading
import time

import device_state


class _Km:
    def code_of(self, idx):
        return {46: "W"}.get(idx)


class _SoftDev:
    """read() would drop the handle; read_soft() must be the one used."""
    def __init__(self, script):
        self.script = list(script)
        self.dead = []
        self.hard_reads = 0

    def read(self, n, timeout_ms=0):
        self.hard_reads += 1
        raise AssertionError("CalibrationReader used read(), which drops the handle")

    def read_soft(self, n, timeout_ms=0):
        if not self.script:
            time.sleep(0.005)
            return []
        x = self.script.pop(0)
        if isinstance(x, Exception):
            raise x
        return x

    def mark_dead(self, why):
        self.dead.append(why)


def _calib_report(idx):
    r = [0] * 64
    r[1] = 33; r[6] = 8; r[7] = 1
    r[8 + idx % 22] |= 1 << (idx // 22)
    return r


def _wait(pred, s=2.0):
    end = time.monotonic() + s
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_one_read_error_does_not_end_calibration():
    dev = _SoftDev([IOError("read error"), _calib_report(46)])
    cr = device_state.CalibrationReader(dev, _Km())
    cr.start()
    try:
        assert _wait(lambda: "W" in cr.calibrated)
        assert not cr.failed and dev.dead == [] and dev.hard_reads == 0
    finally:
        cr.stop()


def test_persistent_read_errors_mark_the_link_dead():
    dev = _SoftDev([IOError("read error")] * 60)
    cr = device_state.CalibrationReader(dev, _Km())
    cr.start()
    try:
        # The reader gives up after 51 failed reads 50 ms apart (~2.6 s here).
        # Hosted macOS runners stretch short sleeps a lot, so allow 15 s: the
        # wait still returns the moment `failed` flips.
        assert _wait(lambda: cr.failed, 15.0)
        assert dev.dead
    finally:
        cr.stop()


def test_read_calibrated_reports_an_aborted_session(tmp_path):
    a = _api(tmp_path, enabled=False)
    a.calibrate(True)
    a.calib_reader.failed = True
    r = a.read_calibrated()
    assert r["aborted"] and r["done"] is False
    a.calibrate(False)
    assert "aborted" not in a.read_calibrated()
