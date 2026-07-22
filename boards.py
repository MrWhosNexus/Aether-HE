"""boards.py — board registry + connected-board detection.

Aether began as a controller for a single keyboard (the Aula Win60 HE). This
module turns that into a data-driven, multi-board system: `data/board_registry.json`
lists every keyboard the app can identify, and at connect time we enumerate the
attached HID devices and match one by USB VID/PID (plus an optional product-string
discriminator when several distinct keyboards ship with the same VID:PID).

A `BoardProfile` carries everything the rest of the app needs to talk to a board:
  * identity        — vid / pid (for HID enumeration + interface selection), and
                      optional `productString` value(s): the USB product strings
                      that positively identify this board when the VID:PID is
                      shared by several models (e.g. five boards share 2E3C:C365)
  * usage_page      — the vendor "config" HID collection to open (None -> fall back)
  * keymap          — path to the board's layout JSON (device_state.KeyMap)
  * protocol        — name of the packet-builder module ("protocol",
                      "protocol_sonix", ...) or None when not yet decoded
  * capabilities    — feature flags, each True | False | "wip". Core three are
                      lighting / actuation / perKeyRgb; finer-grained flags
                      (rapidTrigger, socd, macros, calibration, gamepad,
                      deadzone) default to False when a board doesn't declare
                      them, so old registry entries keep working unchanged.
  * lighting        — OPTIONAL per-board effect table + UI scales: the firmware
                      mode list (id/byte/name + per-mode control rules), slider
                      maxima (brightnessMax/speedMax), off/custom mode bytes,
                      whether the host per-key effects engine may run
                      (hostEngine), and how the mode list is sourced
                      (modeListSource: "static" = table below is the only truth;
                      "hybrid"/"firmware" = the firmware can also be queried via
                      the builders named in modeQuery — e.g. the Win60's
                      readLightList). None when the board doesn't declare one.
  * offer_in_ui     — OPTIONAL explicit "may the UI OFFER this board?" flag
                      (registry key `offerInUi`). None when the entry doesn't
                      declare it; read it through the resolved `offered`
                      property, which falls back to `drivable`. This gates
                      ADVERTISING only (board pickers, the README support
                      table) — never identification: detection, keymap loading
                      and the "recognised but not drivable yet" explanation
                      deliberately ignore it, because a board Aether cannot
                      name is worse than one it can name but not drive.
  * actuation       — OPTIONAL per-board actuation facts: deadzoneScope
                      ("per-key" | "global" — a board whose dead zones live in a
                      global config table must NOT get a per-key dead-zone UI),
                      travel/RT/dead-zone ranges in mm, and the board's
                      switch/axis profile list. None when not declared.

The registry is validated on load (fail-closed): VID/PID must parse, slugs must
be unique, the named `default` must exist, capability values must be
True/False/"wip", and the lighting/actuation blocks must be well-formed when
present. Duplicate VID:PID pairs are allowed ONLY when discriminated by product
strings: at most one entry per (vid, pid) may omit `productString` (it becomes
the fallback match), and all declared product strings within the pair must be
unique. A board whose `protocol` is None is still useful — its layout and
identity load, so the UI can draw it; only the driving commands are gated off
until its protocol lands.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(HERE, "data", "board_registry.json")

CAP_WIP = "wip"                                   # capability decoded from source only — not yet proven
_MODE_LIST_SOURCES = ("static", "firmware", "hybrid")
_DEADZONE_SCOPES = ("per-key", "global")
# Direction-control kinds a lighting mode may expose. Booleans are also allowed:
# False = no direction control, True = simple 0/1 direction byte (HFD boards).
_DIRECTION_KINDS = ("lr", "ud", "all", "rotate", "gather")


class BoardRegistryError(ValueError):
    """Raised when the board registry is malformed (fail-closed)."""


def _parse_id(v, what):
    """Parse a VID/PID from a hex string ('0x0C45' / '0C45') or int. Fail-closed."""
    if isinstance(v, bool):
        raise BoardRegistryError(f"{what} must be a hex string or int, got bool")
    if isinstance(v, int):
        n = v
    elif isinstance(v, str):
        try:
            n = int(v, 16)
        except ValueError as e:
            raise BoardRegistryError(f"{what} {v!r} is not valid hex") from e
    else:
        raise BoardRegistryError(f"{what} must be a hex string or int, got {type(v).__name__}")
    if not (0 <= n <= 0xFFFF):
        raise BoardRegistryError(f"{what} {n:#06x} out of range 0..0xFFFF")
    return n


def _norm_product(s):
    """Normalize a USB product string for matching (strip + casefold)."""
    return (s or "").strip().casefold()


def _int_field(what, v, lo, hi):
    """Validate an int field (bools are NOT ints here). Fail-closed."""
    if isinstance(v, bool) or not isinstance(v, int):
        raise BoardRegistryError(f"{what} must be an int, got {v!r}")
    if not (lo <= v <= hi):
        raise BoardRegistryError(f"{what} = {v} out of range {lo}..{hi}")
    return v


def _bool_field(what, v):
    if not isinstance(v, bool):
        raise BoardRegistryError(f"{what} must be a bool, got {v!r}")
    return v


def _str_field(what, v):
    if not isinstance(v, str) or not v:
        raise BoardRegistryError(f"{what} must be a non-empty string, got {v!r}")
    return v


def _validate_capabilities(slug, caps):
    """Capability values must be exactly True, False or 'wip' (fail-closed).

    'wip' marks a capability whose protocol is decoded from vendor source only
    (SOURCE-ONLY) — never proven on hardware or in a capture. UI treats it as
    'coming, but do not drive'.
    """
    if caps is None:
        return {}
    if not isinstance(caps, dict):
        raise BoardRegistryError(f"{slug}.capabilities must be an object")
    out = {}
    for k, v in caps.items():
        _str_field(f"{slug}.capabilities key", k)
        if not (v is True or v is False or v == CAP_WIP):
            raise BoardRegistryError(
                f"{slug}.capabilities[{k!r}] must be true, false or 'wip', got {v!r}")
        out[k] = v
    return out


def _parse_product_strings(slug, v):
    """Optional 'productString': a string or list of strings. () when absent."""
    if v in (None, ""):
        return ()
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        raise BoardRegistryError(f"{slug}.productString must be a string or list of strings")
    out = []
    for s in v:
        _str_field(f"{slug}.productString entry", s)
        out.append(s)
    if len({_norm_product(s) for s in out}) != len(out):
        raise BoardRegistryError(f"{slug}.productString has duplicate entries")
    return tuple(out)


def _validate_mode(slug, i, m):
    """One lighting-mode row -> normalized dict with all control flags filled in."""
    if not isinstance(m, dict):
        raise BoardRegistryError(f"{slug}.lighting.modes[{i}] must be an object")
    mid = _str_field(f"{slug}.lighting.modes[{i}].id", m.get("id"))
    out = {
        "id": mid,
        "byte": _int_field(f"{slug}.lighting.modes[{i}].byte", m.get("byte"), 0, 255),
        "name": m.get("name", mid),
    }
    if not isinstance(out["name"], str) or not out["name"]:
        raise BoardRegistryError(f"{slug}.lighting.modes[{i}].name must be a non-empty string")
    for key, dflt in (("speed", True), ("color", True), ("bg", False), ("fullColor", False)):
        v = m.get(key, dflt)
        out[key] = _bool_field(f"{slug}.lighting.modes[{i}].{key}", v)
    d = m.get("direction", False)
    if not (isinstance(d, bool) or d in _DIRECTION_KINDS):
        raise BoardRegistryError(
            f"{slug}.lighting.modes[{i}].direction must be a bool or one of "
            f"{_DIRECTION_KINDS}, got {d!r}")
    out["direction"] = d
    return out


def _validate_lighting(slug, d):
    """Validate + normalize the optional per-board 'lighting' block. None passes through."""
    if d is None:
        return None
    if not isinstance(d, dict):
        raise BoardRegistryError(f"{slug}.lighting must be an object")
    out = {}
    out["brightnessMax"] = _int_field(f"{slug}.lighting.brightnessMax", d.get("brightnessMax"), 1, 255)
    out["speedMax"] = _int_field(f"{slug}.lighting.speedMax", d.get("speedMax"), 1, 255)
    out["brightnessMin"] = _int_field(f"{slug}.lighting.brightnessMin",
                                      d.get("brightnessMin", 0), 0, out["brightnessMax"])
    out["speedMin"] = _int_field(f"{slug}.lighting.speedMin",
                                 d.get("speedMin", 0), 0, out["speedMax"])
    src = d.get("modeListSource", "static")
    if src not in _MODE_LIST_SOURCES:
        raise BoardRegistryError(
            f"{slug}.lighting.modeListSource must be one of {_MODE_LIST_SOURCES}, got {src!r}")
    out["modeListSource"] = src
    mq = d.get("modeQuery")
    if src != "static" and mq is None:
        raise BoardRegistryError(
            f"{slug}.lighting.modeListSource {src!r} requires a modeQuery block "
            f"(module/build/parse names for the firmware mode-list command)")
    if mq is not None:
        if not isinstance(mq, dict):
            raise BoardRegistryError(f"{slug}.lighting.modeQuery must be an object")
        out["modeQuery"] = {k: _str_field(f"{slug}.lighting.modeQuery.{k}", mq.get(k))
                            for k in ("module", "build", "parse")}
    for key in ("offModeByte", "customModeByte"):
        if d.get(key) is not None:
            out[key] = _int_field(f"{slug}.lighting.{key}", d.get(key), 0, 255)
    out["hostEngine"] = _bool_field(f"{slug}.lighting.hostEngine", d.get("hostEngine", False))
    # preferFirmwareEffects: drive every effect that HAS a firmware mode byte on
    # the board itself (cmd-7), exactly as the vendor web app's setLightValue
    # does — the board animates natively. Only effects with no firmware
    # equivalent fall through to the host per-key engine. Defaults False so a
    # board without this flag keeps the host-engine-first behaviour untouched.
    out["preferFirmwareEffects"] = _bool_field(
        f"{slug}.lighting.preferFirmwareEffects", d.get("preferFirmwareEffects", False))
    modes = d.get("modes")
    if not isinstance(modes, list) or not modes:
        raise BoardRegistryError(f"{slug}.lighting.modes must be a non-empty array")
    out["modes"] = [_validate_mode(slug, i, m) for i, m in enumerate(modes)]
    ids = [m["id"] for m in out["modes"]]
    if len(ids) != len(set(ids)):
        raise BoardRegistryError(f"{slug}.lighting.modes has duplicate ids")
    # NOTE: mode BYTES may repeat (the Win60 host-engine alias 'frenzy' shares
    # firmware byte 11 with 'fireworks') — only ids must be unique.
    return out


def _validate_range(slug, key, v):
    """[lo, hi] pair of non-negative numbers, lo <= hi."""
    if (not isinstance(v, (list, tuple)) or len(v) != 2
            or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in v)):
        raise BoardRegistryError(f"{slug}.actuation.{key} must be a [min, max] number pair")
    lo, hi = float(v[0]), float(v[1])
    if lo < 0 or lo > hi:
        raise BoardRegistryError(f"{slug}.actuation.{key} [{lo}, {hi}] must satisfy 0 <= min <= max")
    return [lo, hi]


def _validate_actuation(slug, d):
    """Validate the optional per-board 'actuation' block. None passes through."""
    if d is None:
        return None
    if not isinstance(d, dict):
        raise BoardRegistryError(f"{slug}.actuation must be an object")
    out = {}
    scope = d.get("deadzoneScope")
    if scope is not None:
        if scope not in _DEADZONE_SCOPES:
            raise BoardRegistryError(
                f"{slug}.actuation.deadzoneScope must be one of {_DEADZONE_SCOPES}, got {scope!r}")
        out["deadzoneScope"] = scope
    for key in ("travelRange", "rtRange", "deadzoneRange"):
        if d.get(key) is not None:
            out[key] = _validate_range(slug, key, d.get(key))
    sw = d.get("switches")
    if sw is not None:
        if not isinstance(sw, list):
            raise BoardRegistryError(f"{slug}.actuation.switches must be an array")
        seen = set()
        switches = []
        for i, s in enumerate(sw):
            if not isinstance(s, dict):
                raise BoardRegistryError(f"{slug}.actuation.switches[{i}] must be an object")
            sid = _str_field(f"{slug}.actuation.switches[{i}].id", s.get("id"))
            if sid in seen:
                raise BoardRegistryError(f"{slug}.actuation.switches has duplicate id {sid!r}")
            seen.add(sid)
            if s.get("code") is not None:
                _int_field(f"{slug}.actuation.switches[{i}].code", s.get("code"), 0, 255)
            switches.append(dict(s))   # keep display metadata (maker, travel, ...) as-is
        out["switches"] = switches
    return out


@dataclass(frozen=True)
class BoardProfile:
    slug: str
    name: str
    vid: int
    pid: int
    form_factor: str
    usage_page: Optional[int]
    keymap: str            # absolute path
    protocol: Optional[str]
    capabilities: dict = field(default_factory=dict)
    status: str = "planned"
    issues: tuple = ()
    product_strings: tuple = ()          # optional USB product-string discriminators
    lighting: Optional[dict] = None      # per-board effect table + UI scales (validated)
    actuation: Optional[dict] = None     # per-board actuation facts (validated)
    offer_in_ui: Optional[bool] = None   # raw `offerInUi` declaration (None = undeclared)

    @property
    def vid_pid(self):
        return f"{self.vid:04X}:{self.pid:04X}"

    def cap(self, name):
        """Capability value for `name`: True | False | 'wip' (default False)."""
        return self.capabilities.get(name, False)

    @property
    def drivable(self):
        """True once a protocol module is wired (lighting/actuation possible)."""
        return self.protocol is not None

    @property
    def offered(self):
        """May the UI OFFER this board to the user? (resolved `offerInUi`)

        True  -> the board may appear in board pickers / "supported boards"
                 lists and be presented as something you can select and drive.
        False -> the board stays in the registry and is still detected, named
                 and drawn — it is simply never advertised as an option.

        The flag is DATA, not per-call-site inference: every UI surface reads
        this one field instead of each re-deriving "is this board real yet?"
        from status/protocol/capabilities and getting a different answer.
        Undeclared entries fall back to `drivable`, so registries written
        before the flag existed (and the test fixtures) behave as they did.

        NOTE: this is never a gate on identification. `detect()`, `by_ids()`,
        keymap loading and the connected-board badge all ignore it on purpose.
        """
        return self.drivable if self.offer_in_ui is None else self.offer_in_ui

    @property
    def deadzone_scope(self):
        """'per-key' | 'global' | None (unknown / board didn't declare it).

        Callers building dead-zone UI must treat 'global' as whole-board only —
        boards like the MINI 60 HE PRO store dead zones in a global config
        table, so a per-key dead-zone control cannot work there.
        """
        return (self.actuation or {}).get("deadzoneScope")

    def matches_product(self, product_string):
        """True when `product_string` matches one of this board's discriminators."""
        if not self.product_strings:
            return False
        s = _norm_product(product_string)
        return bool(s) and s in {_norm_product(p) for p in self.product_strings}


def _to_profile(b):
    slug = b.get("slug")
    if not slug or not isinstance(slug, str):
        raise BoardRegistryError(f"board missing string 'slug': {b!r}")
    keymap = b.get("keymap")
    if not keymap or not isinstance(keymap, str):
        raise BoardRegistryError(f"board {slug!r} missing 'keymap' path")
    up = b.get("usage_page")
    usage_page = _parse_id(up, f"{slug}.usage_page") if up not in (None, "") else None
    offer = b.get("offerInUi")
    if offer is not None:
        _bool_field(f"{slug}.offerInUi", offer)
    return BoardProfile(
        slug=slug,
        name=b.get("name", slug),
        vid=_parse_id(b.get("vid"), f"{slug}.vid"),
        pid=_parse_id(b.get("pid"), f"{slug}.pid"),
        form_factor=b.get("formFactor", "?"),
        usage_page=usage_page,
        keymap=keymap if os.path.isabs(keymap) else os.path.join(HERE, keymap),
        protocol=b.get("protocol") or None,
        capabilities=_validate_capabilities(slug, b.get("capabilities")),
        status=b.get("status", "planned"),
        issues=tuple(b.get("issues") or ()),
        product_strings=_parse_product_strings(slug, b.get("productString")),
        lighting=_validate_lighting(slug, b.get("lighting")),
        actuation=_validate_actuation(slug, b.get("actuation")),
        offer_in_ui=offer,
    )


class BoardRegistry:
    def __init__(self, profiles, default_slug):
        self.profiles = list(profiles)
        self._by_slug = {p.slug: p for p in self.profiles}
        # Group by (vid, pid): several *different* keyboards can share one
        # VID:PID (five boards ship as 2E3C:C365) — legal only when they are
        # discriminated by USB product string.
        self._groups = {}
        for p in self.profiles:
            self._groups.setdefault((p.vid, p.pid), []).append(p)
        self._by_ids = {}
        for key, group in self._groups.items():
            undisc = [p for p in group if not p.product_strings]
            if len(group) > 1:
                if len(undisc) > 1:
                    raise BoardRegistryError(
                        f"duplicate VID:PID {group[0].vid_pid}: more than one entry without "
                        f"a productString discriminator "
                        f"({', '.join(p.slug for p in undisc)})")
                seen = {}
                for p in group:
                    for s in p.product_strings:
                        n = _norm_product(s)
                        if n in seen:
                            raise BoardRegistryError(
                                f"VID:PID {p.vid_pid}: product string {s!r} claimed by both "
                                f"{seen[n]!r} and {p.slug!r}")
                        seen[n] = p.slug
            # Fallback profile for a bare (vid, pid) lookup: the entry without a
            # discriminator if there is one, else the first in registry order.
            self._by_ids[key] = undisc[0] if undisc else group[0]
        if default_slug not in self._by_slug:
            raise BoardRegistryError(f"default board {default_slug!r} not in registry")
        self.default_slug = default_slug

    @property
    def default(self):
        return self._by_slug[self.default_slug]

    def by_slug(self, slug):
        return self._by_slug.get(slug)

    def by_ids(self, vid, pid, product_string=None):
        """Profile for a VID:PID, optionally discriminated by USB product string.

        With `product_string`, an exact (case-insensitive) match against an
        entry's declared productString wins; otherwise the pair's fallback entry
        is returned — so callers that only know VID:PID keep working unchanged.
        """
        group = self._groups.get((vid, pid))
        if not group:
            return None
        if product_string:
            for p in group:
                if p.matches_product(product_string):
                    return p
        return self._by_ids[(vid, pid)]

    def detect(self, enumerate_fn=None):
        """Return the BoardProfile for the first connected, registered board.

        `enumerate_fn` defaults to hid.enumerate() (injectable for tests). Returns
        None when no registered board is plugged in — callers fall back to
        `self.default` so behaviour is unchanged when detection isn't possible.
        When several registered boards share the device's VID:PID, the USB
        product string picks the right one (falling back to the pair's
        undiscriminated entry when the string is absent or unknown).
        """
        if enumerate_fn is None:
            try:
                import hid
                enumerate_fn = hid.enumerate
            except Exception as e:  # hidapi missing -> can't detect
                log.warning("hid.enumerate unavailable, cannot detect board: %s", e)
                return None
        try:
            devices = enumerate_fn()
        except Exception as e:
            log.warning("HID enumeration failed: %s", e)
            return None
        for d in devices or ():
            key = (d.get("vendor_id"), d.get("product_id"))
            group = self._groups.get(key)
            if not group:
                continue
            ps = d.get("product_string")
            p = self.by_ids(key[0], key[1], ps)
            if len(group) > 1:
                if p.matches_product(ps):
                    log.info("Detected board %s (%s, product %r)", p.name, p.vid_pid, ps)
                else:
                    log.warning(
                        "VID:PID %s is shared by %d boards; product string %r matched none — "
                        "falling back to %s", p.vid_pid, len(group), ps, p.slug)
            else:
                log.info("Detected board %s (%s)", p.name, p.vid_pid)
            return p
        return None


def load_registry(path=REGISTRY_PATH):
    """Load + validate the board registry. Raises BoardRegistryError on problems."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    boards = data.get("boards")
    if not isinstance(boards, list) or not boards:
        raise BoardRegistryError("registry has no 'boards' array")
    profiles = [_to_profile(b) for b in boards]
    seen_slug = set()
    for p in profiles:
        if p.slug in seen_slug:
            raise BoardRegistryError(f"duplicate slug {p.slug!r}")
        seen_slug.add(p.slug)
    # (vid, pid) collision rules are enforced by BoardRegistry.__init__.
    return BoardRegistry(profiles, data.get("default", profiles[0].slug))
