"""drivers/mini60.py — driver for the Aula MINI 60 HE PRO over BOTH
transports: wired USB-C (VID 0x0C45, PID 0x80A2, vendor interface
usage_page 0xFF68, 64-byte frames) and the 2.4GHz dongle (0x0C45:0xFEFE,
usage_page 0xFF60 usage 0x61, 32-byte frames).

Wraps protocol_mini60.py (golden-tested against the 2026-07-20 WebHID
captures of both transports and round-trip verified on the physical board —
see that module's docstring for the per-claim verification labels). This
driver adds only orchestration; framing facts all come from the verified
module:
  * `frame_len`-byte 0xAA frames, no HID report ID — to_report() prepends
    the 0x00 byte hidapi.write() expects. The frame size comes from the
    BOARD PROFILE (registry `frameLen`, default 64 = the wired value), so
    ONE driver serves both transports: the dongle speaks the identical
    protocol at 32-byte frames with payload chunk = frameLen - 8
    (CONFIRMED-BY-CAPTURE + HARDWARE-VERIFIED 2026-07-20: 0x23 lighting
    with colorMode 0/1 and the 21-chunk 0x24 per-key table rendered
    visibly over the dongle; 0x10/0x12/0x13/0x17 all answer 0x55 replies
    on the 0xFF60 raw handle once the vendor page releases the device).
    NEVER hardcode 64: a 64-byte frame at a 32-byte-report interface is
    silently truncated by hidapi and reads exactly like "wrong protocol" —
    that artifact falsified an early dongle probe and cost hours;
  * the RF bridge is NOT transparent for everything: 0x32 host streaming
    is ACCEPTED AND SILENTLY DROPPED over 2.4GHz (see _require_host_stream)
    and the 0x10 reply reports the wired 0x80A2 identity even on the
    dongle;
  * lighting: write 0x23 / read 0x13 (single 16-byte block);
  * actuation: write 0x27 / read 0x17 — the official driver ALWAYS reads
    the 1008-byte table before writing, so set_actuation here is strictly
    read-modify-write: a failed read ABORTS the write (never blind-write a
    partial table, which would zero every untouched key's record);
  * per-key RGB: effect mode 20 (LIGHT_MODE_CUSTOM) + the 504-byte 0x24
    table (write path HARDWARE-VERIFIED by 0x14 read-back round trip);
  * host effect streaming: cmd 0x32 (SET_GIF_LIGHT_DATA), the LIVE per-key
    stream — a SEPARATE channel from the persistent, flash-backed 0x24
    table. HARDWARE-VERIFIED 2026-07-20 on the physical board: 0x24 costs
    17.43 ms/write (6.4 fps — unusable for animation) while 0x32 costs
    4.00 ms/write -> 27.7 fps sustained, zero write errors, p50 36.08 ms /
    p95 36.13 ms per 9-chunk frame. Frame layout additionally confirmed
    from the vendor's own gifLight source (HFD_SDK_DECODE.md §9.3). The
    stream is FIRE-AND-FORGET: the vendor never reads replies while
    streaming, and neither does this driver (an earlier probe found the
    device errors on repeated READS from a persistent handle; writes-only
    is what was benchmarked). 0x36 (CLEAR_LED_DATA) stops/clears;
  * macros: table 0x15/0x25 + key-table binds 0x12/0x22
    (CONFIRMED-BY-CAPTURE, webhid-capture-macros.json 2026-07-21; the
    0x12 read / 0x22 write RMW path is HARDWARE-VERIFIED 2026-07-20).
    Macro writes and key binds are strictly read-modify-write, same as
    actuation: read the whole table, patch only the targeted slots,
    write everything back; a failed read ABORTS.
  * key remap + all five advanced-key types: the SAME 0x12/0x22 key table,
    one 4-byte record per key, keyed by pageType (remap 2, DKS 8, MT 9,
    TGL 10, SOCD 11, RS 12). CONFIRMED-BY-CAPTURE 2026-07-21 over BOTH
    transports — the wired sweep (webhid-capture-macros.json) and a full
    sweep of the vendor app over the 2.4GHz dongle
    (webhid-capture-FULL-SUITE-wireless.json). SOCD and RS are PAIRED: the
    identical record goes to BOTH keys of the pair, in ONE read-modify-
    write pass. DKS additionally points at a slot of the separate 1024-byte
    travel table (0x18 read / 0x28 write, 0.1 mm units) — that op reads
    BOTH tables before writing EITHER. What is NOT known is enumerated at
    the section itself: the SOCD behaviour byte (one value observed of
    four), the MT delay byte's unit (one sample), and the DKS/MT action
    slots (never captured).

Features deliberately NOT implemented (raise UnsupportedFeature, per the
parity plan — each needs its own decode/capture before it may land here):
whole-layer keymap upload (write_keymap / read_keymap_layer — a Win60
command with no equivalent here; per-record remap IS wired, under the
separate "key_remap" feature key), the Fn layer (0x16/0x26, a second key
table, captured but not wired), poll rate (game-mode reportRate byte now
capture-decoded but not wired), calibration (0x64 is on the protocol
module's NEVER-SEND list, and the vendor wipes stored calibration before
starting it so it was never exercised), travel stream (0x60
unimplemented), board-side gamepad mode (no such command in the HFD SDK).

INFERRED (not hardware-verified) items in this file are marked inline:
  * the 0x13 reply field offsets (mirror of the CONFIRMED 0x23 write block;
    the protocol agent round-tripped mode/brightness/speed through it);
  * reply frames arriving with a 0x00 report-id prefix on some hidapi
    builds (handled as a fallback, primary path expects the bare frame);
  * Win60 RT mode 12 mapping "release := press when release is 0".
"""
import json
import logging
import time

import boards
import protocol_mini60 as pm

from .base import BoardDriver

log = logging.getLogger(__name__)


