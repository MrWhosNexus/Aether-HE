"""Phase 1 key statistics through the Api: the shared reader gets owner
"telemetry", every reader the Api builds feeds Telemetry, calibration parks
it, disconnect flushes. Fakes only: no HID, no keyboard."""
import json
import threading

import pytest

import app_web
import boards
import device_state
import drivers
import telemetry
from test_drivers import StubDevice
from test_telemetry import _press

TODAY = "2026-11-04"


class FakeReader:
    def __init__(self, km=None, indices=None):
        self.indices = indices
        self.on_sample = None
        self.started = self.stopped = False

    def start(self): self.started = True
    def stop(self): self.stopped = True
    def alive(self): return self.started and not self.stopped
    def snapshot(self): return {}
    def snapshot_by_index(self): return {}


class FakeDriver:
    FEATURES = frozenset({"travel_stream"})

    def __init__(self):
        self.readers, self.calibration, self.detail = [], [], {}

    def supports(self, f): return f in self.FEATURES
    def connect(self): return {"interface_number": 2}
    def read_keymap_layer(self, fn_layer=False, timeout_s=None): return None
    def make_live_reader(self, km, indices=None):
        r = FakeReader(km, indices)
        self.readers.append(r)
        return r
    def make_calibration_reader(self, km): return FakeReader(km)
    def set_calibration(self, start, any_key=False): self.calibration.append(bool(start))
    def read_trigger_detail(self, km): return self.detail
    def set_actuation(self, *a, **k): pass
    def end_host_stream(self): pass


class FakeDev:
    dead_events = 0
    def __init__(self): self.open = True
    def is_open(self): return self.open
    def close(self): self.open = False


def _api(tmp_path, enabled=True, slug="aula-win60-he"):
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.board = boards.load_registry().by_slug(slug)
    a.km = device_state.KeyMap()
    a.dev = FakeDev()
    a.driver = FakeDriver()
    a.fx = None
    a.pad = None
    a._pad_thread = None
    a._pad_stop = threading.Event()
    a.reader = None
    a.calib_reader = None
    a._reader_users = set()
    a._calibrating = False
    a._trigger_state = {}
    a._settings_path = lambda: str(tmp_path / "settings.json")
    a.telemetry = telemetry.Telemetry(str(tmp_path / "stats"), enabled=enabled,
                                      board=slug, today=lambda: TODAY,
                                      flush_interval_s=None)
    return a


def test_win60_declares_key_stats_and_every_declaring_board_streams_travel():
    reg = boards.load_registry()
    assert reg.by_slug("aula-win60-he").cap("keyStats") is True
    for p in reg.profiles:
        if p.cap("keyStats") is True:
            d = drivers.get_driver(p, StubDevice(), threading.RLock())
            assert d.supports("travel_stream"), p.slug


def test_stats_default_is_on_for_windows_only():
    f = app_web._stats_default_enabled
    assert f(None, "win32") is True
    assert f(None, "linux") is False
    assert f({"collectKeyStats": False}, "win32") is False
    assert f({"collectKeyStats": True}, "linux") is True
    assert f({"collectKeyStats": "yes"}, "win32") is True


def test_make_telemetry_reads_the_setting_and_touches_no_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(app_web, "user_data_dir", lambda: str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({"collectKeyStats": False}))
    a = _api(tmp_path)
    tel = a._make_telemetry()
    assert tel.enabled is False and tel.board == "aula-win60-he"
    assert not (tmp_path / "stats").exists()


def test_api_made_readers_feed_telemetry(tmp_path):
    a = _api(tmp_path)
    r = a._make_live_reader()
    assert r.on_sample == a.telemetry.feed


def test_new_reader_drops_a_press_in_progress(tmp_path):
    a = _api(tmp_path)
    a.telemetry.feed(46, 2.0, 1.0)
    a._make_live_reader()
    a.telemetry.feed(46, 0.0, 1.1)
    assert a.telemetry.aggregate(1) == {}


def test_unsupported_board_is_not_hooked_and_gets_no_owner(tmp_path):
    a = _api(tmp_path, slug="aula-mini60he-pro")
    assert a._make_live_reader().on_sample is None
    assert a._start_stats_reader() is False
    assert "telemetry" not in a._reader_users


def test_connect_starts_the_stats_reader(tmp_path):
    a = _api(tmp_path)
    assert a.connect()["ok"] is True
    assert "telemetry" in a._reader_users
    assert a.reader is a.driver.readers[-1] and a.reader.started


def test_connect_with_stats_disabled_starts_no_reader(tmp_path):
    a = _api(tmp_path, enabled=False)
    assert a.connect()["ok"] is True
    assert a.reader is None and "telemetry" not in a._reader_users


