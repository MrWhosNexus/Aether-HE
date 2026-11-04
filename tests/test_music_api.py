"""Phase 7: Api wiring for the music visualizer — the music_status bridge and
the engine owning the capture through start_multicolor / stop_multicolor.
Fake driver, fake loopback backend: no HID, no keyboard, no audio device."""
import inspect
import threading
import time

import app_web
import boards
import device_state
import effects
import music
from test_music_source import FakeBackend, _spectrum, _wait
from test_overlays_api import FakeDev, FakeDriver

KEYS = {"ok", "available", "reason", "state", "device"}


def _api(backend=None, available=(True, None)):
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.board = boards.load_registry().by_slug("aula-win60-he")
    a.km = device_state.KeyMap()
    a.dev = FakeDev()
    a.driver = FakeDriver()
    a.frames = []
    a.fx = effects.PerKeyEffectEngine(a.km, lambda f: a.frames.append(1))
    a.reader = a.calib_reader = None
    a._reader_users = set()
    a._carrier_on = False
    if backend is not None:
        a._music = music.MusicSource(backend_factory=lambda: backend,
                                     spectrum_factory=_spectrum(),
                                     available=available)
        a._music_attach()
    return a


def test_status_without_a_source_reports_availability(monkeypatch):
    monkeypatch.setattr(music, "availability",
                        lambda: (False, "Music visualizer needs the numpy package (not installed)."))
    r = _api().music_status()
    assert r == {"ok": True, "available": False, "state": "unavailable", "device": None,
                 "reason": "Music visualizer needs the numpy package (not installed)."}
    monkeypatch.setattr(music, "availability", lambda: (True, None))
    assert _api().music_status() == {"ok": True, "available": True, "reason": None,
                                     "state": "off", "device": None}


def test_music_effect_listens_while_running_and_releases_on_stop():
    be = FakeBackend()
    a = _api(be)
    assert a.fx.music is a._music
    assert a.music_status()["state"] == "off" and be.opened == []
    r = a.start_multicolor("music", [[255, 0, 0]], [0, 0, 0], 80, 50)
    assert r["ok"] is True
    assert _wait(lambda: a.music_status()["state"] == "listening")
    st = a.music_status()
    assert set(st) == KEYS and st["device"] == "Speakers A"
    assert a.stop_multicolor()["ok"] is True
    assert be.streams[0].closed and not a._music.running()
    assert a.music_status()["state"] == "off"


def test_other_effects_never_open_the_audio_device():
    be = FakeBackend()
    a = _api(be)
    for mode in ("wave", "reactive", "pressure", "rain"):
        a.start_multicolor(mode, [[255, 0, 0]])
    time.sleep(0.05)
    a.stop_multicolor()
    assert be.opened == [] and be.entered == 0


def test_switching_from_music_to_another_effect_stops_listening():
    be = FakeBackend()
    a = _api(be)
    a.start_multicolor("music", [[255, 0, 0]])
    assert _wait(lambda: be.opened == ["spk-a"])
    a.start_multicolor("wave", [[255, 0, 0]])
    assert not a._music.running() and be.streams[0].closed
    a.stop_multicolor()


def test_a_music_zone_listens_too():
    be = FakeBackend()
    a = _api(be)
    r = a.start_zones([{"codes": ["Q", "W"], "mode": "music", "colors": [[0, 255, 0]]},
                       {"codes": ["A"], "mode": "wave", "colors": [[0, 0, 255]]}])
    assert r["ok"] is True
    assert _wait(lambda: a.music_status()["state"] == "listening")
    a.stop_multicolor()
    assert not a._music.running()


def test_missing_dependencies_still_run_the_effect_and_say_why():
    be = FakeBackend()
    a = _api(be, available=(False, "Music visualizer needs the numpy and soundcard packages (not installed)."))
    assert a.start_multicolor("music", [[255, 0, 0]])["ok"] is True
    assert a.fx.is_running() and be.entered == 0
    st = a.music_status()
    assert st["available"] is False and "numpy and soundcard" in st["reason"]
    a.stop_multicolor()


def test_status_never_raises():
    a = _api(FakeBackend())

    class Boom:
        def status(self):
            raise RuntimeError("bad state")
    a._music = Boom()
    r = a.music_status()
    assert r["ok"] is False and "bad state" in r["error"]


def test_every_engine_gets_the_source():
    for fn in (app_web.Api.__init__, app_web.Api.select_board):
        assert "self._music_attach()" in inspect.getsource(fn), fn.__name__
    assert "self._music = music.MusicSource()" in inspect.getsource(app_web.Api.__init__)
    a = _api(FakeBackend())
    a.fx = effects.PerKeyEffectEngine(a.km, lambda f: None)
    a._music_attach()
    assert a.fx.music is a._music