def frame_len_for_profile(profile):
    """The board's vendor frame size from the registry's raw `frameLen`
    field, defaulting to the wired 64. boards.py's frozen BoardProfile
    doesn't carry the field, so it is fetched from the raw registry JSON by
    slug — the same passthrough pattern as app_web._host_engine_max_fps.
    Registry facts: the wired 0C45:80A2 declares 64 (CONFIRMED-BY-CAPTURE,
    457 frames); the 0C45:FEFE dongle declares 32 (CONFIRMED-BY-CAPTURE,
    webhid-capture-dongle-2026-07-20.json — every frame len=32)."""
    slug = getattr(profile, "slug", None)
    if not slug:
        return pm.FRAME_LEN
    try:
        with open(boards.REGISTRY_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for b in raw.get("boards", []):
            if b.get("slug") == slug:
                v = b.get("frameLen")
                if v:
                    fl = int(v)
                    pm.page_size(fl)   # validates: must leave payload space
                    return fl
                break
    except Exception as e:
        log.warning("frameLen lookup failed for %s (%s); using wired default %d",
                    slug, e, pm.FRAME_LEN)
    return pm.FRAME_LEN

# Win60-heritage Api mode vocabulary this driver must translate:
_WIN60_MODE_STATIC = 0    # Win60 static=0; MINI static=1 and MINI mode 0 = lights OFF
_WIN60_MODE_CUSTOM = 10   # Win60 per-key custom slot; MINI custom = 20
_RT_MODES = (12, 13)      # Win60 trigger modes: 12=RT single, 13=RT separate

_MAX_LEVEL = 5            # MINI brightness/speed scale is 0..5 (Win60 is 0..4)

# ---- host effect stream (cmd 0x32 / 0x36) ----
# These two commands are NOT in protocol_mini60.py (that module is the frozen
# capture-golden decode); their builders live here with the driver that owns
# the stream. Layout source: the vendor's own gifLight-Bulkc0-I.js
# (HFD_SDK_DECODE.md §9.3) and the HARDWARE-VERIFIED 2026-07-20 streaming
# benchmark (27.7 fps sustained over 9x56-byte 0x32 frames, zero errors).
CMD_STREAM_LED = 0x32     # SET_GIF_LIGHT_DATA — live per-key RGB stream
CMD_CLEAR_LED = 0x36      # CLEAR_LED_DATA — stops/clears the stream
# The SDK's generic transaction defaults contentSize to 24 when a command
# carries no payload (hfd-sdk.es fn `m`: contentSize:l=24) — that is the
# length byte the vendor puts on a bare CLEAR_LED_DATA frame.
_CLEAR_LEN = 0x18


def build_stream_frames(table, frame_len=pm.FRAME_LEN):
    """The cmd-0x32 frames streaming one full 504-byte live per-key RGB
    frame (wired: 9 x 0x38 chunks — HARDWARE-VERIFIED, 2026-07-20 streaming
    benchmark — matching the vendor gifLight source exactly; other frame
    sizes page by the same frameLen-8 rule, structural only):

        [0]=0xAA  [1]=0x32  [2]=frameLen-8  [3..4]=LE16 table byte offset
        [5]=0  [6]=last-chunk flag (final page only)  [7]=0
        [8..]=payload: repeated (keyIndex, R, G, B) quads

    `table` is the raw 504-byte quad table (build with
    protocol_mini60.build_custom_led_table — the record format is identical
    to the persistent 0x24 table; only the command byte differs)."""
    table = list(table)
    if len(table) != pm.CUSTOM_LED_TABLE_SIZE:
        raise ValueError(
            f"stream table must be {pm.CUSTOM_LED_TABLE_SIZE} bytes")
    page = pm.page_size(frame_len)
    frames = []
    offsets = pm.custom_led_page_offsets(frame_len)
    last = offsets[-1]
    for off in offsets:
        f = [0] * frame_len
        f[0] = pm.MAGIC
        f[1] = CMD_STREAM_LED
        f[2] = min(page, pm.CUSTOM_LED_TABLE_SIZE - off)
        f[3] = off & 0xFF                    # LE16 table offset
        f[4] = (off >> 8) & 0xFF
        f[6] = 0x01 if off == last else 0x00
        for j, v in enumerate(table[off:off + page]):
            f[pm.PAYLOAD_START + j] = v & 0xFF
        frames.append(f)
    return frames


def build_stream_clear(frame_len=pm.FRAME_LEN):
    """The single cmd-0x36 CLEAR_LED_DATA frame (no payload) that stops and
    clears the live stream: AA 36 18 00 00 00 01 00, rest zero. The command
    itself is HARDWARE-VERIFIED (exercised in the 2026-07-20 streaming
    session); the 0x18 length byte is SOURCE-ONLY, from the SDK transaction
    default for payload-less commands (see _CLEAR_LEN). At 32-byte frames
    the same 0x18 length byte still fits the 0x18-byte payload space."""
    f = [0] * frame_len
    f[0] = pm.MAGIC
    f[1] = CMD_CLEAR_LED
    f[2] = _CLEAR_LEN
    f[6] = 0x01
    return f


class Mini60Driver(BoardDriver):
    FEATURES = frozenset({
        "lighting", "lighting_read", "actuation", "actuation_read",
        "per_key_rgb", "device_info", "deadband", "macros",
        "host_effects", "key_remap", "advanced_keys", "socd",
    })
    # Dead zones live in the global 0x11/0x21 config table — per-key
    # semantics are impossible on this hardware.
    DEADBAND_SCOPE = "global"

    def __init__(self, profile, device, lock=None):
        super().__init__(profile, device, lock)
        # Frame size from the board profile (registry frameLen; wired 64
        # default) — the single knob that retargets every paging decision
        # below. NEVER hardcode it: a 64-byte frame at a 32-byte-report
        # interface is silently truncated by hidapi (see module docstring).
        self.frame_len = frame_len_for_profile(profile)
        self._page = pm.page_size(self.frame_len)
        self._act_offsets = pm.act_page_offsets(self.frame_len)
        self._act_per_frame = pm.act_records_per_frame(self.frame_len)
        # Host-side mirror of the 504-byte custom-LED table so a partial
        # per-key paint doesn't zero every other key (the 0x24 write is
        # always the FULL table). Seeded from the board at connect().
        self._led_state = [(0, 0, 0)] * pm.CUSTOM_LED_COUNT
        # The mode bytes THIS board declares natively (registry lighting
        # table). Empty for profiles with no lighting block — that keeps the
        # legacy Win60-vocabulary translation in set_lighting exactly as it
        # was for legacy/test profiles. See set_lighting for why this set
        # gates the translation instead of it running unconditionally.
        self._native_modes = frozenset(
            int(m["byte"])
            for m in ((getattr(profile, "lighting", None) or {}).get("modes") or ())
            if isinstance(m, dict) and m.get("byte") is not None)

    @property
    def name(self):
        return getattr(self.profile, "name", None) or "Aula Mini 60 HE Pro (wired)"

    # ---- frame IO ----
    def _guard(self, frame):
        """Refuse the protocol module's NEVER-SEND commands outright. Every
        outgoing frame passes through here — including the fire-and-forget
        stream path, which bypasses _send to hold the lock per frame."""
        if len(frame) > 1 and (frame[1] & 0xFF) in pm.DANGEROUS_CMDS:
            raise RuntimeError(
                f"refusing to send dangerous command 0x{frame[1]:02X} "
                f"(flash/factory-reset/calibration family) to {self.name}")

    def _send(self, frame):
        """Write one `frame_len`-byte vendor frame (0x00 report-id prefixed)."""
        self._guard(frame)
        self._write(pm.to_report(frame))

    def _drain(self, max_frames=64):
        """Discard stale input reports (e.g. the firmware's echo-acks of our
        own writes) so a read transaction only sees its reply."""
        for _ in range(max_frames):
            try:
                r = self.dev.read(self.frame_len, timeout_ms=2)
            except Exception:
                return
            if not r:
                return

    def _transact(self, frame, timeout_s=0.5):
        """Send one request frame and return its reply, matched on the 0x55
        reply magic + echoed command + echoed LE16 table offset. Raises
        IOError on timeout — callers must treat that as ABORT (a paged
        read-modify-write must never proceed on a partial table)."""
        cmd = frame[1]
        off = frame[3] | (frame[4] << 8)
        self._send(frame)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                r = self.dev.read(self.frame_len, timeout_ms=50)
            except Exception as e:
                raise IOError(f"read failed waiting for 0x{cmd:02X} reply: {e}")
            if not r:
                continue
            r = list(r)
            if r and r[0] == pm.REPLY_MAGIC:
                fr = r
            elif len(r) > 1 and r[0] == 0x00 and r[1] == pm.REPLY_MAGIC:
                # INFERRED fallback: some hidapi builds prepend the report id
                # on read; the primary path (bare frame) matches the capture.
                fr = r[1:]
            else:
                continue
            if len(fr) >= pm.PAYLOAD_START and fr[1] == cmd \
                    and (fr[3] | (fr[4] << 8)) == off:
                return fr
        raise IOError(
            f"{self.name}: no reply to cmd 0x{cmd:02X} @0x{off:04X} "
            f"within {timeout_s}s")

    def _read_table(self, frames, size):
        """Run a paged read (0x11/0x14/0x17 family) and reassemble the full
        table. All-or-nothing: any missing page raises."""
        self._drain()
        table = bytearray(size)
        for f in frames:
            rep = self._transact(f)
            ln = min(rep[2], self._page)
            off = rep[3] | (rep[4] << 8)
            for j in range(ln):
                if off + j < size and pm.PAYLOAD_START + j < len(rep):
                    table[off + j] = rep[pm.PAYLOAD_START + j]
        return bytes(table)

    # ---- lifecycle ----
    def connect(self):
        """Open the 0xFF68 vendor interface, send the 0x10 device-info
        handshake (first frame of the official driver's init sequence), and
        seed the per-key LED mirror from the board's stored 0x14 table."""
        info = self.dev.open()
        try:
            # the vendor's init handshake: the full 0x10 sweep (one frame
            # wired, three at 32-byte frames — CONFIRMED-BY-CAPTURE on both)
            for f in pm.build_device_info_frames(self.frame_len):
                self._send(f)
        except Exception:
            pass
        try:
            self._seed_led_state()
        except Exception as e:
            log.warning("%s: could not seed per-key LED table (%s); "
                        "starting from black", self.name, e)
        return info

    def _seed_led_state(self):
        table = self._read_table(
            list(pm.build_custom_led_read_frames(self.frame_len)),
            pm.CUSTOM_LED_TABLE_SIZE)
        for i in range(pm.CUSTOM_LED_COUNT):
            base = i * pm.CUSTOM_LED_RECORD_SIZE
            self._led_state[i] = (table[base + 1], table[base + 2],
                                  table[base + 3])

    # ---- device info (0x10) ----
    def device_info(self):
        """Run the paged 0x10 sweep (single frame wired) and parse VID/PID
        from the offset-0 reply. NOTE: over the 2.4GHz dongle the firmware
        reports the WIRED identity (0x0C45:0x80A2), not the receiver's
        0xFEFE — CONFIRMED-BY-CAPTURE (handshake capture) — so callers must
        not use this to identify the transport."""
        self._drain()
        vid = pid = None
        for f in pm.build_device_info_frames(self.frame_len):
            rep = self._transact(f)
            if (f[3] | (f[4] << 8)) == 0:
                vid, pid = pm.parse_device_info(rep)
        if vid is None:
            raise IOError(f"{self.name}: no offset-0 device-info reply")
        return {"vid": vid, "pid": pid, "vidPid": f"{vid:04X}:{pid:04X}"}

    # ---- lighting (0x23 write / 0x13 read) ----
    def _color_mode_for(self, mode_byte):
        """colorMode (0x23 frame byte [16]) for a native MINI mode byte,
        derived from the board profile's lighting table: a mode the
        registry marks `color: false` is forced-random (SDK: colorMode =
        randomColor ? 1 : 0) and gets 1; a colour-pickable mode gets 0 so
        the user's chosen colour actually applies.

        CORRECTION 2026-07-20 (the wireless capture resolved this): the
        byte used to be hardcoded to 1 because every wired-capture frame
        carried 1 — a single-valued sample mistaken for a constant. Pinned
        to 1, user-chosen colours are likely IGNORED in fixed-colour modes.
        The captured correlation (fixed-colour modes 0x01/0x02/0x04/0x07 ->
        0; multicolour 0x08/0x0F/0x11/0x12/0x13 -> 1) matches this
        derivation against the registry table exactly.

        Deliberate LEGACY-1 fallbacks (today's byte, no behaviour change):
          * no lighting table on the profile, or a mode byte not in it
            (includes mode 0 = lights off);
          * LIGHT_MODE_CUSTOM (20): the per-key path was HARDWARE-VERIFIED
            with [16]=1 (mode-20 + 0x24 round trip, 2026-07-20) and no
            capture shows its colorMode — do not change a proven frame on
            an inference."""
        lt = getattr(self.profile, "lighting", None) or {}
        if mode_byte == pm.LIGHT_MODE_CUSTOM:
            return 1
        for m in lt.get("modes", ()):
            if m.get("byte") == mode_byte:
                return 1 if m.get("color", True) is False else 0
        return 1

    def set_lighting(self, mode, fg, bg=(0, 0, 0), brightness=4, speed=4,
                     direction=0, full_color=0, power_on=True):
        """Send a MINI mode byte, with the Win60-heritage vocabulary
        translation applied ONLY as a fallback for bytes this board does not
        declare natively.

        The mode byte is now resolved against THE ACTIVE BOARD's registry
        table one layer up (the UI's light dispatch sends the board's OWN
        byte), so a native byte must reach the wire untouched. Gating on
        `self._native_modes` is what makes that true:

          * MINI registry present -> mode 10 IS `colorful-cross` and is sent
            as 10. Translating it to 20 (LIGHT_MODE_CUSTOM) — as this method
            did unconditionally — silently put the board into per-key Custom
            and rendered the stale/black 0x24 table while the UI showed
            "Colorful Cross" selected. Same failure shape as the FW_MODES
            bug: per-board data reached the layer that was updated and fell
            through a translation in the layer that was not.
          * no lighting block on the profile (legacy/test profiles) -> the
            set is empty, every byte takes the old path, and the emitted
            frames are byte-identical to before this gate existed.
          * mode 0 is NOT in the MINI table (the registry declares it via
            `offModeByte`, not as a mode), so Api mode 0 (Win60 static)
            still maps to MINI static 0x01 on every profile — unchanged.

        power_on=False -> MINI mode 0 (lights off), applied last.

        colorMode (frame byte [16]) is derived from the selected mode via
        the registry lighting table (see _color_mode_for) — the fix for
        user-chosen colours being ignored in fixed-colour modes.

        Not wired (the builder has no parameters for them): bg, direction,
        full_color — build_light has no direction byte; needs
        protocol_mini60 owner (follow-up)."""
        m = int(mode)
        if m not in self._native_modes:
            if m == _WIN60_MODE_STATIC:
                m = pm.LIGHT_MODE_STATIC
            elif m == _WIN60_MODE_CUSTOM:
                m = pm.LIGHT_MODE_CUSTOM
        if not power_on:
            m = 0    # MINI: mode 0 = lights off (vendor UI semantics)
        if not (0 <= m <= pm.LIGHT_MODE_CUSTOM):
            raise ValueError(f"lighting mode {mode} out of range for {self.name}")
        r, g, b = (int(c) & 0xFF for c in fg)
        self._send(pm.build_light(
            m, r, g, b,
            brightness=max(0, min(_MAX_LEVEL, int(brightness))),
            speed=max(0, min(_MAX_LEVEL, int(speed))),
            color_mode=self._color_mode_for(m),
            frame_len=self.frame_len))

    def get_lighting(self):
        """Read the current 0x23 lighting block via 0x13. Field offsets are
        INFERRED from the CONFIRMED write-frame layout (same 16-byte block;
        the protocol agent round-tripped mode/brightness/speed through this
        read on hardware)."""
        self._drain()
        rep = self._transact(pm.build_light_read(self.frame_len))
        return {"mode": rep[8], "rgb": [rep[9], rep[10], rep[11]],
                "brightness": rep[17], "speed": rep[18]}

    # ---- actuation (0x17 read / 0x27 write, strict read-modify-write) ----
    def _read_actuation_records(self):
        """The full 126-record table as parse_actuation_records tuples
        ((rt_flags, trip_mm, press_mm, release_mm, axis_type) or None)."""
        table = self._read_table(list(pm.iter_actuation_reads(self.frame_len)),
                                 pm.ACT_TABLE_SIZE)
        records = []
        for off in self._act_offsets:
            pseudo = [0] * pm.PAYLOAD_START + list(table[off:off + self._page])
            records.extend(pm.parse_actuation_records(pseudo))
        return records

    def _write_actuation_records(self, records):
        last = self._act_offsets[-1]
        for off in self._act_offsets:
            start = off // pm.ACT_RECORD_SIZE
            recs = records[start:start + self._act_per_frame]
            self._send(pm.build_actuation_frame(off, recs, final=(off == last),
                                                frame_len=self.frame_len))
            time.sleep(0.005)

    def set_actuation(self, indices, mode, travel_mm,
                      rt_press_mm=0.0, rt_release_mm=0.0):
        """Vendor flow: 0x17 sweep -> patch ONLY the selected slots
        (preserving axisType, the rampage flag bit and every other key's
        record) -> full 0x27 sweep. A failed read aborts before any write.

        Win60 mode mapping: 0 = fixed (RT flag off, stored RT sensitivities
        kept in the record), 12/13 = rapid trigger (flag bit0 on). For mode
        12 a zero release falls back to the press value (INFERRED — the
        Win60 UI sends a single sensitivity in that mode)."""
        idxs = sorted({int(i) for i in indices
                       if 0 <= int(i) < pm.ACT_TABLE_SIZE // pm.ACT_RECORD_SIZE})
        if not idxs:
            raise ValueError("no valid key indices for this board")
        rt = int(mode) in _RT_MODES
        press = float(rt_press_mm)
        release = float(rt_release_mm)
        if rt and release <= 0:
            release = press
        # Atomic across the 0x17 read -> patch -> 0x27 write (see transaction()).
        with self.transaction():
            records = self._read_actuation_records()   # raises on partial read
            for i in idxs:
                old = records[i]
                axis = old[4] if old else 0
                old_flags = old[0] if old else 0
                flags = (old_flags & ~0x01) | (0x01 if rt else 0x00)
                if rt:
                    records[i] = (flags, float(travel_mm), press, release, axis)
                else:
                    records[i] = (flags, float(travel_mm),
                                  old[2] if old else 0.0,
                                  old[3] if old else 0.0, axis)
            self._write_actuation_records(records)

    def get_actuation(self):
        """{device index: {rt, travel_mm, rt_press_mm, rt_release_mm,
        axis_type}} for every populated record slot."""
        out = {}
        for i, rec in enumerate(self._read_actuation_records()):
            if rec is None:
                continue
            flags, trip, press, release, axis = rec
            out[i] = {"rt": bool(flags & 0x01), "travel_mm": trip,
                      "rt_press_mm": press, "rt_release_mm": release,
                      "axis_type": axis}
        return out

    def read_actuation(self, keymap):
        """{key name: travel mm} from one 0x17 sweep. NOTE: correctness of
        the names depends on the board's layout JSON, which is being
        regenerated (its current indices are provisional — parity plan §2)."""
        vals = {}
        for i, rec in enumerate(self._read_actuation_records()):
            if rec is None:
                continue
            name = keymap.name_of(i) if keymap else None
            if name:
                vals[name] = rec[1]
        return vals

    # ---- per-key RGB (effect mode 20 + 0x24 table) ----
    def set_per_key_rgb(self, colors_by_index, brightness=4, speed=4):
        """Update the host-side table mirror with the given keys, switch the
        board to effect mode 20 (custom), then write the FULL 504-byte 0x24
        table. Cumulative: keys not in this call keep their last color
        (seeded from the board at connect)."""
        changed = False
        for idx, rgb in (colors_by_index or {}).items():
            idx = int(idx)
            if 0 <= idx < pm.CUSTOM_LED_COUNT and rgb is not None:
                self._led_state[idx] = tuple(int(c) & 0xFF for c in list(rgb)[:3])
                changed = True
        if not changed:
            raise ValueError("no valid key indices for this board")
        # colorMode stays the default 1 on this mode-20 frame — the
        # HARDWARE-VERIFIED per-key round trip used exactly that byte.
        self._send(pm.build_light(
            pm.LIGHT_MODE_CUSTOM,
            brightness=max(0, min(_MAX_LEVEL, int(brightness))),
            speed=max(0, min(_MAX_LEVEL, int(speed))),
            frame_len=self.frame_len))
        table = pm.build_custom_led_table(list(self._led_state))
        for f in pm.build_custom_led_write_frames(table, self.frame_len):
            self._send(f)
            time.sleep(0.005)

    # ---- host-driven effect stream (cmd 0x32 live path, 0x36 to clear) ----
    # HARDWARE-VERIFIED 2026-07-20: 0x32 sustains 27.7 fps (4.00 ms/write,
    # 9x56-byte chunks/frame, zero errors) where the persistent 0x24 table
    # manages only 6.4 fps (17.43 ms/write). The stream is a separate live
    # channel: it never touches the flash-backed 0x24 table or this driver's
    # _led_state mirror, so "Per-key Paint" state survives an animation.

    def _require_host_stream(self):
        """Refuse host streaming when the board profile EXPLICITLY declares
        lighting.hostEngine false. HARDWARE-VERIFIED necessity (2026-07-20,
        the 2.4GHz dongle): the RF bridge ACCEPTS 0x32 writes and silently
        drops them — a 15 s rainbow sweep ran at a rock-steady 23.8 fps of
        zero-error no-ops while the keyboard showed nothing, and a capture
        of the vendor's own app driving effects over the dongle contains
        ONLY 0x23/0x14 (it never streams over 2.4GHz; wireless effects are
        firmware-side). Accepted-but-ignored is not working — refuse loudly
        rather than pretend an animation is running. Profiles without a
        lighting block (legacy/tests) and the wired board (hostEngine true,
        27.7 fps HARDWARE-VERIFIED) are unaffected."""
        lt = getattr(self.profile, "lighting", None)
        if lt is not None and not lt.get("hostEngine", False):
            self._unsupported("host_effects")

    def begin_host_stream(self):
        """Put the board into per-key Custom mode (effect mode 20) for the
        effect engine, full brightness — the engine bakes brightness into
        the colors it streams (same contract as the Win60 driver)."""
        self._require_host_stream()
        self._send(pm.build_light(pm.LIGHT_MODE_CUSTOM,
                                  brightness=_MAX_LEVEL, speed=_MAX_LEVEL,
                                  frame_len=self.frame_len))

    def stream_frame(self, colors_by_index, force=False):
        """Stream one live per-key RGB frame ({device index: (r, g, b)};
        unlisted keys go dark, exactly like the Win60's cmd-9 table).

        Always sends the full 9-chunk 0x32 frame — no diff cache. That
        full-frame cadence is precisely what the 27.7 fps benchmark
        measured, and the vendor's gifLight loop does the same; `force` is
        accepted for signature parity and is a no-op here. Fire-and-forget:
        NO replies are read mid-stream (repeated reads on a persistent
        handle error on this device — writes-only is the verified mode).
        Holds the outer lock for the whole frame so a set_light can't slip
        between chunks and yank the board out of Custom mode."""
        self._require_host_stream()
        colors = [(0, 0, 0)] * pm.CUSTOM_LED_COUNT
        for idx, rgb in (colors_by_index or {}).items():
            idx = int(idx)
            if 0 <= idx < pm.CUSTOM_LED_COUNT and rgb is not None:
                colors[idx] = tuple(int(c) & 0xFF for c in list(rgb)[:3])
        frames = build_stream_frames(pm.build_custom_led_table(colors),
                                     self.frame_len)
        with self._lock:
            if not self.dev.is_open():
                self.dev.open()
            for f in frames:
                self._guard(f)
                self.dev.write(pm.to_report(f))

    def end_host_stream(self):
        """Stop/clear the live stream (CLEAR_LED_DATA 0x36) when the effect
        engine stops, handing the LEDs back to the firmware effect."""
        self._send(build_stream_clear(self.frame_len))

    # ---- dead zone (GLOBAL — 0x11 read / 0x21 write config table) ----
    def set_deadband(self, raw_by_index, top_mm=None, bottom_mm=None):
        """Dead zones are board-global on this hardware; the per-key
        `raw_by_index` map is ignored and `top_mm`/`bottom_mm` apply to the
        whole board (DEADBAND_SCOPE == "global" tells callers/UI).

        Strict read-modify-write of the 64-byte game-mode table: most of its
        fields are live settings that a partial write would zero. Top dead
        zone at payload offset 8 is CONFIRMED-BY-CAPTURE (via
        pm.set_deadzone); bottom at offset 9 is SOURCE-ONLY (SDK field map,
        parity plan §2)."""
        if top_mm is None and bottom_mm is None:
            raise ValueError("no dead-zone values given")
        # Atomic across the 64-byte config read -> patch -> write (see
        # transaction()); most fields are live settings a partial/raced write
        # would zero.
        with self.transaction():
            tbl = self._read_table(pm.build_config_read_frames(self.frame_len),
                                   pm.CONFIG_TABLE_SIZE)
            payload = list(tbl[:pm.PAGE])
            if top_mm is not None:
                payload = pm.set_deadzone(payload, float(top_mm))
            if bottom_mm is not None:
                raw = pm.mm_to_raw(float(bottom_mm))
                if raw > 0xFF:
                    raise ValueError("dead zone > 2.55 mm: field is a single byte")
                # SOURCE-ONLY: SDK game-mode field map has payload[9] = bottomDeadZone
                payload[pm.CONFIG_DEADZONE_OFFSET + 1] = raw
            for f in pm.build_config_write_frames(payload, self.frame_len):
                self._send(f)
                time.sleep(0.005)

    # ---- macros (0x15 read / 0x25 write, binds via 0x12/0x22) ----
    # Frame layouts are CONFIRMED-BY-CAPTURE (webhid-capture-macros.json);
    # the 0x12 read / 0x22 write RMW path is HARDWARE-VERIFIED (2026-07-20:
    # 512-byte read, 11 records zeroed, write-back, read-back byte-identical
    # everywhere else). Everything here follows the actuation/RGB pattern:
    # strict read-modify-write, never a blind partial write.

    def _read_key_table(self):
        """The full 512-byte 0x12 key table. All-or-nothing (raises on a
        partial read — callers must NOT write after a failure)."""
        return self._read_table(pm.build_key_table_read_frames(self.frame_len),
                                pm.KEY_TABLE_SIZE)

    def _write_key_table(self, table):
        for f in pm.build_key_table_write_frames(table, self.frame_len):
            self._send(f)
            time.sleep(0.005)

    def _check_key_index(self, key_index):
        """Validate a key-table record index. Deliberately called BEFORE any
        read so a bad index costs zero frames on the wire."""
        k = int(key_index)
        if not 0 <= k < pm.KEY_WRITABLE_RECORDS:
            raise ValueError(
                f"key index must be 0..{pm.KEY_WRITABLE_RECORDS - 1} "
                f"(records 126..127 are readable but the vendor write path "
                f"never writes them)")
        return k

    def _patch_key_records(self, records_by_index):
        """Strict read-modify-write of ANY number of key-table records in
        ONE pass: validate every index, read all 512 bytes, patch only the
        listed records, write the table back (vendor-shaped 504-byte
        write). A failed read aborts before a single write frame is sent.

        Multi-record in one pass is what makes the PAIRED advanced types
        (SOCD, RS) safe: their two keys carry the identical record and must
        land in the same 0x22 sweep, because two sequential single-record
        passes leave the board half-configured if the second one fails."""
        patches = {}
        for k, rec in records_by_index.items():
            rec = list(rec)
            if len(rec) != pm.KEY_RECORD_SIZE:
                raise ValueError(f"a key record is {pm.KEY_RECORD_SIZE} bytes")
            patches[self._check_key_index(k)] = rec
        if not patches:
            raise ValueError("no key records to write")
        # Atomic across the read+patch+write so a concurrent op can't read the
        # same snapshot and clobber our write (the reentrant lock lets the
        # per-frame _write inside re-acquire it).
        with self.transaction():
            table = list(self._read_key_table())   # raises on partial read
            for k, rec in patches.items():
                base = k * pm.KEY_RECORD_SIZE
                table[base:base + pm.KEY_RECORD_SIZE] = rec
            self._write_key_table(table)

    def _patch_key_record(self, key_index, record):
        """Strict read-modify-write of ONE key-table record (see
        _patch_key_records — this is the single-record spelling of it and
        emits the identical frames it always did)."""
        self._patch_key_records({key_index: record})

    def bind_macro(self, key_index, macro_index, play_mode=0, loop_count=1):
        """Bind macro slot `macro_index` to key-table record `key_index`
        (matrix position) as a pageType-6 record, preserving every other
        record byte-for-byte. play_mode 0/1 are CONFIRMED-BY-CAPTURE;
        mode 2 ("press again to end") is accepted but NOT CAPTURED."""
        self._patch_key_record(
            key_index,
            pm.key_record_macro(macro_index, play_mode, loop_count))

    def unbind_key(self, key_index):
        """Clear key-table record `key_index` back to UNASSIGNED
        (00 00 00 00 — the captured state of unbound keys), preserving
        every other record."""
        self._patch_key_record(key_index, pm.key_record_unassigned())

    def _read_macro_body(self, offset):
        """The vendor two-step body read: 4-byte count at `offset`, then
        count*2 bytes at offset+4. Returns the decoded event list."""
        rep = self._transact(pm.build_macro_count_read(offset, self.frame_len))
        words = rep[pm.PAYLOAD_START] | (rep[pm.PAYLOAD_START + 1] << 8)
        if words == 0:
            return []
        data = []
        for f in pm.build_macro_body_read_frames(offset, words, self.frame_len):
            r = self._transact(f)
            ln = min(r[2], self._page)
            data += list(r[pm.PAYLOAD_START:pm.PAYLOAD_START + ln])
        return pm.decode_macro_events(
            [words & 0xFF, (words >> 8) & 0xFF, 0, 0] + data)

    def _read_macros(self):
        """All stored macros as {slot: events}. All-or-nothing: any missing
        page or body chunk raises (mandatory before any 0x25 write)."""
        header = self._read_table(pm.build_macro_read_frames(self.frame_len),
                                  pm.MACRO_HEADER_SIZE)
        self._drain()
        out = {}
        for slot, off in enumerate(pm.parse_macro_header(list(header))):
            if off:
                out[slot] = self._read_macro_body(off)
        return out

    def list_macros(self):
        """{slot: [(delay_ms, hid_usage, is_down), ...]} for every stored
        macro (empty slots omitted)."""
        return self._read_macros()

    def read_macro(self, index):
        """One macro slot's events, or None if the slot is empty."""
        idx = int(index)
        if not 0 <= idx < pm.MACRO_SLOTS:
            raise ValueError(f"macro slot must be 0..{pm.MACRO_SLOTS - 1}")
        return self._read_macros().get(idx)

    def write_macro(self, index, events):
        """Store `events` ([(delay_ms, hid_usage, is_down), ...]) in macro
        slot `index`; an empty/None event list deletes the slot. Strict
        read-modify-write of the WHOLE macro table — the vendor driver
        rewrites the 400-byte header and every body on each save (a
        partial header write would orphan the other macros' offsets), and
        so does this. A failed read aborts before any write."""
        idx = int(index)
        if not 0 <= idx < pm.MACRO_SLOTS:
            raise ValueError(f"macro slot must be 0..{pm.MACRO_SLOTS - 1}")
        # Atomic across the whole-table read -> patch -> write (see
        # transaction()); a raced partial header write orphans other offsets.
        with self.transaction():
            macros = self._read_macros()             # raises on partial read
            if events:
                macros[idx] = list(events)
            else:
                macros.pop(idx, None)
            table = pm.build_macro_table(macros)
            for f in pm.build_macro_write_frames(table, self.frame_len):
                self._send(f)
                time.sleep(0.005)

    # ---- key remap + advanced keys (0x12 read / 0x22 write; DKS also
    #      0x18 read / 0x28 write) ----
    # CONFIRMED-BY-CAPTURE 2026-07-21 over BOTH transports: the wired sweep
    # (webhid-capture-macros.json, FULL_APP_CAPTURE_NOTES.md sections 1+3) and
    # the full wireless sweep over the 2.4GHz dongle
    # (webhid-capture-FULL-SUITE-wireless.json, decoded by analyze_full_suite
    # .py) both put plain remap AND all five advanced-key types on the wire as
    # 4-byte records in the SAME 512-byte key table the macro binds already
    # use. Nothing new is invented here: the record builders live in
    # protocol_mini60 with their own capture provenance, and this layer only
    # orchestrates the read-modify-write — the identical pattern as actuation,
    # per-key RGB and macros. A failed read ABORTS before any write.
    #
    # WHAT IS NOT KNOWN, and is therefore not claimed anywhere below:
    #   * SOCD `mode` — only 0x03 ("Key 1 Priority") was ever observed on the
    #     wire (the wired capture separately shows 0x02). The SDK offers four
    #     values for four UI behaviours but the label<->value mapping is
    #     UNVERIFIED, so mode is a raw pass-through parameter and this driver
    #     offers NO named-mode vocabulary that would imply otherwise;
    #   * the MT delay byte's UNIT — one sample per transport (0x28 = 40
    #     wireless, 0x19 = 25 wired at a UI setting of 250 ms). Consistent
    #     with 10 ms units, still one sample: the parameter is named `delay`,
    #     not `delay_ms`, and no conversion happens here;
    #   * DKS and MT ACTION slots — the vendor UI never filled them in
    #     (it demands a physical key press), so their encoding is NOT
    #     CAPTURED. They are accepted as pass-through and default to the
    #     captured empty form;
    #   * DKS byte 1 as a slot index is consistent across two captures
    #     (wired slot 0, wireless slot 1) but only one DKS key existed in
    #     each, so it is not proven.

    def read_key_records(self):
        """{record index: parsed record dict} for the whole 0x12 key table
        (see pm.parse_key_record). The read side of every remap and
        advanced-key edit; also the honest way to show what is bound,
        because undecoded pageTypes come back as raw bytes rather than
        being guessed at."""
        return pm.parse_key_table(self._read_key_table())

    def set_key_remap(self, key_index, hid_usage, modifiers=0):
        """Bind `key_index` to a plain HID keyboard usage (pageType 2),
        preserving every other record byte-for-byte. `modifiers` is the
        record's modifier bitmask — CONFIRMED-BY-CAPTURE as a bitmask, not
        padding, by the stock Fn table's modifier-only 02 40 00 00."""
        self._patch_key_record(
            key_index, pm.key_record_remap(hid_usage, modifiers))

    def clear_advanced_key(self, key_index):
        """Clear ONE key-table record back to UNASSIGNED (00 00 00 00).

        Same wire effect as unbind_key(), exposed under the advanced-keys
        feature so undoing a remap or an advanced key never requires the
        caller to hold the macro feature. NOTE for paired types: this
        clears the ONE index given. Undoing a SOCD/RS pair means calling it
        for both keys — the driver cannot infer the partner from a single
        record, and pm.find_paired_key_records() over read_key_records()'s
        table is the honest way to discover it."""
        self._patch_key_record(key_index, pm.key_record_unassigned())

    def set_advanced_tgl(self, key_index, hid_usage=0):
        """Toggle (pageType 10) on `key_index`. The captured form is
        parameterless (0A 00 00 00); a non-zero `hid_usage` in byte 1 is
        SOURCE-ONLY from the SDK and never observed."""
        self._patch_key_record(key_index, pm.key_record_tgl(hid_usage))

    def set_advanced_mt(self, key_index, delay, tap_hid=0, hold_hid=0):
        """Mod-Tap (pageType 9) on `key_index` with the RAW firmware delay
        byte. See the section header: the delay UNIT is unverified and the
        tap/hold action slots are NOT CAPTURED — both are passed through
        untouched rather than converted or defaulted to a guess."""
        self._patch_key_record(
            key_index, pm.key_record_mt(delay, tap_hid, hold_hid))

    def _patch_paired_record(self, key_index_a, key_index_b, record):
        """Write one paired-type record onto both keys in a SINGLE 0x22
        sweep. Validation and the pairing rules (distinct indices, pageType
        must actually be a paired type) run BEFORE the 0x12 read, so a bad
        pair costs zero frames; the read then gates the write as usual."""
        a = self._check_key_index(key_index_a)
        b = self._check_key_index(key_index_b)
        # Runs the protocol module's paired-type + distinct-index checks on a
        # throwaway table so they fire before anything touches the wire.
        pm.apply_paired_key_record([0] * pm.KEY_TABLE_SIZE, a, b, record)
        self._patch_key_records({a: record, b: record})

    def set_advanced_socd(self, key_index_a, key_index_b, hid_a, hid_b,
                          mode=pm.SOCD_MODE_KEY1_PRIORITY):
        """SOCD (pageType 11) on the PAIR (`key_index_a`, `key_index_b`).

        ONE read-modify-write pass writes the IDENTICAL record into BOTH
        slots — CONFIRMED-BY-CAPTURE (the vendor's SOCD save put
        0B 03 04 07 on key indices 49 AND 51). Mirroring is delegated to
        pm.apply_paired_key_record so it cannot be forgotten and so a
        non-paired pageType can never be duplicated by accident.

        `mode` defaults to the ONLY value ever seen on the wire; other
        values are accepted but NOT decoded (see the section header)."""
        self._patch_paired_record(key_index_a, key_index_b,
                                  pm.key_record_socd(hid_a, hid_b, mode))

    def set_socd(self, prcs_list):
        """The BOARD-NEUTRAL SOCD entry point (the shape Api.set_socd already
        sends), mapped onto this board's key table.

        The Win60 sends SOCD as its own cmd-36 PRCS packet built from HID
        usages alone. This board has no such command: SOCD is a record in the
        512-byte key table at the pair's MATRIX POSITIONS, so each entry
        needs two extra fields beyond {model, key1_hid, key2_hid} —
        `key1_index` and `key2_index`.

        Those indices are NOT derivable here and are not guessed at. A HID
        usage does not identify a matrix position on this board: an unbound
        key's record reads back 00 00 00 00, so the table cannot be searched
        for "the key that sends 0x04". The index is layout data the caller
        owns. Missing it is a loud ValueError, never a silent wrong-key write.

        `model` is the raw SOCD behaviour byte and defaults to the ONLY value
        ever observed (see set_advanced_socd) — it is deliberately the same
        pass-through parameter, not a decoded vocabulary.

        EVERY pair lands in ONE read-modify-write pass: partially applied
        SOCD is a broken board state, and that is just as true across pairs
        as it is across the two keys of one pair."""
        entries = list(prcs_list or ())
        if not entries:
            raise ValueError(
                f"{self.name}: no SOCD pairs given (this board stores SOCD "
                f"per key record — there is no 'clear all' packet; clear a "
                f"pair with clear_advanced_key on both of its keys)")
        patches = {}
        for e in entries:
            try:
                a = self._check_key_index(e["key1_index"])
                b = self._check_key_index(e["key2_index"])
                hid_a = int(e["key1_hid"])
                hid_b = int(e["key2_hid"])
            except (KeyError, TypeError):
                raise ValueError(
                    f"{self.name}: an SOCD pair needs key1_index/key2_index "
                    f"(this board's key-table matrix positions) as well as "
                    f"key1_hid/key2_hid — got {e!r}")
            mode = int(e.get("model", pm.SOCD_MODE_KEY1_PRIORITY))
            rec = pm.key_record_socd(hid_a, hid_b, mode)
            # the protocol module's paired-type + distinct-index checks, run
            # on a throwaway table so they fire before anything is written
            pm.apply_paired_key_record([0] * pm.KEY_TABLE_SIZE, a, b, rec)
            patches[a] = rec
            patches[b] = rec
        self._patch_key_records(patches)

    def set_advanced_rs(self, key_index_a, key_index_b, hid_a, hid_b):
        """Rapid Snap / Swift (pageType 12) on the PAIR
        (`key_index_a`, `key_index_b`) — same both-slots rule as SOCD
        (CONFIRMED-BY-CAPTURE: 0C 00 14 08 on key indices 33 AND 35).
        Byte 1 is a constant 0 in every captured RS record, so there is no
        mode parameter to expose."""
        self._patch_paired_record(key_index_a, key_index_b,
                                  pm.key_record_rs(hid_a, hid_b))

    # ---- DKS travel table (0x18 read / 0x28 write) ----
    def _read_dks_table(self):
        """The full 1024-byte DKS travel table. All-or-nothing (raises on a
        partial read — callers must NOT write after a failure)."""
        return self._read_table(
            pm.build_dks_travel_read_frames(self.frame_len),
            pm.DKS_TABLE_SIZE)

    def read_dks_slots(self):
        """{slot index: decoded DKS slot} for every populated slot (see
        pm.parse_dks_travel: points_mm, actions, raw trigger masks)."""
        return pm.parse_dks_table(self._read_dks_table())

    def set_advanced_dks(self, key_index, slot, points_mm,
                         actions=(), trigger_masks=(0, 0, 0, 0)):
        """Dynamic Keystroke (pageType 8) on `key_index`, pointing at DKS
        entry `slot`, with the four travel points in mm (wire order: press /
        bottom-out / release / reset, 0.1 mm units on the wire).

        TWO tables, both strictly read-modify-write, in the vendor's
        CONFIRMED-BY-CAPTURE order: the 1024-byte DKS travel table first
        (0x18 read -> patch this slot only -> 0x28 write), then the key
        record (0x12 read -> patch -> 0x22 write).

        BOTH reads happen BEFORE EITHER write. That ordering is deliberate:
        the naive read/write/read/write sequence can leave a DKS slot
        populated with no key pointing at it if the second read fails, and
        this driver's rule everywhere is that a failed read aborts before
        any write at all.

        `actions` and `trigger_masks` are pass-through: the vendor UI never
        assigned an action during either capture, so their meaning is NOT
        CAPTURED — the defaults reproduce the captured empty form."""
        k = self._check_key_index(key_index)
        s = int(slot)
        if not 0 <= s < pm.DKS_USABLE_SLOTS:
            raise ValueError(f"DKS slot must be 0..{pm.DKS_USABLE_SLOTS - 1}")
        record = pm.dks_slot_record(points_mm, actions, trigger_masks)
        key_record = pm.key_record_dks(s)
        # Atomic across BOTH table reads and BOTH writes (see transaction()) so
        # a concurrent op can't clobber either half of this two-table pair.
        with self.transaction():
            # --- both reads first; either failure aborts with nothing written ---
            dks_table = list(self._read_dks_table())
            key_table = list(self._read_key_table())
            base = s * pm.DKS_SLOT_SIZE
            dks_table[base:base + pm.DKS_SLOT_SIZE] = record
            key_table[k * pm.KEY_RECORD_SIZE:
                      (k + 1) * pm.KEY_RECORD_SIZE] = key_record
            # --- vendor write order: travel table (0x28) then key record (0x22) ---
            for f in pm.build_dks_travel_write_frames(dks_table, self.frame_len):
                self._send(f)
                time.sleep(0.005)
            self._write_key_table(key_table)
