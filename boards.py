"""boards.py — board registry + connected-board detection.

Aether began as a controller for a single keyboard (the Aula Win60 HE). This
module turns that into a data-driven, multi-board system: `data/board_registry.json`
lists every keyboard the app can identify, and at connect time we enumerate the
attached HID devices and match one by USB VID/PID.

A `BoardProfile` carries everything the rest of the app needs to talk to a board:
  * identity        — vid / pid (for HID enumeration + interface selection)
  * usage_page      — the vendor "config" HID collection to open (None -> fall back)
  * keymap          — path to the board's layout JSON (device_state.KeyMap)
  * protocol        — name of the packet-builder module ("protocol",
                      "protocol_sonix", ...) or None when not yet decoded
  * capabilities    — lighting / actuation / per-key RGB (True | False | "wip")

The registry is validated on load (fail-closed): VID/PID must parse, slugs and
VID:PID pairs must be unique, the named `default` must exist. A board whose
`protocol` is None is still useful — its layout and identity load, so the UI can
draw it; only the driving commands are gated off until its protocol lands.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(HERE, "data", "board_registry.json")


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


def _to_profile(b):
    slug = b.get("slug")
    if not slug or not isinstance(slug, str):
        raise BoardRegistryError(f"board missing string 'slug': {b!r}")
    keymap = b.get("keymap")
    if not keymap or not isinstance(keymap, str):
        raise BoardRegistryError(f"board {slug!r} missing 'keymap' path")
    up = b.get("usage_page")
    usage_page = _parse_id(up, f"{slug}.usage_page") if up not in (None, "") else None
    return BoardProfile(
        slug=slug,
        name=b.get("name", slug),
        vid=_parse_id(b.get("vid"), f"{slug}.vid"),
        pid=_parse_id(b.get("pid"), f"{slug}.pid"),
        form_factor=b.get("formFactor", "?"),
        usage_page=usage_page,
        keymap=keymap if os.path.isabs(keymap) else os.path.join(HERE, keymap),
        protocol=b.get("protocol") or None,
        capabilities=dict(b.get("capabilities") or {}),
        status=b.get("status", "planned"),
        issues=tuple(b.get("issues") or ()),
    )


class BoardRegistry:
    def __init__(self, profiles, default_slug):
        self.profiles = list(profiles)
        self._by_slug = {p.slug: p for p in self.profiles}
        self._by_ids = {(p.vid, p.pid): p for p in self.profiles}
        if default_slug not in self._by_slug:
            raise BoardRegistryError(f"default board {default_slug!r} not in registry")
        self.default_slug = default_slug

    @property
    def default(self):
        return self._by_slug[self.default_slug]

    def by_slug(self, slug):
        return self._by_slug.get(slug)

    def by_ids(self, vid, pid):
        return self._by_ids.get((vid, pid))

    def detect(self, enumerate_fn=None):
        """Return the BoardProfile for the first connected, registered board.

        `enumerate_fn` defaults to hid.enumerate() (injectable for tests). Returns
        None when no registered board is plugged in — callers fall back to
        `self.default` so behaviour is unchanged when detection isn't possible.
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
            if key in self._by_ids:
                p = self._by_ids[key]
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
    seen_slug, seen_ids = set(), set()
    for p in profiles:
        if p.slug in seen_slug:
            raise BoardRegistryError(f"duplicate slug {p.slug!r}")
        if (p.vid, p.pid) in seen_ids:
            raise BoardRegistryError(f"duplicate VID:PID {p.vid_pid}")
        seen_slug.add(p.slug)
        seen_ids.add((p.vid, p.pid))
    return BoardRegistry(profiles, data.get("default", profiles[0].slug))
