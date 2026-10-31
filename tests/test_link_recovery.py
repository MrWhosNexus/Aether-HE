"""Dead-connection detection and recovery (the 0.5.2 "app goes dead after the
keyboard re-enumerates" bug, verified on hardware).

After a USB re-enumeration (a poll-rate change restarts the board, a replug)
the old Windows HID handle stays "open": writes are accepted and go nowhere,
reads come back empty. Api.status() used to answer `dev.is_open()`, so the
UI's 2.5 s status -> connect() watchdog never fired and the app stayed dead
until a manual reconnect. These tests pin:

  * AulaDevice drops a handle whose I/O fails (hidapi write -1 / read raise)
    and counts it, so the Api can tell "died" from "closed on purpose".
  * Api.status() proves liveness: it trusts a recent reply, otherwise it runs
    one cheap heartbeat probe, only when the link is idle (never while a
    transaction holds the lock or calibration runs), at most once per window.
  * a failed probe closes the handle and reports connected False, and a plain
    connect() brings the board back.
"""
import threading
import time
import types

import pytest

import aula_device
import app_web
import device_state
import protocol
from aula_device import AulaDevice
from drivers import Win60Driver


# ------------------------------------------------------------ fake HID ----
def _init_info_reply():
    """A cmd-1 initInfo reply frame (report id first) parse_init_info accepts."""
    body = [0] * 63
    body[0] = 1
    body[4] = 0x11
    body[17] = 0x7F
    return [protocol.REPORT_ID] + body


class FakeHid:
    """Stands in for hid.device(). `mode`:
        alive  - answers a heartbeat with an initInfo reply
        stale  - accepts writes (returns the length) but never answers
                 (the real post-re-enumeration Windows behaviour)
        broken - write returns -1, read raises IOError (hidapi on a gone handle)
    """

    def __init__(self, mode="alive"):
        self.mode = mode
        self.queue = []
        self.writes = []
        self.closed = False

    def open_path(self, path):
        pass

    def set_nonblocking(self, flag):
        pass

    def close(self):
        self.closed = True

    def write(self, payload):
        payload = list(payload)
        if self.mode == "broken":
            return -1
        self.writes.append(payload)
        if self.mode == "alive" and payload[1] == 1:      # heartbeat
            self.queue.append(_init_info_reply())
        return len(payload)

    def read(self, n, timeout_ms=0):
        if self.mode == "broken":
            raise IOError("read error")
        if self.mode != "alive":
            return []
        return self.queue.pop(0) if self.queue else []


@pytest.fixture
def hidworld(monkeypatch):
    """Every hid.device() the AulaDevice opens is a fresh FakeHid; `world.mode`
    is the mode the NEXT opened handle starts in."""
    world = types.SimpleNamespace(mode="alive", handles=[], present=True)

    def fake_find(vid=None, pid=None, usage_page=None):
        if not world.present:
            return None
        return {"interface_number": 2, "usage_page": 0xFF1B, "path": b"fake"}

    def fake_device():
        h = FakeHid(world.mode)
        world.handles.append(h)
        return h

    monkeypatch.setattr(aula_device, "find_vendor_interface", fake_find)
    monkeypatch.setattr(aula_device.hid, "device", fake_device)
    return world


def _api():
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.board = None
    a.dev = AulaDevice()
    a.driver = Win60Driver(None, a.dev, a._lock)
    # connect() snapshots the Fn layer; the fake board has no keymap tables.
    a.driver.read_keymap_layer = lambda fn_layer=False, timeout_s=None: None
    a._PROBE_TIMEOUT_S = 0.05
    a.km = None
    a.fx = None
    a.pad = None
    a._pad_thread = None
    a._pad_stop = threading.Event()
    a.reader = None
    a.calib_reader = None
    a._reader_users = set()
    a._calibrating = False
    a._init_link_state()
    return a


def _go_quiet(a):
    """Pretend the last reply was long ago (the probe window has passed)."""
    a.dev._last_rx = time.monotonic() - 3600
    a._last_probe = 0.0


