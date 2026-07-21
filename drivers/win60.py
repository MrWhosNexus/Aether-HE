"""drivers/win60.py — driver for the Aula Win60 HE (VID 2E3C, PID C365).

A REFACTOR, not a rewrite: every method body here is the protocol-touching
code that previously lived inline in app_web.Api, moved verbatim (same
builders, same packet order, same inter-packet sleeps, same locking against
the Api's outer lock). The Win60 user must see zero behavior change.

Packet building stays in protocol.py (report-ID-1, 63-byte bodies); live
readers stay in device_state.py — this module only owns the dispatch.
"""
import logging
import time

import protocol
import device_state

from .base import BoardDriver

log = logging.getLogger(__name__)


class Win60Driver(BoardDriver):
    FEATURES = frozenset({
        "lighting", "actuation", "actuation_read", "per_key_rgb",
        "per_key_rgb_read",
        "host_effects", "deadband", "switch_profile", "poll_rate",
        "remap", "socd", "calibration", "travel_stream", "gamepad_mode",
        "device_info", "macros",
    })
    DEADBAND_SCOPE = "per-key"

    #: How long read_deadband_table() waits before set_deadband aborts.
    DEADBAND_READ_TIMEOUT_S = 1.5

    #: How long the cumulative set_per_key_rgb read-back waits before
    #: aborting (same strict RMW contract as set_deadband).
    CUSTOM_READ_TIMEOUT_S = 1.5

    def __init__(self, profile, device, lock=None):
        super().__init__(profile, device, lock)
        # diff cache for the host effect stream: only re-send changed pages
        self._last_pkts = None

    @property
    def name(self):
        return getattr(self.profile, "name", None) or "Aula Win60 HE"

    # ---- lifecycle ----
    def connect(self):
        """Open + the device-info heartbeat handshake (was Api.connect)."""
        info = self.dev.open()
        try:
            self.dev.write(protocol.build_heartbeat())
        except Exception:
            pass
        return info

    # ---- lighting ----
    def set_lighting(self, mode, fg, bg=(0, 0, 0), brightness=4, speed=4,
                     direction=0, full_color=0, power_on=True):
        self._write(protocol.build_light(
            int(mode), int(brightness), int(speed),
            tuple(int(c) for c in fg), tuple(int(c) for c in bg),
            int(direction), int(full_color), bool(power_on)))

    def set_per_key_rgb(self, colors_by_index, brightness=4, speed=4,
                        slot=0, cumulative=False):
        """Custom mode 10 + the cmd-9 per-key table (was Api.set_custom_colors).

        The cmd-9 table is BOARD-PERSISTENT "Per-key Paint" storage —
        CONFIRMED-BY-CAPTURE, the board served back a previous session's
        colors at mount and renders mode 10 from the stored table at
        power-on. Two flash-backed slots exist (0 = the vendor UI's
        "Custom1", 1 = "Custom2"); writing a slot also makes it the
        displayed one (the vendor switches palettes exactly this way).

        Defaults are byte-identical to the original method: slot 0,
        absolute write (keys not in `colors_by_index` go dark — the
        hardware-verified behavior every existing caller relies on).

        `cumulative=True` gives the MINI 60 HE PRO's Paint semantics
        instead: the slot's CURRENT stored table is read back first and
        only the given keys are patched (strict read-modify-write, same
        pattern as set_deadband). A failed read ABORTS before any write —
        never blind-darken the keys the user didn't touch."""
        colors = {int(k): v for k, v in (colors_by_index or {}).items()}
        if cumulative:
            base = self.read_per_key_rgb(
                slot=slot, timeout_s=self.CUSTOM_READ_TIMEOUT_S)
            base.update(colors)                       # read failure raised
            colors = base
        self._write(protocol.build_light(10, int(brightness), int(speed),
                                         (255, 255, 255)))
        for pkt in protocol.build_custom_light(colors, slot=int(slot)):
            self._write(pkt)
            time.sleep(0.005)

    def read_per_key_rgb(self, slot=0, timeout_s=1.5):
        """Read one stored per-key color slot back (cmd 9, [1]=0x80|slot;
        CONFIRMED-BY-CAPTURE framing: 8 chunks, 7x54+18 = 396 bytes).
        Returns {device index: (r, g, b)} for all 132 slots — feed it
        straight back to set_per_key_rgb()/build_custom_light() for a
        byte-exact round trip. Raises RuntimeError on an incomplete read
        (all-or-nothing, like read_macro)."""
        slot = int(slot)
        raw = self._read_paged_table(
            protocol.build_read_custom_light(slot),
            parse=lambda body: protocol.parse_custom_light_chunk(body, slot),
            total=protocol.CUSTOM_LIGHT_TABLE_BYTES,
            timeout_s=timeout_s,
            stride=protocol.CUSTOM_LIGHT_CHUNK)
        if raw is None:
            raise RuntimeError(
                "per-key color read failed (cmd 9, slot %d)" % slot)
        return protocol.custom_light_colors(raw)

    def read_active_custom_slot(self, timeout_s=1.0):
        """Which custom slot the board is currently displaying (cmd 9 sub
        0x20, the vendor's initCustomNumber — CONFIRMED-BY-CAPTURE, sent at
        every vendor mount). Returns 0 or 1; raises RuntimeError on no
        reply."""
        out = {}

        def sink(body):
            s = protocol.parse_custom_number(body)
            if s is None:
                return False
            out["slot"] = s
            return True

        if not self._read_frames(protocol.build_read_custom_number(),
                                 sink, timeout_s):
            raise RuntimeError("custom-slot read failed (cmd 9 sub 0x20)")
        return out["slot"]

    # ---- host-driven effect stream (cmd 9) ----
    def begin_host_stream(self):
        """Put the board into per-key Custom mode for the effect engine
        (full brightness — the engine bakes brightness into the colors)."""
        self._write(protocol.build_light(10, 4, 4, (255, 255, 255)))
        self._last_pkts = None

    def stream_frame(self, colors_by_index, force=False):
        """Stream one per-key RGB frame; only changed 54-byte pages are
        re-sent (diff cache) unless `force`. Holds the outer lock for the
        whole frame, exactly like the old Api._send_frame, so a set_light
        can't slip between pages and yank the board out of Custom mode."""
        try:
            pkts = protocol.build_custom_light(colors_by_index, slot=0)
            last = None if force else self._last_pkts
            with self._lock:
                for i, pkt in enumerate(pkts):
                    if last is None or i >= len(last) or pkt != last[i]:
                        self.dev.write(pkt)
            self._last_pkts = pkts
        except Exception:
            self._last_pkts = None
            raise

    # ---- actuation / trigger (cmd 33) ----
    def set_actuation(self, indices, mode, travel_mm,
                      rt_press_mm=0.0, rt_release_mm=0.0):
        self._write(protocol.build_trigger(
            int(mode), list(indices),
            float(travel_mm), float(rt_press_mm), float(rt_release_mm)))

    def read_actuation(self, keymap):
        """{key name: travel mm} via the per-key cmd33/sub5 query (holds the
        outer lock for the whole sweep, as Api.verify_actuation did)."""
        with self._lock:
            return device_state.read_actuation(self.dev, keymap)

    # ---- dead band / switch / poll ----
    def set_deadband(self, raw_by_index, top_mm=None, bottom_mm=None):
        """Per-key dead band (cmd 38) — READ-MODIFY-WRITE.

        CONFIRMED-BY-CAPTURE (webhid-capture-win60.json frames 7690-7695):
        this board's real per-key dead band is 2/2 (0.02 mm) on its 61
        physical keys and 0/0 on unpopulated slots, so the old constant
        4/5 default fill silently rewrote every key the user did NOT touch.
        We now read the current 264-byte table, patch only the requested
        indices, and write the merged table back — the same strict RMW
        pattern the MINI 60 driver uses. If the read fails, the write is
        ABORTED (RuntimeError) rather than falling back to assumed defaults.

        The pre-fix constant-fill path remains reachable for devices that
        expose no raw input handle at all (write-only stubs — a real
        AulaDevice always has one once open), and for direct
        protocol.build_deadband_table callers passing explicit defaults.
        """
        patch = dict(raw_by_index or {})
        if not self.dev.is_open():
            self.dev.open()
        if getattr(self.dev, "_dev", None) is None:
            # No readable handle: original behavior, byte-for-byte.
            for pkt in protocol.build_deadband_table(patch):
                self._write(pkt)
                time.sleep(0.005)
            return
        base = self.read_deadband_table(timeout_s=self.DEADBAND_READ_TIMEOUT_S)
        if base is None:
            raise RuntimeError(
                "dead-band read failed; aborting write (refusing to "
                "overwrite the other keys' dead bands with assumed defaults)")
        for pkt in protocol.build_deadband_table(patch, base_table=base):
            self._write(pkt)
            time.sleep(0.005)

    def read_deadband_table(self, timeout_s=1.5):
        """Read the current 264-byte per-key dead-band table (cmd 38, [1]=0).
        CONFIRMED-BY-CAPTURE framing (5 chunks, 4x58+32). Returns bytes(264)
        only if every page arrived; None otherwise."""
        raw = self._read_paged_table(
            protocol.build_read_deadband(),
            parse=protocol.parse_deadband_chunk,
            total=protocol.DEADBAND_TABLE_BYTES,
            timeout_s=timeout_s)
        return raw

    def set_switch(self, switch_by_index):
        for pkt in protocol.build_switch_table(dict(switch_by_index or {})):
            self._write(pkt)
            time.sleep(0.005)

    def set_poll_rate(self, rate):
        self._write(protocol.build_poll_rate(int(rate)))

    # ---- keymap / remap (cmd 24, both layers) ----
    def write_keymap(self, default_hids, overrides, layer_indices, fn_layer_raw):
        """Base layer with overrides, then the Fn layer replayed verbatim —
        the official driver writes both on every Apply; writing only the
        base leaves the firmware stuck in function mode. If no Fn snapshot
        exists we skip the Fn write rather than wipe the user's mappings
        with zeros (was Api._flush_remaps)."""
        for pkt in protocol.build_base_keymap_table(default_hids, overrides,
                                                    layer_indices=layer_indices):
            self._write(pkt)
            time.sleep(0.005)
        if fn_layer_raw is not None and any(fn_layer_raw):
            for pkt in protocol.build_fn_keymap_table(fn_layer_raw):
                self._write(pkt)
                time.sleep(0.005)
        else:
            log.warning("skipping Fn-layer write: no snapshot captured at connect")

    def read_keymap_layer(self, fn_layer=False, timeout_s=1.5):
        """Send initKeyValue and reassemble the 528-byte [code1, hidCode,
        code3, code4] table (cmd-24 [1]=128 base / 130 fn). Returns the
        table only if ALL pages arrived; None on a partial read so callers
        skip the Fn write instead of writing a half-zeroed table.
        (Moved verbatim from Api._read_keymap_layer.)"""
        if not self.dev.is_open():
            return None
        # Drain any pending packets first so we only see the response.
        with self.dev._lock:
            try:
                self.dev._dev.set_nonblocking(True)
                while True:
                    r = self.dev._dev.read(64)
                    if not r:
                        break
            except Exception:
                pass
        self._write(protocol.build_read_keymap_init(fn_layer=fn_layer))
        want = 130 if fn_layer else 128
        table = bytearray(528)
        seen = set()
        deadline = time.time() + timeout_s
        n_pages = (528 + 55) // 56
        while time.time() < deadline and len(seen) < n_pages:
            try:
                with self.dev._lock:
                    if not self.dev._dev:
                        break
                    self.dev._dev.set_nonblocking(True)
                    r = self.dev._dev.read(64)
            except Exception:
                break
            if not r or len(r) < 6:
                time.sleep(0.005)
                continue
            # hidapi's read on this codebase includes the report ID at r[0],
            # so the cmd byte sits at r[1]. We still scan a small offset
            # range as a safety net for hidapi variants that don't prepend.
            base = None
            for off in (1, 0, 4, 5):
                if off + 5 >= len(r):
                    continue
                if r[off] == 24 and r[off + 1] == want:
                    base = off
                    break
            if base is None:
                continue
            page = (r[base + 2] << 8) | r[base + 3]
            ln = min(r[base + 4], 56)
            data_off = base + 5
            start = page * 56
            end = start + ln
            if end > len(table):
                end = len(table)
                ln = end - start
            if ln <= 0 or data_off + ln > len(r):
                continue
            table[start:end] = bytes(r[data_off:data_off + ln])
            seen.add(page)
        complete = len(seen) >= n_pages
        log.info("keymap snapshot: layer=%s pages=%d/%d complete=%s",
                 "fn" if fn_layer else "base", len(seen), n_pages, complete)
        return bytes(table) if complete else None

    # ---- SOCD / PRCS (cmd 36) ----
    def set_socd(self, prcs_list):
        self._write(protocol.build_prcs_power(True))
        for pkt in protocol.build_prcs(list(prcs_list)):
            self._write(pkt)

    # ---- calibration ----
    def set_calibration(self, start, any_key=False):
        self._write(protocol.build_calibration(bool(start), bool(any_key)))

    def make_calibration_reader(self, keymap):
        return device_state.CalibrationReader(self.dev, keymap)

    # ---- live travel stream ----
    def make_live_reader(self, keymap, indices=None):
        return device_state.LiveReader(self.dev, keymap, indices)

    def open_trigger_test(self, indices):
        self._write(protocol.build_open_trigger_test(list(indices)))

    def close_trigger_test(self):
        self._write(protocol.build_close_trigger_test())

    # ---- misc ----
    def set_gamepad_mode(self, on):
        self._write(protocol.build_gamepad_mode(1 if on else 0))

    def set_music_rhythm(self, on):
        """Enter/leave music-rhythm state (cmd 23). CONFIRMED-BY-CAPTURE;
        the vendor driver sends OFF before every non-music light write —
        see protocol.build_music_rhythm for why Aether's light path does
        not (yet) mirror that ordering."""
        self._write(protocol.build_music_rhythm(bool(on)))

    # ---- capture-verified readers (all CONFIRMED-BY-CAPTURE framing) ----
    def _drain_input(self):
        """Discard pending input reports so a reader only sees its reply
        (same drain the keymap snapshot uses)."""
        with self.dev._lock:
            try:
                self.dev._dev.set_nonblocking(True)
                while True:
                    r = self.dev._dev.read(64)
                    if not r:
                        break
            except Exception:
                pass

    def _read_frames(self, request_pkt, sink, timeout_s):
        """Send `request_pkt`, then feed every candidate reply BODY to
        `sink(body)` until it returns True (done) or the deadline passes.
        Bodies are tried both report-id-prefixed and bare, like
        read_keymap_layer's offset scan. Returns True if sink finished."""
        if not self.dev.is_open():
            self.dev.open()
        if getattr(self.dev, "_dev", None) is None:
            return False
        self._drain_input()
        self._write(request_pkt)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                with self.dev._lock:
                    if not self.dev._dev:
                        return False
                    self.dev._dev.set_nonblocking(True)
                    r = self.dev._dev.read(64)
            except Exception:
                return False
            if not r:
                time.sleep(0.005)
                continue
            for off in (1, 0):
                if len(r) > off and sink(list(r[off:])):
                    return True
        return False

    def _read_paged_table(self, request_pkt, parse, total, timeout_s=1.5,
                          stride=58):
        """Reassemble a paged read reply (58-byte stride by default; the
        cmd-9 custom-light tables page at 54) into `total` bytes using
        `parse(body) -> {"page", "data"} | None`. Returns bytes(total)
        only when every page arrived; None on a partial read."""
        table = bytearray(total)
        seen = set()
        n_pages = (total + stride - 1) // stride

        def sink(body):
            ch = parse(body)
            if not ch:
                return False
            start = ch["page"] * stride
            data = ch["data"][:max(0, total - start)]
            if data:
                table[start:start + len(data)] = bytes(data)
                seen.add(ch["page"])
            return len(seen) >= n_pages

        done = self._read_frames(request_pkt, sink, timeout_s)
        return bytes(table) if done else None

    def device_info(self):
        """Firmware/model string + build date (cmd 13). CONFIRMED-BY-CAPTURE:
        the vendor driver requests twice at mount; reply body[3] selects the
        string (0 = firmware/model, 1 = build date). Raises RuntimeError if
        nothing answers."""
        found = {}

        def sink(body):
            p = protocol.parse_device_info(body)
            if p:
                found[p["index"]] = p["text"]
            return 0 in found and 1 in found

        for _ in range(2):
            if self._read_frames(protocol.build_device_info_query(), sink, 1.0):
                break
        if not found:
            raise RuntimeError("device-info read failed (cmd 13, no reply)")
        return {"firmware": found.get(0), "build_date": found.get(1)}

    def read_init_info(self, timeout_s=1.0):
        """Send one heartbeat (cmd 1) and decode the capability bitmask /
        battery / tri-mode reply (protocol.parse_init_info). Use these bits
        — not the static registry — to gate deadband/poll-rate/music-rhythm/
        gamepad/high-precision behavior. Returns the parsed dict, or raises
        RuntimeError on no reply."""
        out = {}

        def sink(body):
            p = protocol.parse_init_info(body)
            if p:
                out.update(p)
            return bool(p)

        if not self._read_frames(protocol.build_heartbeat(), sink, timeout_s):
            raise RuntimeError("initInfo read failed (cmd 1, no reply)")
        return out

    def read_max_trigger_travel(self, high_precision=False, timeout_s=1.0):
        """Read the device-reported travel unit / range (cmd 33 sub 4).
        On the WIN 60 HE this returns exactly Aether's hardcoded constants
        (0.01 mm / 3.40 / 0.08 — CONFIRMED-BY-CAPTURE); call it on other
        boards in the family instead of assuming. Pass is_high_precision
        from read_init_info() for the correct divisor. Raises RuntimeError
        on no reply."""
        out = {}

        def sink(body):
            p = protocol.parse_max_trigger_travel(body, high_precision)
            if p:
                out.update(p)
            return bool(p)

        if not self._read_frames(protocol.build_read_max_trigger_travel(),
                                 sink, timeout_s):
            raise RuntimeError("max-trigger-travel read failed (cmd 33 sub 4)")
        return out

    # ---- macros (cmd 25) ----
    def write_macro(self, slot, events, repeat_count=1):
        """Write one 256-byte macro slot (cmd 25, CONFIRMED-BY-CAPTURE
        format — NOT the MINI's). `events` = [(hid_code, is_down, delay_ms)].
        NOTE: the macro only fires once a key is bound to it via a keymap
        entry protocol.macro_keymap_entry(slot, hid) — a full 528-byte
        keymap rewrite, which is the caller's job (the shared BoardDriver
        macro API is tracked separately)."""
        for pkt in protocol.build_macro_packets(int(slot), events,
                                                int(repeat_count)):
            self._write(pkt)
            time.sleep(0.005)

    def read_macro(self, slot, timeout_s=1.5):
        """Read one macro slot back (cmd 25, [1]=slot|0x80). Returns
        protocol.parse_macro_table()'s dict, None for an empty slot
        (all 0xFF), and raises RuntimeError if the read didn't complete."""
        raw = self._read_paged_table(
            protocol.build_read_macro(int(slot)),
            parse=lambda body: protocol.parse_macro_chunk(body, int(slot)),
            total=protocol.MACRO_SLOT_BYTES,
            timeout_s=timeout_s)
        if raw is None:
            raise RuntimeError("macro read failed (cmd 25, slot %d)" % slot)
        return protocol.parse_macro_table(raw)
