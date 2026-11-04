"""Phase 6 / Task 5: the Api bridge for status-on-keys (get_overlays,
set_overlay, flash), per-profile follow, wiring to the engine. Fakes only: no
HID, no keyboard, no nvidia-smi."""
import json
import threading
import time

import pytest

import app_web
import boards
import device_state
import effects
import overlays


@pytest.fixture(autouse=True)
def _fake_sensors(monkeypatch):
    class Probe:
        available, reason = True, None
        def read(self): return 0.3
    monkeypatch.setattr(overlays, "GpuProbe", Probe)
    ticks = {"n": 0}

    def busy_cpu():                    # never idle: the load reads 100 % from the 2nd sample on
        ticks["n"] += 10
        return (0, ticks["n"])
    monkeypatch.setattr(overlays, "read_cpu_counters", busy_cpu)
    monkeypatch.setattr(overlays, "read_memory_load", lambda: 0.5)
    monkeypatch.setattr(overlays, "_run_nvidia_smi",
                        lambda exe: (_ for _ in ()).throw(AssertionError("real nvidia-smi")))


class FakeDev:
    dead_events = 0
    def __init__(self): self.open = True
    def is_open(self): return self.open
    def close(self): self.open = False


class FakeDriver:
    FEATURES = frozenset({"host_effects", "lighting"})

    def __init__(self):
        self.calls = []

    def supports(self, f): return f in self.FEATURES
    def begin_host_stream(self): self.calls.append(("begin",))
    def end_host_stream(self): self.calls.append(("end",))
    def stream_frame(self, colors, force=False): self.calls.append(("frame",))

    def set_lighting(self, mode, fg, bg=(0, 0, 0), brightness=4, speed=4, direction=0,
                     full_color=0, power_on=True):
        self.calls.append(("light", mode, tuple(fg), tuple(bg), brightness, speed, direction,
                           full_color, power_on))

    def set_per_key_rgb(self, colors, brightness=4, speed=4):
        self.calls.append(("paint", dict(colors), brightness, speed))

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


def _api(tmp_path, slug="aula-win60-he"):
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.board = boards.load_registry().by_slug(slug)
    a.km = device_state.KeyMap()
    a.dev = FakeDev()
    a.driver = FakeDriver()
    a.frames = []
    a.fx = effects.PerKeyEffectEngine(a.km, lambda f: a.frames.append(dict(f)))
    a._settings_path = lambda: str(tmp_path / "settings.json")
    a.reader = a.calib_reader = None
    a._reader_users = set()
    a._overlays = None
    a._ov_profile = None
    a._carrier_on = False
    a._light_src = None
    a._ov_attach()
    return a


def _wait(pred, secs=2.0):
    end = time.time() + secs
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def _teardown(a):
    a.fx.stop()
    a._stop_overlays()


def test_get_overlays_matches_the_dashboard_contract(tmp_path):
    a = _api(tmp_path)
    r = a.get_overlays()
    assert r["ok"] is True and r["supported"] is True
    assert [o["id"] for o in r["overlays"]] == ["cpu", "ram", "gpu", "pomodoro"]
    for o in r["overlays"]:
        assert {"id", "label", "row", "on", "available", "reason", "value"} <= set(o)
        assert o["on"] is False and o["available"] is True and o["reason"] is None
    assert r["pomodoro"] == {"phase": None, "remaining_s": None}
    _teardown(a)


def test_set_overlay_returns_the_contract_and_persists_for_the_active_profile(tmp_path):
    a = _api(tmp_path)
    assert a.set_overlay("cpu", True) == {"ok": True, "id": "cpu", "on": True}
    row = a.get_overlays()["overlays"][0]
    assert row["on"] is True
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["overlays"]["profiles"] == {"p1": {"cpu": True}}      # no profile known yet -> p1
    assert a.set_overlay("cpu", False) == {"ok": True, "id": "cpu", "on": False}
    _teardown(a)


def test_bad_arguments_and_unknown_ids_never_raise(tmp_path):
    a = _api(tmp_path)
    assert a.set_overlay("fan", True)["ok"] is False
    assert a.set_overlay(None, None)["ok"] is False
    assert a.set_overlay({"x": 1}, [])["ok"] is False
    _teardown(a)


