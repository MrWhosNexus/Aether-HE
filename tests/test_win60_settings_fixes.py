"""WIN 60 HE settings-path fixes, pinned to the live vendor capture
(docs/context/hed-aulacn-raw/webhid-capture-win60.json) where the wire
shows the right answer.

  1. Fixed-actuation writes (trigger mode 0) preserve each key's STORED RT
     interval pair instead of sending 0/0 — the vendor re-sends the pair it
     read back at mount (frame 1842 `... 00 ... 2c 2c 78 78`, frame 1849
     `aa aa 78 78`); the factory pair is 1/1 (frames 173 / 922).
  2. Base-layer remap is read-modify-write over the board's current table
     (vendor macro bindings like slot 96 `10 10 00 00` survive) and never
     writes the base layer without an Fn layer.
  3. device_state.read_actuation (wrong discriminator) is gone.
  4. cmd-7/8 brightness + speed bytes clamp to the registry 0..4 / 0..4.
  5. Api.send_raw validates every byte and routes through the driver's
     never-send guard (factory reset / trigger reset / calibration arm).
"""
import threading
import types

import pytest

import boards
import device_state
import protocol
import app_web
from drivers import Win60Driver
from drivers.base import UnsupportedFeature

from test_keyboard_review import (FRAMES, ReadableDevice, _body, _prefixed,
                                  _trigger_reply, _win60_profile)


def _drv(reply):
    dev = ReadableDevice(reply)
    return Win60Driver(_win60_profile(), dev, threading.RLock()), dev


def _keymap():
    return device_state.KeyMap()          # ui/keymap.json = the WIN 60 HE layout


def _phys_indices():
    return [int(k["index"]) for k in _keymap().keys]


# ----------------------------------------------------- 1. mode-0 intervals --
_ALL_KEYS_MODE0_120 = _body(1849)   # RESTORE travel -> 1.70 mm, RT off, pair 78/78
_ALL_KEYS_MODE0_001 = _body(941)    # travel ALL keys -> 1.70 mm, factory pair 01/01


def _sub5_replies(pairs):
    """reply_fn answering readTriggerData with a stored (i1, i2) per key."""
    def reply(payload):
        if payload[1] == 33 and payload[5] == 24 and payload[6] == 5:
            row, col = payload[7], payload[8]
            idx = row * 22 + col
            if idx in pairs:
                i1, i2 = pairs[idx]
                return [_trigger_reply(row, col, travel=300, mode=12, i1=i1, i2=i2)]
        return []
    return reply


def test_capture_pins_vendor_mode0_writes_carry_stored_intervals():
    """Ground truth: the vendor's own mode-0 frames carry the previously
    stored RT pair (0x78 = 1.20 mm from frame 1172), never zeros."""
    assert _ALL_KEYS_MODE0_120[5] == 0 and _ALL_KEYS_MODE0_120[30:32] == [0x78, 0x78]
    assert _ALL_KEYS_MODE0_001[5] == 0 and _ALL_KEYS_MODE0_001[30:32] == [1, 1]
    assert protocol.parse_trigger_config(_body(173))["interval1"] == 1  # factory
    assert protocol.TRIGGER_DEFAULT_INTERVAL_RAW == 1


def test_mode0_write_preserves_stored_pair_and_reproduces_vendor_frame():
    idxs = _phys_indices()
    d, dev = _drv(_sub5_replies({i: (120, 120) for i in idxs}))
    d.set_actuation(idxs, 0, 1.70)                      # intervals omitted
    writes = [w[1:] for w in dev.writes if w[1] == 33 and w[6] == 0]
    assert writes == [_ALL_KEYS_MODE0_120]               # byte-for-byte frame 1849
    # every key was read back first (one sub-5 query per key, then the write)
    reads = [w for w in dev.writes if w[1] == 33 and w[6] == 5]
    assert len(reads) == len(idxs)
    assert dev.writes.index(reads[-1]) < dev.writes.index([1] + _ALL_KEYS_MODE0_120)


