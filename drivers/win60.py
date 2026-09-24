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

    #: Macro storage limits (cmd 25; see protocol.py's macro section).
    MACRO_SLOTS = protocol.MACRO_SLOTS
    MACRO_MAX_EVENTS = protocol.MACRO_MAX_EVENTS
    MACRO_MAX_DELAY_MS = protocol.MACRO_MAX_DELAY_MS
    MACRO_MAX_REPEAT = protocol.MACRO_MAX_REPEAT
    MACRO_PLAY_MODES = protocol.MACRO_PLAY_MODES

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
    #: Firmware slider scales when the profile declares none (the WIN 60 HE
    #: registry says 0..4 / 0..4 — re-confirmed on hardware via readLightList
    #: cmd 10, see data/board_registry.json lighting._note).
    LIGHT_BRIGHTNESS_RANGE = (0, 4)
    LIGHT_SPEED_RANGE = (0, 4)

    def _clamp_light(self, brightness, speed):
        """Clamp the cmd-7/8 brightness and speed BYTES to the board's
        registry `lighting.brightnessMin..Max` / `speedMin..Max`. The wire
        field is one byte and the builder masks with & 0xFF, so an
        unclamped 5 on a 0..4 board is an undefined step and 256 would
        silently wrap to OFF. Only the firmware paths use these units; the
        host effect engine's 0..100 brightness is baked into the streamed
        colors and never reaches this byte."""
        lt = getattr(self.profile, "lighting", None) or {}
        b_lo = int(lt.get("brightnessMin", self.LIGHT_BRIGHTNESS_RANGE[0]))
        b_hi = int(lt.get("brightnessMax", self.LIGHT_BRIGHTNESS_RANGE[1]))
        s_lo = int(lt.get("speedMin", self.LIGHT_SPEED_RANGE[0]))
        s_hi = int(lt.get("speedMax", self.LIGHT_SPEED_RANGE[1]))
        b = min(b_hi, max(b_lo, int(brightness)))
        s = min(s_hi, max(s_lo, int(speed)))
        if (b, s) != (int(brightness), int(speed)):
            log.warning("lighting brightness/speed %s/%s clamped to %d/%d "
                        "(%s registry range)", brightness, speed, b, s, self.name)
        return b, s

    def set_lighting(self, mode, fg, bg=(0, 0, 0), brightness=4, speed=4,
                     direction=0, full_color=0, power_on=True):
        brightness, speed = self._clamp_light(brightness, speed)
        self._write(protocol.build_light(
            int(mode), brightness, speed,
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
        brightness, speed = self._clamp_light(brightness, speed)
        if cumulative:
            base = self.read_per_key_rgb(
                slot=slot, timeout_s=self.CUSTOM_READ_TIMEOUT_S)
            base.update(colors)                       # read failure raised
            colors = base
        self._write(protocol.build_light(10, brightness, speed,
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
        brightness, speed = self._clamp_light(*self._full_light())
        self._write(protocol.build_light(10, brightness, speed, (255, 255, 255)))
        self._last_pkts = None

    def _full_light(self):
        """(brightnessMax, speedMax) from the registry — the byte pair that
        means "full" on THIS board (4/4 on the WIN 60 HE, unchanged)."""
        lt = getattr(self.profile, "lighting", None) or {}
        return (int(lt.get("brightnessMax", self.LIGHT_BRIGHTNESS_RANGE[1])),
                int(lt.get("speedMax", self.LIGHT_SPEED_RANGE[1])))

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
                      rt_press_mm=None, rt_release_mm=None):
        """Trigger write (cmd 33). Modes 12/13 send the given RT intervals.

        Mode 0 (fixed actuation) with the intervals left as None PRESERVES
        each key's STORED interval pair — READ-MODIFY-WRITE, the vendor's
        behavior: setAnyTriggerValue always copies key.trigger.interval1/2
        (deobfuscated.js L1532-1538), which readTriggerData filled at mount,
        so "Rapid Trigger -> OFF" goes out as mode 0 with the old RT pair
        still in place (CONFIRMED-BY-CAPTURE frame 1842: `00 ... 2c 2c 78
        78`, frame 1849: `aa aa 78 78`) and the factory pair is 1/1 (frame
        173 read-back, frame 922 `64 64 01 01`). Aether used to send 0/0
        here, which the vendor never does. Keys whose stored pair cannot be
        read back fall back to protocol.TRIGGER_DEFAULT_INTERVAL_RAW (1/1).
        Explicit intervals in mode 0 are sent exactly as given (unchanged
        byte path for callers that want that)."""
        mode = int(mode)
        idxs = [int(i) for i in indices]
        if mode == 0 and (rt_press_mm is None or rt_release_mm is None):
            self._set_fixed_preserving_intervals(idxs, float(travel_mm))
            return
        self._write(protocol.build_trigger(
            mode, idxs, float(travel_mm),
            float(rt_press_mm or 0.0), float(rt_release_mm or 0.0)))

    #: Consecutive unanswered readTriggerData queries after which the
    #: mode-0 read-back gives up (a silent board would otherwise cost
    #: 61 x TRIGGER_READ_TIMEOUT_S before the fallback write).
    TRIGGER_READ_MAX_MISSES = 3

    def _set_fixed_preserving_intervals(self, idxs, travel_mm):
        travel_raw = protocol.mm_to_raw(travel_mm)
        default = (protocol.TRIGGER_DEFAULT_INTERVAL_RAW,
                   protocol.TRIGGER_DEFAULT_INTERVAL_RAW)
        # Atomic across the read -> group -> write (see transaction()).
        with self.transaction():
            stored = {}
            if getattr(self.dev, "_dev", None) is not None:   # readable handle
                stored = self.read_trigger_config(
                    idxs, stop_after_misses=self.TRIGGER_READ_MAX_MISSES)
            missing = [i for i in idxs if i not in stored]
            if missing:
                log.warning("mode-0 trigger write: %d/%d keys did not answer "
                            "readTriggerData; using the factory RT pair %s for "
                            "them", len(missing), len(idxs), default)
            groups = {}                                    # (i1, i2) -> [idx]
            for i in idxs:
                c = stored.get(i)
                pair = (c["interval1"], c["interval2"]) if c else default
                groups.setdefault(pair, []).append(i)
            for (i1, i2), keys in groups.items():
                self._write(protocol.build_trigger_raw(0, keys, travel_raw, i1, i2))
                if len(groups) > 1:
                    time.sleep(0.005)

    #: Per-key wait for the readTriggerData reply before moving on.
    TRIGGER_READ_TIMEOUT_S = 0.04

    def read_trigger_config(self, indices, timeout_s=None, stop_after_misses=None):
        """{device index: {"mode", "travel", "interval1", "interval2"}} via
        one cmd-33 sub-5 readTriggerData query per key (raw trigger units,
        0.01 mm on this board). Holds the outer lock for the whole sweep.

        CONFIRMED-BY-CAPTURE reply layout — see protocol.parse_trigger_config.
        The previous implementation (device_state.read_actuation) matched
        raw r[5] == 5, which is the payload LENGTH byte (0x0c on this reply,
        5 only on a live travel-test frame), and decoded travel from the
        stream-frame offsets — so it either saw nothing or, with a key held
        during the sweep, reported live depth as the stored actuation.
        Replies are matched to the requested key by the echoed row/col, so a
        stale frame can never be booked against the wrong key. Keys that do
        not answer are simply absent from the result. `stop_after_misses`
        (optional) ends the sweep early after that many CONSECUTIVE
        unanswered keys — a board that is not answering at all costs one
        short timeout instead of one per key."""
        if timeout_s is None:
            timeout_s = self.TRIGGER_READ_TIMEOUT_S
        out = {}
        misses = 0
        with self._lock:
            if not self.dev.is_open():
                self.dev.open()
            self._drain_input()
            try:
                self.dev.set_nonblocking(True)
            except Exception:
                pass
            for idx in indices:
                idx = int(idx)
                try:
                    self.dev.write(protocol.build_read_trigger_config(idx))
                except Exception:
                    break
                deadline = time.time() + timeout_s
                got = False
                while time.time() < deadline:
                    try:
                        r = self.dev.read(64, timeout_ms=0)
                    except Exception:
                        return out
                    if not r:
                        time.sleep(0.001)
                        continue
                    p = None
                    for off in (1, 0):
                        if len(r) > off:
                            p = protocol.parse_trigger_config(list(r[off:]))
                            if p:
                                break
                    if p and p["index"] == idx:
                        out[idx] = {k: p[k] for k in
                                    ("mode", "travel", "interval1", "interval2")}
                        got = True
                        break
                misses = 0 if got else misses + 1
                if stop_after_misses is not None and misses >= stop_after_misses:
                    break
        return out

    def read_actuation(self, keymap):
        """{key name: travel mm} for every key in `keymap` (see
        read_trigger_config; was Api.verify_actuation)."""
        idxs = [int(k["index"]) for k in keymap.keys]
        cfg = self.read_trigger_config(idxs)
        out = {}
        for k in keymap.keys:
            c = cfg.get(int(k["index"]))
            if c is not None:
                out[k["name"]] = round(c["travel"] * protocol.TRIGGER_UNIT_MM, 2)
        return out

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
        # Atomic across the read -> patch -> write (see transaction()); a raced
        # read would let a concurrent op's snapshot clobber the merged write.
        with self.transaction():
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

    #: How long read_switch_table() waits before set_switch aborts.
    SWITCH_READ_TIMEOUT_S = 1.5

    def set_switch(self, switch_by_index):
        """Per-key switch profile (cmd 37) — READ-MODIFY-WRITE.

        The old constant fill (`default_switch=1` for every key not in the
        patch) sent HM1 to every key the user did NOT select on each apply:
        WASD -> TC1 followed by Space -> HH1 put WASD back on HM1. The
        vendor builds the table from each key's own stored switch value
        (CONFIRMED-BY-CAPTURE frames 298-301 read / 1578-1581 write), so we
        read the current 132-byte table (cmd 37 sub 2), patch only the
        requested indices, and write it back. A failed read ABORTS the
        write. Write-only stubs (no raw handle) keep the constant-fill
        behavior byte-for-byte, as set_deadband does."""
        patch = dict(switch_by_index or {})
        with self.transaction():
            if not self.dev.is_open():
                self.dev.open()
            if getattr(self.dev, "_dev", None) is None:
                for pkt in protocol.build_switch_table(patch):
                    self._write(pkt)
                    time.sleep(0.005)
                return
            base = self.read_switch_table(timeout_s=self.SWITCH_READ_TIMEOUT_S)
            if base is None:
                raise RuntimeError(
                    "switch-table read failed; aborting write (refusing to "
                    "overwrite the other keys' switch profiles with a default)")
            for pkt in protocol.build_switch_table(patch, base_table=base):
                self._write(pkt)
                time.sleep(0.005)

    def read_switch_table(self, timeout_s=1.5):
        """The board's current 132-byte per-key switch table (cmd 37 sub 2;
        CONFIRMED-BY-CAPTURE framing: 3 chunks, 58+58+16). bytes(132) only
        if every page arrived; None otherwise."""
        return self._read_paged_table(
            protocol.build_read_switch_table(),
            parse=protocol.parse_switch_chunk,
            total=protocol.SWITCH_TABLE_BYTES,
            timeout_s=timeout_s)

    def read_switch_list(self, timeout_s=1.0):
        """Switch profile ids the firmware offers (cmd 37 sub 0; the WIN 60
        HE answers [1, 2, 3, 5]). Raises RuntimeError on no reply."""
        out = {}

        def sink(body):
            ids = protocol.parse_switch_list(body)
            if ids is None:
                return False
            out["ids"] = ids
            return True

        if not self._read_frames(protocol.build_read_switch_list(), sink,
                                 timeout_s):
            raise RuntimeError("switch-list read failed (cmd 37 sub 0)")
        return out["ids"]

    def set_poll_rate(self, rate):
        self._write(protocol.build_poll_rate(int(rate)))

    # ---- keymap / remap (cmd 24, both layers) ----
    def write_keymap(self, default_hids, overrides, layer_indices, fn_layer_raw,
                     restore_indices=()):
        """Base-layer remap — READ-MODIFY-WRITE over the board's CURRENT
        table, then the Fn layer replayed, the way the official driver
        writes both layers on every Apply (writing only the base leaves the
        firmware stuck in function mode).

        The base table is read back and composed with the layout defaults
        (protocol.compose_base_keymap: an all-zero read-back entry means
        "firmware default", any other stored entry — a vendor macro binding
        `10 <hid> <slot> 00`, an advanced key, a remap made elsewhere — is
        kept verbatim, exactly as the vendor's own read handler treats it,
        deobfuscated.js L302-431). Only `overrides` ({index: hid} ->
        `[0, hid, 0, 0]`) and `restore_indices` (back to the layout default
        entry) change. CONFIRMED-BY-CAPTURE: from the factory all-zero table
        (frame 97 read-back) this reproduces the vendor's "remap Z -> B"
        write (frames 2063-2082) byte-for-byte. The old rebuild-from-layout
        path zeroed every binding Aether did not make.

        Fn layer: the board's current Fn table is preferred, else
        `fn_layer_raw` (the connect-time snapshot). If NEITHER is available
        the whole write is ABORTED before the first base packet — the old
        "skip the Fn write" behavior is exactly what left the board in Fn
        mode. An all-zero Fn table is a legitimate one and IS written (the
        vendor replays it, frames 2084-2102; the old `any()` check skipped
        it). Write-only stubs (no readable handle) keep the legacy layout
        rebuild, and still need an explicit Fn table."""
        default_hids = {int(k): int(v) for k, v in (default_hids or {}).items()}
        overrides = {int(k): int(v) for k, v in (overrides or {}).items()}
        layer_set = set(int(i) for i in (layer_indices or ()))
        restore = [int(i) for i in (restore_indices or ())
                   if int(i) in default_hids and int(i) not in overrides]

        with self.transaction():
            if not self.dev.is_open():
                self.dev.open()
            if getattr(self.dev, "_dev", None) is None:
                # No readable handle: legacy rebuild, byte-for-byte — but
                # never without the Fn layer (see above).
                if fn_layer_raw is None:
                    raise RuntimeError(
                        "no Fn-layer table available; aborting remap (the base "
                        "layer alone would leave the board stuck in Fn mode)")
                for pkt in protocol.build_base_keymap_table(
                        default_hids, overrides, layer_indices=layer_set):
                    self._write(pkt)
                    time.sleep(0.005)
                for pkt in protocol.build_fn_keymap_table(fn_layer_raw):
                    self._write(pkt)
                    time.sleep(0.005)
                return
            fn = fn_layer_raw
            if fn is None:
                fn = self.read_keymap_layer(fn_layer=True,
                                            timeout_s=self.KEYMAP_READ_TIMEOUT_S)
            if fn is None:
                raise RuntimeError(
                    "Fn-layer read failed and no connect-time snapshot exists; "
                    "aborting remap before any write (the base layer alone "
                    "would leave the board stuck in Fn mode)")

            def patch(table):
                for idx in restore:
                    off = idx * 4
                    if off + 4 <= len(table):
                        table[off:off + 4] = bytes([1 if idx in layer_set else 0,
                                                    default_hids[idx] & 0xFF, 0, 0])

            # _rmw_base_layer aborts on a failed base read before writing,
            # and with `fn` guaranteed above it can never take its skip path.
            self._rmw_base_layer(patch, default_hids, layer_set, overrides, fn)

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

    def send_raw(self, report):
        """Developer-console raw output report. Validates the shape (64
        bytes, report id 1, every value a byte) and refuses the never-send
        frames in protocol.dangerous_command_reason (factory reset, trigger
        reset, blind calibration arm) BEFORE anything reaches the wire.
        Raises ValueError (shape) / RuntimeError (guarded frame)."""
        report = list(report)
        if any((not isinstance(b, int)) or not 0 <= b <= 0xFF for b in report):
            raise ValueError("raw report bytes must be integers 0..255")
        if len(report) != 1 + protocol.BODY:
            raise ValueError("raw report must be %d bytes (report id + %d)"
                             % (1 + protocol.BODY, protocol.BODY))
        if report[0] != protocol.REPORT_ID:
            raise ValueError("%s output reports use report id %d, got %d"
                             % (self.name, protocol.REPORT_ID, report[0]))
        reason = protocol.dangerous_command_reason(report[1:])
        if reason:
            raise RuntimeError("refusing to send raw frame to %s: %s"
                               % (self.name, reason))
        self._write(report)

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

    # ---- macros (cmd 25 storage + cmd 24 type-0x10 keymap binds) ----
    # Storage format CONFIRMED-BY-CAPTURE (NOT the MINI's) — see the macro
    # section of protocol.py for the byte layout and vendor-JS citations.
    # Event tuples follow the drivers/base.py contract:
    # (delay_before_ms, hid_usage, is_down).

    #: Per-slot wait for the 5-chunk cmd-25 read reply.
    MACRO_READ_TIMEOUT_S = 1.5
    #: Wait for each keymap-layer read inside a bind/unbind RMW.
    KEYMAP_READ_TIMEOUT_S = 1.5

    @staticmethod
    def _macro_slot(index):
        idx = int(index)
        if not 0 <= idx < protocol.MACRO_SLOTS:
            raise ValueError("macro slot must be 0..%d, got %d"
                             % (protocol.MACRO_SLOTS - 1, idx))
        return idx

    def write_macro(self, index, events, play_mode=protocol.MACRO_PLAY_ONCE,
                    repeat_count=1):
        """Store `events` in macro slot `index` (5 cmd-25 pages). An empty/None
        event list writes the vendor's all-zero image, i.e. deletes the slot.
        `play_mode` is header byte 1 (protocol.MACRO_PLAY_*; only ONCE and
        REPEAT are capture-verified) and `repeat_count` the BE16 count.
        Validation (slot, event count, hid 0..255, delay 0..65535) happens in
        the builder BEFORE any byte is sent. NOTE: a macro only fires once a
        key points at the slot — see bind_macro()."""
        slot = self._macro_slot(index)
        pkts = protocol.build_macro_packets(slot, events, int(repeat_count),
                                            int(play_mode))
        with self.transaction():          # never interleave the 5 pages
            for pkt in pkts:
                self._write(pkt)
                time.sleep(0.005)

    def read_macro(self, index, timeout_s=None):
        """Read one macro slot back (cmd 25, [1]=slot|0x80). Returns
        protocol.parse_macro_table()'s dict {"slot", "play_mode",
        "repeat_count", "events"}, None for an empty slot, and raises
        RuntimeError if the 5-chunk read didn't complete."""
        slot = self._macro_slot(index)
        if timeout_s is None:
            timeout_s = self.MACRO_READ_TIMEOUT_S
        raw = self._read_paged_table(
            protocol.build_read_macro(slot),
            parse=lambda body: protocol.parse_macro_chunk(body, slot),
            total=protocol.MACRO_SLOT_BYTES,
            timeout_s=timeout_s)
        if raw is None:
            raise RuntimeError("macro read failed (cmd 25, slot %d)" % slot)
        return protocol.parse_macro_table(raw)

    def list_macros(self, timeout_s=None):
        """{slot: read_macro() dict} for every NON-empty slot — the vendor's
        initMacroValue sweep (cmd 25, [1] = 0x80..0x89). All-or-nothing:
        a slot that doesn't answer raises rather than being reported empty."""
        out = {}
        with self.transaction():
            for slot in range(protocol.MACRO_SLOTS):
                m = self.read_macro(slot, timeout_s=timeout_s)
                if m is not None:
                    out[slot] = m
        return out

    def read_macro_bindings(self, fn_layer=False, timeout_s=None):
        """{key index: macro slot} for every type-0x10 entry of a keymap
        layer (base by default). Raises RuntimeError on a partial read."""
        if timeout_s is None:
            timeout_s = self.KEYMAP_READ_TIMEOUT_S
        table = self.read_keymap_layer(fn_layer=fn_layer, timeout_s=timeout_s)
        if table is None:
            raise RuntimeError("keymap read failed (cmd 24, layer %s)"
                               % ("fn" if fn_layer else "base"))
        return protocol.parse_macro_bindings(table)

    def _rmw_base_layer(self, patch, default_hids=None, layer_indices=(),
                        overrides=None, fn_layer_raw=None):
        """Read the base keymap layer, merge it with the known defaults
        (protocol.compose_base_keymap — zero read-back entries mean
        "firmware default" on this board), apply `patch(table)`, write the
        full 528-byte base layer back and replay the Fn layer, the way the
        vendor writes both layers on every Apply (and write_keymap does —
        the base layer alone leaves the firmware stuck in Fn mode, so the
        Fn table is resolved FIRST and the whole op ABORTS before the first
        packet if neither the board's current Fn layer nor the connect-time
        snapshot is available). Atomic under transaction(); a failed base
        read likewise aborts before any write so other keys' bindings are
        never replaced by guesses. Returns the written base table."""
        with self.transaction():
            if not self.dev.is_open():
                self.dev.open()
            base = self.read_keymap_layer(fn_layer=False,
                                          timeout_s=self.KEYMAP_READ_TIMEOUT_S)
            if base is None:
                raise RuntimeError(
                    "keymap read failed; aborting write (refusing to rewrite "
                    "the base layer from assumed defaults)")
            # The board's CURRENT Fn layer is preferred over the connect-time
            # snapshot (an all-zero Fn table is legitimate and IS written —
            # the vendor replays it, capture frames 2084-2102).
            fn = self.read_keymap_layer(fn_layer=True,
                                        timeout_s=self.KEYMAP_READ_TIMEOUT_S)
            if fn is None:
                fn = fn_layer_raw
            if fn is None:
                raise RuntimeError(
                    "Fn-layer read failed and no connect-time snapshot exists; "
                    "aborting before any write (the base layer alone would "
                    "leave the board stuck in Fn mode)")
            table = protocol.compose_base_keymap(base, default_hids,
                                                 layer_indices, overrides)
            patch(table)
            for pkt in protocol.build_base_keymap_raw(table):
                self._write(pkt)
                time.sleep(0.005)
            for pkt in protocol.build_fn_keymap_table(fn):
                self._write(pkt)
                time.sleep(0.005)
            return bytes(table)

    def bind_macro(self, key_index, macro_index, play_mode=None, loop_count=None,
                   default_hids=None, layer_indices=(), overrides=None,
                   fn_layer_raw=None):
        """Point key-table record `key_index` at macro slot `macro_index`
        with the CONFIRMED-BY-CAPTURE entry [0x10, key's default hid, slot,
        0] (deobfuscated.js L1048-1052), preserving every other record via
        _rmw_base_layer. On this board the playback mode and repeat count
        live in the MACRO SLOT HEADER, not the keymap entry, so when
        `play_mode` / `loop_count` are given the slot is read back and
        rewritten with the new header (same events) first — a slot that is
        empty cannot be bound with a mode (ValueError). `default_hids` /
        `layer_indices` / `overrides` / `fn_layer_raw` are the Api's keymap
        context (see Api._keymap_context)."""
        key_index = int(key_index)
        slot = self._macro_slot(macro_index)
        if not 0 <= key_index < 132:
            raise ValueError("key index must be 0..131, got %d" % key_index)
        default_hids = dict(default_hids or {})
        with self.transaction():
            if play_mode is not None or loop_count is not None:
                cur = self.read_macro(slot)
                if cur is None:
                    raise ValueError("macro slot %d is empty; save the macro "
                                     "before binding it with a play mode" % slot)
                self.write_macro(
                    slot, cur["events"],
                    play_mode=cur["play_mode"] if play_mode is None else int(play_mode),
                    repeat_count=cur["repeat_count"] if loop_count is None else int(loop_count))

            def patch(table):
                off = key_index * 4
                hid = default_hids.get(key_index)
                if hid is None:
                    # no default known: keep whatever hid the board reports
                    hid = table[off + 1] if table[off] in (0, protocol.KEYMAP_TYPE_MACRO) else 0
                table[off:off + 4] = bytes(protocol.macro_keymap_entry(slot, hid))

            return self._rmw_base_layer(patch, default_hids, layer_indices,
                                        overrides, fn_layer_raw)

    def unbind_key(self, key_index, default_hids=None, layer_indices=(),
                   overrides=None, fn_layer_raw=None):
        """Restore key-table record `key_index` to its plain default entry
        [code1, default hid, 0, 0] — what the vendor writes when a macro is
        removed from a key (capture: M back to `00 10 00 00`). Other records
        preserved (same RMW as bind_macro)."""
        key_index = int(key_index)
        if not 0 <= key_index < 132:
            raise ValueError("key index must be 0..131, got %d" % key_index)
        default_hids = dict(default_hids or {})
        layer_set = set(layer_indices or ())

        def patch(table):
            off = key_index * 4
            hid = default_hids.get(key_index)
            if hid is None:
                hid = table[off + 1]          # keep the hid the entry carries
            table[off:off + 4] = bytes([1 if key_index in layer_set else 0,
                                        int(hid) & 0xFF, 0, 0])

        return self._rmw_base_layer(patch, default_hids, layer_indices,
                                    overrides, fn_layer_raw)