# ------------------------------------------------------- AulaDevice ----
def test_device_write_minus_one_marks_handle_dead(hidworld):
    d = AulaDevice()
    d.open()
    hidworld.handles[-1].mode = "broken"
    with pytest.raises(IOError):
        d.write([1] + [0] * 63)
    assert not d.is_open()
    assert d.dead_events == 1
    assert hidworld.handles[-1].closed


def test_device_read_ioerror_marks_handle_dead(hidworld):
    d = AulaDevice()
    d.open()
    hidworld.handles[-1].mode = "broken"
    with pytest.raises(IOError):
        d.read(64, timeout_ms=0)
    assert not d.is_open() and d.dead_events == 1


def test_device_read_with_data_records_rx(hidworld):
    d = AulaDevice()
    d.open()
    assert d.rx_age() == float("inf")
    d.write(protocol.build_heartbeat())
    assert d.read(64, timeout_ms=0)
    assert d.rx_age() < 1.0


def test_close_is_not_a_dead_event(hidworld):
    d = AulaDevice()
    d.open()
    d.close()
    assert d.dead_events == 0


# ---------------------------------------------------------- status() ----
def test_status_flips_false_on_stale_handle_and_connect_recovers(hidworld):
    a = _api()
    assert a.connect()["ok"]
    assert a.status()["connected"] is True          # first status probes: alive
    # Board re-enumerates: the handle we hold now swallows writes silently.
    hidworld.handles[-1].mode = "stale"
    _go_quiet(a)
    st = a.status()
    assert st["connected"] is False
    assert not a.dev.is_open()                      # the stale handle was dropped
    assert hidworld.handles[-1].closed
    # The UI's watchdog now calls connect(); a fresh handle answers again.
    assert a.connect()["ok"]
    _go_quiet(a)
    assert a.status()["connected"] is True


def test_status_trusts_a_recent_reply_without_probing(hidworld):
    a = _api()
    a.connect()
    a.dev.note_rx()                                 # board just answered
    h = hidworld.handles[-1]
    before = len(h.writes)
    assert a.status()["connected"] is True
    assert len(h.writes) == before                  # no heartbeat sent


def test_status_probes_at_most_once_per_window(hidworld):
    a = _api()
    a.connect()
    h = hidworld.handles[-1]
    _go_quiet(a)
    assert a.status()["connected"] is True
    n = len(h.writes)
    for _ in range(5):                              # UI polls every 2.5 s
        assert a.status()["connected"] is True
    assert len(h.writes) == n                       # no keyboard spam


def test_status_never_probes_while_a_transaction_holds_the_lock(hidworld):
    a = _api()
    a.connect()
    h = hidworld.handles[-1]
    h.mode = "stale"                                # would FAIL a probe
    _go_quiet(a)
    held, release = threading.Event(), threading.Event()

    def busy():                                     # e.g. a macro write
        with a._lock:
            held.set()
            release.wait(5)

    t = threading.Thread(target=busy)
    t.start()
    held.wait(2)
    try:
        before = len(h.writes)
        t0 = time.monotonic()
        st = a.status()
        assert time.monotonic() - t0 < 1.0          # did not block on the lock
        assert st["connected"] is True              # no verdict while busy
        assert len(h.writes) == before
    finally:
        release.set()
        t.join(2)


def test_status_never_probes_during_calibration(hidworld):
    a = _api()
    a.connect()
    h = hidworld.handles[-1]
    h.mode = "stale"
    _go_quiet(a)
    a._calibrating = True
    before = len(h.writes)
    assert a.status()["connected"] is True
    assert len(h.writes) == before


def test_status_reports_disconnected_after_an_io_failure(hidworld):
    """A write that fails underneath (effect frame, reader re-arm) drops the
    handle; status must report it even though nobody called disconnect()."""
    a = _api()
    a.connect()
    hidworld.handles[-1].mode = "broken"
    with pytest.raises(IOError):
        a.dev.write([1] + [0] * 63)
    assert a.status()["connected"] is False


