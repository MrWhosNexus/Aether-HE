"""drivers — per-board protocol dispatch (parity plan Task 0 / step 1).

get_driver(profile, device, lock) maps a boards.BoardProfile to its driver
by `profile.protocol` (the registry field naming the packet-builder module):

    "protocol"        -> Win60Driver  (Aula Win60 HE, 2E3C:C365)
    "protocol_mini60" -> Mini60Driver (Aula MINI 60 HE PRO — BOTH transports:
                                       wired 0C45:80A2 at 64-byte frames AND
                                       the 2.4GHz dongle 0C45:FEFE at
                                       32-byte frames; ONE driver, the frame
                                       size comes from the registry frameLen
                                       via drivers.mini60.frame_len_for_profile)
    "protocol_sonix"  -> NullDriver   (module exists, no driver yet — its
                                       frames were FALSIFIED on the 80A2;
                                       safer inert than wrong)
    "protocol_sayo"   -> NullDriver   (lighting decoded; driver is follow-up)
    null / unknown    -> NullDriver   (undecoded boards stay non-drivable)

connected_profiles() is the detection layer's multi-board fix: with several
registered boards attached, BoardRegistry.detect() returns whichever HID
enumeration happens to list first (observed returning different boards on
different runs on a machine with 2E3C:C365 + 0C45:80A2 + the 0C45:FEFE
dongle attached). Here we rank every connected registered board — drivable
before non-drivable, registry order within each group — so a non-drivable
board can never shadow a drivable one, and when BOTH MINI 60 HE PRO
transports are attached the WIRED entry wins (it precedes the dongle in
registry order): the cable is the better link — full host-effects support
(the RF bridge drops 0x32 streams) and the hardware-verified round-trip
history. An explicit Api.select_board(slug) overrides detection entirely.
"""
import logging

from .base import BoardDriver, NullDriver, UnsupportedFeature
from .win60 import Win60Driver
from .mini60 import Mini60Driver

log = logging.getLogger(__name__)

#: registry `protocol` field -> driver class
DRIVER_BY_PROTOCOL = {
    "protocol": Win60Driver,
    "protocol_mini60": Mini60Driver,
}


def get_driver(profile, device, lock=None):
    """Driver instance for `profile` (a boards.BoardProfile) bound to
    `device` (aula_device.AulaDevice) and the Api's write `lock`.

    `profile=None` is the legacy registry-unavailable fallback and yields
    the Win60 driver, matching the app's historical single-board behavior.
    Any board without a mapped driver gets the inert NullDriver: every
    write raises UnsupportedFeature — an undecoded board must NEVER receive
    another board's frames.
    """
    if profile is None:
        return Win60Driver(None, device, lock)
    proto = getattr(profile, "protocol", None)
    cls = DRIVER_BY_PROTOCOL.get(proto)
    if cls is None:
        if proto:
            log.info("no driver implemented for protocol %r (%s) — board is "
                     "inert until one lands", proto, profile.name)
        return NullDriver(profile, device, lock)
    return cls(profile, device, lock)


def connected_profiles(registry, enumerate_fn=None):
    """Every registered board currently attached, best-first: drivable
    boards before non-drivable ones, registry order within each group
    (stable sort). Returns [] when nothing registered is attached or HID
    enumeration is unavailable — callers fall back to registry.default.
    """
    if enumerate_fn is None:
        try:
            import hid
            enumerate_fn = hid.enumerate
        except Exception as e:
            log.warning("hid.enumerate unavailable, cannot detect boards: %s", e)
            return []
    try:
        devices = enumerate_fn() or ()
    except Exception as e:
        log.warning("HID enumeration failed: %s", e)
        return []
    # Resolve each attached device to ONE profile. Several registered boards can
    # share a VID:PID (five different keyboards ship as 2E3C:C365), so matching on
    # the pair alone reports every sibling as "connected" — one physical Win60 was
    # being listed as three boards. registry.by_ids() applies the USB product-string
    # discriminator and falls back to the pair's undiscriminated entry, so a device
    # whose string we don't recognise still resolves exactly as it always did.
    resolved = {}
    for d in devices:
        vid, pid = d.get("vendor_id"), d.get("product_id")
        product = (d.get("product_string") or "").strip()
        try:
            p = registry.by_ids(vid, pid, product or None)
        except Exception:
            p = None
        if p is not None:
            resolved[p.slug] = p
    # keep registry order within each group, drivable boards first
    hits = [p for p in registry.profiles if p.slug in resolved]
    return sorted(hits, key=lambda p: 0 if p.drivable else 1)