def test_closing_the_analog_tab_keeps_the_stats_stream(tmp_path):
    a = _api(tmp_path)
    a._start_stats_reader()
    assert a.open_analog_codes(["W"])["ok"]
    assert a.reader.indices == a.km.indices()       # whole board: others own it
    assert a.reader.on_sample == a.telemetry.feed
    a.close_analog()
    assert a.reader is not None and "telemetry" in a._reader_users


def test_reader_paused_restores_a_hooked_reader(tmp_path):
    a = _api(tmp_path)
    a._start_stats_reader()
    first = a.reader
    with a._reader_paused():
        assert a.reader is None
    assert first.stopped and a.reader is not first
    assert a.reader.on_sample == a.telemetry.feed


def test_calibration_parks_the_stats_reader_then_restores_it(tmp_path):
    a = _api(tmp_path)
    a._start_stats_reader()
    first = a.reader
    assert a.calibrate(True)["ok"]
    assert a.reader is None and first.stopped
    assert "telemetry" in a._reader_users
    a._restore_shared_reader()                       # e.g. a read-back ends
    assert a.reader is None                          # calibration owns the stream
    assert a.calibrate(False)["ok"]
    assert a.reader is not None and a.reader.started


def test_disconnect_flushes_and_drops_the_owner(tmp_path):
    a = _api(tmp_path)
    a._start_stats_reader()
    first = a.reader
    _press(a.telemetry, 46, [2.0])
    assert a.disconnect()["ok"]
    assert (tmp_path / "stats" / f"{TODAY}.json").exists()
    assert a._reader_users == set() and first.stopped


def test_actuation_read_back_classifies_shallow_presses(tmp_path):
    a = _api(tmp_path)
    w = a.km.index_of_code["W"]
    a.driver.detail = {a.km.by_index[w]["name"]: {"travel_mm": 0.80, "mode": 0}}
    assert a.verify_actuation([])["ok"]
    _press(a.telemetry, w, [0.20, 0.50])
    agg = a.telemetry.aggregate(1)[w]
    assert agg["shallow"] == 1 and agg["presses"] == 0


def test_writing_actuation_forgets_the_read_back(tmp_path):
    a = _api(tmp_path)
    w = a.km.index_of_code["W"]
    a.driver.detail = {a.km.by_index[w]["name"]: {"travel_mm": 0.80, "mode": 0}}
    a.verify_actuation([])
    assert a.set_trigger_codes(["W"], 1.2)["ok"]
    _press(a.telemetry, w, [0.50])
    agg = a.telemetry.aggregate(1)[w]
    assert agg["presses"] == 1 and agg["unrated"] == 1


def test_get_stats_returns_per_code_aggregates_and_totals(tmp_path):
    a = _api(tmp_path)
    _press(a.telemetry, a.km.index_of_code["W"], [1.0, 3.35])
    r = a.get_stats(1)
    assert r["ok"] and r["enabled"] and r["supported"] and r["days"] == 1
    assert r["board"] == "aula-win60-he"
    assert r["keys"]["W"]["presses"] == 1 and r["keys"]["W"]["bottom"] == 1
    assert r["totals"] == {"presses": 1, "shallow": 0, "barely": 0, "bottom": 1}
    for rec in r["keys"].values():                  # privacy: aggregates only
        assert set(rec) == set(telemetry.FIELDS) | {"hist"}


def test_get_stats_clamps_days(tmp_path):
    a = _api(tmp_path)
    assert a.get_stats(0)["days"] == 1
    assert a.get_stats(1000)["days"] == 90
    assert a.get_stats("x")["days"] == 1
    assert a.get_stats(None)["days"] == 1


def test_set_stats_enabled_persists_and_releases_the_reader(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"theme": "neon"}))
    a = _api(tmp_path)
    a._start_stats_reader()
    first = a.reader
    assert a.set_stats_enabled(False) == {"ok": True, "enabled": False}
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved == {"theme": "neon", "collectKeyStats": False}
    assert "telemetry" not in a._reader_users and first.stopped
    assert a.telemetry.enabled is False
    assert a.set_stats_enabled(True) == {"ok": True, "enabled": True}
    assert "telemetry" in a._reader_users and a.reader is not None


def test_clear_stats_deletes_everything(tmp_path):
    a = _api(tmp_path)
    w = a.km.index_of_code["W"]
    _press(a.telemetry, w, [2.0])
    a.telemetry.flush()
    _press(a.telemetry, w, [2.0])
    assert a.clear_stats() == {"ok": True, "deleted": 1}
    assert a.get_stats(1)["keys"] == {}


def test_bridge_methods_without_telemetry_fail_softly(tmp_path):
    a = _api(tmp_path)
    a.telemetry = None
    for r in (a.get_stats(1), a.clear_stats(), a.set_stats_enabled(True)):
        assert r["ok"] is False and r["error"]
