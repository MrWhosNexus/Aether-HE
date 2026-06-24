"""Tests for the board registry (boards.py) + every board's layout.

Run: python -m pytest tests/test_boards.py   (or: python tests/test_boards.py)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import boards
from validate_keymap import load_keymap


def test_registry_loads():
    reg = boards.load_registry()
    assert reg.profiles, "registry has no boards"
    assert reg.default is not None


def test_default_is_win60():
    reg = boards.load_registry()
    assert reg.default.slug == "aula-win60-he"
    assert reg.default.vid == 0x2E3C and reg.default.pid == 0xC365


def test_all_submitted_boards_present():
    """Every keyboard submitted via the issue form must be in the registry."""
    reg = boards.load_registry()
    expected = {
        (0x0C45, 0x80A1),  # MINI60HE Max (#1/#4)
        (0x0C45, 0xFEFE),  # Mini 60 HE Pro (#6)
        (0x1CA2, 0x1902),  # Win60 HE Max (#5)
        (0x1CA2, 0x1901),  # win68 HE Max (#7)
        (0x8089, 0x0009),  # WIN 60 HE Pro / SayoDevice (#3)
    }
    have = {(p.vid, p.pid) for p in reg.profiles}
    missing = expected - have
    assert not missing, f"submitted boards missing from registry: {missing}"


def test_ids_and_slugs_unique():
    reg = boards.load_registry()
    slugs = [p.slug for p in reg.profiles]
    ids = [(p.vid, p.pid) for p in reg.profiles]
    assert len(slugs) == len(set(slugs))
    assert len(ids) == len(set(ids))


def test_every_board_keymap_validates():
    reg = boards.load_registry()
    for p in reg.profiles:
        assert os.path.exists(p.keymap), f"{p.slug}: keymap missing {p.keymap}"
        load_keymap(p.keymap)  # raises on any schema violation


def test_detect_matches_by_vid_pid():
    reg = boards.load_registry()
    fake = [{"vendor_id": 0x0C45, "product_id": 0x80A1, "interface_number": 1}]
    p = reg.detect(enumerate_fn=lambda: fake)
    assert p is not None and p.slug == "aula-mini60he-max"


def test_detect_returns_none_when_unknown():
    reg = boards.load_registry()
    fake = [{"vendor_id": 0xDEAD, "product_id": 0xBEEF, "interface_number": 0}]
    assert reg.detect(enumerate_fn=lambda: fake) is None


def test_drivable_flag():
    reg = boards.load_registry()
    assert reg.by_slug("aula-win60-he").drivable          # protocol wired (on-HW)
    assert reg.by_slug("aula-mini60he-max").drivable      # protocol_sonix (capture #4)


def test_only_captured_boards_are_drivable():
    """A board may be 'drivable' ONLY if we have its own decoded protocol.

    Guards against the shared-VID fallacy: 0C45:FEFE (#6) shares a vendor ID with
    the decoded 0C45:80A1 (#4) but has no capture of its own, so it must NOT be
    drivable. Same for the 1CA2 pair (#5/#7) and the SayoDevice 8089 (#3).
    """
    reg = boards.load_registry()
    captured = {"aula-win60-he", "aula-mini60he-max"}  # the only boards with verified protocol
    for p in reg.profiles:
        if p.slug in captured:
            assert p.drivable, f"{p.slug} should be drivable"
        else:
            assert not p.drivable, (
                f"{p.slug} ({p.vid_pid}) is marked drivable but has no captured "
                f"protocol of its own")
            assert p.protocol is None
            assert p.cap("lighting") is False and p.cap("actuation") is False


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    sys.exit(1 if failed else 0)
