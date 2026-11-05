"""drivers/magnet.py (WIN 68 HE Max) against a fake device: no HID, no board."""
import threading

import pytest

import app_web
import boards
import device_state
import drivers
import protocol_magnet as pm
from drivers.base import UnsupportedFeature
from drivers.magnet import MagnetDriver, MagnetLiveReader


class FakeDev:
    def __init__(self, replies=None):
        self.writes = []
        self.replies = list(replies or [])
        self.dead = []
        self.rx = 0
        self._lock = threading.Lock()

    def is_open(self): return True
    def open(self): return {}
    def write(self, payload):
        self.writes.append(list(payload)); return len(payload)
    def read_soft(self, n, timeout_ms=0):
        return self.replies.pop(0) if self.replies else []
    def note_rx(self): self.rx += 1
    def mark_dead(self, why): self.dead.append(why)


def _drv(dev=None, experimental=False):
    p = boards.load_registry().by_slug("aula-win68he-max")
    d = drivers.get_driver(p, dev or FakeDev())
    assert isinstance(d, MagnetDriver)
    d.experimental = experimental
    return d


def _frames(dev):
    out = []
    for w in dev.writes:
        assert w[0] == pm.REPORT_ID and len(w) == 65
        f = w[1:]
        assert pm.is_valid(f)
        out.append(f)
    return out


def test_registry_dispatches_the_magnet_driver_and_withholds_it_from_the_picker():
    p = boards.load_registry().by_slug("aula-win68he-max")
    assert p.protocol == "protocol_magnet" and p.drivable and p.offered is False
    assert p.capabilities["actuation"] == "wip" and p.capabilities["perKeyRgb"] is True


def test_static_colour_is_custom_mode_plus_every_key():
    dev = FakeDev()
    _drv(dev).set_lighting(pm.LIGHT_MODE_CUSTOM, (10, 20, 30), brightness=3, speed=2)
    fs = _frames(dev)
    assert fs[0] == pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=3, speed=2)
    keys = [f[5] for f in fs[1:]]
    assert sorted(keys) == sorted(pm.KEY_ORDER)
    assert all(f[6:9] == [10, 20, 30] and f[2] == pm.CMD_KEY_RGB for f in fs[1:])


def test_lights_off_clears_the_power_flag():
    dev = FakeDev()
    _drv(dev).set_lighting(pm.LIGHT_MODE_CUSTOM, (255, 0, 0), power_on=False)
    (f,) = _frames(dev)
    assert f[2] == pm.CMD_LIGHTING and f[4 + 37] & pm.LIGHT_FLAG_POWER == 0


def test_unmapped_firmware_effect_is_refused_not_guessed():
    dev = FakeDev()
    with pytest.raises(UnsupportedFeature):
        _drv(dev).set_lighting(2, (255, 0, 0))
    assert dev.writes == []


def test_per_key_paint_writes_only_the_listed_keys():
    dev = FakeDev()
    d = _drv(dev)
    km = device_state.KeyMap("ui/layouts/aula-win68he-max.json")
    w = km.index_of_code["W"]
    d.set_per_key_rgb({w: (1, 2, 3)})
    fs = _frames(dev)
    assert fs[0][2] == pm.CMD_LIGHTING and fs[0][4 + 39] == pm.LIGHT_MODE_CUSTOM
    assert [f[4:9] for f in fs[1:]] == [[pm.OP_WRITE, 0x1A, 1, 2, 3]]
    with pytest.raises(ValueError):
        d.set_per_key_rgb({9999: (1, 1, 1)})


def test_stream_sends_only_changed_keys():
    dev = FakeDev()
    d = _drv(dev)
    km = device_state.KeyMap("ui/layouts/aula-win68he-max.json")
    a = km.index_of_code["A"]
    d.begin_host_stream()
    d.stream_frame({a: (9, 9, 9)})
    assert len(dev.writes) == 1 + 68                  # mode + every key once
    dev.writes.clear()
    d.stream_frame({a: (9, 9, 9)})
    assert dev.writes == []                           # nothing changed
    d.stream_frame({a: (0, 0, 9)})
    (f,) = _frames(dev)
    assert f[5] == 0x04 and f[6:9] == [0, 0, 9]
    dev.writes.clear()
    d.stream_frame({a: (0, 0, 9)}, force=True)
    assert len(dev.writes) == 68


