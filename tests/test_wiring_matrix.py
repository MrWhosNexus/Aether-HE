"""Cross-board wiring matrix — the regression guard for the whole class of
bug found on 2026-07-21.

Every bug in that audit had the SAME shape: a per-board fact (a registry
mode byte, a dead-zone scope, a switch code) reached the layer that had been
updated and then fell through a hardcoded Win60 assumption in a layer that
had not. Nothing caught it because every existing driver test asserts ONE
board at a time.

This file asserts the product instead: for EACH drivable board profile in
the REAL registry x EACH declared capability, exercise the driver and
require that it either

  * produces frames in THAT BOARD's own protocol framing (never another
    board's — the failure mode drivers/base.py exists to prevent), or
  * raises UnsupportedFeature with zero bytes on the wire.

...plus the three specific invariants the audit found broken:

  * a capability declared ``true`` must actually be reachable (a flag that
    gates nothing is a lie the UI acts on);
  * a capability declared ``false`` must refuse — never a silent no-op;
  * a lighting mode byte the registry declares for a board must reach the
    wire AS THAT BYTE on that board (the "Colorful Cross" -> Custom bug);
  * ``driver.DEADBAND_SCOPE`` must agree with the registry's
    ``actuation.deadzoneScope``, and a global-scope board must actually
    WRITE when nothing is selected (the silent-Apply bug).

No hardware: devices are the same stubs test_drivers.py uses.
"""
import threading

import pytest

import boards
import protocol
import protocol_mini60 as pm
import app_web
from drivers import UnsupportedFeature, NullDriver, get_driver
from drivers import mini60 as mini60_mod

from test_drivers import StubDevice, FakeMiniBoard


# ------------------------------------------------------------- framing ----
# What ONE frame from each protocol module must look like on the wire. The
# whole point of the driver layer is that a board can only ever be sent its
# own shape, so this is asserted on every frame every op emits.
def _is_win60_frame(f, profile):
    return len(f) == protocol.BODY + 1 and f[0] == protocol.REPORT_ID


def _is_mini60_frame(f, profile):
    n = mini60_mod.frame_len_for_profile(profile)
    return len(f) == n + 1 and f[0] == 0x00 and f[1] == pm.MAGIC


FRAME_SHAPE = {
    "protocol": _is_win60_frame,
    "protocol_mini60": _is_mini60_frame,
}


def _registry():
    return boards.load_registry()


def _drivable():
    """Every registered board with a protocol module, as (slug, profile)."""
    return [(p.slug, p) for p in _registry().profiles if p.drivable]


DRIVABLE_SLUGS = [s for s, _ in _drivable()]


def _driver_for(profile):
    """A driver bound to a stub device appropriate for its protocol. The
    MINI stub serves 0x55 replies at the board's OWN frame length so the
    read-modify-write paths complete instead of timing out."""
    if profile.protocol == "protocol_mini60":
        board = FakeMiniBoard(
            frame_len=mini60_mod.frame_len_for_profile(profile))
        dev = StubDevice(reply_fn=board.reply)
    else:
        board = None
        dev = StubDevice()
    return get_driver(profile, dev, threading.Lock()), dev, board


def _first_mode_byte(profile):
    modes = (getattr(profile, "lighting", None) or {}).get("modes") or ()
    for m in modes:
        if isinstance(m, dict) and m.get("byte") is not None:
            return int(m["byte"])
    return 0


# ------------------------------------------------------------- the ops ----
# registry capability name -> a call that exercises it end to end. Keep these
# minimal and side-effect free at the stub level: the assertion is about
# WHICH bytes come out, not about the payload's content.
CAPABILITY_OPS = {
    "lighting":
        lambda d, p: d.set_lighting(_first_mode_byte(p), (255, 0, 0)),
    "perKeyRgb":
        lambda d, p: d.set_per_key_rgb({0: (1, 2, 3)}),
    "actuation":
        lambda d, p: d.set_actuation([0], 0, 1.5),
    "rapidTrigger":
        lambda d, p: d.set_actuation([0], 12, 1.5, 0.2, 0.2),
    "deadzone":
        lambda d, p: d.set_deadband({0: (4, 5)}, top_mm=0.04, bottom_mm=0.05),
    "socd":
        lambda d, p: d.set_socd([]),
    "calibration":
        lambda d, p: d.set_calibration(True),
    "gamepad":
        lambda d, p: d.set_gamepad_mode(True),
    "macros":
        lambda d, p: d.write_macro(0, []),
}

