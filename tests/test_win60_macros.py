"""Win60 HE macros end-to-end: driver storage + keymap binding RMW + Api.

Wire facts pinned here come from the vendor driver
(driver_src/dec_agreement/deobfuscated.js — setMacroValue L1216-1297,
initMacroValue L1195-1214, the cmd-25 read handler L440-523, setKeyValue
L1020-1110 with the type-0x10 branch at L1048-1052, and the keymap read
handler's macro branch L317-338) and the live capture
(docs/context/hed-aulacn-raw/webhid-capture-win60.json — see
tests/test_protocol_win60_capture.py for the byte-for-byte packet pins).

A fake board below stores what the driver writes and answers reads with the
board's real framing (cmd 24 / 25 paged replies, report-id-prefixed), so a
bind is exercised as a true read-modify-write against stored state.

Run: python -m pytest -q tests/test_win60_macros.py
"""
import json
import os
import sys
import tempfile
import threading
import types
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app_web                                   # noqa: E402
import device_state                              # noqa: E402
import protocol                                  # noqa: E402
from drivers import Win60Driver, NullDriver, UnsupportedFeature  # noqa: E402

CAPTURE = (Path(ROOT) / "docs" / "context" / "hed-aulacn-raw"
           / "webhid-capture-win60.json")

# Vendor-UI event lists (delay BEFORE each step), see the capture tests.
M1 = [(0, 0x04, True), (126, 0x04, False), (202, 0x05, True),
      (122, 0x05, False), (203, 0x06, True), (122, 0x06, False)]
M2 = [(0, 0x14, True), (77, 0x14, False), (108, 0x1A, True),
      (76, 0x1A, False), (109, 0x08, True), (77, 0x08, False),
      (110, 0x15, True), (78, 0x15, False), (109, 0x17, True),
      (77, 0x17, False), (108, 0xE1, True), (92, 0x1E, True),
      (94, 0x1E, False), (93, 0xE1, False)]

KM = device_state.KeyMap()
DEFAULTS = {i: KM.by_index[i]["hid"] for i in KM.by_index}
LAYER = set(KM.layer_indices)
M_IDX, N_IDX, Z_IDX = 96, 95, 90            # M / N / Z (capture slots)
assert KM.index_of_code["M"] == M_IDX and KM.index_of_code["N"] == N_IDX


# ------------------------------------------------------------ fake board ----
class _Handle:
    def __init__(self):
        self.frames = []

    def set_nonblocking(self, v):
        pass

    def read(self, n):
        return self.frames.pop(0) if self.frames else []


class FakeWin60Board:
    """Stores the keymap layers + macro slots the driver writes and answers
    the paged reads with the board's real framing."""

    def __init__(self, answer=True):
        self.base = bytearray(528)          # factory: all zero (capture)
        self.fn = bytearray(528)
        self.slots = {s: bytearray([0xFF] * 256) for s in range(10)}
        self.answer = answer
        self.keymap_writes = []             # (layer_byte, table) per full write

    @staticmethod
    def _pages(cmd, sub, table, stride):
        out = []
        for page, start in enumerate(range(0, len(table), stride)):
            part = table[start:start + stride]
            body = [cmd, sub, (page >> 8) & 0xFF, page & 0xFF, len(part)] + list(part)
            body += [0] * (63 - len(body))
            out.append([protocol.REPORT_ID] + body)
        return out

    def reply(self, payload):
        b = list(payload)[1:]
        cmd, sub = b[0], b[1]
        if cmd == 24:
            if sub in (0x80, 0x82):
                if not self.answer:
                    return []
                table = self.base if sub == 0x80 else self.fn
                return self._pages(24, sub, table, 56)
            if sub in (0, 2):
                table = self.base if sub == 0 else self.fn
                page = (b[2] << 8) | b[3]
                n = b[4]
                table[page * 56:page * 56 + n] = bytes(b[5:5 + n])
                if page == 9:
                    self.keymap_writes.append((sub, bytes(table)))
                return [[protocol.REPORT_ID, 24, sub] + [0] * 61]
        if cmd == 25:
            if sub & 0x80:
                if not self.answer:
                    return []
                return self._pages(25, sub, self.slots[sub & 0x0F], 58)
            page = (b[2] << 8) | b[3]
            n = b[4]
            slot = self.slots[sub]
            if all(x == 0xFF for x in slot):
                slot[:] = bytes(256)
            slot[page * 58:page * 58 + n] = bytes(b[5:5 + n])
            return [[protocol.REPORT_ID, 25, 0] + [0] * 61]
        return []


