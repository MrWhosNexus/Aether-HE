"""AulaDevice.open() must be idempotent.

Found on macOS with a board attached: the app auto-connects at launch, so
clicking Pair calls connect() again on a device already held. open() built a
fresh hid.device() every time and overwrote self._dev without closing it —

  * macOS  : the second open_path() fails outright, so Pair appeared to do
             nothing and the UI stayed OFFLINE.
  * Win/Linux: the second open SUCCEEDED and the previous handle leaked,
             silently, on every reconnect.

One root cause, two symptoms. These pin the fix on all platforms.

Run: python -m pytest tests/test_reopen_idempotent.py
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import aula_device


class FakeHid:
    """Counts opens/closes so a leak is observable."""
    opened = 0
    closed = 0

    def __init__(self):
        self.is_closed = False

    def open_path(self, path):
        FakeHid.opened += 1
        self.path = path

    def set_nonblocking(self, flag):
        pass

    def close(self):
        FakeHid.closed += 1
        self.is_closed = True


IFACE = {"vendor_id": 0x2E3C, "product_id": 0xC365, "usage_page": 0xFF1B,
         "usage": 0x91, "interface_number": 2, "path": b"DevSrvsID:1"}


@pytest.fixture
def dev(monkeypatch):
    FakeHid.opened = FakeHid.closed = 0
    monkeypatch.setattr(aula_device.hid, "device", FakeHid)
    monkeypatch.setattr(aula_device.hid, "enumerate",
                        lambda vid=None, pid=None: [dict(IFACE)])
    return aula_device.AulaDevice()


def test_first_open_opens_once(dev):
    info = dev.open()
    assert FakeHid.opened == 1
    assert info["interface_number"] == 2
    assert dev.is_open()


def test_second_open_reuses_the_handle(dev):
    """The Pair-after-autoconnect path. Must not open a second handle."""
    first = dev.open()
    second = dev.open()
    assert FakeHid.opened == 1, "opened a second handle for an already-open device"
    assert FakeHid.closed == 0, "closed a handle that was still in use"
    assert second == first


def test_repeated_opens_do_not_leak(dev):
    """The Windows/Linux symptom: every reconnect leaked the previous handle."""
    dev.open()
    for _ in range(10):
        dev.open()
    assert FakeHid.opened == 1
    assert FakeHid.closed == 0


def test_stale_handle_is_replaced_when_device_re_enumerates(dev, monkeypatch):
    """Unplug/replug gives a NEW path. Reporting the dead handle as open would
    be a silent success — reopen instead."""
    dev.open()
    assert FakeHid.opened == 1
    replugged = dict(IFACE, path=b"DevSrvsID:2")
    monkeypatch.setattr(aula_device.hid, "enumerate",
                        lambda vid=None, pid=None: [replugged])
    info = dev.open()
    assert FakeHid.opened == 2, "did not reopen after the device re-enumerated"
    assert FakeHid.closed == 1, "stale handle was not closed"
    assert info["path"] == b"DevSrvsID:2"


def test_open_after_close_opens_again(dev):
    dev.open()
    dev.close()
    assert not dev.is_open()
    dev.open()
    assert FakeHid.opened == 2


def test_absent_device_still_raises(dev, monkeypatch):
    monkeypatch.setattr(aula_device.hid, "enumerate", lambda vid=None, pid=None: [])
    with pytest.raises(IOError):
        dev.open()