#: Boards whose registry declares a capability ``true`` that their driver
#: cannot actually perform. These are REGISTRY defects (data/board_registry
#: .json is owned elsewhere): the value should be ``"wip"`` until a driver
#: lands, because ``true`` is what the UI advertises as working. The test
#: asserts the discrepancy STILL EXISTS so it fails the moment the registry
#: is fixed (delete the entry then) — and equally if a new board joins the
#: list without anyone noticing.
KNOWN_OVERCLAIMS = {
    # protocol_sayo is decoded but has no driver yet -> NullDriver refuses.
    ("aula-win60he-pro", "lighting"),
}

MATRIX = [(slug, cap) for slug in DRIVABLE_SLUGS for cap in CAPABILITY_OPS]


@pytest.mark.parametrize("slug,cap", MATRIX,
                         ids=[f"{s}-{c}" for s, c in MATRIX])
def test_capability_matrix_right_frames_or_loud_refusal(slug, cap):
    """THE cross-board guard. For this board x this capability the driver
    must either emit frames in this board's own protocol framing, or refuse
    with UnsupportedFeature having written nothing at all."""
    profile = _registry().by_slug(slug)
    declared = profile.cap(cap)
    if declared is False and cap not in profile.capabilities:
        pytest.skip(f"{slug} declares no {cap} capability")
    d, dev, _ = _driver_for(profile)

    refused = None
    try:
        CAPABILITY_OPS[cap](d, profile)
    except UnsupportedFeature as e:
        refused = e
    except (ValueError, RuntimeError, IOError, NotImplementedError) as e:
        # A parameter/precondition rejection is acceptable behaviour, but it
        # must not have left half a board's worth of frames behind.
        assert dev.writes == [], (
            f"{slug}/{cap} raised {e!r} AFTER writing "
            f"{len(dev.writes)} frames — partial board state")
        return

    if refused is not None:
        # Refusals are the safe outcome, but they must be silent on the wire
        # and honest about who refused.
        assert dev.writes == [], (
            f"{slug}/{cap} raised UnsupportedFeature after writing "
            f"{len(dev.writes)} frames")
        assert refused.board == d.name
        assert declared is not True or (slug, cap) in KNOWN_OVERCLAIMS, (
            f"{slug} declares {cap}=true but its driver refuses it — a "
            f"capability flag that gates nothing")
        return

    # It succeeded: the capability must not have been declared FALSE (a
    # false flag that still writes is the silent-wrong-board failure), and
    # every emitted frame must be this board's own shape.
    assert declared is not False, (
        f"{slug} declares {cap}=false but its driver wrote "
        f"{len(dev.writes)} frames")
    assert dev.writes, f"{slug}/{cap} claimed success but wrote nothing"
    shape = FRAME_SHAPE[profile.protocol]
    for f in dev.writes:
        assert shape(f, profile), (
            f"{slug}/{cap} emitted a frame that is not "
            f"{profile.protocol} framing: len={len(f)} head={list(f[:3])}")


@pytest.mark.parametrize("slug,cap", MATRIX,
                         ids=[f"{s}-{c}" for s, c in MATRIX])
def test_capability_true_is_reachable_or_a_known_overclaim(slug, cap):
    """A ``true`` capability must be in the driver's FEATURES set. This is
    the cheap static half of the matrix above — it catches a registry that
    advertises a board feature no driver implements even for ops whose call
    shape this file does not model."""
    profile = _registry().by_slug(slug)
    if profile.cap(cap) is not True:
        return
    d, _, _ = _driver_for(profile)
    feature = {"perKeyRgb": "per_key_rgb", "rapidTrigger": "actuation",
               "deadzone": "deadband", "gamepad": "gamepad_mode"}.get(cap, cap)
    reachable = d.supports(feature)
    if (slug, cap) in KNOWN_OVERCLAIMS:
        assert not reachable, (
            f"{slug}/{cap} is now implemented — drop it from "
            f"KNOWN_OVERCLAIMS (and the registry may stay true)")
    else:
        assert reachable, (
            f"{slug} declares {cap}=true but {type(d).__name__} does not "
            f"implement {feature!r}")


