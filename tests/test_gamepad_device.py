"""Gamepad façade + vendor-interface selection (no hardware, no uinput)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import gamepad
import aula_device


# ----------------------------------------------------------- gamepad ----
class _RecordingImpl:
    def __init__(self):
        self.frames = []

    def open(self):
        pass

    def is_open(self):
        return True

    def update(self, depths):
        self.frames.append(dict(depths))

    def close(self):
        pass


def _pad(monkeypatch, mappings=None):
    monkeypatch.setattr(gamepad, "_BACKEND", "evdev")
    p = gamepad.VirtualGamepad(mappings)
    p._impl = _RecordingImpl()
    return p


def test_update_skips_unchanged_frames(monkeypatch):
    """The 120 Hz capture loop calls update() every tick; only a change in a
    MAPPED key's depth may reach the backend (uinput / ViGEm)."""
    p = _pad(monkeypatch)
    p.update({"W": 1.0})
    p.update({"W": 1.0})
    p.update({"W": 1.0, "Q": 2.0})      # Q is not mapped -> still no change
    assert len(p._impl.frames) == 1
    p.update({"W": 1.5})
    p.update({})                        # release
    assert len(p._impl.frames) == 3


def test_unknown_axis_fails_early_and_empty_map_means_defaults(monkeypatch):
    monkeypatch.setattr(gamepad, "_BACKEND", "evdev")
    with pytest.raises(ValueError):
        gamepad.VirtualGamepad([gamepad.KeyMap("W", "THROTTLE")])
    # Api.set_gamepad_map stores None for an empty map -> driving defaults.
    assert gamepad.VirtualGamepad([]).mappings == gamepad.DEFAULT_DRIVING_MAP


def test_no_backend_message_names_the_fix(monkeypatch):
    monkeypatch.setattr(gamepad, "_BACKEND", None)
    with pytest.raises(RuntimeError) as ei:
        gamepad.VirtualGamepad()
    assert "backend" in str(ei.value)


def test_vigembus_probe_is_not_run_off_windows(monkeypatch):
    monkeypatch.setattr(gamepad, "_BACKEND", "evdev")
    assert gamepad.vigembus_present() is False


# ----------------------------------------------- interface selection ----
def _enum(rows):
    return [{"interface_number": i, "usage_page": up, "path": f"p{n}".encode()}
            for n, (i, up) in enumerate(rows)]


def test_vendor_usage_page_wins(monkeypatch):
    rows = _enum([(0, 0x0001), (1, 0x000C), (2, 0xFF1B)])
    monkeypatch.setattr(aula_device, "enumerate_interfaces", lambda v, p: rows)
    assert aula_device.find_vendor_interface()["usage_page"] == 0xFF1B


def test_linux_zero_usage_pages_fall_back_to_highest_interface(monkeypatch):
    rows = _enum([(0, 0), (1, 0), (2, 0)])
    monkeypatch.setattr(aula_device, "enumerate_interfaces", lambda v, p: rows)
    assert aula_device.find_vendor_interface()["interface_number"] == 2


def test_fallback_prefers_vendor_collection_on_the_top_interface(monkeypatch):
    """Windows/macOS split one interface into several collections: when the
    expected page is absent, never pick the generic (keyboard/consumer)
    collection that shares the highest interface number."""
    rows = _enum([(0, 0x0001), (2, 0x000C), (2, 0xFF60), (2, 0x0001)])
    monkeypatch.setattr(aula_device, "enumerate_interfaces", lambda v, p: rows)
    got = aula_device.find_vendor_interface(usage_page=0xFF1B)
    assert got["interface_number"] == 2 and got["usage_page"] == 0xFF60


def test_no_device_returns_none(monkeypatch):
    monkeypatch.setattr(aula_device, "enumerate_interfaces", lambda v, p: [])
    assert aula_device.find_vendor_interface() is None