class ReadableDevice:
    def __init__(self, board):
        self.board = board
        self.writes = []
        self._lock = threading.Lock()
        self._dev = _Handle()
        self._is_open = True

    def open(self):
        self._is_open = True
        return {"interface_number": 2, "usage_page": 0xFF1B}

    def close(self):
        self._is_open = False

    def is_open(self):
        return self._is_open

    def write(self, payload):
        self.writes.append(list(payload))
        self._dev.frames.extend(self.board.reply(list(payload)) or [])
        return len(payload)

    def read(self, n, timeout_ms=0):
        return self._dev.read(n)

    def set_nonblocking(self, v):
        pass


def _driver(board=None):
    board = board or FakeWin60Board()
    dev = ReadableDevice(board)
    d = Win60Driver(None, dev, threading.RLock())
    d.KEYMAP_READ_TIMEOUT_S = 0.3
    d.MACRO_READ_TIMEOUT_S = 0.3
    return d, dev, board


def _ctx():
    return dict(default_hids=DEFAULTS, layer_indices=LAYER, overrides={},
                fn_layer_raw=None)


def _entry(table, idx):
    return list(table[idx * 4:idx * 4 + 4])


def _expected_default_table():
    t = bytearray(528)
    for i, h in DEFAULTS.items():
        t[i * 4] = 1 if i in LAYER else 0
        t[i * 4 + 1] = h
    return t


# ------------------------------------------------------ storage (cmd 25) ----
def test_write_then_read_macro_round_trips_with_mode_and_count():
    d, dev, board = _driver()
    d.write_macro(4, M2, play_mode=protocol.MACRO_PLAY_REPEAT, repeat_count=3)
    # 5 pages, [1] = slot, header [slot, mode, lenBE16, countBE16, 0, 0]
    pages = [w[1:] for w in dev.writes if w[1] == 25]
    assert [(p[1], p[3], p[4]) for p in pages] == [(4, i, n) for i, n in
                                                  enumerate([58, 58, 58, 58, 24])]
    assert pages[0][5:13] == [4, 1, 0, 56, 0, 3, 0, 0]
    assert d.read_macro(4) == {"slot": 4, "play_mode": 1, "repeat_count": 3,
                               "events": M2}


def test_write_macro_empty_deletes_slot_with_vendor_zero_image():
    d, dev, board = _driver()
    d.write_macro(2, M1)
    assert d.read_macro(2) is not None
    dev.writes.clear()
    d.write_macro(2, None)
    pages = [w[1:] for w in dev.writes if w[1] == 25]
    assert len(pages) == 5 and all(not any(p[5:5 + p[4]]) for p in pages)
    assert d.read_macro(2) is None
    assert d.list_macros() == {}


def test_list_macros_sweeps_all_ten_slots_and_skips_empty():
    d, dev, board = _driver()
    d.write_macro(0, M1)
    d.write_macro(9, M2, play_mode=1, repeat_count=2)
    dev.writes.clear()
    got = d.list_macros()
    reads = [w[2] for w in dev.writes if w[1] == 25]
    assert reads == [0x80 | s for s in range(10)]        # initMacroValue L1200
    assert sorted(got) == [0, 9]
    assert got[0]["events"] == M1 and got[0]["play_mode"] == 0
    assert got[9]["events"] == M2 and got[9]["repeat_count"] == 2


def test_read_macro_raises_when_board_does_not_answer():
    d, dev, board = _driver(FakeWin60Board(answer=False))
    with pytest.raises(RuntimeError):
        d.read_macro(0)
    with pytest.raises(RuntimeError):
        d.list_macros()