def test_no_drivable_board_is_silently_inert():
    """A board with a protocol module but a NullDriver may exist (a decoded
    protocol whose driver hasn't landed), but it must never ALSO advertise
    capabilities as true — that combination is exactly the lie the audit
    found. Every such pair must be listed in KNOWN_OVERCLAIMS."""
    for slug, profile in _drivable():
        d, _, _ = _driver_for(profile)
        if not isinstance(d, NullDriver):
            continue
        for cap, value in profile.capabilities.items():
            if value is True:
                assert (slug, cap) in KNOWN_OVERCLAIMS, (
                    f"{slug} has no driver but declares {cap}=true")


# ------------------------------------------------- lighting mode bytes ----
LIGHT_BOARDS = [s for s, p in _drivable()
                if ((getattr(p, "lighting", None) or {}).get("modes")
                    and p.cap("lighting") is True)]


def _wire_mode_byte(profile, frames):
    """The mode byte the board actually received, read out of the LAST
    lighting frame in this board's own layout."""
    if profile.protocol == "protocol_mini60":
        # frames carry the 0x00 report id: [0]=id [1]=0xAA [2]=cmd
        light = [f for f in frames if f[2] == pm.CMD_LIGHTING]
        return light[-1][9] if light else None       # report id + frame[8]
    light = [f for f in frames if f[1] == 7]         # Win60 cmd 7
    return light[-1][6] if light else None           # report id + d[5]


@pytest.mark.parametrize("slug", LIGHT_BOARDS)
def test_every_declared_mode_byte_reaches_the_wire_unchanged(slug):
    """THE "Colorful Cross" regression, generalised to every board.

    The UI's light dispatch resolves a mode against THE ACTIVE BOARD's
    registry table and sends that board's OWN byte. So for every byte a
    board declares, the driver must put exactly that byte in the lighting
    frame — no cross-board vocabulary translation may rewrite it. Byte 10 on
    the MINI is `colorful-cross`; the driver used to silently turn it into
    20 (per-key Custom) because 10 is the WIN60's custom slot.
    """
    profile = _registry().by_slug(slug)
    modes = [int(m["byte"]) for m in profile.lighting["modes"]
             if m.get("byte") is not None]
    assert modes, f"{slug} declares an empty mode table"
    for byte in modes:
        d, dev, _ = _driver_for(profile)
        d.set_lighting(byte, (255, 0, 0))
        got = _wire_mode_byte(profile, dev.writes)
        assert got == byte, (
            f"{slug}: registry mode byte {byte} "
            f"({[m['id'] for m in profile.lighting['modes'] if m.get('byte') == byte]}) "
            f"reached the board as {got}")


def test_mini_registry_actually_declares_colorful_cross_at_ten():
    """Pins the fact the regression above depends on — if the registry ever
    moves `colorful-cross` off byte 10 this test says so out loud instead of
    the guard quietly testing nothing."""
    for slug in ("aula-mini60he-pro", "aula-mini60he-pro-24g"):
        modes = {m["id"]: m["byte"]
                 for m in _registry().by_slug(slug).lighting["modes"]}
        assert modes["colorful-cross"] == 10
        assert modes["custom"] == pm.LIGHT_MODE_CUSTOM


# -------------------------------------------------- dead-zone scope ----
@pytest.mark.parametrize("slug", DRIVABLE_SLUGS)
def test_driver_deadband_scope_matches_the_registry(slug):
    """The scope fact must be the SAME fact in the registry and the driver.
    It reached the widget and the driver but fell through the two layers in
    between; step one of never repeating that is asserting they agree."""
    profile = _registry().by_slug(slug)
    scope = profile.deadzone_scope
    if scope is None:
        return
    d, _, _ = _driver_for(profile)
    if isinstance(d, NullDriver):
        return
    assert d.DEADBAND_SCOPE == scope, (
        f"{slug}: registry says deadzoneScope={scope!r} but "
        f"{type(d).__name__}.DEADBAND_SCOPE={d.DEADBAND_SCOPE!r}")


