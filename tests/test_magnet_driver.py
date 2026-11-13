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


class FakeBoard(FakeDev):
    """A WIN 68 HE Max that answers read requests the way the fork's reply
    parsers expect, and applies 0x23 / 0x2C writes to its key table."""

    def __init__(self, version=(1, 0, 9), light=True, props=True, light_len=44):
        super().__init__()
        self.version = version
        self.block = pm.block_with_palette_slot(pm.LIGHT_BLOCK, 6, (1, 2, 3))
        self.light = [0x01, 4, 21, 3, 30, 2, 5] if light else None   # flags..slot
        self.light_len = light_len
        self.props = None
        if props:
            self.props = {k: {pm.PROP_MODE: pm.TOUCH_FIXED << 4, pm.PROP_ACTUATION: 2000,
                              pm.PROP_DEAD_TOP: 40, pm.PROP_DEAD_BOTTOM: 50}
                          for k in pm.KEY_ORDER}
        self.silent = False

    def _answer(self, cmd, body):
        r = [0] * 64
        r[0], r[1], r[2] = 0xDC, len(body), cmd | 0x80
        r[4:4 + len(body)] = body
        self.replies.append([0] + r)                  # with the report id, as hidapi may

    def write(self, payload):
        super().write(payload)
        f = list(payload)[1:]
        cmd, body = f[2], f[4:4 + f[1]]
        if self.silent:
            return len(payload)
        if cmd == pm.CMD_SYS and self.version is not None:
            if body[0] == 0x01:
                major, minor, patch = self.version
                self._answer(cmd, [0, 1, (minor << 4) | patch, major])
            elif body[0] == 0x25:
                self._answer(cmd, [0, 0x25, 10, 100, 0, 0x48, 0x0D])
            elif body[0] == 0x26:
                self._answer(cmd, [0, 0x26] + list(b"WIN 68 HE MAX") + [0])
        elif cmd == pm.CMD_GLOBAL_TRAVEL and body[0] == pm.OP_READ:
            self._answer(cmd, [0, 0, 0, 0xD0, 0x07, 0, 0, 0, 0])
        elif cmd == pm.CMD_LIGHTING and body[0] == pm.OP_READ and self.light:
            self._answer(cmd, ([0] + list(self.block) + self.light)[:self.light_len])
        elif cmd == pm.CMD_KEY_CONFIG and self.props is not None:
            if body[0] == pm.OP_READ:
                out = [0]
                for i in range(1, len(body) - 3, 4):
                    k, prop = body[i], body[i + 1]
                    v = self.props.get(k, {}).get(prop, 0) if k != 0xFF else 0
                    out += [k, prop, v & 0xFF, v >> 8]
                self._answer(cmd, out)
            else:
                for i in range(1, len(body) - 3, 4):
                    self.props[body[i]][body[i + 1]] = body[i + 2] | (body[i + 3] << 8)
        elif cmd == pm.CMD_SOCD and self.props is not None:
            for k in body[1:3]:                       # the firmware marks both keys
                self.props[k][pm.PROP_MODE] = (self.props[k][pm.PROP_MODE] & 0xF0) | pm.ADV_SOCD
        return len(payload)


def _drv(dev=None, experimental=False):
    p = boards.load_registry().by_slug("aula-win68he-max")
    d = drivers.get_driver(p, dev or FakeDev())
    assert isinstance(d, MagnetDriver)
    d.experimental = experimental
    d.QUERY_TIMEOUT_S = 0.02
    return d


def _connected(board=None, **kw):
    """(driver, board) after connect(), with the connect traffic forgotten."""
    board = board or FakeBoard(**kw)
    d = _drv(board)
    d.connect()
    board.writes.clear()
    return d, board


def _records(frames):
    """(key, prop, value) of every 0x23 write frame."""
    out = []
    for f in frames:
        if f[2] == pm.CMD_KEY_CONFIG and f[4] == pm.OP_WRITE:
            body = f[4:4 + f[1]]
            out += [(body[i], body[i + 1], body[i + 2] | (body[i + 3] << 8))
                    for i in range(1, len(body) - 3, 4)]
    return out


