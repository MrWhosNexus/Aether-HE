"""drivers/base.py — the board-neutral driver interface the Api talks to.

Aether's Api (app_web.py) used to call the Win60 packet builders
(protocol.py) directly from every write path, regardless of which board was
actually connected — with an Aula MINI 60 HE PRO plugged in, Win60
report-ID-1 frames went to the MINI's 0xFF68 vendor interface (a completely
different 0xAA-magic protocol) and the firmware echo-looped them while the
UI reported success.

BoardDriver is the seam that fixes that: one object per connected board that
owns *all* protocol traffic. The Api never imports a protocol module again;
it asks the driver, and the driver either performs the operation with the
board's own packet format or raises UnsupportedFeature — loudly, never a
silent no-op, and NEVER by falling through to another board's protocol.

Contract for implementers:
  * Override an operation only when the underlying protocol support is
    verified for that board. Everything left un-overridden raises
    UnsupportedFeature carrying the board name + feature name, which the Api
    converts to {"ok": False, "error": ..., "unsupported": True} for the UI.
  * List each implemented feature name in FEATURES so callers can gate
    without try/except (e.g. the capture path checks "travel_stream" before
    arming a stream).
  * The lock passed in is the Api's outer write lock — hold it exactly the
    way the old inline code did so write interleaving behavior is unchanged.
"""
import logging
import threading

log = logging.getLogger(__name__)


class UnsupportedFeature(Exception):
    """A board's driver cannot perform the requested operation.

    Carries `board` (display name) and `feature` (stable feature key, e.g.
    "lighting", "actuation", "host_effects") so callers can gate UI per
    feature. The message is user-presentable: "<feature> is not supported on
    <board>".
    """

    def __init__(self, board, feature):
        self.board = board
        self.feature = feature
        super().__init__(f"{feature} is not supported on {board}")