class _KM:
    """Minimal KeyMap stand-in: the dead-zone path only needs code->index
    resolution and the board's key count."""

    def __init__(self, n=61):
        self._n = n

    def indices(self):
        return list(range(self._n))

    def indices_for_codes(self, codes):
        return [int(c) for c in (codes or []) if 0 <= int(c) < self._n]


def _api_for(slug):
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.Lock()
    a.board = _registry().by_slug(slug)
    a.km = _KM()
    a._deadband_state = {}
    d, dev, _ = _driver_for(a.board)
    a.driver = d
    return a, dev


def test_global_scope_board_writes_with_no_selection():
    """THE silent-Apply bug: on a global-scope board the normal case is
    "whole board, nothing selected". The Api used to return {"ok": False,
    "error": "no keys"} and send nothing while the UI flashed a success
    toast. It must WRITE, and say how many keys it covered."""
    a, dev = _api_for("aula-mini60he-pro")
    assert a.driver.DEADBAND_SCOPE == "global"
    r = a.set_deadband_codes([], top_mm=0.04, bottom_mm=0.05)
    assert r["ok"] is True and r["scope"] == "global"
    assert r["keys"] == 61                       # whole board, not 0
    writes = [f for f in dev.writes if f[2] == pm.CMD_CONFIG_WRITE]
    assert writes, "global dead-zone Apply emitted no config write"


def test_per_key_board_still_refuses_an_empty_selection():
    """The Win60 path is untouched: no selection is still an error and
    still puts zero bytes on the wire."""
    a, dev = _api_for("aula-win60-he")
    assert a.driver.DEADBAND_SCOPE == "per-key"
    r = a.set_deadband_codes([], top_mm=0.04, bottom_mm=0.05)
    assert r == {"ok": False, "error": "no keys"}
    assert dev.writes == []
    # ...and a real selection writes exactly as before.
    r2 = a.set_deadband_codes([0, 1], top_mm=0.04, bottom_mm=0.05)
    assert r2["ok"] is True and r2["keys"] == 2 and r2["scope"] == "per-key"
    assert dev.writes


# ------------------------------------------------------ switch codes ----
def test_switch_selection_resolves_registry_ids_and_fails_closed():
    """The registry's per-switch `code` is now READ instead of a hardcoded
    Win60 table with a `|| 1` fallback: an id resolves to that board's own
    code, and anything the board does not declare is refused rather than
    silently becoming HM1."""
    a, dev = _api_for("aula-win60-he")
    switches = {s["id"]: s["code"] for s in a.board.actuation["switches"]}
    assert switches, "the Win60 registry entry lost its switch table"
    for sid, code in switches.items():
        dev.writes.clear()
        r = a.set_switch_codes([0], sid)
        assert r["ok"] is True and r["code"] == code
        assert dev.writes and all(_is_win60_frame(f, a.board)
                                  for f in dev.writes)
    # raw codes the board declares still work (the old call shape)
    assert a.set_switch_codes([0], 1)["code"] == 1
    # ...and everything else fails closed, with nothing on the wire
    dev.writes.clear()
    for bad in ("nope", 4, 200, None):
        r = a.set_switch_codes([0], bad)
        assert r["ok"] is False, f"switch selection {bad!r} was accepted"
    assert dev.writes == []


def test_switch_selection_passes_through_when_board_declares_none():
    """Boards with no declared switch table (and the legacy no-profile
    path) keep the original behaviour byte-for-byte: an int code goes
    straight to the driver."""
    a, dev = _api_for("aula-win68-he")          # switches: []
    assert a.board.actuation["switches"] == []
    r = a.set_switch_codes([0], 3)
    assert r["ok"] is True and r["code"] == 3
    assert all(_is_win60_frame(f, a.board) for f in dev.writes)