KM = "ui/layouts/aula-win68he-max.json"


def _frames(dev):
    out = []
    for w in dev.writes:
        assert w[0] == pm.REPORT_ID and len(w) == 65
        f = w[1:]
        assert pm.is_valid(f)
        out.append(f)
    return out


def test_registry_dispatches_the_magnet_driver():
    p = boards.load_registry().by_slug("aula-win68he-max")
    assert p.protocol == "protocol_magnet" and p.drivable
    assert p.capabilities["lighting"] is True and p.capabilities["perKeyRgb"] is True


def test_registry_effect_table_matches_the_protocol_table():
    """The registry is the UI's mode list; protocol_magnet.LIGHT_EFFECTS is
    the byte table. Any firmware effect the registry lists must be the same
    (id, byte, name) and must say its name is unverified."""
    p = boards.load_registry().by_slug("aula-win68he-max")
    by_id = {e[1]: e for e in pm.LIGHT_EFFECTS}
    listed = [m for m in (p.lighting or {}).get("modes", []) if m["id"] in by_id]
    for m in listed:
        byte, _id, name = by_id[m["id"]]
        assert (m["byte"], m["name"]) == (byte, name)
        assert m.get("nameUnverified") is True
    assert len(listed) in (0, len(pm.LIGHT_EFFECTS))       # all of them, or not yet applied


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


def test_a_mode_byte_outside_the_captured_range_is_refused():
    dev = FakeDev()
    for mode in (22, 99, -1):
        with pytest.raises(UnsupportedFeature):
            _drv(dev).set_lighting(mode, (255, 0, 0))
    assert dev.writes == []


@pytest.mark.parametrize("byte", [e[0] for e in pm.LIGHT_EFFECTS])
def test_firmware_effects_send_their_captured_mode_byte(byte):
    dev = FakeDev()
    _drv(dev).set_lighting(byte, (255, 0, 0), brightness=3, speed=2, direction=1)
    (f,) = _frames(dev)
    # Red is palette slot 0 of the captured block: effect colour id 1, no palette edit.
    assert f == pm.build_lighting(byte, brightness=3, speed=2, direction=True, color_slot=1)


def test_effect_colour_maps_to_spectrum_or_a_stored_slot():
    dev = FakeDev()
    d = _drv(dev)
    d.set_lighting(5, (0, 0, 255), full_color=1)
    d.set_lighting(5, (0, 0, 255))                       # blue = slot 3 -> id 4
    d.set_lighting(pm.LIGHT_MODE_STATIC, (0, 0, 255))    # static: slot 3 as is
    d.set_lighting(pm.LIGHT_MODE_STATIC, (0, 0, 255), full_color=1)
    fs = _frames(dev)
    assert [f[4 + 43] for f in fs[:2]] == [pm.EFFECT_SPECTRUM, 4]
    assert [f[4 + 42] for f in fs[2:]] == [3, pm.STATIC_SPECTRUM]
    assert all(bytes(f[5:41]) == pm.LIGHT_BLOCK for f in fs)


def test_a_colour_the_board_does_not_store_rewrites_palette_slot_0():
    dev = FakeDev()
    d = _drv(dev)
    d.set_lighting(7, (10, 20, 30))
    (f,) = _frames(dev)
    assert f[4 + 43] == 1
    assert bytes(f[5:41]) == pm.block_with_palette_slot(pm.LIGHT_BLOCK, 0, (10, 20, 30))
    dev.writes.clear()
    d.set_lighting(7, (10, 20, 30))                      # now stored: same frame again
    assert _frames(dev) == [f]


