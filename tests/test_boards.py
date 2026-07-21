"""Tests for the board registry (boards.py) + every board's layout.

Run: python -m pytest tests/test_boards.py   (or: python tests/test_boards.py)
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import boards
from validate_keymap import load_keymap


# ---------------------------------------------------------------- helpers
def _board(slug, vid="0x1111", pid="0x2222", **extra):
    """Minimal valid registry entry (keymap reuses the real Win60 layout)."""
    b = {"slug": slug, "name": slug, "vid": vid, "pid": pid,
         "formFactor": "60%", "usage_page": None, "keymap": "ui/keymap.json",
         "protocol": None,
         "capabilities": {"lighting": False, "actuation": False, "perKeyRgb": False},
         "status": "planned", "issues": []}
    b.update(extra)
    return b


def _load(boards_list, default=None):
    """Write a throwaway registry file and load it through the real validator."""
    d = tempfile.mkdtemp(prefix="aether-reg-")
    path = os.path.join(d, "registry.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"default": default or boards_list[0]["slug"], "boards": boards_list}, f)
    return boards.load_registry(path)


def _raises_registry_error(fn):
    try:
        fn()
    except boards.BoardRegistryError:
        return True
    return False


# ---------------------------------------------------------------- existing behaviour
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
        (0x258A, 0x010C),  # Aula F75 Tri-Mode (#8)
    }
    have = {(p.vid, p.pid) for p in reg.profiles}
    missing = expected - have
    assert not missing, f"submitted boards missing from registry: {missing}"


def test_ids_and_slugs_unique():
    """Slugs are globally unique. VID:PID pairs are unique UNLESS discriminated:
    a shared (vid, pid) group may hold several boards only when at most one of
    them omits `productString` (the fallback) and all declared product strings
    in the group are distinct — mirrors the loader's fail-closed rule.
    """
    reg = boards.load_registry()
    slugs = [p.slug for p in reg.profiles]
    assert len(slugs) == len(set(slugs))
    groups = {}
    for p in reg.profiles:
        groups.setdefault((p.vid, p.pid), []).append(p)
    for key, group in groups.items():
        if len(group) == 1:
            continue
        undisc = [p for p in group if not p.product_strings]
        assert len(undisc) <= 1, (
            f"{group[0].vid_pid}: multiple undiscriminated entries "
            f"{[p.slug for p in undisc]}")
        ps = [s.strip().casefold() for p in group for s in p.product_strings]
        assert len(ps) == len(set(ps)), f"{group[0].vid_pid}: duplicate product strings"


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
    assert reg.by_slug("aula-win60he-pro").drivable       # protocol_sayo (capture #3)
    assert reg.by_slug("aula-mini60he-pro").drivable      # protocol_mini60 (WebHID capture, on-HW)


def test_only_captured_boards_are_drivable():
    """A board may be 'drivable' ONLY if we have its own decoded protocol.

    Guards against the shared-VID fallacy: 0C45:FEFE (#6) shares a vendor ID with
    the decoded 0C45:80A1 (#4) but has no capture of its own, so it must NOT be
    drivable. Same for the 1CA2 pair (#5/#7). The SayoDevice 8089:0009 (#3)
    earned its slot via its own captures (protocol_sayo).

    0C45:80A2 (the wired MINI 60 HE PRO) earned its slot the hard way: it shares
    BOTH the vendor ID and the 0xFF68 usage page with the decoded 0x80A1, and
    protocol_sonix STILL did not drive it (wrong byte[16], wrong endianness).
    It is drivable only because it has its own WebHID capture of the official
    driver (docs/context/issue-6-mini60-pro-raw/), golden tests pinned to those
    frames, and a round-trip verification against the physical board.

    PROMOTION 2026-07-20: aula-mini60he-pro-24g (0C45:FEFE — the same
    keyboard's 2.4GHz dongle) is now in the captured set, and it earned it
    at the FULL standard, not by inference from the wired decode:
      * its OWN captures — webhid-capture-dongle-2026-07-20.json (0x17/0x11
        reads + a complete 42-frame 0x27 write pass) and
        webhid-capture-dongle-handshake.json (the vendor connect handshake
        with 0x55 IN replies), plus WIRELESS_DONGLE_FINDINGS.md — prove it
        speaks protocol_mini60 at 32-byte frames (registry frameLen: 32,
        chunk = frameLen - 8), golden-tested byte-for-byte in
        tests/test_protocol_mini60.py;
      * the TRANSPORT is HARDWARE-VERIFIED: usage_page 0xFF60 usage 0x61
        report id 0 answers 0x55 replies on a raw hidapi handle, and 0x23
        lighting (both colorMode values) + the 21-chunk 0x24 per-key table
        rendered VISIBLY on the physical keyboard over the dongle.
    The promotion was NOT smooth, and the traps are worth their weight:
    an early probe sent 64-byte frames that hidapi silently truncated at
    the 32-byte-report interface and concluded "different protocol"; later
    probes ran while the vendor web page still held the device and saw
    writes ACCEPTED with no reply — including a fake zero-error 23.8 fps
    0x32 "streaming benchmark" with the keyboard dark. Judge a transport
    ONLY on a valid 0x55 reply or a visible effect; write acceptance is
    not evidence. (0x32 host streaming genuinely does NOT work over the
    dongle — the RF bridge drops it and the vendor never streams over
    2.4GHz — hence lighting.hostEngine false on that entry.)

    The OTHER dongle (0C45:FEFC, MINI60HE/MINI68HE Max's) has NO capture of
    its own and stays non-drivable. Its temptation is now even stronger —
    a sibling dongle of the same vendor with a decoded twin — but that is
    the exact adjacent-identity inference this guard exists to block. The
    same rule covers every identity-only sibling recorded from the HFD SDK
    device registry (0x80B2 alt PID, the 0x38A6 MINI 68 / F75 HE family):
    the vendor driver says they speak the same protocol, but none of them
    has a capture, so none of them is drivable.

    DELIBERATE EXCEPTION (2026-07-20): aula-win68-he and aula-kp-te153 are
    drivable without a board-specific capture. This is NOT the shared-VID
    fallacy, and here is the evidence (audited in
    docs/context/hed-aulacn-raw/driver_deobf/):

    1. IDENTICAL USB IDENTITY. All 2E3C:C365 boards are bit-identical at the
       transport layer (same VID, PID, usage page 0xFF1B). Every falsified
       "same protocol" inference this project has recorded (80A1 vs 80A2, the
       FEFE/FEFC dongles, the 38A6 family, the 80B2 alt PID) crossed a
       DIFFERENT USB identity. No falsification has ever occurred within one.
    2. THE VENDOR'S PROTOCOL LAYER IS PROVABLY PRODUCT-AGNOSTIC. The entire
       packet layer (agreement.deobf.js) references curDevice.product exactly
       once — as a localStorage cache key. Every full-table write is a
       fixed-size full-matrix constant (keymap 528 = 132x4, per-key RGB
       396 = 132x3, switch 132, dead-band 264 = 132x2, trigger select =
       22-column bitmask), NEVER sized from key count; index math is the
       shared 6x22 matrix; travel unit, max travel and optional features
       (dead-band, gamepad, high-precision) are negotiated from the device at
       connect. The hardcoded per-product quirks (KGA75HEARGB DKS defaults,
       YC75HEARGB, 7575US/QK75C) are all UI-layer and touch no command bytes.
       One driver code path serves all five boards in production — if the
       sibling firmware spoke a different protocol, the vendor's own driver
       would be broken.
    3. THE DANGEROUS DIVERGENCE IS THE LAYOUT, AND IT IS HANDLED. R-Shift is
       index 100 on the 60% board and 101 on the 68/69-key boards. Before
       these entries existed, a WIN 68 owner FELL BACK to aula-win60-he and
       was driven with the wrong 60% indices — the exact misdirection this
       guard exists to prevent. The sibling entries carry the vendor's own
       per-product index tables (the same source that reproduced the
       hardware-verified Win60 map exactly), so adding them drivable strictly
       REDUCES the misdirection risk relative to the previous fallback.
    4. WHAT STAYS GATED: firmware-feature-bit capabilities (deadzone, gamepad)
       are 'wip' until the bits are read from real hardware, and SOCD on the
       UK ISO KP-TE153 is 'wip' pending the type!='us' PRCS hidCode check.
       Bring-up must also confirm triggerUnit = 0.01 mm (cmd 33 sub 4) since
       a high-precision firmware would rescale actuation 10x.

    Everything else in this test keeps its teeth: any board whose USB identity
    differs from a captured one still needs its own capture.
    """
    reg = boards.load_registry()
    captured = {"aula-win60-he", "aula-mini60he-max",
                "aula-win60he-pro", "aula-mini60he-pro",  # own decoded protocol
                "aula-mini60he-pro-24g",  # own dongle captures + HW-verified 0xFF60 transport (see docstring)
                "aula-win68-he", "aula-kp-te153"}  # 2E3C:C365 shared-identity exception (see docstring)
    for p in reg.profiles:
        if p.slug in captured:
            assert p.drivable, f"{p.slug} should be drivable"
        else:
            assert not p.drivable, (
                f"{p.slug} ({p.vid_pid}) is marked drivable but has no captured "
                f"protocol of its own")
            assert p.protocol is None
            assert p.cap("lighting") is False and p.cap("actuation") is False


# ---------------------------------------------------------------- new: frame sizes
def test_frame_len_declared_in_raw_registry():
    """`frameLen` rides in the RAW registry JSON — boards.py's frozen
    BoardProfile doesn't carry it, so drivers/mini60.frame_len_for_profile
    reads it by slug (the hostEngineMaxFps passthrough pattern). Wired MINI
    60 HE PRO declares 64 explicitly (CONFIRMED-BY-CAPTURE: all 457 wired
    frames are 64 bytes); the 2.4GHz dongle declares 32
    (CONFIRMED-BY-CAPTURE: every frame in
    webhid-capture-dongle-2026-07-20.json is len=32). The rule that fell
    out of the wireless capture: payload chunk = frameLen - 8."""
    with open(boards.REGISTRY_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    by_slug = {b["slug"]: b for b in raw["boards"]}
    assert by_slug["aula-mini60he-pro"]["frameLen"] == 64
    assert by_slug["aula-mini60he-pro-24g"]["frameLen"] == 32
    # no other board declares a frame length yet — the wired 64 default
    # covers everything else, so nothing changes for existing boards
    for slug, b in by_slug.items():
        if slug not in ("aula-mini60he-pro", "aula-mini60he-pro-24g"):
            assert "frameLen" not in b, f"{slug} unexpectedly declares frameLen"


def test_mini60_pro_24g_drivable_with_honest_gating():
    """The dongle entry (2026-07-20): drivable through protocol_mini60 at
    frameLen 32 on the HARDWARE-VERIFIED 0xFF60/0x61 collection.

    Capability gating rule (see the registry _note): true ONLY for what was
    observed working over the RF bridge —
      lighting / perKeyRgb  HARDWARE-VERIFIED (rendered visibly: static
                            red with colorMode 0, blue, Spectrum Cycle,
                            and the 21-chunk 0x24 solid-green table);
      actuation             true on the capture: the COMPLETE 42-frame
                            0x27 write pass is CONFIRMED-BY-CAPTURE over
                            this transport ('wip' would misstate it —
                            this registry defines 'wip' as SOURCE-ONLY),
                            with the Aether-side round trip as the first
                            bring-up check;
      rapidTrigger          rides the same capture-confirmed 0x27 records
                            (content, not framing; the firmware behind
                            the bridge IS the wired board — 0x10 reports
                            0x80A2 over the dongle);
      deadzone              'wip' — its 0x21 WRITE was never observed
                            over the bridge (only the 0x11 read answers);
      socd/macros/calibration 'wip' — never exercised wirelessly;
      gamepad               false — no board-side command exists.
    hostEngine MUST be false: the RF bridge accepts 0x32 stream writes and
    silently drops them (HARDWARE-VERIFIED negative — 23.8 fps of no-ops,
    keyboard dark; the vendor's own app never streams over 2.4GHz), so no
    hostEngineMaxFps is declared either."""
    reg = boards.load_registry()
    p = reg.by_slug("aula-mini60he-pro-24g")
    assert p.protocol == "protocol_mini60" and p.drivable
    assert p.usage_page == 0xFF60
    assert p.cap("lighting") is True
    assert p.cap("perKeyRgb") is True
    assert p.cap("actuation") is True
    assert p.cap("rapidTrigger") is True
    assert p.cap("deadzone") == "wip"
    for flag in ("socd", "macros", "calibration"):
        assert p.cap(flag) == "wip", f"dongle {flag} must stay 'wip'"
    assert p.cap("gamepad") is False
    # host streaming does not exist over 2.4GHz — hard false, no fps cap
    assert p.lighting is not None
    assert p.lighting["hostEngine"] is False
    with open(boards.REGISTRY_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    raw_entry = next(b for b in raw["boards"]
                     if b["slug"] == "aula-mini60he-pro-24g")
    assert "hostEngineMaxFps" not in raw_entry["lighting"]
    # same firmware as the wired board: identical 20-mode table, identical
    # forced-random color flags, same layout file, global dead zones
    wired = reg.by_slug("aula-mini60he-pro")
    assert p.lighting["modes"] == wired.lighting["modes"]
    assert p.keymap == wired.keymap
    assert p.deadzone_scope == "global"
    assert p.product_strings == ("MINI 60 HE PRO Dongle",)


# ---------------------------------------------------------------- new: identity siblings
def test_hfd_sibling_identity_entries_present():
    """The HFD SDK device registry siblings are recorded as identity-only entries."""
    reg = boards.load_registry()
    expected = {
        "aula-mini60he-pro-80b2": (0x0C45, 0x80B2),
        "aula-mini68he": (0x38A6, 0x2722),
        "aula-mini68he-pro": (0x38A6, 0x2723),
        "aula-mini68he-max": (0x38A6, 0x2724),
        "aula-f75-he": (0x38A6, 0x2729),
        "aula-mini60he-max-24g": (0x0C45, 0xFEFC),
    }
    for slug, (vid, pid) in expected.items():
        p = reg.by_slug(slug)
        assert p is not None, f"missing identity entry {slug}"
        assert (p.vid, p.pid) == (vid, pid)
        assert p.protocol is None and not p.drivable, (
            f"{slug} is an identity-only entry and must stay non-drivable")


# ---------------------------------------------------------------- new: capability flags
def test_capability_values_validated():
    """Capability values must be exactly true/false/'wip' — fail-closed."""
    for bad in ("yes", 1, 0, None, "WIP"):
        entry = _board("x", capabilities={"lighting": bad})
        assert _raises_registry_error(lambda e=entry: _load([e])), (
            f"capability value {bad!r} should be rejected")
    reg = _load([_board("ok", capabilities={"lighting": True, "macros": "wip",
                                            "gamepad": False})])
    p = reg.by_slug("ok")
    assert p.cap("lighting") is True
    assert p.cap("macros") == "wip"
    assert p.cap("gamepad") is False


def test_undeclared_capabilities_default_false():
    """Boards that don't declare the finer-grained flags degrade safely."""
    reg = boards.load_registry()
    p = reg.by_slug("aula-win60he-max")   # legacy-style entry, no new fields
    for flag in ("rapidTrigger", "socd", "macros", "calibration", "gamepad", "deadzone"):
        assert p.cap(flag) is False
    assert p.lighting is None
    assert p.actuation is None
    assert p.deadzone_scope is None
    assert p.product_strings == ()


def test_win60_capabilities():
    """Board A: everything hardware-verified is true; macros stays 'wip' (SOURCE-ONLY)."""
    p = boards.load_registry().by_slug("aula-win60-he")
    for flag in ("lighting", "actuation", "perKeyRgb", "rapidTrigger",
                 "socd", "deadzone", "calibration", "gamepad"):
        assert p.cap(flag) is True, f"win60 {flag} should be True"
    assert p.cap("macros") == "wip"
    assert p.deadzone_scope == "per-key"


def test_mini60pro_capabilities():
    """Board B: hardware/capture-verified flags true; SOURCE-ONLY stays 'wip';
    board-side gamepad has no evidence in the HFD SDK -> false.

    `macros` moved 'wip' -> True on 2026-07-21: a macro composed by OUR encoder
    (not a captured vendor replay) round-tripped on the physical board via
    0x25 write / 0x15 read, and the 0x22 key-table binding path was verified
    separately. The flag had lagged the verification, which left the driver
    implementing macros while the gate still claimed SOURCE-ONLY — a
    cross-board hardware sweep caught the disagreement (list_macros returned
    instead of raising UnsupportedFeature).
    """
    p = boards.load_registry().by_slug("aula-mini60he-pro")
    for flag in ("lighting", "actuation", "perKeyRgb", "rapidTrigger", "deadzone", "macros"):
        assert p.cap(flag) is True, f"mini60pro {flag} should be True"
    for flag in ("socd", "calibration"):
        assert p.cap(flag) == "wip", f"mini60pro {flag} is SOURCE-ONLY -> 'wip'"
    assert p.cap("gamepad") is False
    assert p.deadzone_scope == "global", (
        "MINI 60 HE PRO dead zones live in the global 0x11/0x21 table — "
        "a per-key dead-zone UI cannot work on this board")


# ---------------------------------------------------------------- new: lighting blocks
def test_win60_lighting_table():
    """Board A keeps its own firmware mode table (FW_MODES moved verbatim)."""
    lt = boards.load_registry().by_slug("aula-win60-he").lighting
    assert lt is not None
    assert lt["brightnessMax"] == 4 and lt["speedMax"] == 4
    assert lt["hostEngine"] is True
    assert lt["customModeByte"] == 10
    assert lt["modeListSource"] == "hybrid"           # firmware answers readLightList
    assert lt["modeQuery"] == {"module": "protocol",
                               "build": "build_read_light_list",
                               "parse": "parse_light_list"}
    by_id = {m["id"]: m for m in lt["modes"]}
    expected_bytes = {"static": 0, "breath": 1, "wave": 2, "neon": 3, "radar": 4,
                      "reactive": 6, "cross": 7, "ripple": 8, "twinkle": 9,
                      "custom": 10, "fireworks": 11, "frenzy": 11, "speedres": 12,
                      "autorip": 14, "striation": 15, "aurora": 16}
    assert {k: v["byte"] for k, v in by_id.items()} == expected_bytes
    assert by_id["static"]["speed"] is False and by_id["custom"]["speed"] is False
    assert by_id["wave"]["direction"] == "all"
    assert by_id["radar"]["direction"] == "rotate"
    assert by_id["breath"]["bg"] is True and by_id["breath"]["fullColor"] is True


def test_mini60pro_lighting_table():
    """Board B declares its OWN 20 firmware modes (0x23) — not the Win60 list."""
    lt = boards.load_registry().by_slug("aula-mini60he-pro").lighting
    assert lt is not None
    assert lt["brightnessMax"] == 5 and lt["speedMax"] == 5, \
        "board B scales are 0..5 — clamping to the Win60's 4 loses top brightness"
    assert lt["brightnessMin"] == 0 and lt["speedMin"] == 0
    assert lt["offModeByte"] == 0
    assert lt["customModeByte"] == 20
    assert lt["hostEngine"] is True, (
        "host engine enabled 2026-07-20: the 0x32 live stream (NOT the "
        "persistent 0x24 table) is HARDWARE-VERIFIED at 27.7 fps sustained")
    assert lt["modeListSource"] == "static", "HFD SDK has no firmware mode-list query"
    modes = lt["modes"]
    assert len(modes) == 20
    assert [m["byte"] for m in modes] == list(range(1, 21))
    by_byte = {m["byte"]: m for m in modes}
    # vendor i18n English names
    assert by_byte[1]["name"] == "Static"
    assert by_byte[4]["name"] == "Starry Sky"
    assert by_byte[12]["name"] == "Twisting Path"
    assert by_byte[18]["name"] == "Gentle Rain"
    # direction only meaningful for modes 10, 11, 12, 16, 18
    assert {b for b, m in by_byte.items() if m["direction"]} == {10, 11, 12, 16, 18}
    # speed ignored for modes 1 (static) and 20 (custom)
    assert {b for b, m in by_byte.items() if not m["speed"]} == {1, 20}
    # forced-random-color modes (drivers derive 0x23 byte[16] colorMode = 1
    # from this flag): 6 and 8 are SOURCE-ONLY from the vendor's
    # lightDisabled(); 15/17/18/19 were added 2026-07-20 from the wireless
    # capture (CONFIRMED-BY-CAPTURE (transcribed), WIRELESS_DONGLE_FINDINGS
    # .md: multicolour modes 8/15/17/18/19 send colorMode 1, fixed-colour
    # modes 1/2/4/7 send 0 — mode 8 doubly confirmed).
    assert {b for b, m in by_byte.items() if not m["color"]} == {6, 8, 15, 17, 18, 19}


def test_lighting_block_fail_closed():
    """A malformed lighting block must reject the whole registry."""
    good_modes = [{"id": "static", "byte": 1}]
    bad_blocks = [
        {"brightnessMax": 5, "speedMax": 5},                                # no modes
        {"brightnessMax": 5, "speedMax": 5, "modes": []},                   # empty modes
        {"brightnessMax": 0, "speedMax": 5, "modes": good_modes},           # bad max
        {"brightnessMax": 5, "speedMax": 5,
         "modes": [{"id": "a", "byte": 1}, {"id": "a", "byte": 2}]},        # dup id
        {"brightnessMax": 5, "speedMax": 5,
         "modes": [{"id": "a", "byte": 300}]},                              # byte range
        {"brightnessMax": 5, "speedMax": 5,
         "modes": [{"id": "a", "byte": 1, "direction": "diagonal"}]},       # bad direction
        {"brightnessMax": 5, "speedMax": 5, "modes": good_modes,
         "modeListSource": "hybrid"},                                       # hybrid w/o modeQuery
        {"brightnessMax": 5, "speedMax": 5, "modes": good_modes,
         "modeListSource": "telepathy"},                                    # bad source
    ]
    for i, blk in enumerate(bad_blocks):
        entry = _board("x", lighting=blk)
        assert _raises_registry_error(lambda e=entry: _load([e])), (
            f"bad lighting block #{i} should be rejected: {blk}")


def test_lighting_mode_defaults_normalized():
    """Omitted per-mode flags land as full normalized records (safe defaults)."""
    reg = _load([_board("x", lighting={
        "brightnessMax": 5, "speedMax": 5,
        "modes": [{"id": "m", "byte": 3}],
    })])
    lt = reg.by_slug("x").lighting
    assert lt["modeListSource"] == "static"
    assert lt["hostEngine"] is False
    assert lt["brightnessMin"] == 0 and lt["speedMin"] == 0
    m = lt["modes"][0]
    assert m == {"id": "m", "byte": 3, "name": "m", "speed": True,
                 "color": True, "bg": False, "fullColor": False, "direction": False}


# ---------------------------------------------------------------- new: actuation blocks
def test_actuation_block_fail_closed():
    bad_blocks = [
        {"deadzoneScope": "per-board"},                                     # bad scope
        {"travelRange": [3.4, 0.1]},                                        # min > max
        {"rtRange": [0.01]},                                                # not a pair
        {"switches": [{"id": "a"}, {"id": "a"}]},                           # dup switch id
        {"switches": [{"name": "no id"}]},                                  # missing id
        {"switches": [{"id": "a", "code": 999}]},                           # code range
    ]
    for i, blk in enumerate(bad_blocks):
        entry = _board("x", actuation=blk)
        assert _raises_registry_error(lambda e=entry: _load([e])), (
            f"bad actuation block #{i} should be rejected: {blk}")


def test_per_board_actuation_facts():
    reg = boards.load_registry()
    a = reg.by_slug("aula-win60-he").actuation
    assert a["deadzoneScope"] == "per-key"
    assert a["travelRange"] == [0.1, 3.4]
    assert a["rtRange"] == [0.05, 2.0]
    codes = {s["id"]: s["code"] for s in a["switches"]}
    assert codes == {"hm1": 1, "hh1": 2, "cy1": 3, "tc1": 5}   # cmd-37 codes

    b = reg.by_slug("aula-mini60he-pro").actuation
    assert b["deadzoneScope"] == "global"
    assert b["rtRange"] == [0.01, 3.4]
    assert b["deadzoneRange"] == [0.0, 0.5]
    assert b["switches"] == [], "axis ids for board B are not captured yet"


# ---------------------------------------------------------------- new: product strings
def test_duplicate_vid_pid_requires_discriminator():
    """Two boards may share a VID:PID only when discriminated by product string."""
    a = _board("a")
    b = _board("b")
    assert _raises_registry_error(lambda: _load([a, b])), \
        "undiscriminated VID:PID duplicates must be rejected"
    # duplicate product strings across the group are also rejected
    a2 = _board("a", productString="SAME")
    b2 = _board("b", productString="same")     # case-insensitive collision
    assert _raises_registry_error(lambda: _load([a2, b2]))


def test_product_string_discrimination():
    """detect()/by_ids() pick the right sibling by USB product string, and fall
    back to the undiscriminated entry when the string is absent or unknown."""
    win60 = _board("win60-like")                                   # fallback entry
    win68 = _board("win68-like", productString=["SI2828HEARGB", "SI2828KZHEARGB"])
    reg = _load([win60, win68])

    assert reg.by_ids(0x1111, 0x2222).slug == "win60-like"          # bare lookup unchanged
    assert reg.by_ids(0x1111, 0x2222, "SI2828HEARGB").slug == "win68-like"
    assert reg.by_ids(0x1111, 0x2222, " si2828kzheargb ").slug == "win68-like"  # normalized
    assert reg.by_ids(0x1111, 0x2222, "TOTALLY-UNKNOWN").slug == "win60-like"   # fallback

    dev = {"vendor_id": 0x1111, "product_id": 0x2222}
    assert reg.detect(enumerate_fn=lambda: [dict(dev, product_string="SI2828HEARGB")]
                      ).slug == "win68-like"
    assert reg.detect(enumerate_fn=lambda: [dict(dev)]).slug == "win60-like"
    assert reg.detect(enumerate_fn=lambda: [dict(dev, product_string="???")]
                      ).slug == "win60-like"


def test_win60_claims_its_product_strings():
    """The real registry marks the Win60 HE with its two SI2825 product strings
    and keeps it as the fallback for the five-way 2E3C:C365 collision."""
    reg = boards.load_registry()
    p = reg.by_slug("aula-win60-he")
    # "WIN 60 HE" is the string the PHYSICAL board reports (read from
    # hid.enumerate() 2026-07-20). The SI2825* values are the vendor's internal
    # model codes from device.json, kept for documentation — they were wrongly
    # assumed to be USB product strings when the discriminator was first built.
    assert set(p.product_strings) == {"WIN 60 HE", "SI2825HEARGB", "SI2825KZHEARGB"}
    assert reg.by_ids(0x2E3C, 0xC365, "WIN 60 HE").slug == "aula-win60-he"
    assert reg.by_ids(0x2E3C, 0xC365).slug == "aula-win60-he"
    assert reg.by_ids(0x2E3C, 0xC365, "SI2825KZHEARGB").slug == "aula-win60-he"
    # WIN 68 HE product strings now route to their own discriminated entry;
    # an unknown string still falls back to the win60 entry
    assert reg.by_ids(0x2E3C, 0xC365, "SI2828HEARGB").slug == "aula-win68-he"
    assert reg.by_ids(0x2E3C, 0xC365, "NO-SUCH-BOARD").slug == "aula-win60-he"


def test_c365_siblings_discriminated():
    """The 2E3C:C365 siblings (WIN 68 HE, KP-TE153) each get their OWN layout —
    the whole point of the discriminator: R-Shift sits at index 100 on the 60%
    board but 101 on the 68/69-key boards, so driving a sibling with the Win60
    keymap would land actuation writes on the wrong key."""
    reg = boards.load_registry()

    win68 = reg.by_slug("aula-win68-he")
    assert win68 is not None and (win68.vid, win68.pid) == (0x2E3C, 0xC365)
    # "WIN 68 HE" is ASSUMED by analogy with the verified Win60 string; no real
    # WIN 68 HE has been read. An unrecognised string still falls back to the
    # win60 entry, i.e. today's behaviour.
    assert set(win68.product_strings) == {"WIN 68 HE", "SI2828HEARGB", "SI2828KZHEARGB"}
    te153 = reg.by_slug("aula-kp-te153")
    assert te153 is not None and (te153.vid, te153.pid) == (0x2E3C, 0xC365)
    assert set(te153.product_strings) == {"SI2851UKKZHEARGB"}

    assert reg.by_ids(0x2E3C, 0xC365, "SI2828KZHEARGB").slug == "aula-win68-he"
    assert reg.by_ids(0x2E3C, 0xC365, "SI2851UKKZHEARGB").slug == "aula-kp-te153"

    def rshift_index(profile):
        with open(profile.keymap, encoding="utf-8") as f:
            keys = json.load(f)["keys"]
        return next(int(k["index"]) for k in keys if k["name"] == "R-Shift")

    assert rshift_index(reg.by_slug("aula-win60-he")) == 100
    assert rshift_index(win68) == 101
    assert rshift_index(te153) == 101

    # Capability guardrails from the drivability audit (see the registry _notes):
    # firmware-feature-bit-gated flags stay 'wip' until the bits are read from
    # real hardware, and SOCD on the UK ISO board stays 'wip' because of the
    # vendor's type!='us' PRCS hidCode remap (0x31 -> 0x32).
    for p in (win68, te153):
        assert p.cap("deadzone") == "wip", f"{p.slug} deadzone needs the isDeadBand bit"
        assert p.cap("gamepad") == "wip", f"{p.slug} gamepad needs the isGamePad bit"
        assert p.cap("macros") == "wip"
        assert p.cap("lighting") is True and p.cap("actuation") is True
    assert win68.cap("socd") is True
    assert te153.cap("socd") == "wip", "KP-TE153 is UK ISO — PRCS hidCodes unverified"


# ------------------------------------------- new: offerInUi (unsupported-board gating)
def _raw_registry():
    with open(boards.REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _boards_json():
    with open(os.path.join(ROOT, "data", "boards.json"), encoding="utf-8") as f:
        return json.load(f)


def test_offer_in_ui_declared_on_every_board():
    """The flag is DATA, not inference. Every registry entry states it outright
    so no UI site has to re-derive "is this board real yet?" from
    status/protocol/capabilities — which is exactly how the same board ends up
    offered on one screen and hidden on another."""
    for b in _raw_registry()["boards"]:
        assert isinstance(b.get("offerInUi"), bool), (
            f"{b['slug']} must declare offerInUi explicitly (true|false)")


def test_offer_in_ui_matches_evidence():
    """offerInUi is true exactly when the board is drivable AND at least one
    capability is proven true. A board whose every capability is false or 'wip'
    (SOURCE-ONLY) has nothing working to offer, so it is identified but never
    advertised — e.g. aula-mini60he-max, whose protocol_sonix decode has never
    been proven on hardware."""
    for p in boards.load_registry().profiles:
        has_proven = any(v is True for v in p.capabilities.values())
        expected = bool(p.drivable and has_proven)
        assert p.offered is expected, (
            f"{p.slug}: offerInUi={p.offered} but drivable={p.drivable}, "
            f"proven capabilities={has_proven}")


def test_unsupported_boards_are_never_offered():
    """The actual user-facing guarantee: nothing without a wired protocol may be
    offered, and the identity-only entries stay in the registry (Aether must
    still be able to NAME the hardware in front of it — that is why they are
    flagged rather than deleted)."""
    reg = boards.load_registry()
    offered = {p.slug for p in reg.profiles if p.offered}
    assert offered == {"aula-win60-he", "aula-win68-he", "aula-kp-te153",
                       "aula-mini60he-pro", "aula-mini60he-pro-24g",
                       "aula-win60he-pro"}
    for p in reg.profiles:
        if not p.drivable:
            assert p.offered is False, f"{p.slug} has no protocol but is offered"
        # identity survives regardless of the flag
        assert os.path.exists(p.keymap)
        assert reg.by_ids(p.vid, p.pid) is not None


def test_offer_in_ui_defaults_and_validated():
    """Undeclared -> falls back to `drivable` (old registries/test fixtures are
    unchanged). Non-boolean values fail the registry closed."""
    reg = _load([_board("plain")])                       # protocol None
    assert reg.by_slug("plain").offer_in_ui is None
    assert reg.by_slug("plain").offered is False
    reg = _load([_board("drv", protocol="protocol")])
    assert reg.by_slug("drv").offered is True
    reg = _load([_board("hidden", protocol="protocol", offerInUi=False)])
    assert reg.by_slug("hidden").drivable and reg.by_slug("hidden").offered is False
    for bad in ("true", 1, 0, "yes"):
        entry = _board("x", offerInUi=bad)
        assert _raises_registry_error(lambda e=entry: _load([e])), (
            f"offerInUi {bad!r} should be rejected")


def test_boards_json_tracks_the_registry():
    """data/boards.json (the README lists) may not drift from the registry: the
    supported table is exactly the offered boards, and every remaining registry
    entry appears in the identify-only 'recognized' list — so a board can never
    silently vanish from the docs, only move between the two lists."""
    reg = boards.load_registry()
    data = _boards_json()
    supported = [b["slug"] for b in data["boards"]]
    recognized = [b["slug"] for b in data["recognized"]]
    assert len(supported) == len(set(supported))
    assert len(recognized) == len(set(recognized))
    assert not (set(supported) & set(recognized))
    assert set(supported) == {p.slug for p in reg.profiles if p.offered}
    assert set(recognized) == {p.slug for p in reg.profiles if not p.offered}


def test_boards_json_never_overclaims():
    """A ✅ in the README table may never claim more than the registry does."""
    reg = boards.load_registry()
    for b in _boards_json()["boards"]:
        p = reg.by_slug(b["slug"])
        assert p is not None, f"boards.json slug {b['slug']} not in the registry"
        for cell in ("lighting", "actuation"):
            if b[cell] is True:
                assert p.cap(cell) is True, (
                    f"{b['slug']}: README claims {cell} works but the registry "
                    f"says {p.cap(cell)!r}")


def test_readme_boards_block_in_sync():
    """The rendered block (table + identify-only paragraph) is what README holds."""
    import gen_boards_table
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        readme = f.read()
    assert gen_boards_table.build_block() in readme, (
        "README boards block is stale — run: python tools/gen_boards_table.py --write")


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
