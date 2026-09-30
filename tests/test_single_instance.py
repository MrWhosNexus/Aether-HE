"""single_instance: no-op off Windows; on Windows the kernel32 calls are
exercised through a fake DLL so the mutex/event logic is pinned without a
real Win32 environment."""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import single_instance as si  # noqa: E402


def test_non_windows_is_a_no_op(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    s = si.SingleInstance()
    assert s.acquire() is True
    assert s.poke_existing() is False
    s.listen(lambda: None)          # must not start anything
    assert s._thread is None
    s.release()


class FakeK32:
    """Just enough kernel32: one process-wide mutex and named-event table."""
    SHOW, ACK = 22, 33

    def __init__(self):
        self.mutex_exists = False
        self.events = {}                # handle -> threading.Event
        self.signals = 0
        self.closed = []
        self.last_error = 0

    @property
    def event(self):                    # the show event (older tests)
        return self.events.get(self.SHOW)

    @event.setter
    def event(self, v):
        if v is None:
            self.events.pop(self.SHOW, None)
        else:
            self.events[self.SHOW] = v

    def _handle(self, name):
        return self.ACK if name == si.ACK_NAME else self.SHOW

    def CreateMutexW(self, sa, initial, name):
        self.last_error = si.ERROR_ALREADY_EXISTS if self.mutex_exists else 0
        self.mutex_exists = True
        return 11

    def CreateEventW(self, sa, manual, initial, name):
        h = self._handle(name)
        self.events[h] = threading.Event(); return h

    def OpenEventW(self, access, inherit, name):
        h = self._handle(name)
        return h if h in self.events else 0

    def SetEvent(self, h):
        if h == self.SHOW:
            self.signals += 1
        self.events[h].set(); return 1

    def WaitForSingleObject(self, h, ms):
        if self.events[h].wait(ms / 1000.0):
            self.events[h].clear()      # auto-reset semantics
            return si.WAIT_OBJECT_0
        return 0x102                    # WAIT_TIMEOUT

    def CloseHandle(self, h):
        self.closed.append(h); return 1


def _fake_windows(monkeypatch):
    k = FakeK32()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(si, "_k32", lambda: k)
    import ctypes
    monkeypatch.setattr(ctypes, "get_last_error", lambda: k.last_error, raising=False)
    return k


def test_first_instance_owns_mutex_second_is_refused(monkeypatch):
    k = _fake_windows(monkeypatch)
    first, second = si.SingleInstance(), si.SingleInstance()
    assert first.acquire() is True
    assert second.acquire() is False
    assert 11 in k.closed               # the loser closed its handle


def test_poke_wakes_listener_and_release_stops_it(monkeypatch):
    k = _fake_windows(monkeypatch)
    owner = si.SingleInstance(); assert owner.acquire()
    shown = []
    owner.listen(lambda: shown.append(time.monotonic()))
    other = si.SingleInstance(); assert other.acquire() is False
    assert other.poke_existing() == si.SHOWN   # waits for the ack
    assert len(shown) == 1 and k.signals == 1
    owner.release()
    owner._thread.join(1.0)
    assert not owner._thread.is_alive()


def test_poke_without_running_instance_is_false(monkeypatch):
    _fake_windows(monkeypatch)
    assert si.SingleInstance().poke_existing() == si.UNREACHABLE


def test_poke_reports_hung_instance_as_unresponsive(monkeypatch):
    """The failure behind 'it isn't booting at all': a stuck background
    instance holds the mutex, SetEvent still succeeds, but its window never
    comes up. The new launch must learn that instead of exiting quietly."""
    _fake_windows(monkeypatch)
    owner = si.SingleInstance(); assert owner.acquire()
    owner.listen(lambda: False)         # show failed / GUI thread stuck
    other = si.SingleInstance(); assert other.acquire() is False
    assert other.poke_existing(ack_timeout_ms=200) == si.UNRESPONSIVE
    owner.release()


def test_poke_trusts_older_instance_without_ack_event(monkeypatch):
    k = _fake_windows(monkeypatch)
    k.event = threading.Event()         # show event only, no ack (old build)
    assert si.SingleInstance().poke_existing(ack_timeout_ms=50) == si.SHOWN


def test_main_uses_single_instance_and_own_storage_path():
    src = open(os.path.join(ROOT, "app_web.py"), encoding="utf-8").read()
    assert "single_instance.SingleInstance()" in src
    assert "storage_path=storage" in src and '"webview")' in src


def test_kernel32_signatures_are_pointer_sized():
    """HANDLEs are pointer-sized on Win64; ctypes' default int restype
    truncates them. _declare must pin restype/argtypes on every call used."""
    from ctypes import wintypes

    class Fn:
        restype = None
        argtypes = None

    class FakeDLL:
        def __init__(self):
            for n in ("CreateMutexW", "CreateEventW", "OpenEventW", "SetEvent",
                      "WaitForSingleObject", "CloseHandle"):
                setattr(self, n, Fn())

    k = si._declare(FakeDLL())
    for n in ("CreateMutexW", "CreateEventW", "OpenEventW"):
        assert getattr(k, n).restype is wintypes.HANDLE
    assert k.WaitForSingleObject.argtypes == (wintypes.HANDLE, wintypes.DWORD)
    assert k.WaitForSingleObject.restype is wintypes.DWORD
    assert k.CloseHandle.argtypes == (wintypes.HANDLE,)
    assert k.SetEvent.argtypes == (wintypes.HANDLE,)


def test_listener_exits_on_wait_failed_instead_of_spinning(monkeypatch):
    k = _fake_windows(monkeypatch)
    calls = []

    def bad_wait(h, ms):
        calls.append(ms)
        return si.WAIT_FAILED

    k.WaitForSingleObject = bad_wait
    owner = si.SingleInstance(); assert owner.acquire()
    owner.listen(lambda: None)
    owner._thread.join(1.0)
    assert not owner._thread.is_alive()
    assert len(calls) == 1                  # one failed wait, then out
    owner.release()


def test_poke_logs_access_denied_and_reports_false(monkeypatch, caplog):
    """Elevated instance (installer-launched) → OpenEventW fails with
    ERROR_ACCESS_DENIED; the launcher must get False, not an exception."""
    k = _fake_windows(monkeypatch)
    k.event = None
    import ctypes
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    with caplog.at_level("WARNING"):
        assert si.SingleInstance().poke_existing() == si.UNREACHABLE
    assert "error 5" in caplog.text


def test_notify_unreachable_is_a_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert si.SingleInstance.notify_unreachable() is False


def test_main_notifies_when_running_instance_is_unreachable():
    src = open(os.path.join(ROOT, "app_web.py"), encoding="utf-8").read()
    assert "inst.notify_unreachable(" in src
    assert "inst.notify_unresponsive(" in src
    # logging is armed before the third-party imports that can fail
    assert src.index("boot.install_file_logging()") < src.index("import webview")


def test_notify_unresponsive_is_a_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert si.SingleInstance.notify_unresponsive() is False