@pytest.mark.parametrize("bad", [
    lambda d: d.write_macro(10, M1),                                   # slot
    lambda d: d.write_macro(-1, M1),
    lambda d: d.write_macro(0, [(0, 1, True)] * 63),                   # count
    lambda d: d.write_macro(0, [(0, 256, True)]),                      # hid
    lambda d: d.write_macro(0, [(0, -1, True)]),
    lambda d: d.write_macro(0, [(70000, 4, True)]),                    # delay
    lambda d: d.write_macro(0, [(-5, 4, True)]),
    lambda d: d.write_macro(0, M1, play_mode=4),                       # mode
    lambda d: d.write_macro(0, M1, repeat_count=70000),                # count
    lambda d: d.read_macro(10),
    lambda d: d.bind_macro(96, 10),
    lambda d: d.bind_macro(132, 0),
    lambda d: d.unbind_key(-1),
])
def test_validation_rejects_before_any_write(bad):
    d, dev, board = _driver()
    with pytest.raises(ValueError):
        bad(d)
    assert dev.writes == []


def test_sixty_two_events_fill_the_slot_exactly():
    evs = [(i, 0x04 + (i % 26), bool(i % 2 == 0)) for i in range(62)]
    t = protocol.build_macro_table(0, evs, 1)
    assert t[2:4] == [0, 248] and len(t) == 256
    parsed = protocol.parse_macro_table(t)
    assert parsed["events"] == evs


# ------------------------------------------------ binding (cmd 24 RMW) ----
def test_bind_macro_is_read_modify_write_preserving_other_entries():
    d, dev, board = _driver()
    # Board state from "elsewhere": a remap Z->B, N already on macro 1 and a
    # vendor advanced-key record on key 50 — none made by this driver.
    board.base[Z_IDX * 4:Z_IDX * 4 + 4] = bytes([0, 0x05, 0, 0])
    board.base[N_IDX * 4:N_IDX * 4 + 4] = bytes(protocol.macro_keymap_entry(1, 0x11))
    board.base[50 * 4:50 * 4 + 4] = bytes([0x17, 0x02, 0x03, 0x04])
    board.fn[0:4] = bytes([0, 0x3A, 0, 0])              # a stored Fn mapping

    written = d.bind_macro(M_IDX, 0, **_ctx())

    # Order: base read, fn read, 10 base pages, 10 fn pages
    cmds = [(w[1], w[2]) for w in dev.writes]
    assert cmds[:2] == [(24, 0x80), (24, 0x82)]
    assert cmds[2:12] == [(24, 0)] * 10 and cmds[12:22] == [(24, 2)] * 10
    # the target got the capture's exact entry ...
    assert _entry(written, M_IDX) == [0x10, 0x10, 0x00, 0x00]
    # ... every foreign entry survived byte-for-byte ...
    assert _entry(written, Z_IDX) == [0, 0x05, 0, 0]
    assert _entry(written, N_IDX) == [0x10, 0x11, 0x01, 0x00]
    assert _entry(written, 50) == [0x17, 0x02, 0x03, 0x04]
    # ... zero read-back entries were filled from the layout defaults
    # (never written back as zeros), Fn key type intact ...
    expect = _expected_default_table()
    for idx in DEFAULTS:
        if idx in (M_IDX, Z_IDX, N_IDX, 50):
            continue
        assert _entry(written, idx) == _entry(expect, idx), idx
    assert _entry(written, 122) == [1, 0xFA, 0, 0]
    # ... the board now holds it, and its Fn layer was replayed unchanged.
    assert bytes(board.base) == written
    assert board.keymap_writes[-1][0] == 2 and board.fn[0:4] == bytes([0, 0x3A, 0, 0])