# ---- read-back at connect (reply layouts: COMMUNITY-TESTED) ----
def test_connect_sends_only_captured_read_requests():
    import os
    fix = os.path.join(os.path.dirname(__file__), "fixtures", "magnet_win68max_tx.txt")
    with open(fix, encoding="utf-8") as fh:
        captured = {tuple(bytes.fromhex(l.strip())) for l in fh
                    if l.strip() and not l.startswith("#")}
    board = FakeBoard()
    d = _drv(board)
    d.connect()
    fs = _frames(board)
    assert fs[0] == pm.build_hello() and len(fs) == 6 + 4 * 5
    assert all(tuple(f) in captured for f in fs)
    info = d.device_info()
    assert info["protocol_version"] == "1.0.9" and info["name"] == "WIN 68 HE MAX"
    assert info["travel_limits"]["max_mm"] == 3.4 and info["state_read"] is True


def test_lighting_write_echoes_the_boards_palette_sleep_and_slots():
    d, board = _connected()
    d.set_lighting(pm.LIGHT_MODE_CUSTOM, (10, 20, 30), brightness=3, speed=2)
    f = _frames(board)[0]
    assert f == pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=3, speed=2,
                                  block=board.block, sleep_min=30, static_mode=2, color_slot=5)
    board.writes.clear()
    d.set_lighting(pm.LIGHT_MODE_CUSTOM, (1, 1, 1), power_on=False)
    (off,) = _frames(board)
    assert bytes(off[5:41]) == board.block and off[4 + 41] == 30
    assert off[4 + 37] & pm.LIGHT_FLAG_POWER == 0
    board.writes.clear()
    d.set_per_key_rgb({device_state.KeyMap(KM).index_of_code["W"]: (1, 2, 3)})
    assert _frames(board)[0][4 + 41] == 30
    board.writes.clear()
    d.begin_host_stream()
    assert bytes(_frames(board)[0][5:41]) == board.block


@pytest.mark.parametrize("board", [
    lambda: FakeBoard(light=False),                      # no lighting reply
    lambda: FakeBoard(light_len=30),                     # short reply
    lambda: FakeBoard(version=None, light=False, props=False),   # nothing answers
])
def test_no_usable_lighting_reply_falls_back_to_the_captured_frame(board):
    d, b = _connected(board())
    d.set_lighting(pm.LIGHT_MODE_CUSTOM, (10, 20, 30), brightness=3, speed=2)
    assert _frames(b)[0] == pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=3, speed=2)


def test_a_foreign_report_is_not_taken_for_the_lighting_reply():
    board = FakeBoard(light=False)
    d = _drv(board)
    junk = [0] + [0xAA] * 64
    board.replies = [junk]
    assert d._read_light_state() is None and d._light is None


def test_a_board_with_a_43_byte_lighting_state_gets_43_byte_writes():
    d, board = _connected(light_len=43)
    d.set_lighting(3, (255, 0, 0))
    (f,) = _frames(board)
    assert f[1] == 43 and f[4 + 39] == 3 and f[4 + 41] == 30


def test_effect_colour_is_remembered_for_the_next_write():
    d, board = _connected()
    d.set_lighting(5, (0, 0, 255))                       # slot 3 -> effect colour 4
    board.writes.clear()
    d.begin_host_stream()
    assert _frames(board)[0][4 + 43] == 4


def test_per_key_paint_writes_only_the_listed_keys():
    dev = FakeDev()
    d = _drv(dev)
    km = device_state.KeyMap(KM)
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
    km = device_state.KeyMap(KM)
    a = km.index_of_code["A"]
    d.begin_host_stream()
    d.stream_frame({a: (9, 9, 9)})
    assert len(dev.writes) == 1 + 5                   # mode + 68 keys, 14 to a frame
    keys = [k for f in _frames(dev)[1:] for k in f[5:4 + f[1]:4]]
    assert sorted(keys) == sorted(pm.KEY_ORDER)
    dev.writes.clear()
    d.stream_frame({a: (9, 9, 9)})
    assert dev.writes == []                           # nothing changed
    d.stream_frame({a: (0, 0, 9)})
    (f,) = _frames(dev)
    assert f[5] == 0x04 and f[6:9] == [0, 0, 9]
    dev.writes.clear()
    d.stream_frame({a: (0, 0, 9)}, force=True)
    assert len(dev.writes) == 5