def test_status_lost_even_if_the_handle_was_reopened_meanwhile(hidworld):
    """The driver's _write auto-reopens a closed handle. A death followed by
    such a reopen must still surface once, so recovery (step 2) runs."""
    a = _api()
    a.connect()
    hidworld.handles[-1].mode = "broken"
    with pytest.raises(IOError):
        a.dev.write([1] + [0] * 63)
    a.driver.set_poll_rate(1)                       # any driver write reopens
    assert a.dev.is_open()
    assert a.status()["connected"] is False
    assert a.connect()["ok"]
    assert a.status()["connected"] is True


def test_status_without_device_handle_is_false():
    a = app_web.Api.__new__(app_web.Api)
    a.dev = types.SimpleNamespace(is_open=lambda: False)
    assert a.status() == {"connected": False}


def test_failed_probe_tears_down_readers(hidworld):
    a = _api()
    a.connect()

    class R:
        stopped = False
        def stop(self): self.stopped = True
        def alive(self): return False

    r = R()
    a.reader = r
    a._reader_users = {"analog"}
    hidworld.handles[-1].mode = "stale"
    _go_quiet(a)
    assert a.status()["connected"] is False
    assert r.stopped and a.reader is None


# ------------------------------------------- probe with a live reader ----
def test_probe_with_running_live_reader_does_not_restart_it(hidworld):
    """With the travel-test reader draining the handle the heartbeat reply is
    consumed by the reader; it must still count as proof of life, and the
    reader must NOT be restarted (a restart forgets held keys)."""
    a = _api()
    a.connect()
    km = types.SimpleNamespace(indices=lambda: [0], code_of=lambda i: None,
                               code_of_index={})
    lr = device_state.LiveReader(a.dev, km, indices=[0])
    lr.start()
    a.reader = lr
    a._reader_users = {"analog"}
    try:
        _go_quiet(a)
        assert a.status()["connected"] is True
        assert a.reader is lr and lr._thread.is_alive()
        hidworld.handles[-1].mode = "stale"
        _go_quiet(a)
        assert a.status()["connected"] is False
    finally:
        lr.stop()


# ------------------------------------------------ recovery (step 2) ----
class _Pad:
    opened = 0
    closed = 0

    def __init__(self, mappings=None):
        pass

    def open(self):
        _Pad.opened += 1
        return self

    def close(self):
        _Pad.closed += 1

    def update(self, depths):
        pass


class _Reader:
    """A minimal live reader the Api can start/stop."""
    made = []

    def __init__(self):
        self.started = self.stopped = False
        _Reader.made.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def alive(self):
        return self.started and not self.stopped

    def snapshot(self):
        return {}


def _api_with_session(monkeypatch):
    monkeypatch.setattr(app_web.gamepad, "VirtualGamepad", _Pad)
    _Pad.opened = _Pad.closed = 0
    _Reader.made = []
    a = _api()
    a.km = types.SimpleNamespace(indices=lambda: [0])
    a._pad_map = None
    a.driver.make_live_reader = lambda km, indices=None: _Reader()
    return a


def test_reconnect_restores_claimed_reader_and_gamepad(hidworld, monkeypatch):
    a = _api_with_session(monkeypatch)
    assert a.connect()["ok"]
    assert a.set_gamepad_capture(True)["ok"]
    a._acquire_reader("analog", lambda: a.driver.make_live_reader(a.km))
    first = a.reader
    assert first is not None and first.started
    assert _Pad.opened == 1
    # the board re-enumerates and stops answering
    hidworld.handles[-1].mode = "stale"
    _go_quiet(a)
    assert a.status()["connected"] is False
    assert first.stopped and a.reader is None
    assert a.pad is None and _Pad.closed == 1          # gamepad torn down
    assert "analog" in a._reader_users                  # claim survives the loss
    # the UI watchdog reconnects
    assert a.connect()["ok"]
    assert a.reader is not None and a.reader is not first and a.reader.started
    assert {"analog", "gamepad"} <= a._reader_users
    assert a.pad is not None and _Pad.opened == 2       # gamepad back on
    assert a._pad_thread is not None and a._pad_thread.is_alive()
    a.set_gamepad_capture(False)