def test_bind_two_macros_reproduces_the_captured_keymap_table():
    """From the factory all-zero read-back, binding macro 0 to M then macro
    1 to N yields the exact 528-byte base table the vendor wrote for that
    Apply (frames with slot 96 = 10 10 00 00 and slot 95 = 10 11 01 00)."""
    with open(CAPTURE, encoding="utf-8") as fh:
        frames = json.load(fh)["frames"]

    def body(f):
        return [int(x, 16) for x in f["hex"].split()]

    tables = []
    i = 0
    while i < len(frames):
        f = frames[i]
        b = body(f) if f["dir"] == "OUT" else None
        if b and b[0] == 0x18 and b[1] == 0 and b[2] == 0 and b[3] == 0:
            t = bytearray(528)
            got = 0
            j = i
            while j < len(frames) and got < 10:
                g = frames[j]
                if g["dir"] == "OUT":
                    gb = body(g)
                    if gb[0] == 0x18 and gb[1] == 0:
                        page = (gb[2] << 8) | gb[3]
                        t[page * 56:page * 56 + gb[4]] = bytes(gb[5:5 + gb[4]])
                        got += 1
                j += 1
            tables.append(bytes(t))
            i = j
        else:
            i += 1
    target = [t for t in tables
              if t[M_IDX * 4:M_IDX * 4 + 4] == bytes([0x10, 0x10, 0, 0])
              and t[N_IDX * 4:N_IDX * 4 + 4] == bytes([0x10, 0x11, 1, 0])]
    assert target, "capture has the two-macro keymap write"

    d, dev, board = _driver()
    d.bind_macro(M_IDX, 0, **_ctx())
    final = d.bind_macro(N_IDX, 1, **_ctx())
    assert final == target[0]


def test_bind_aborts_before_writing_when_keymap_read_fails():
    d, dev, board = _driver(FakeWin60Board(answer=False))
    with pytest.raises(RuntimeError):
        d.bind_macro(M_IDX, 0, **_ctx())
    assert [w for w in dev.writes if w[1] == 24 and w[2] in (0, 2)] == []
    assert not any(board.base)


def test_bind_honours_api_overrides_and_fn_snapshot_fallback():
    d, dev, board = _driver()
    board.answer = True
    # Fn read fails only for the fn layer: simulate by a board that answers
    # base but not fn.
    orig = board.reply

    def reply(payload):
        b = list(payload)[1:]
        if b[0] == 24 and b[1] == 0x82:
            return []
        return orig(payload)
    board.reply = reply
    snap = bytes([0, 7] * 264)
    written = d.bind_macro(M_IDX, 3, default_hids=DEFAULTS, layer_indices=LAYER,
                           overrides={Z_IDX: 0x05}, fn_layer_raw=snap)
    assert _entry(written, Z_IDX) == [0, 0x05, 0, 0]       # Aether remap kept
    assert _entry(written, M_IDX) == [0x10, 0x10, 3, 0]
    assert bytes(board.fn) == snap                          # snapshot replayed


def test_bind_aborts_before_writing_when_no_fn_table_exists():
    """Base alone leaves the firmware in Fn mode: with the Fn read failing
    AND no connect-time snapshot, nothing is written at all."""
    d, dev, board = _driver()
    orig = board.reply

    def reply(payload):
        b = list(payload)[1:]
        return [] if (b[0] == 24 and b[1] == 0x82) else orig(payload)
    board.reply = reply
    with pytest.raises(RuntimeError, match="Fn"):
        d.bind_macro(M_IDX, 0, **_ctx())
    assert [w for w in dev.writes if w[1] == 24 and w[2] in (0, 2)] == []
    assert not any(board.base)
    with pytest.raises(RuntimeError, match="Fn"):
        d.unbind_key(M_IDX, **_ctx())
    assert [w for w in dev.writes if w[1] == 24 and w[2] in (0, 2)] == []


def test_bind_replays_an_all_zero_fn_layer():
    """A factory board answers the Fn read with zeros; that IS the Fn table
    (the vendor replays it) and must be written, not skipped."""
    d, dev, board = _driver()
    d.bind_macro(M_IDX, 0, **_ctx())
    fn_pages = [w for w in dev.writes if w[1] == 24 and w[2] == 2]
    assert len(fn_pages) == 10 and board.keymap_writes[-1][0] == 2


def test_unbind_key_restores_layout_default_entry():
    d, dev, board = _driver()
    d.bind_macro(M_IDX, 0, **_ctx())
    d.bind_macro(N_IDX, 1, **_ctx())
    written = d.unbind_key(M_IDX, **_ctx())
    assert _entry(written, M_IDX) == [0, 0x10, 0, 0]        # capture: restore
    assert _entry(written, N_IDX) == [0x10, 0x11, 1, 0]     # other bind kept
    assert d.read_macro_bindings() == {N_IDX: 1}
    # unbinding the Fn key would keep its layer type byte
    written = d.unbind_key(122, **_ctx())
    assert _entry(written, 122) == [1, 0xFA, 0, 0]