def test_only_the_travel_stream_is_behind_the_experimental_flag():
    d = _drv(FakeDev())
    for feat in ("lighting", "per_key_rgb", "host_effects", "actuation", "deadband", "socd"):
        assert d.supports(feat)
    assert not d.supports("travel_stream")
    with pytest.raises(UnsupportedFeature):
        d.make_live_reader(device_state.KeyMap(KM))
    d.experimental = True
    assert d.supports("travel_stream")
    assert isinstance(d.make_live_reader(device_state.KeyMap(KM)), MagnetLiveReader)


# ---- actuation / dead band / SOCD (0x23 and 0x2C writes: COMMUNITY-TESTED) ----
def test_key_writes_refuse_when_the_key_table_was_never_read():
    """No table = no advanced-key nibble to keep. Refuse, never guess."""
    for board in (FakeBoard(props=False), FakeBoard(version=None, light=False, props=False)):
        d, b = _connected(board)
        km = device_state.KeyMap(KM)
        w = km.index_of_code["W"]
        for call in (lambda: d.set_actuation([w], 0, 1.5),
                     lambda: d.set_deadband({w: (4, 5)}),
                     lambda: d.set_socd([{"model": 1, "key1_hid": 4, "key2_hid": 7}]),
                     lambda: d.set_socd([])):
            with pytest.raises(RuntimeError):
                call()
        assert b.writes == []                            # refused without any traffic


def test_a_silent_board_connects_quickly_and_reads_nothing():
    board = FakeBoard()
    board.silent = True
    d = _drv(board)
    d.connect()
    assert [f[2] for f in _frames(board)] == [pm.CMD_HELLO, pm.CMD_SYS]
    assert d.device_info()["state_read"] is False


def test_actuation_write_keeps_the_advanced_key_nibble():
    board = FakeBoard()
    board.props[0x1A][pm.PROP_MODE] = pm.mode_value(pm.TOUCH_FIXED, pm.ADV_SOCD)
    d, board = _connected(board)
    km = device_state.KeyMap(KM)
    d.set_actuation([km.index_of_code["W"], km.index_of_code["A"]], 12, 0.8, 0.1, 0.2)
    recs = _records(_frames(board))
    assert (0x1A, pm.PROP_MODE, pm.mode_value(pm.TOUCH_RAPID, pm.ADV_SOCD)) in recs
    assert (0x04, pm.PROP_MODE, pm.mode_value(pm.TOUCH_RAPID, pm.ADV_NONE)) in recs
    assert (0x1A, pm.PROP_ACTUATION, 800) in recs and (0x1A, pm.PROP_ACTUATION_2, 800) in recs
    assert (0x1A, pm.PROP_RT_PRESS, 100) in recs and (0x1A, pm.PROP_RT_RELEASE, 200) in recs
    assert (0x1A, pm.PROP_DEAD_TOP, 790) in recs                 # Standard RT pin
    assert board.props[0x1A][pm.PROP_MODE] & 0x0F == pm.ADV_SOCD


def test_fixed_mode_leaves_the_stored_rt_pair_and_dead_band_alone():
    d, board = _connected()
    w = device_state.KeyMap(KM).index_of_code["W"]
    d.set_actuation([w], 0, 1.5, None, None)
    assert _records(_frames(board)) == [(0x1A, pm.PROP_MODE, pm.TOUCH_FIXED << 4),
                                        (0x1A, pm.PROP_ACTUATION, 1500),
                                        (0x1A, pm.PROP_ACTUATION_2, 1500)]