def test_reconnect_after_manual_disconnect_restores_nothing(hidworld, monkeypatch):
    a = _api_with_session(monkeypatch)
    a.connect()
    a.set_gamepad_capture(True)
    a.disconnect()                                      # the user's choice
    assert a.connect()["ok"]
    assert a.reader is None and a.pad is None
    assert _Pad.opened == 1


def test_gamepad_not_resumed_when_it_was_off(hidworld, monkeypatch):
    a = _api_with_session(monkeypatch)
    a.connect()
    hidworld.handles[-1].mode = "stale"
    _go_quiet(a)
    assert a.status()["connected"] is False
    a.connect()
    assert a.pad is None and _Pad.opened == 0


# ------------------------------------------ poll-rate restart (step 3) ----
def _restarting_board(hidworld, drop_after=0.05, back_after=0.15, comes_back=True):
    """Make the poll-rate write behave like the WIN 60 HE (measured): the
    board drops off USB ~1 s after the write and re-enumerates ~0.35 s later;
    the old handle then returns -1 on write and raises on read."""
    orig = FakeHid.write

    def write(self, payload):
        n = orig(self, payload)
        p = list(payload)
        if p[1] == 33 and p[6] == 9:                    # cmd 33 sub 9: poll rate
            def drop():
                self.mode = "broken"
                hidworld.present = False
            def back():
                hidworld.present = True
            threading.Timer(drop_after, drop).start()
            if comes_back:
                threading.Timer(back_after, back).start()
        return n
    return write


def _fast_restart(a):
    a._POLL_STEP_S = 0.01
    a._POLL_DROP_WAIT_S = 1.0
    a._POLL_RESTART_TIMEOUT_S = 2.0


def test_set_poll_waits_for_the_restart_and_reconnects(hidworld, monkeypatch):
    monkeypatch.setattr(FakeHid, "write", _restarting_board(hidworld))
    a = _api_with_session(monkeypatch)
    _fast_restart(a)
    assert a.connect()["ok"]
    a.set_gamepad_capture(True)
    a._acquire_reader("analog", lambda: a.driver.make_live_reader(a.km))
    old_handle = hidworld.handles[-1]
    r = a.set_poll(8)
    assert r["ok"] is True and r["restarted"] is True and r["reconnected"] is True
    assert a.dev.is_open() and hidworld.handles[-1] is not old_handle
    assert old_handle.closed
    # session state came back without a manual connect()
    assert a.reader is not None and a.reader.started and "analog" in a._reader_users
    assert a.pad is not None and _Pad.opened == 2
    assert a.status()["connected"] is True
    # and the new handle carries traffic
    assert a.driver.probe_link(0.05) is True
    a.set_gamepad_capture(False)


def test_set_poll_reports_when_the_board_does_not_come_back(hidworld, monkeypatch):
    monkeypatch.setattr(FakeHid, "write", _restarting_board(hidworld, comes_back=False))
    a = _api()
    _fast_restart(a)
    a._POLL_RESTART_TIMEOUT_S = 0.4
    a.connect()
    r = a.set_poll(8)
    assert r["ok"] is True and r["restarted"] is True and r["reconnected"] is False
    assert a.status()["connected"] is False
    hidworld.present = True                              # replugged later
    assert a.connect()["ok"] and a.status()["connected"] is True


def test_status_and_connect_stand_aside_while_the_board_restarts(hidworld, monkeypatch):
    monkeypatch.setattr(FakeHid, "write",
                        _restarting_board(hidworld, drop_after=0.1, back_after=0.4))
    a = _api()
    _fast_restart(a)
    a.connect()
    seen = {}

    def ui_watchdog():
        time.sleep(0.2)                                  # mid-restart
        seen["status"] = a.status()
        seen["connect"] = a.connect()

    t = threading.Thread(target=ui_watchdog)
    t.start()
    r = a.set_poll(8)
    t.join(2)
    assert seen["status"] == {"connected": False, "restarting": True}
    assert seen["connect"]["ok"] is False and seen["connect"].get("restarting") is True
    assert r["reconnected"] is True


def test_set_poll_write_failure_is_reported(hidworld):
    a = _api()
    a.connect()
    hidworld.handles[-1].mode = "broken"
    hidworld.present = False
    r = a.set_poll(8)
    assert r["ok"] is False