def test_mode0_write_groups_keys_by_their_own_stored_pair():
    idxs = [22, 23, 24, 25]
    stored = {22: (120, 120), 23: (1, 1), 24: (120, 120), 25: (50, 35)}
    d, dev = _drv(_sub5_replies(stored))
    d.set_actuation(idxs, 0, 1.0)
    writes = [w for w in dev.writes if w[1] == 33 and w[6] == 0]
    assert len(writes) == 3
    seen = {}
    for w in writes:
        pair = (w[31] | (w[35] << 8), w[32] | (w[36] << 8))
        mask = w[7:29]
        keys = [i for i in range(176) if mask[i % 22] >> (i // 22) & 1]
        seen[pair] = keys
        assert w[29] == w[30] == 100 and w[33] == w[34] == 0     # 1.00 mm
    assert seen == {(120, 120): [22, 24], (1, 1): [23], (50, 35): [25]}
    # never a zero interval in mode 0
    assert all((w[31], w[32]) != (0, 0) for w in writes)


def test_mode0_fallback_is_factory_pair_when_board_does_not_answer():
    idxs = _phys_indices()
    d, dev = _drv(lambda payload: [])                   # silent board
    d.TRIGGER_READ_TIMEOUT_S = 0.002
    d.set_actuation(idxs, 0, 1.70)
    writes = [w[1:] for w in dev.writes if w[1] == 33 and w[6] == 0]
    assert writes == [_ALL_KEYS_MODE0_001]               # frame 941: `aa aa 01 01`
    # the sweep gave up after TRIGGER_READ_MAX_MISSES silent keys, not 61
    reads = [w for w in dev.writes if w[1] == 33 and w[6] == 5]
    assert len(reads) == d.TRIGGER_READ_MAX_MISSES


def test_mode0_explicit_intervals_and_rt_modes_unchanged():
    d, dev = _drv(lambda payload: [])
    d.set_actuation([22], 0, 1.5, 0.0, 0.0)              # explicit -> as given
    assert dev.writes == [protocol.build_trigger(0, [22], 1.5, 0.0, 0.0)]
    dev.writes.clear()
    d.set_actuation([22], 12, 1.5, 0.3, 0.3)
    assert dev.writes == [protocol.build_trigger(12, [22], 1.5, 0.3, 0.3)]
    dev.writes.clear()
    d.set_actuation([22], 13, 1.5, 0.3, None)            # None in RT = 0
    assert dev.writes == [protocol.build_trigger(13, [22], 1.5, 0.3, 0.0)]


def test_build_trigger_raw_roundtrips_read_back_values_exactly():
    for pair in ((1, 1), (120, 120), (0x123, 0x45), (29, 7)):
        raw = protocol.build_trigger_raw(0, [22], 170, *pair)
        p = raw[1:]
        assert (p[30] | (p[34] << 8), p[31] | (p[35] << 8)) == pair
    assert protocol.build_trigger(12, [1, 2], 1.5, 0.3, 0.25) == \
        protocol.build_trigger_raw(12, [1, 2], 150, 30, 25)
    with pytest.raises(ValueError):
        protocol.build_trigger_raw(0, [0], 0x10000, 1, 1)


# ------------------------------------------------------- 2. keymap RMW --
def _table_from_capture(req_frame, want):
    """Reassemble the 528-byte layer the board answered after `req_frame`."""
    t = bytearray(528)
    for i in range(req_frame + 1, req_frame + 40):
        f = FRAMES[i]
        if f.get("dir") != "IN":
            continue
        b = _body(i)
        if b[0] == 24 and b[1] == want and b[4]:
            page = (b[2] << 8) | b[3]
            t[page * 56:page * 56 + b[4]] = bytes(b[5:5 + b[4]])
    return bytes(t)


_BASE_AT_MOUNT = _table_from_capture(97, 128)      # factory: all zero
_FN_AT_MOUNT = _table_from_capture(107, 130)       # all zero too
_BASE_AFTER_VENDOR = _table_from_capture(7485, 128)  # full table after writes
_VENDOR_Z_TO_B = [_body(i) for i in (2063, 2065, 2068, 2070, 2073,
                                     2074, 2076, 2078, 2080, 2082)]
_VENDOR_FN_REPLAY = [_body(i) for i in range(2084, 2103)
                     if FRAMES[i].get("dir") == "OUT" and _body(i)[0] == 24
                     and _body(i)[1] == 2]


def _chunks(table, want):
    out = []
    for page in range(10):
        part = table[page * 56:page * 56 + 56]
        out.append(_prefixed([24, want, 0, page, len(part)] + list(part)
                             + [0] * (56 - len(part))))
    return out


def _keymap_board(base, fn):
    """reply_fn serving base/Fn reads from the given tables."""
    def reply(payload):
        if payload[1] == 24 and payload[2] == 128:
            return _chunks(base, 128)
        if payload[1] == 24 and payload[2] == 130:
            return _chunks(fn, 130)
        return []
    return reply


def _split_writes(dev):
    base = [w[1:] for w in dev.writes if w[1] == 24 and w[2] == 0]
    fn = [w[1:] for w in dev.writes if w[1] == 24 and w[2] == 2]
    return base, fn


def _merge(pkts):
    t = bytearray(528)
    for b in pkts:
        page = (b[2] << 8) | b[3]
        t[page * 56:page * 56 + b[4]] = bytes(b[5:5 + b[4]])
    return bytes(t)


def test_capture_facts_for_keymap_rmw():
    assert not any(_BASE_AT_MOUNT) and not any(_FN_AT_MOUNT)
    assert any(_BASE_AFTER_VENDOR)
    assert len(_VENDOR_FN_REPLAY) == 10 and _merge(_VENDOR_FN_REPLAY) == _FN_AT_MOUNT
    # the vendor's own macro binding shape this RMW must preserve
    assert _body(3536)[5 + (96 * 4 - 6 * 56):5 + (96 * 4 - 6 * 56) + 4] == [0x10, 0x10, 0, 0]


def test_remap_rmw_from_factory_table_reproduces_vendor_z_to_b_write():
    km = _keymap()
    defaults = {i: km.by_index[i]["hid"] for i in km.by_index}
    d, dev = _drv(_keymap_board(_BASE_AT_MOUNT, _FN_AT_MOUNT))
    z = km.index_of_code["Z"]
    assert z == 90
    d.write_keymap(defaults, {z: 0x05}, km.layer_indices, None)   # no snapshot
    base, fn = _split_writes(dev)
    assert base == _VENDOR_Z_TO_B                          # frames 2063-2082
    assert fn == _VENDOR_FN_REPLAY                         # all-zero Fn IS written
    # order: base read, Fn read, then all writes (never a write before the reads)
    cmds = [(w[1], w[2]) for w in dev.writes if w[1] == 24]
    assert cmds[:2] == [(24, 130), (24, 128)] or cmds[:2] == [(24, 128), (24, 130)]
    assert all(c in ((24, 0), (24, 2)) for c in cmds[2:] if c not in ((24, 128), (24, 130)))


def test_remap_rmw_preserves_vendor_macro_binding_and_other_remaps():
    km = _keymap()
    defaults = {i: km.by_index[i]["hid"] for i in km.by_index}
    board = bytearray(_BASE_AFTER_VENDOR)
    board[96 * 4:96 * 4 + 4] = bytes([0x10, 0x10, 0, 0])   # vendor macro on M
    board[91 * 4:91 * 4 + 4] = bytes([0, 0x29, 0, 0])      # X -> Esc made elsewhere
    d, dev = _drv(_keymap_board(bytes(board), _FN_AT_MOUNT))
    d.write_keymap(defaults, {90: 0x05}, km.layer_indices, bytes(_FN_AT_MOUNT))
    base, fn = _split_writes(dev)
    written = _merge(base)
    assert written[90 * 4:90 * 4 + 4] == bytes([0, 0x05, 0, 0])     # our remap
    assert written[96 * 4:96 * 4 + 4] == bytes([0x10, 0x10, 0, 0])  # macro kept
    assert written[91 * 4:91 * 4 + 4] == bytes([0, 0x29, 0, 0])     # foreign remap kept
    assert written[122 * 4:122 * 4 + 4] == bytes(board[122 * 4:122 * 4 + 4])  # Fn key kept
    # nothing else changed
    for i in range(132):
        if i != 90:
            assert written[i * 4:i * 4 + 4] == bytes(board[i * 4:i * 4 + 4]), i
    # the OLD rebuild would have zeroed the macro entry
    legacy = _merge([p[1:] for p in protocol.build_base_keymap_table(
        defaults, {90: 0x05}, layer_indices=km.layer_indices)])
    assert legacy[96 * 4:96 * 4 + 4] == bytes([0, 0x10, 0, 0])
    assert len(fn) == 10


def test_remap_reset_restores_only_named_keys_to_layout_default():
    km = _keymap()
    defaults = {i: km.by_index[i]["hid"] for i in km.by_index}
    board = bytearray(_BASE_AFTER_VENDOR)
    board[90 * 4:90 * 4 + 4] = bytes([0, 0x05, 0, 0])      # Z -> B on the board
    board[91 * 4:91 * 4 + 4] = bytes([0, 0x29, 0, 0])      # X -> Esc on the board
    d, dev = _drv(_keymap_board(bytes(board), _FN_AT_MOUNT))
    d.write_keymap(defaults, {}, km.layer_indices, bytes(_FN_AT_MOUNT),
                   restore_indices=[90])
    written = _merge(_split_writes(dev)[0])
    assert written[90 * 4:90 * 4 + 4] == bytes([0, defaults[90], 0, 0])   # Z back
    assert written[91 * 4:91 * 4 + 4] == bytes([0, 0x29, 0, 0])          # X untouched
    fn_idx = next(iter(km.layer_indices))
    d2, dev2 = _drv(_keymap_board(bytes(board), _FN_AT_MOUNT))
    d2.write_keymap(defaults, {}, km.layer_indices, bytes(_FN_AT_MOUNT),
                    restore_indices=[fn_idx])
    w2 = _merge(_split_writes(dev2)[0])
    assert w2[fn_idx * 4] == 1                              # Fn keeps code1 = 1


def test_remap_aborts_before_any_write_when_no_fn_layer_can_be_had():
    km = _keymap()
    defaults = {i: km.by_index[i]["hid"] for i in km.by_index}

    def reply(payload):                       # base answers, Fn never does
        if payload[1] == 24 and payload[2] == 128:
            return _chunks(_BASE_AFTER_VENDOR, 128)
        return []

    d, dev = _drv(reply)
    d.KEYMAP_READ_TIMEOUT_S = 0.01
    with pytest.raises(RuntimeError):
        d.write_keymap(defaults, {90: 0x05}, km.layer_indices, None)
    assert _split_writes(dev) == ([], [])     # no base write without the Fn layer


def test_remap_aborts_when_base_read_fails_instead_of_rebuilding():
    km = _keymap()
    defaults = {i: km.by_index[i]["hid"] for i in km.by_index}

    def reply(payload):                       # base read: one page only
        if payload[1] == 24 and payload[2] == 128:
            return _chunks(_BASE_AFTER_VENDOR, 128)[:1]
        if payload[1] == 24 and payload[2] == 130:
            return _chunks(_FN_AT_MOUNT, 130)
        return []

    d, dev = _drv(reply)
    d.KEYMAP_READ_TIMEOUT_S = 0.01
    with pytest.raises(RuntimeError):
        d.write_keymap(defaults, {90: 0x05}, km.layer_indices, bytes(_FN_AT_MOUNT))
    assert _split_writes(dev) == ([], [])


def _api(driver):
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.board = _win60_profile()
    a.driver = driver
    a.km = _keymap()
    a._remaps = {}
    a._fn_layer_raw = None
    a.dev = types.SimpleNamespace(is_open=lambda: True)
    return a


def test_api_reset_remap_names_the_restored_keys():
    calls = []

    class _D:
        def write_keymap(self, defaults, overrides, layer, fn, restore_indices=()):
            calls.append((dict(overrides), sorted(restore_indices)))

    a = _api(_D())
    assert a.set_remap(["Z"], 0x05)["ok"] and a.set_remap(["X"], 0x29)["ok"]
    assert calls[-1] == ({90: 0x05, 91: 0x29}, [])
    assert a.reset_remap(["Z"])["ok"]
    assert calls[-1] == ({91: 0x29}, [90])
    assert a.reset_remap([])["ok"]                     # reset all
    assert calls[-1] == ({}, [91])
    # a driver refusal surfaces as a failed call, never a half-applied state
    class _Refuse:
        def write_keymap(self, *a, **k):
            raise RuntimeError("Fn-layer read failed")
    b = _api(_Refuse())
    r = b.set_remap(["Z"], 0x05)
    assert r["ok"] is False and "Fn" in r["error"]


# ------------------------------------------- 3. dead read_actuation gone --
def test_device_state_has_no_read_actuation():
    assert not hasattr(device_state, "read_actuation")
    # the driver's read-back is the surviving path
    assert callable(Win60Driver.read_trigger_config) and callable(Win60Driver.read_actuation)


# --------------------------------------------- 4. brightness/speed clamp --
def test_registry_scale_is_0_to_4_and_firmware_paths_clamp():
    lt = _win60_profile().lighting
    assert (lt["brightnessMin"], lt["brightnessMax"], lt["speedMin"], lt["speedMax"]) == (0, 4, 0, 4)
    d, dev = _drv(lambda p: [])
    d.set_lighting(2, (1, 2, 3), brightness=9, speed=300)
    assert (dev.writes[-1][7], dev.writes[-1][8]) == (4, 4)          # cmd-7 [6],[7]
    d.set_lighting(2, (1, 2, 3), brightness=-3, speed=-1)
    assert (dev.writes[-1][7], dev.writes[-1][8]) == (0, 0)
    d.set_lighting(2, (1, 2, 3), brightness=3, speed=1)
    assert dev.writes[-1] == protocol.build_light(2, 3, 1, (1, 2, 3))   # in range: untouched
    dev.writes.clear()
    d.set_per_key_rgb({0: (255, 0, 0)}, brightness=255, speed=256)
    mode10 = [w for w in dev.writes if w[1] == 7][0]
    assert (mode10[6], mode10[7], mode10[8]) == (10, 4, 4)            # 256 would have wrapped to 0
    dev.writes.clear()
    d.begin_host_stream()
    assert dev.writes == [protocol.build_light(10, 4, 4, (255, 255, 255))]  # unchanged bytes


def test_api_set_light_and_custom_colors_reach_the_clamp():
    d, dev = _drv(lambda p: [])
    a = _api(d)
    assert a.set_light(0, 255, 255, 255, brightness=7, speed=9)["ok"]
    assert (dev.writes[-1][7], dev.writes[-1][8]) == (4, 4)
    assert a.set_custom_colors({"Z": [1, 2, 3]}, brightness=99, speed=0)["ok"]
    mode10 = [w for w in dev.writes if w[1] == 7][-1]
    assert (mode10[7], mode10[8]) == (4, 0)


# --------------------------------------------------------- 5. send_raw --
def test_dangerous_command_table_matches_vendor_source():
    body = lambda pkt: pkt[1:]
    assert protocol.dangerous_command_reason(body(protocol.build_reset_keyboard()))
    assert protocol.dangerous_command_reason(body(protocol.build_reset_trigger()))
    assert protocol.dangerous_command_reason(body(protocol.build_calibration(True)))
    assert protocol.dangerous_command_reason(body(protocol.build_calibration(True, any_key=True)))
    # the stop frames and every ordinary setting are allowed
    for pkt in (protocol.build_calibration(False),
                protocol.build_calibration(False, any_key=True),
                protocol.build_win_lock(), protocol.build_gamepad_mode(1),
                protocol.build_poll_rate(8), protocol.build_heartbeat(),
                protocol.build_light(0, 4, 4, (1, 2, 3)),
                protocol.build_trigger(0, [22], 1.7, 0.01, 0.01),
                protocol.build_read_trigger_config(22),
                protocol.build_open_trigger_test([22]),
                protocol.build_close_trigger_test()):
        assert protocol.dangerous_command_reason(body(pkt)) is None, pkt[:8]
    # the captured cmd-20 win-lock frame (4456) is NOT the reset
    assert protocol.dangerous_command_reason(_body(4456)) is None
    assert _body(4456)[0] == 20 and _body(4456)[4] == 1 and _body(4456)[5] == 0


def test_api_send_raw_validates_bytes_and_refuses_guarded_frames():
    d, dev = _drv(lambda p: [])
    a = _api(d)
    ok = a.send_raw("01 07 00 00 00 0e 00 04 04 ff 00 00")
    assert ok == {"ok": True}
    assert dev.writes[-1][:12] == [1, 7, 0, 0, 0, 0x0E, 0, 4, 4, 0xFF, 0, 0]
    assert len(dev.writes[-1]) == 64
    n = len(dev.writes)
    for bad in ("01 14 00 00 00 01 01",            # resetKeyboard
                "01 21 00 00 00 18 06",            # resetTrigger
                "01 21 00 00 00 18 08 00",         # calibration arm (all keys)
                "01 21 00 00 00 18 0f 00"):        # calibration arm (any key)
        r = a.send_raw(bad)
        assert r["ok"] is False and "refusing" in r["error"], bad
    for bad in ("01 07 100", "01 zz", "01 07 1ff", "", "01 " + "00 " * 64,
                "02 07 00"):                       # >255, junk, too long, wrong report id
        r = a.send_raw(bad)
        assert r["ok"] is False, bad
    assert len(dev.writes) == n                    # nothing reached the wire
    assert a.send_raw("0x01,0x21,0,0,0,0x18,0x03")["ok"]   # close travel test, 0x form
    assert dev.writes[-1][:7] == [1, 0x21, 0, 0, 0, 0x18, 3]


def test_send_raw_is_refused_on_boards_without_a_guard_table():
    from drivers.base import NullDriver
    d = NullDriver(None, ReadableDevice())
    with pytest.raises(UnsupportedFeature):
        d.send_raw([1] + [0] * 63)


def test_mini60_send_raw_goes_through_its_dangerous_cmds_guard():
    import protocol_mini60 as pm
    from drivers import Mini60Driver
    dev = ReadableDevice()
    d = Mini60Driver(boards.load_registry().by_slug("aula-mini60he-pro"),
                     dev, threading.RLock())
    bad = [0x00, 0xAA, 0x4F] + [0] * 61            # flash write family
    assert 0x4F in pm.DANGEROUS_CMDS
    with pytest.raises(RuntimeError):
        d.send_raw(bad)
    assert dev.writes == []