def test_leaving_standard_rt_restores_the_users_dead_band():
    d, board = _connected()
    w = device_state.KeyMap(KM).index_of_code["W"]
    d.set_actuation([w], 12, 1.0, 0.1, 0.1)
    assert board.props[0x1A][pm.PROP_DEAD_TOP] == 990
    d.set_deadband({w: (30, 60)})                        # 0.30 / 0.60 mm while pinned
    assert board.props[0x1A][pm.PROP_DEAD_TOP] == 990            # the pin stays on the board
    assert board.props[0x1A][pm.PROP_DEAD_BOTTOM] == 600
    d.set_actuation([w], 13, 1.0, 0.1, 0.1)              # Continuous: the user's value
    assert board.props[0x1A][pm.PROP_DEAD_TOP] == 300
    d.set_actuation([w], 12, 1.0, 0.1, 0.1)
    d.set_actuation([w], 0, 1.0, None, None)             # back to fixed: restored too
    assert board.props[0x1A][pm.PROP_DEAD_TOP] == 300


def test_a_key_found_in_standard_rt_at_connect_is_unpinned_with_the_default():
    board = FakeBoard()
    board.props[0x1A].update({pm.PROP_MODE: pm.TOUCH_RAPID << 4, pm.PROP_ACTUATION: 1000,
                              pm.PROP_DEAD_TOP: 990})
    d, board = _connected(board)
    d.set_actuation([device_state.KeyMap(KM).index_of_code["W"]], 13, 1.0, 0.1, 0.1)
    assert board.props[0x1A][pm.PROP_DEAD_TOP] == pm.DEAD_DEFAULT_UM
    assert board.props[0x1A][pm.PROP_DEAD_BOTTOM] == 50          # as the board had it


def test_actuation_is_clamped_to_the_travel_limits_the_board_reported():
    d, board = _connected()
    d._limits = {"precision_mm": 0.01, "min_mm": 0.2, "max_mm": 3.3}
    w = device_state.KeyMap(KM).index_of_code["W"]
    d.set_actuation([w], 0, 9.0, None, None)
    assert board.props[0x1A][pm.PROP_ACTUATION] == 3300


def test_dead_band_write():
    d, board = _connected()
    km = device_state.KeyMap(KM)
    d.set_deadband({km.index_of_code["W"]: (4, 5), km.index_of_code["A"]: (0, 500)})
    assert _records(_frames(board)) == [
        (0x1A, pm.PROP_DEAD_TOP, 40), (0x1A, pm.PROP_DEAD_BOTTOM, 50),
        (0x04, pm.PROP_DEAD_TOP, 0), (0x04, pm.PROP_DEAD_BOTTOM, 1000)]
    with pytest.raises(ValueError):
        d.set_deadband({9999: (4, 5)})


def test_read_actuation_reports_what_the_board_holds():
    board = FakeBoard()
    board.props[0x1A][pm.PROP_ACTUATION] = 1250
    board.props[0x04][pm.PROP_MODE] = pm.TOUCH_GLOBAL << 4      # follows the board-wide 2.00 mm
    board.props[0x04][pm.PROP_ACTUATION] = 700
    d, board = _connected(board)
    got = d.read_actuation(device_state.KeyMap(KM))
    assert len(got) == 68 and got["W"] == 1.25 and got["A"] == 2.0 and got["Esc"] == 2.0
    board.silent = True
    with pytest.raises(RuntimeError):
        d.read_actuation(device_state.KeyMap(KM))


def test_socd_writes_the_corrected_frame_for_every_model():
    for model in (1, 2, 3, 4):
        d, board = _connected()
        d.set_socd([{"model": model, "key1_hid": 4, "key2_hid": 7}])
        writes = [f for f in _frames(board) if f[4] == pm.OP_WRITE]
        assert writes == [pm.build_socd(4, 7, model)]
        assert writes[0][4:15] == [1, 4, 7, 0, 0, 0, 0, 0, model - 1, 0, 0]


