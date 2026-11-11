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
    fake_enum([_iface(0x0001, -1, path=b"a"), _iface(0x000C, -1, path=b"b"),
               _iface(0x0001, -1, path=b"c", usage=0x06)])
    with pytest.raises(aula_device.VendorInterfaceUnresolved) as ei:
        aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    msg = str(ei.value)
    assert "refusing to guess" in msg
    # The error must carry what WAS seen, so a user can file a usable report.
    assert "0xc" in msg.lower() and "0x6" in msg.lower()


def test_result_does_not_depend_on_enumeration_order(fake_enum):
    """The defect was max() returning whatever came first. Whatever is
    decided now must be the same for every ordering of the same entries."""
    import itertools
    entries = [_iface(0x0001, -1, path=b"kbd"), _iface(0x000C, -1, path=b"consumer"),
               _iface(0xFF00, -1, path=b"vendor")]
    for perm in itertools.permutations(entries):
        fake_enum(perm)
        assert aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)["path"] == b"vendor"
    tied = [_iface(0xFF00, -1, path=b"v1"), _iface(0xFF00, -1, path=b"v2"),
            _iface(0x0001, -1, path=b"kbd")]
    for perm in itertools.permutations(tied):
        fake_enum(perm)
        with pytest.raises(aula_device.VendorInterfaceUnresolved):
            aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)


# ------------------- Windows: one interface, several top-level collections
def test_windows_multi_collection_interface_picks_the_vendor_collection(fake_enum):
    """hidapi on Windows gives every collection of an interface (&Col01,
    &Col02, ...) the SAME interface_number. A board whose vendor page is not
    the requested one therefore has all-equal numbers; the pre-port ranking
    (number, is-vendor-page, page) picked its vendor collection, and raising
    here made such a board impossible to open."""
    fake_enum([_iface(0x0001, 0, path=b"hid#vid_2e3c&pid_c365&col01", usage=0x06),
               _iface(0x000C, 0, path=b"hid#vid_2e3c&pid_c365&col02", usage=0x01),
               _iface(0xFF60, 0, path=b"hid#vid_2e3c&pid_c365&col03", usage=0x61)])
    got = aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert got["usage_page"] == 0xFF60 and got["path"].endswith(b"col03")


def test_windows_single_interface_number_minus_one_also_resolves(fake_enum):
    """Same shape with the -1 hidapi reports when it cannot parse MI_xx."""
    fake_enum([_iface(0xFF00, -1, path=b"col02"), _iface(0x0001, -1, path=b"col01")])
    assert aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)["path"] == b"col02"


NOT_MAC = ["win32", "linux"]


@pytest.fixture
def on(monkeypatch):
    def _set(platform):
        monkeypatch.setattr(aula_device.sys, "platform", platform)
    return _set


@pytest.mark.parametrize("platform", NOT_MAC)
def test_several_vendor_collections_on_one_path_are_one_choice(fake_enum, on, platform):
    """Windows/Linux, unchanged: entries under one path open the same thing,
    and the ranking takes the highest page."""
    on(platform)
    fake_enum([_iface(0x0001, -1, path=b"shared"),
               _iface(0xFF00, -1, path=b"shared", usage=1),
               _iface(0xFF01, -1, path=b"shared", usage=2)])
    got = aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert got["path"] == b"shared" and got["usage_page"] == 0xFF01


@pytest.mark.parametrize("platform", NOT_MAC)
def test_several_vendor_collections_keep_the_old_ranking_when_it_is_unique(
        fake_enum, on, platform):
    """Pre-port behaviour for all-equal numbers on Windows/Linux: the highest
    vendor page."""
    on(platform)
    fake_enum([_iface(0xFF00, 0, path=b"a"), _iface(0xFF60, 0, path=b"b"),
               _iface(0x0001, 0, path=b"c")])
    assert aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)["path"] == b"b"


# ------------------------------------- macOS: no "highest page" guess
@pytest.mark.parametrize("entries", [
    # distinct vendor pages on different paths
    [_iface(0xFF00, -1, path=b"a"), _iface(0xFF60, -1, path=b"b"), _iface(0x0001, -1, path=b"c")],
    # distinct vendor pages under ONE path: still two candidates, still no
    # evidence which is the config collection
    [_iface(0x0001, -1, path=b"shared"), _iface(0xFF00, -1, path=b"shared", usage=1),
     _iface(0xFF01, -1, path=b"shared", usage=2)],
])
def test_macos_refuses_several_distinct_vendor_pages(fake_enum, on, entries):
    """None is the board's configured page, and "the highest one" is a guess
    about firmware nobody measured on macOS."""
    on("darwin")
    fake_enum(entries)
    with pytest.raises(aula_device.VendorInterfaceUnresolved) as ei:
        aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert "refusing to guess" in str(ei.value)


def test_macos_takes_the_only_vendor_page(fake_enum, on):
    on("darwin")
    fake_enum([_iface(0x0001, -1, path=b"kbd"), _iface(0x000C, -1, path=b"media"),
               _iface(0xFF60, -1, path=b"vendor")])
    got = aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert got["path"] == b"vendor" and got["usage_page"] == 0xFF60


def test_macos_one_vendor_page_listed_twice_under_one_path_is_one_choice(fake_enum, on):
    on("darwin")
    fake_enum([_iface(0x0001, -1, path=b"shared"),
               _iface(0xFF60, -1, path=b"shared", usage=1),
               _iface(0xFF60, -1, path=b"shared", usage=2)])
    got = aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)
    assert got["path"] == b"shared" and got["usage"] == 1


def test_macos_configured_page_still_wins_among_several_vendor_pages(fake_enum, on):
    """Several vendor pages are fine when one of them IS the configured one."""
    on("darwin")
    fake_enum([_iface(0xFF00, -1, path=b"a"), _iface(0xFF60, -1, path=b"b"),
               _iface(0xFFFF, -1, path=b"c")])
    assert aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF60)["path"] == b"b"


@pytest.mark.parametrize("platform", NOT_MAC + ["darwin"])
def test_strict_flag_follows_the_platform(on, platform):
    on(platform)
    two = [_iface(0xFF00, 0, path=b"a"), _iface(0xFF60, 0, path=b"b")]
    got = aula_device._sole_vendor_collection(two)
    assert (got is None) if platform == "darwin" else (got["path"] == b"b")


def test_two_vendor_collections_with_the_same_page_on_different_paths_refuse(fake_enum):
    fake_enum([_iface(0xFF60, 0, path=b"a"), _iface(0xFF60, 0, path=b"b")])
    with pytest.raises(aula_device.VendorInterfaceUnresolved):
        aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)


def test_win60_on_macos_still_takes_its_0xff1b_collection(fake_enum):
    """The measured macOS shape: all -1, vendor collection 0xFF1B. It matches
    on the usage page and never reaches the fallback, even with another
    vendor-defined page beside it."""
    fake_enum([_iface(0x0001, -1, path=b"kbd"), _iface(0xFFFF, -1, path=b"other"),
               _iface(0xFF1B, -1, path=b"vendor")])
    assert aula_device.find_vendor_interface(0x2E3C, 0xC365, 0xFF1B)["path"] == b"vendor"


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