def test_read_macro_bindings_decodes_type_0x10_entries():
    d, dev, board = _driver()
    assert d.read_macro_bindings() == {}
    board.base[M_IDX * 4:M_IDX * 4 + 4] = bytes(protocol.macro_keymap_entry(7, 0x10))
    board.base[Z_IDX * 4:Z_IDX * 4 + 4] = bytes([0, 5, 0, 0])
    assert d.read_macro_bindings() == {M_IDX: 7}
    assert protocol.parse_macro_bindings(board.base) == {M_IDX: 7}


def test_bind_with_play_mode_rewrites_slot_header_keeping_events():
    d, dev, board = _driver()
    d.write_macro(0, M1)                                   # once, x1
    d.bind_macro(M_IDX, 0, play_mode=protocol.MACRO_PLAY_REPEAT, loop_count=3,
                 **_ctx())
    assert d.read_macro(0) == {"slot": 0, "play_mode": 1, "repeat_count": 3,
                               "events": M1}
    assert d.read_macro_bindings() == {M_IDX: 0}
    # without a mode the header is left alone
    d.bind_macro(N_IDX, 0, **_ctx())
    assert d.read_macro(0)["repeat_count"] == 3


def test_bind_with_play_mode_on_empty_slot_refuses():
    d, dev, board = _driver()
    with pytest.raises(ValueError):
        d.bind_macro(M_IDX, 5, play_mode=0, **_ctx())
    assert [w for w in dev.writes if w[2] in (0, 2) and w[1] == 24] == []


def test_bind_holds_the_outer_lock_for_the_whole_rmw():
    """No other frame can slip between the read and the write."""
    d, dev, board = _driver()
    seen = []
    orig_write = dev.write

    def spy(payload):
        seen.append(d._lock._is_owned())
        return orig_write(payload)
    dev.write = spy
    d.bind_macro(M_IDX, 0, **_ctx())
    assert seen and all(seen)


# ------------------------------------------------------------------ Api ----
def _api(tmp, board=None):
    a = app_web.Api.__new__(app_web.Api)
    a._settings_path = types.MethodType(lambda self: os.path.join(tmp, "settings.json"), a)
    a._lock = threading.RLock()
    a.km = KM
    a._remaps = {}
    a._fn_layer_raw = None
    d, dev, brd = _driver(board)
    d._lock = a._lock
    a.driver, a.dev = d, dev
    return a, dev, brd


def _events_json(evs):
    return [{"delay": dl, "hid": h, "down": dn} for dl, h, dn in evs]


def test_api_save_list_bind_unbind_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        a, dev, board = _api(tmp)
        r = a.save_macro(0, "  Hello ABC  ", _events_json(M1))
        assert r == {"ok": True, "slot": 0, "events": 6}
        r = a.save_macro(1, "QWERT!", _events_json(M2), play_mode=1, repeat_count=3)
        assert r["ok"]
        # names live in settings.json under macroNames, merged with the rest
        with open(a._settings_path(), encoding="utf-8") as f:
            assert json.load(f)["macroNames"] == {"0": "Hello ABC", "1": "QWERT!"}
        a.save_settings({"profiles": [{"name": "Default"}]})
        with open(a._settings_path(), encoding="utf-8") as f:
            assert json.load(f)["macroNames"]["1"] == "QWERT!"

        assert a.bind_macro("M", 0) == {"ok": True, "code": "M", "index": M_IDX, "slot": 0}
        assert a.bind_macro("N", 1)["ok"]
        lst = a.list_macros()
        assert lst["ok"] and lst["slots"] == 10 and lst["max_events"] == 62
        assert [m["slot"] for m in lst["macros"]] == [0, 1]
        assert lst["macros"][0]["name"] == "Hello ABC"
        assert lst["macros"][0]["events"] == _events_json(M1)
        assert lst["macros"][1]["play_mode"] == 1 and lst["macros"][1]["repeat_count"] == 3
        assert lst["bindings"] == {"M": 0, "N": 1}
        assert a.read_macro(1)["macro"]["name"] == "QWERT!"
        assert a.read_macro(5) == {"ok": True, "macro": None}

        assert a.unbind_macro("M") == {"ok": True, "code": "M", "index": M_IDX}
        assert a.list_macros()["bindings"] == {"N": 1}
        assert _entry(board.base, M_IDX) == [0, 0x10, 0, 0]

        r = a.delete_macro(1)
        assert r == {"ok": True, "slot": 1, "released": ["N"]}
        assert a.list_macros()["bindings"] == {}
        assert [m["slot"] for m in a.list_macros()["macros"]] == [0]
        with open(a._settings_path(), encoding="utf-8") as f:
            assert json.load(f)["macroNames"] == {"0": "Hello ABC"}


