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