def test_the_activated_profile_follows_games_sync(tmp_path):
    a = _api(tmp_path)
    a.games_sync({"activeProfile": "fps", "profiles": []})
    assert a.set_overlay("pomodoro", True)["ok"]
    a.games_sync({"activeProfile": "desk", "profiles": []})            # switch: all off
    rows = {o["id"]: o["on"] for o in a.get_overlays()["overlays"]}
    assert rows == {"cpu": False, "ram": False, "gpu": False, "pomodoro": False}
    a.set_overlay("cpu", True)
    a.games_sync({"activeProfile": "fps", "profiles": []})             # back: its own choice returns
    rows = {o["id"]: o["on"] for o in a.get_overlays()["overlays"]}
    assert rows["pomodoro"] is True and rows["cpu"] is False
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["overlays"]["profiles"] == {"fps": {"pomodoro": True}, "desk": {"cpu": True}}
    _teardown(a)


def test_games_sync_garbage_is_ignored_by_the_overlay_follow(tmp_path):
    a = _api(tmp_path)
    for bad in (None, "x", {}, {"activeProfile": 5}, {"activeProfile": ""}, {"activeProfile": "x" * 99}):
        a._ov_follow(bad)
    assert a._ov_profile is None
    _teardown(a)


def test_start_up_profile_comes_from_settings_json(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({
        "activeProfile": "fps",
        "overlays": {"profiles": {"fps": {"ram": True}}}}), encoding="utf-8")
    a = _api(tmp_path)
    rows = {o["id"]: o["on"] for o in a.get_overlays()["overlays"]}
    assert rows["ram"] is True and rows["cpu"] is False
    _teardown(a)


def test_a_board_without_host_effects_reports_unsupported(tmp_path):
    a = _api(tmp_path)
    a.driver.FEATURES = frozenset()
    assert a.get_overlays() == {"ok": True, "supported": False, "overlays": [],
                                "pomodoro": {"phase": None, "remaining_s": None}}
    assert a.set_overlay("cpu", True)["ok"] is False
    _teardown(a)


def test_the_2_4ghz_dongle_that_drops_stream_writes_is_unsupported(tmp_path):
    a = _api(tmp_path, slug="aula-mini60he-pro-24g")
    assert a.get_overlays()["supported"] is False
    _teardown(a)


def test_no_engine_means_unsupported_not_an_error(tmp_path):
    a = _api(tmp_path)
    a.fx = None
    a._ov_attach()
    assert a.get_overlays()["supported"] is False
    assert a.flash([1, 2, 3])["ok"] is False


def test_the_engine_gets_the_layer(tmp_path):
    a = _api(tmp_path)
    assert a.fx.overlay is a._overlays.layer
    old = a._overlays
    a._ov_attach()                                  # board switch: rebuilt, old sampler stopped
    assert a._overlays is not old and a.fx.overlay is a._overlays.layer
    _teardown(a)


def test_flash_needs_a_running_engine_and_validates_its_arguments(tmp_path):
    a = _api(tmp_path)
    assert a.flash([255, 0, 0])["ok"] is False                           # nothing streaming
    a.fx.start_zones([], global_bg=(0, 0, 0), base={})
    assert _wait(lambda: a.frames)
    assert a.flash([255, 0, 0], 800) == {"ok": True}
    assert _wait(lambda: any(max(v[0] for v in f.values()) > 200 for f in a.frames))
    for bad in (None, "red", [1, 2], ["a", "b", "c"]):
        assert a.flash(bad)["ok"] is False
    assert a.flash([1, 2, 3], "soon")["ok"] is False
    _teardown(a)


def test_pomodoro_state_is_reported_while_on(tmp_path):
    a = _api(tmp_path)
    a.set_overlay("pomodoro", True)
    r = a.get_overlays()
    assert r["pomodoro"]["phase"] == "work" and 1495 <= r["pomodoro"]["remaining_s"] <= 1500
    row = [o for o in r["overlays"] if o["id"] == "pomodoro"][0]
    assert row["on"] and row["phase"] == "work"
    _teardown(a)


def test_the_uis_settings_saves_keep_the_overlay_choices(tmp_path):
    a = _api(tmp_path)
    a.set_overlay("cpu", True)
    assert a.save_settings({"profiles": [{"id": "p1", "name": "Default", "state": {}}],
                            "activeProfile": "p1", "globals": {}})["ok"]
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["overlays"]["profiles"] == {"p1": {"cpu": True}}
    assert saved["activeProfile"] == "p1"
    _teardown(a)