def test_api_bind_with_mode_updates_slot_header():
    with tempfile.TemporaryDirectory() as tmp:
        a, dev, board = _api(tmp)
        assert a.save_macro(2, "x", _events_json(M1))["ok"]
        assert a.bind_macro("Z", 2, play_mode=1, repeat_count=4)["ok"]
        m = a.read_macro(2)["macro"]
        assert m["play_mode"] == 1 and m["repeat_count"] == 4
        assert a.list_macros()["bindings"] == {"Z": 2}


@pytest.mark.parametrize("call, needle", [
    (lambda a: a.save_macro(10, "x", _events_json(M1)), "slot"),
    (lambda a: a.save_macro(0, "x", []), "at least one"),
    (lambda a: a.save_macro(0, "x", [{"delay": 0, "hid": 300, "down": True}]), "HID"),
    (lambda a: a.save_macro(0, "x", [{"delay": 99999, "hid": 4, "down": True}]), "delay"),
    (lambda a: a.save_macro(0, "x", [{"delay": 0, "hid": "q", "down": True}]), "integer"),
    (lambda a: a.save_macro(0, "x", _events_json([(0, 4, True)] * 63)), "too long"),
    (lambda a: a.save_macro(0, "x", _events_json(M1), play_mode=9), "play mode"),
    (lambda a: a.save_macro(0, "x", _events_json(M1), repeat_count=0), "repeat"),
    (lambda a: a.bind_macro("M", 12), "slot"),
    (lambda a: a.bind_macro("NoSuchKey", 0), "resolve"),
    (lambda a: a.bind_macro("M", 0, play_mode=7), "play mode"),
    (lambda a: a.unbind_macro("Nope"), "resolve"),
    (lambda a: a.delete_macro(-3), "slot"),
])
def test_api_validation_fails_closed_without_writing(call, needle):
    with tempfile.TemporaryDirectory() as tmp:
        a, dev, board = _api(tmp)
        r = call(a)
        assert r["ok"] is False and needle.lower() in r["error"].lower()
        assert [w for w in dev.writes if w[1] in (24, 25) and not (w[2] & 0x80)] == []


def test_api_macro_name_is_trimmed_and_capped():
    with tempfile.TemporaryDirectory() as tmp:
        a, dev, board = _api(tmp)
        a.save_macro(3, " " + "n" * 80, _events_json(M1))
        assert a.read_macro(3)["macro"]["name"] == "n" * 32


def test_api_reports_unsupported_on_a_board_without_macros():
    with tempfile.TemporaryDirectory() as tmp:
        a, dev, board = _api(tmp)
        a.driver = NullDriver(None, dev)
        for r in (a.list_macros(), a.read_macro(0),
                  a.save_macro(0, "x", _events_json(M1)),
                  a.bind_macro("M", 0), a.unbind_macro("M"), a.delete_macro(0)):
            assert r["ok"] is False and r.get("unsupported") is True
            assert r["feature"] == "macros"


def test_api_list_reports_binding_read_failure_but_still_lists_macros():
    with tempfile.TemporaryDirectory() as tmp:
        a, dev, board = _api(tmp)
        a.save_macro(0, "x", _events_json(M1))
        orig = board.reply

        def reply(payload):
            b = list(payload)[1:]
            return [] if b[0] == 24 else orig(payload)
        board.reply = reply
        lst = a.list_macros()
        assert lst["ok"] and [m["slot"] for m in lst["macros"]] == [0]
        assert lst["bindings"] is None and "keymap read failed" in lst["bindings_error"]


def test_api_not_connected_shape():
    a = app_web.Api.__new__(app_web.Api)
    assert a.list_macros() == {"ok": False, "error": "not connected"}
    assert a.bind_macro("M", 0) == {"ok": False, "error": "not connected"}