class BoardDriver:
    """Abstract per-board protocol driver.

    Every operation the Api needs is declared here; the default
    implementation of each refuses with UnsupportedFeature. Subclasses
    override only what their board verifiably supports.
    """

    #: Feature keys this driver actually implements (see supports()).
    FEATURES = frozenset()

    #: "per-key" or "global" — how set_deadband applies. The MINI 60 HE PRO
    #: stores dead zones in a global config table, not per key.
    DEADBAND_SCOPE = "per-key"

    def __init__(self, profile, device, lock=None):
        """`profile` is a boards.BoardProfile (or None for the legacy
        registry-unavailable fallback), `device` an aula_device.AulaDevice,
        `lock` the Api's outer write lock (a private one is created when the
        driver is used standalone, e.g. in tests)."""
        self.profile = profile
        self.dev = device
        self._lock = lock if lock is not None else threading.Lock()

    # ---- identity / capability ----
    @property
    def name(self):
        return getattr(self.profile, "name", None) or "unknown board"

    @property
    def capabilities(self):
        """The registry capability flags for this board (True|False|"wip")."""
        return dict(getattr(self.profile, "capabilities", None) or {})

    def supports(self, feature):
        return feature in self.FEATURES

    def _unsupported(self, feature):
        raise UnsupportedFeature(self.name, feature)

    # ---- shared write helper (same semantics as the old Api._write) ----
    def _write(self, payload):
        with self._lock:
            if not self.dev.is_open():
                self.dev.open()
            self.dev.write(payload)

    # ---- lifecycle ----
    def connect(self):
        """Open the vendor interface. Base version performs NO writes — safe
        for boards whose protocol is unknown (layout/identity still load, so
        the UI can draw the board). Returns the hid interface info dict."""
        return self.dev.open()

    def disconnect(self):
        self.dev.close()

    def is_open(self):
        return self.dev.is_open()

    # ---- operations (default: refuse loudly, never no-op) ----
    def device_info(self):
        self._unsupported("device_info")

    def set_lighting(self, mode, fg, bg=(0, 0, 0), brightness=4, speed=4,
                     direction=0, full_color=0, power_on=True):
        self._unsupported("lighting")

    def get_lighting(self):
        self._unsupported("lighting_read")

    def set_actuation(self, indices, mode, travel_mm,
                      rt_press_mm=0.0, rt_release_mm=0.0):
        self._unsupported("actuation")

    def get_actuation(self):
        self._unsupported("actuation_read")

    def read_actuation(self, keymap):
        """Read-back per-key actuation as {key name: travel mm}."""
        self._unsupported("actuation_read")

    def set_per_key_rgb(self, colors_by_index, brightness=4, speed=4):
        """Static per-key colors ({device index: (r, g, b)})."""
        self._unsupported("per_key_rgb")

    def begin_host_stream(self):
        """Put the board into the mode the host effect engine streams into."""
        self._unsupported("host_effects")

    def stream_frame(self, colors_by_index, force=False):
        """One high-rate per-key RGB frame from the host effect engine."""
        self._unsupported("host_effects")

    def end_host_stream(self):
        """Leave host-stream mode when the effect engine stops.

        DELIBERATE default no-op — the one exception to the refuse-loudly
        rule: doing nothing emits zero bytes, so no board can ever receive a
        foreign frame from it, and "stop a stream that never started" must be
        safe for every caller (Api.stop_multicolor runs unconditionally in
        teardown paths). The Win60 has no stop command at all — its board
        simply keeps the last streamed frame in Custom mode, which is the
        pre-existing behavior and must stay byte-identical — while the MINI
        60 HE PRO overrides this to send its CLEAR_LED_DATA (0x36) command.
        """
        return None

    def set_deadband(self, raw_by_index, top_mm=None, bottom_mm=None):
        """`raw_by_index` = per-key {index: (top_raw, bottom_raw)} in 0.01 mm
        units (used by per-key boards); `top_mm`/`bottom_mm` are the values
        of the current edit (used by global-scope boards)."""
        self._unsupported("deadband")

    def set_switch(self, switch_by_index):
        self._unsupported("switch_profile")

    def set_poll_rate(self, rate):
        self._unsupported("poll_rate")

    def write_keymap(self, default_hids, overrides, layer_indices, fn_layer_raw):
        self._unsupported("remap")

    def read_keymap_layer(self, fn_layer=False, timeout_s=1.5):
        self._unsupported("remap")

    def set_socd(self, prcs_list):
        self._unsupported("socd")

    def set_calibration(self, start, any_key=False):
        self._unsupported("calibration")

    def make_live_reader(self, keymap, indices=None):
        """A started-elsewhere live travel reader bound to this device."""
        self._unsupported("travel_stream")

    def make_calibration_reader(self, keymap):
        self._unsupported("calibration")

    def open_trigger_test(self, indices):
        self._unsupported("travel_stream")

    def close_trigger_test(self):
        self._unsupported("travel_stream")

    def set_gamepad_mode(self, on):
        self._unsupported("gamepad_mode")

    # ---- macros (feature key "macros") ----
    def list_macros(self):
        """All stored macros: {slot: [(delay_ms, hid_usage, is_down), ...]}."""
        self._unsupported("macros")

    def read_macro(self, index):
        """One macro slot as an event list, or None if the slot is empty."""
        self._unsupported("macros")

    def write_macro(self, index, events):
        """Store `events` ([(delay_ms, hid_usage, is_down), ...]) in macro
        slot `index`; an empty/None event list deletes the slot."""
        self._unsupported("macros")

    def bind_macro(self, key_index, macro_index, play_mode=0, loop_count=1):
        """Bind macro slot `macro_index` to key-table record `key_index`
        (play_mode: 0 = once, 1 = fixed repeat count, 2 = press-again-to-
        end where supported)."""
        self._unsupported("macros")

    def unbind_key(self, key_index):
        """Clear key-table record `key_index` back to UNASSIGNED."""
        self._unsupported("macros")

    # ---- plain key remap, one record at a time (feature key "key_remap") ----
    # DELIBERATELY a separate feature key from "remap" (write_keymap /
    # read_keymap_layer above): that pair is the Win60's whole-layer keymap
    # upload, this is a single record in a board's key table. A board can have
    # one without the other — the MINI 60 HE PRO has no whole-layer upload
    # command at all — so gating them on one key would let a caller that
    # checked supports("remap") call an op the driver refuses.
    def read_key_records(self):
        """The board's key table decoded per record:
        {record index: {"type": ..., ...}} (see the board protocol module's
        record parser). Read-only — the input side of every remap/advanced-key
        read-modify-write."""
        self._unsupported("key_remap")

    def set_key_remap(self, key_index, hid_usage, modifiers=0):
        """Bind key-table record `key_index` to a plain HID keyboard usage
        with an optional modifier bitmask, leaving every other record
        byte-identical."""
        self._unsupported("key_remap")

    # ---- advanced keys (feature key "advanced_keys") ----
    # The five vendor "Advanced Key" types. All of them are key-table records
    # like a remap, so they share the read-modify-write path, but they are
    # gated separately: a board can support plain remap without any of these.
    def read_dks_slots(self):
        """The board's DKS travel table decoded per populated slot:
        {slot index: {"points_mm": [...], ...}}."""
        self._unsupported("advanced_keys")

    def set_advanced_dks(self, key_index, slot, points_mm,
                         actions=(), trigger_masks=(0, 0, 0, 0)):
        """Dynamic Keystroke on `key_index`, pointing at DKS entry `slot`.
        `points_mm` are the four travel points in mm, in wire order
        (press / bottom-out / release / reset), and are written to the
        board's separate DKS travel table."""
        self._unsupported("advanced_keys")

    def set_advanced_mt(self, key_index, delay, tap_hid=0, hold_hid=0):
        """Mod-Tap on `key_index`.

        `delay` is the RAW firmware delay byte, deliberately NOT named
        `delay_ms`: its unit is UNVERIFIED (one captured sample). Drivers
        pass it straight through rather than inventing a conversion."""
        self._unsupported("advanced_keys")

    def set_advanced_tgl(self, key_index, hid_usage=0):
        """Toggle (press-on / press-off) on `key_index`. The parameterless
        form (hid_usage 0) is the captured one."""
        self._unsupported("advanced_keys")

    def set_advanced_socd(self, key_index_a, key_index_b,
                          hid_a, hid_b, mode):
        """SOCD on the PAIR (`key_index_a`, `key_index_b`) — one operation,
        both records, because the vendor writes the identical record into
        both slots and a half-applied pair is a broken board state.

        `mode` is the raw behaviour byte and is a caller parameter on
        purpose: the boards this exists for accept several values but only
        one has ever been observed on the wire, so no driver may present a
        named-mode vocabulary as if it were decoded."""
        self._unsupported("advanced_keys")

    def set_advanced_rs(self, key_index_a, key_index_b, hid_a, hid_b):
        """Rapid Snap / Swift on the PAIR (`key_index_a`, `key_index_b`) —
        one operation, both records (same pairing rule as SOCD)."""
        self._unsupported("advanced_keys")

    def clear_advanced_key(self, key_index):
        """Clear ONE advanced-key/remap record back to UNASSIGNED.

        Distinct from unbind_key() above, which is the macro feature's
        clear: a board may implement advanced keys without macros (or the
        reverse), and a caller must not have to hold the macro feature to
        undo an advanced key."""
        self._unsupported("advanced_keys")


class NullDriver(BoardDriver):
    """Deliberately-inert driver for boards with no decoded/wired protocol
    (registry `protocol: null`, e.g. the MINI 60 HE PRO 2.4G dongle) or a
    protocol module that has no driver yet (protocol_sonix, protocol_sayo).

    connect() still opens the interface read-only so the UI can show the
    board; every write raises UnsupportedFeature. This is the guarantee that
    an undecoded board is never written to with some other board's frames.
    """
    FEATURES = frozenset()
