"""Phase 8 review: the carrier and the UI-started host effects must not race.
`_overlay_sync` (games_sync thread) and `start_multicolor` / `start_zones` /
`stop_multicolor` (pywebview threads) all drive ONE engine, so they serialise on
the module _CARRIER_LOCK. Interleavings are forced with delays on fakes: no HID,
no keyboard."""
import threading
import time

import effects
import pytest

# _fake_sensors is autouse: importing it registers it here (no real sensors / nvidia-smi).
from test_overlays_api import _api, _fake_sensors, _teardown, _wait  # noqa: F401

ZONES = [{"codes": ["Space", "A"], "mode": "wave", "colors": [[255, 0, 0]], "bg": [0, 0, 0],
          "brightness": 80, "speed": 60, "direction": 0}]
LIGHT = (0, 200, 100, 0, 4, 4, 0, 0, 20, 0, True, 0)       # set_light positional args


def _engine_threads():
    return [t for t in threading.enumerate()
            if t.is_alive() and getattr(t, "_target", None) is not None
            and getattr(t._target, "__func__", None) is effects.PerKeyEffectEngine._run]


def _slow_is_running(a, secs):
    """is_running answers, THEN dawdles: the caller acts on a stale answer."""
    real = a.fx.is_running

    def slow():
        r = real()
        time.sleep(secs)
        return r
    a.fx.is_running = slow


@pytest.mark.parametrize("starter", ["zones", "multicolor"])
def test_a_profile_switch_carrier_never_overwrites_a_concurrent_ui_effect(tmp_path, starter):
    a = _api(tmp_path)
    a.set_light(*LIGHT)                                  # a static colour the carrier would paint
    a._overlays.pid = "p1"
    a._overlays._pref["cpu"] = True
    a._overlays._apply()                                 # overlay on, nothing streaming yet
    _slow_is_running(a, 0.25)
    t1 = threading.Thread(target=a._overlay_sync)        # games_sync thread
    t1.start()
    time.sleep(0.05)                                     # t1 holds a stale "not running"
    if starter == "zones":
        res = a.start_zones(ZONES)
    else:
        res = a.start_multicolor("wave", [[255, 0, 0]], [0, 0, 0], 80, 60, 0, "v")
    t1.join()
    assert res["ok"]
    assert a._carrier_on is False                        # the user's effect won, not the carrier
    assert a.fx.zones and a.fx.zones[0].mode == "wave"
    assert len(_engine_threads()) == 1
    a.stop_multicolor()
    assert _wait(lambda: not _engine_threads())
    _teardown(a)


def test_concurrent_effect_starts_leave_no_orphan_engine_thread(tmp_path):
    a = _api(tmp_path)
    real_halt = a.fx._halt

    def slow_halt():
        real_halt()
        time.sleep(0.15)                                 # both starters pass _halt, then both start
    a.fx._halt = slow_halt
    gate = threading.Barrier(2)

    def go():
        gate.wait()
        a.start_zones(ZONES)
    ts = [threading.Thread(target=go) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(_engine_threads()) == 1
    a.stop_multicolor()
    assert _wait(lambda: not _engine_threads())          # nothing left streaming
    _teardown(a)


def test_stop_cannot_slip_between_a_carrier_check_and_its_start(tmp_path):
    a = _api(tmp_path)
    a.set_light(*LIGHT)
    a._overlays.pid = "p1"
    a._overlays._pref["cpu"] = True
    a._overlays._apply()
    _slow_is_running(a, 0.25)
    t1 = threading.Thread(target=a._overlay_sync)
    t1.start()
    time.sleep(0.05)
    a.stop_multicolor()                                  # waits for the sync; then stops its engine
    t1.join()
    assert a._carrier_on is False
    assert _wait(lambda: not _engine_threads())
    _teardown(a)
