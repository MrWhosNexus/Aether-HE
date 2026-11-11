"""macOS HID-layer behaviour for aula_device.

Two macOS facts drive these tests, both MEASURED on macOS 26.5.2 / arm64 rather
than inferred:

1. hidapi's macOS backend reports `interface_number == -1` for every device on a
   non-USB transport — 27 of 34 entries on the dev machine. The old fallback
   `max(matches, key=interface_number)` over an all-equal key returns the FIRST
   element, so an arbitrary collection was being presented as a deliberate pick.

2. macOS enumerates one entry per top-level COLLECTION, and collections sharing a
   USB interface share one `path` (three built-in-keyboard entries all reported
   `DevSrvsID:4294970020`). So `open_path()` opens the interface, not a collection.

Run: python -m pytest tests/test_macos_hid.py
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import aula_device


# ---------------------------------------------------------------- helpers
def _iface(usage_page, interface_number, path=b"p", usage=0x00):
    return {"vendor_id": 0x2E3C, "product_id": 0xC365, "usage_page": usage_page,
            "usage": usage, "interface_number": interface_number, "path": path}


@pytest.fixture
def fake_enum(monkeypatch):
    """Replace hid.enumerate with a canned interface list."""
    def _install(entries):
        monkeypatch.setattr(aula_device.hid, "enumerate",
                            lambda vid=None, pid=None: list(entries))
    return _install


# ------------------------------------------------- unchanged happy paths
def test_absent_board_returns_none(fake_enum):
    fake_enum([])
    assert aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B) is None


def test_usage_page_match_wins(fake_enum):
    """The normal path. Must not change — Win60 ships to a real user."""
    fake_enum([_iface(0x0001, 0), _iface(0xFF1B, 2, path=b"vendor")])
    got = aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert got["usage_page"] == 0xFF1B and got["path"] == b"vendor"


def test_informative_interface_numbers_still_use_max(fake_enum):
    """Windows/Linux fallback is untouched: distinct numbers -> highest wins."""
    fake_enum([_iface(0x0001, 0), _iface(0x000C, 1), _iface(0x0001, 3)])
    got = aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert got["interface_number"] == 3


# ------------------------------------------------------ the macOS defect
def test_all_minus_one_refuses_instead_of_guessing(fake_enum):
    """macOS: every interface_number is -1, so max() would pick arbitrarily."""
    fake_enum([_iface(0x0001, -1), _iface(0x000C, -1), _iface(0xFF00, -1)])
    with pytest.raises(aula_device.VendorInterfaceUnresolved) as ei:
        aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    msg = str(ei.value)
    assert "refusing to guess" in msg
    # The error must carry what WAS seen, so a user can file a usable report.
    assert "0xff00" in msg.lower()


def test_all_equal_numbers_refuse_too(fake_enum):
    """Not macOS-specific: any all-equal key makes max() meaningless."""
    fake_enum([_iface(0x0001, 0), _iface(0x000C, 0)])
    with pytest.raises(aula_device.VendorInterfaceUnresolved):
        aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)


def test_single_interface_no_match_refuses(fake_enum):
    fake_enum([_iface(0x0001, -1)])
    with pytest.raises(aula_device.VendorInterfaceUnresolved):
        aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)


def test_single_node_with_unknown_usage_page_is_still_opened(fake_enum):
    """Legacy Linux hidraw: one node, usage page reported as 0. There is
    nothing to choose between, so this is not a guess and must keep working."""
    fake_enum([_iface(0x0000, -1, path=b"only")])
    got = aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert got["path"] == b"only"


def test_ranked_fallback_survives_informative_numbers(fake_enum):
    """Upstream's rank (vendor-defined page on the top interface) is kept
    whenever the interface numbers DO discriminate."""
    fake_enum([_iface(0x0001, 0), _iface(0x000C, 2), _iface(0xFF60, 2), _iface(0x0001, 2)])
    got = aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert got["interface_number"] == 2 and got["usage_page"] == 0xFF60


def test_duplicate_usage_page_collections_pick_first(fake_enum):
    """Shared-path collections are legal on macOS; first wins, deterministically."""
    fake_enum([_iface(0xFF1B, -1, path=b"shared", usage=0x91),
               _iface(0xFF1B, -1, path=b"shared", usage=0x92)])
    got = aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert got["usage"] == 0x91


# ------------------------------------------------------ TCC translation
def test_open_error_untouched_off_darwin(monkeypatch):
    monkeypatch.setattr(aula_device.sys, "platform", "win32")
    original = IOError("open failed")
    assert aula_device._translate_open_error(
        original, "Aula Win60 HE", _iface(0xFF1B, 2)) is original


def test_open_error_on_darwin_names_both_causes(monkeypatch):
    monkeypatch.setattr(aula_device.sys, "platform", "darwin")
    out = aula_device._translate_open_error(
        IOError("open failed"), "Aula Win60 HE", _iface(0xFF1B, -1))
    assert isinstance(out, aula_device.HidPermissionError)
    text = str(out)
    assert "Input Monitoring" in text
    assert aula_device.INPUT_MONITORING_URL in text
    # hidapi cannot tell TCC from exclusive-access, so we must not claim it did.
    assert "exclusiv" in text.lower()


def test_darwin_generic_desktop_collection_flags_tcc_as_likely(monkeypatch):
    monkeypatch.setattr(aula_device.sys, "platform", "darwin")
    out = aula_device._translate_open_error(
        IOError("open failed"), "Some Board", _iface(0x0001, -1, usage=0x06))
    assert "always gates" in str(out)


def test_darwin_vendor_collection_does_not_claim_tcc(monkeypatch):
    """A vendor usage page is normally TCC-exempt — don't over-claim."""
    monkeypatch.setattr(aula_device.sys, "platform", "darwin")
    out = aula_device._translate_open_error(
        IOError("open failed"), "Some Board", _iface(0xFF68, -1))
    assert "always gates" not in str(out)