def test_unverified_writes_are_off_unless_experimental():
    dev = FakeDev()
    d = _drv(dev)
    assert not d.supports("actuation") and not d.supports("travel_stream")
    for call in (lambda: d.set_actuation([46], 0, 1.5),
                 lambda: d.set_socd([{"model": 4, "key1_hid": 4, "key2_hid": 7}]),
                 lambda: d.make_live_reader(device_state.KeyMap("ui/layouts/aula-win68he-max.json"))):
        with pytest.raises(UnsupportedFeature):
            call()
    assert dev.writes == []


def test_experimental_actuation_and_socd_frames():
    dev = FakeDev()
    d = _drv(dev, experimental=True)
    assert d.supports("actuation")
    km = device_state.KeyMap("ui/layouts/aula-win68he-max.json")
    d.set_actuation([km.index_of_code["W"]], 12, 0.8, 0.1, 0.2)
    (f,) = _frames(dev)
    p = f[4:4 + f[1]]
    assert f[2] == pm.CMD_KEY_CONFIG and p[0] == pm.OP_WRITE
    assert [0x1A, pm.PROP_RT_PRESS, 100, 0] == p[13:17]
    dev.writes.clear()
    d.set_socd([{"model": 4, "key1_hid": 4, "key2_hid": 7}])
    (s,) = _frames(dev)
    assert s == pm.build_socd(4, 7, 4)


def _reply(half, depths_um):
    data = [0] * 192
    data[0], data[1], data[2], data[5] = 0xDC, 0x80, pm.TRAVEL_REPLY_CMD, 0x02
    for slot, um in depths_um.items():
        i = slot - (half - 1) * 63
        data[6 + 2 * i], data[7 + 2 * i] = um & 0xFF, um >> 8
    return [data[0:64], data[64:128], data[128:192]]


def test_live_reader_polls_both_halves_and_reports_releases():
    km = device_state.KeyMap("ui/layouts/aula-win68he-max.json")
    w, space = km.index_of_code["W"], km.index_of_code["Space"]
    dev = FakeDev(_reply(1, {w: 1500}) + _reply(2, {space: 3400}))
    r = MagnetLiveReader(dev, km)
    seen = []
    r.on_sample = lambda idx, mm, t: seen.append((idx, mm))
    got = {}
    for half in (1, 2):
        got.update(r.poll_half(half))
    r._apply(got, 0.0)
    assert r.snapshot() == {"W": 1.5, "Space": 3.4}
    assert set(seen) == {(w, 1.5), (space, 3.4)}
    assert [f[1:][2] for f in dev.writes] == [pm.CMD_TRAVEL_MATRIX] * 2
    seen.clear()
    r._apply({w: 0.0, space: 3.4}, 1.0)                # W released
    assert r.snapshot() == {"Space": 3.4} and seen == [(w, 0.0)]


def test_live_reader_gives_up_on_a_missing_reply():
    r = MagnetLiveReader(FakeDev(), device_state.KeyMap("ui/layouts/aula-win68he-max.json"))
    r.REPLY_TIMEOUT_S = 0.01
    assert r.poll_half(1) is None


def test_experimental_flag_comes_only_from_the_env_switch():
    try:
        app_web._apply_experimental_flags({})
        assert MagnetDriver.experimental is False
        app_web._apply_experimental_flags({"AETHER_EXPERIMENTAL": "foo, magnet"})
        assert MagnetDriver.experimental is True
    finally:
        MagnetDriver.experimental = False


def test_board_draws_the_68_key_layout():
    api = app_web.Api.__new__(app_web.Api)
    api.km = device_state.KeyMap("ui/layouts/aula-win68he-max.json")
    assert api._ui_layout() == "68"