def test_socd_clears_the_pairs_the_board_holds_before_applying():
    board = FakeBoard()
    for k in (0x1A, 0x16):                               # W/S paired by the vendor driver
        board.props[k][pm.PROP_MODE] = pm.mode_value(pm.TOUCH_RAPID, pm.ADV_SOCD)
    d, board = _connected(board)
    d.set_socd([{"model": 4, "key1_hid": 4, "key2_hid": 7}])
    writes = [f for f in _frames(board) if f[4] == pm.OP_WRITE]
    assert sorted(_records(writes[:-1])) == [(0x16, pm.PROP_MODE, pm.TOUCH_RAPID << 4),
                                             (0x1A, pm.PROP_MODE, pm.TOUCH_RAPID << 4)]
    assert writes[-1] == pm.build_socd(4, 7, 4)
    board.writes.clear()
    d.set_socd([])                                       # an empty list only clears
    writes = [f for f in _frames(board) if f[4] == pm.OP_WRITE]
    assert sorted(r[0] for r in _records(writes)) == [4, 7]
    assert all(v[pm.PROP_MODE] & 0x0F == 0 for v in board.props.values())


@pytest.mark.parametrize("pair", [
    {"model": 0, "key1_hid": 4, "key2_hid": 7},
    {"model": 5, "key1_hid": 4, "key2_hid": 7},
    {"model": 1, "key1_hid": 4, "key2_hid": 4},
    {"model": 1, "key1_hid": 4, "key2_hid": 0x3A},       # F1: not on this board
])
def test_an_invalid_socd_pair_writes_nothing(pair):
    d, board = _connected()
    with pytest.raises(ValueError):
        d.set_socd([{"model": 1, "key1_hid": 0x1A, "key2_hid": 0x16}, pair])
    assert _frames(board) == []


def test_socd_is_refused_on_a_protocol_older_than_1_0_7():
    d, board = _connected(version=(1, 0, 6))
    with pytest.raises(RuntimeError):
        d.set_socd([{"model": 1, "key1_hid": 4, "key2_hid": 7}])
    assert _frames(board) == []


def test_api_set_socd_passes_the_model_number_to_the_driver():
    """PR #32 contract: the bridge carries Model 1..4, the driver converts."""
    d, board = _connected()
    api = app_web.Api.__new__(app_web.Api)
    api._lock = threading.RLock()
    api.km = device_state.KeyMap(KM)
    api.dev, api.driver = board, d
    assert api.set_socd([{"model": 3, "key1": "A", "key2": "D"}]) == {"ok": True}
    (f,) = [f for f in _frames(board) if f[2] == pm.CMD_SOCD]
    assert f[4:15] == [1, 4, 7, 0, 0, 0, 0, 0, 2, 0, 0]


def _reply(half, depths_um):
    data = [0] * 192
    data[0], data[1], data[2], data[5] = 0xDC, 0x80, pm.TRAVEL_REPLY_CMD, 0x02
    for slot, um in depths_um.items():
        i = slot - (half - 1) * 63
        data[6 + 2 * i], data[7 + 2 * i] = um & 0xFF, um >> 8
    return [data[0:64], data[64:128], data[128:192]]


def test_live_reader_polls_both_halves_and_reports_releases():
    km = device_state.KeyMap(KM)
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
    r = MagnetLiveReader(FakeDev(), device_state.KeyMap(KM))
    r.REPLY_TIMEOUT_S = 0.01
    assert r.poll_half(1) is None


def test_experimental_flag_comes_only_from_the_env_switch():
    try:
        app_web._apply_experimental_flags({})
        assert MagnetDriver.experimental is False
        app_web._apply_experimental_flags({"AETHER_EXPERIMENTAL": "foo, magnet"})
        assert MagnetDriver.experimental is True
        app_web._apply_experimental_flags({"AETHER_EXPERIMENTAL": "f75"})
        assert MagnetDriver.experimental is False
    finally:
        MagnetDriver.experimental = False


def test_board_draws_the_68_key_layout():
    api = app_web.Api.__new__(app_web.Api)
    api.km = device_state.KeyMap(KM)
    assert api._ui_layout() == "68"
