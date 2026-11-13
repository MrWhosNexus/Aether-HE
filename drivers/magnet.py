"""drivers/magnet.py — Aula WIN 68 HE Max (1CA2:1901), magnet.aulastar.com protocol.

Frames come from protocol_magnet (see its docstring for provenance). What
this driver sends, by the evidence behind it:

  CONFIRMED-BY-CAPTURE (the vendor driver sent these exact frames):
    * lighting   — static colour (custom mode 21 + every key that colour),
                   per-key paint, lights off, and the firmware's effects
                   1..20 (their mode bytes; the effect NAMES are source-only
                   and labelled unverified in the registry and the UI);
    * the read REQUESTS sent at connect (hello, version, travel limits,
      lighting state, per-key properties).
  COMMUNITY-TESTED (nieruuu19: adapted from the contributor's fork, which
  its author ran on their own board; no capture):
    * the layout of every reply, so everything read back at connect;
    * lighting state preservation — a lighting write sends back the palette,
      sleep timer and colour slots the board reported instead of the
      capture's; with no usable reply the captured frame is sent unchanged;
    * a colour for an effect that is not in the board's palette rewrites
      palette slot 0;
    * actuation  — 0x23 per-key mode / actuation / rapid trigger, keeping
                   each key's advanced-key binding;
    * deadband   — 0x23 per-key press / release dead band;
    * socd       — 0x2C pairs, old pairs cleared first;
    * host_effects — the effect engine's frames go out 14 keys per 0x2A
                   frame (static paint keeps the captured one-key frame).
  SOURCE-ONLY, off unless AETHER_EXPERIMENTAL=magnet (app_web.main sets
  MagnetDriver.experimental):
    * travel_stream — 0x12 depth-matrix polling (MagnetLiveReader).

The 0x23 writes carry state the driver cannot invent (a key's advanced-key
nibble), so they REFUSE with a RuntimeError when the board's key modes could
not be read, rather than write a guess.

Keys are addressed by vendor key id = the layout's hidCode (protocol_magnet
docstring); device indices (the layout `index`) map to it through the board
keymap.
"""
import logging
import threading
import time

import device_state
import protocol_magnet as pm

from .base import BoardDriver

log = logging.getLogger(__name__)


class MagnetDriver(BoardDriver):
    FEATURES = frozenset({"lighting", "per_key_rgb", "host_effects", "actuation",
                          "actuation_read", "deadband", "socd", "device_info"})
    EXPERIMENTAL_FEATURES = frozenset({"travel_stream"})
    DEADBAND_SCOPE = "per-key"
    #: Set True only for a hardware bring-up (app_web.main, AETHER_EXPERIMENTAL=magnet).
    experimental = False
    #: How long one read request waits for its reply.
    QUERY_TIMEOUT_S = 0.2

    def __init__(self, profile, device, lock=None):
        super().__init__(profile, device, lock)
        self._key_ids = None          # device index -> vendor key id (lazy)
        self._sent = {}               # key id -> last colour streamed
        self._lights_on = True
        self._reset_board_state()

    def _reset_board_state(self):
        """Forget everything read from the board (a new handle may be a
        different board, or the same one changed by the vendor driver)."""
        self._version = None          # (major, minor, patch)
        self._limits = None           # {"precision_mm", "min_mm", "max_mm"}
        self._device_name = None
        self._global_travel_um = None
        self._light = None            # pm.parse_lighting_reply() of the board's state
        self._block = None            # palette block to send (None = the capture's)
        self._modes = {}              # key id -> (touch mode, advanced-key type)
        self._act_um = {}             # key id -> actuation, micrometres
        self._dead = {}               # key id -> (top um, bottom um) the user's dead band
        self._standard = set()        # key ids in Standard RT (press dead band pinned)

    @property
    def name(self):
        return getattr(self.profile, "name", None) or "Aula WIN 68 HE Max"

    def supports(self, feature):
        return feature in self.FEATURES or (
            self.experimental and feature in self.EXPERIMENTAL_FEATURES)

    def _require_experimental(self, feature):
        if not self.experimental:
            self._unsupported(feature)

    # ---- key identity ----
    def key_ids(self):
        """{device index: vendor key id} from the board's layout."""
        if self._key_ids is None:
            path = getattr(self.profile, "keymap", None)
            km = device_state.KeyMap(path) if path else device_state.KeyMap()
            self._key_ids = {idx: int(e["hid"]) for idx, e in km.by_index.items()
                             if int(e["hid"]) in pm.KEY_ORDER}
        return self._key_ids

    def _keys_for(self, indices):
        ids = self.key_ids()
        keys = []
        for i in (indices or ids):
            k = ids.get(int(i))
            if k is not None and k not in keys:
                keys.append(k)
        if not keys:
            raise ValueError("no valid key indices for this board")
        return keys

    # ---- frame IO ----
    def _send(self, pkt):
        self._write(pm.to_report(pkt))

    def _send_all(self, frames):
        with self._lock:
            if not self.dev.is_open():
                self.dev.open()
            for f in frames:
                self.dev.write(pm.to_report(f))

    def _query(self, pkt, accept=None):
        """Send one read request and return the body of its reply, or None.
        Reports that are not the reply (another command, a stale answer the
        `accept` test rejects) are skipped, so nothing has to be drained."""
        cmd = pkt[2]
        with self._lock:
            if not self.dev.is_open():
                self.dev.open()
            self.dev.write(pm.to_report(pkt))
            deadline = time.monotonic() + self.QUERY_TIMEOUT_S
            while time.monotonic() < deadline:
                try:
                    raw = self.dev.read_soft(65, timeout_ms=10)
                except Exception:
                    return None
                if not raw:
                    time.sleep(0.001)
                    continue
                body = pm.reply_body(raw, cmd)
                if body is not None and (accept is None or accept(body)):
                    return body
        return None

    @staticmethod
    def _rgb(c):
        return tuple(int(v) & 0xFF for v in list(c)[:3])

    # ---- connect + read-back (replies: COMMUNITY-TESTED) ----
    def connect(self):
        """Open the interface, then read what the board holds: protocol
        version, travel limits, lighting state and every key's mode,
        actuation and dead band. Only read requests are sent (all captured).
        A board that does not answer still connects: lighting falls back to
        the captured frame and the 0x23 writes refuse."""
        info = self.dev.open()
        self._reset_board_state()
        self._sent = {}
        try:
            self._read_board_state()
        except Exception as e:
            log.warning("%s: read-back failed (%s); lighting uses the captured "
                        "frame, actuation / dead band / SOCD writes will refuse",
                        self.name, e)
        return info

    def _sys(self, sub):
        return self._query(pm.build_sys_query(sub),
                           lambda b: len(b) >= 2 and b[1] == sub)

    def _read_board_state(self):
        self._send(pm.build_hello())
        body = self._sys(0x01)
        if body is None:
            log.warning("%s: no reply to the version query; nothing read back", self.name)
            return
        self._version = pm.parse_version(body)
        body = self._sys(0x25)
        self._limits = pm.parse_travel_limits(body) if body else None
        body = self._sys(0x26)
        self._device_name = pm.parse_device_name(body) if body else None
        body = self._query(pm.build_global_travel_read())
        if body and len(body) >= 5:
            self._global_travel_um = (body[3] | (body[4] << 8)) or None
        self._read_light_state()
        self._read_key_state()

    def _read_light_state(self):
        body = self._query(pm.build_lighting_read())
        st = pm.parse_lighting_reply(body) if body else None
        if st is None:
            log.info("%s: no usable lighting reply; writes use the captured palette", self.name)
            return None
        self._light = st
        self._block = st["block"]
        return st

    def _read_prop(self, prop):
        """{key id: value} of one property for all 68 keys, or None unless
        every key answered (a partial table is never used)."""
        out = {}
        frames = pm.build_key_config_read(prop)
        for n, f in enumerate(frames):
            first = pm.KEY_ORDER[n * pm.RECORDS_PER_FRAME]

            def accept(body, first=first):
                recs = pm.parse_key_config_reply(body)
                return bool(recs) and recs[0][0] == first and all(r[1] == prop for r in recs)

            body = self._query(f, accept)
            if body is None:
                return None
            for key, _prop, val in pm.parse_key_config_reply(body):
                out[key] = val
        return out if all(k in out for k in pm.KEY_ORDER) else None

    def _read_key_state(self):
        modes = self._read_prop(pm.PROP_MODE)
        if modes is None:
            log.warning("%s: key modes not read; actuation / dead band / SOCD "
                        "writes will refuse", self.name)
            return False
        self._modes = {k: pm.split_mode(v) for k, v in modes.items()}
        act = self._read_prop(pm.PROP_ACTUATION)
        top = self._read_prop(pm.PROP_DEAD_TOP)
        bottom = self._read_prop(pm.PROP_DEAD_BOTTOM)
        if act is not None:
            self._act_um = dict(act)
        if act is not None and top is not None and bottom is not None:
            self._dead, self._standard = {}, set()
            for k in pm.KEY_ORDER:
                # Standard RT is not a mode on the wire: it is rapid trigger
                # with the press dead band pinned just above the actuation
                # point. Such a key's own dead band is not on the board.
                if (self._modes[k][0] == pm.TOUCH_RAPID
                        and top[k] == pm.standard_rt_dead_um(act[k])):
                    self._standard.add(k)
                    self._dead[k] = (pm.DEAD_DEFAULT_UM, pm.dead_um(bottom[k]))
                else:
                    self._dead[k] = (pm.dead_um(top[k]), pm.dead_um(bottom[k]))
        return True

    def _require_key_modes(self, refresh=False):
        """The key-mode table connect() read. Raises RuntimeError, with no
        traffic, when the board never gave one: a 0x23 mode write without it
        would drop advanced-key bindings (reconnect to read again).
        `refresh` re-reads it first and keeps the old table if that fails."""
        if not self._modes:
            raise RuntimeError(
                f"{self.name}: the keys' current modes were not read at connect, so "
                "nothing was written (a blind write would drop SOCD / macro bindings)")
        if refresh:
            modes = self._read_prop(pm.PROP_MODE)
            if modes is not None:
                self._modes = {k: pm.split_mode(v) for k, v in modes.items()}
        return self._modes

    def _travel_range(self):
        lim = self._limits or {}
        return (lim.get("min_mm", pm.TRAVEL_MIN_MM), lim.get("max_mm", pm.TRAVEL_MAX_MM))

    def device_info(self):
        """What connect() read back (no I/O). Values are None when the board
        did not answer."""
        v = self._version
        return {"name": self._device_name or self.name,
                "protocol_version": "%d.%d.%d" % v if v else None,
                "travel_limits": dict(self._limits) if self._limits else None,
                "state_read": bool(self._modes)}

    # ---- lighting ----
    def _light_args(self):
        """The fields a lighting write must send back unchanged. Empty when
        the board's state is unknown, which builds the captured frame."""
        st = self._light
        if st is None:
            return {} if self._block is None else {"block": self._block}
        return {"block": self._block, "sleep_min": st["sleep_min"],
                "static_mode": st["static_mode"], "color_slot": st["color_slot"]}

    def _palette_slot(self, rgb):
        """The palette slot holding `rgb`. A colour the board does not store
        is written into slot 0 (COMMUNITY-TESTED palette edit; it goes out
        with the lighting write that uses it)."""
        block = self._block if self._block is not None else pm.LIGHT_BLOCK
        palette = pm.palette_from_block(block)
        if rgb in palette:
            return palette.index(rgb)
        self._block = pm.block_with_palette_slot(block, 0, rgb)
        return 0

    def _has_effect_colour(self):
        return self._light is None or self._light["color_slot"] is not None

    def set_lighting(self, mode, fg, bg=(0, 0, 0), brightness=4, speed=4,
                     direction=0, full_color=0, power_on=True):
        mode = int(mode)
        bri = max(0, min(pm.LIGHT_LEVEL_MAX, int(brightness)))
        spd = max(0, min(pm.LIGHT_LEVEL_MAX, int(speed)))
        if not power_on or bri == 0:
            self._lights_on = False
            self._send(pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=0, speed=spd,
                                         power=False, **self._light_args()))
            return
        if not 0 <= mode <= pm.LIGHT_MODE_MAX:
            self._unsupported("lighting_mode")
        rgb = self._rgb(fg or (255, 255, 255))
        if mode != pm.LIGHT_MODE_CUSTOM:
            # A firmware mode: 0 = static palette colour, 1..20 = effects.
            # The two colour fields do not share an index (static: slot 0..6,
            # 7 = spectrum; effect: 0 = spectrum, 1..7 = slot 0..6).
            if mode == pm.LIGHT_MODE_STATIC:
                static = pm.STATIC_SPECTRUM if int(full_color) else self._palette_slot(rgb)
                args = self._light_args()
                args["static_mode"] = static
            else:
                slot = None
                if self._has_effect_colour():
                    slot = (pm.EFFECT_SPECTRUM if int(full_color)
                            else self._palette_slot(rgb) + 1)
                args = self._light_args()
                args["color_slot"] = slot
            self._lights_on = True
            self._send(pm.build_lighting(mode, brightness=bri, speed=spd,
                                         direction=bool(direction), **args))
            if self._light is not None:
                self._light["static_mode"] = args.get("static_mode", self._light["static_mode"])
                self._light["color_slot"] = args.get("color_slot", self._light["color_slot"])
            self._sent = {}
            return
        self._lights_on = True
        self._send(pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=bri, speed=spd,
                                     direction=bool(direction), **self._light_args()))
        # Static colour = custom mode with every key that colour (a per-key
        # paint sent next overrides the keys it lists).
        self._send_all([pm.build_key_rgb(k, *rgb) for k in self.key_ids().values()])
        self._sent = {k: rgb for k in self.key_ids().values()}

    def set_per_key_rgb(self, colors_by_index, brightness=4, speed=4):
        """Static per-key colours ({device index: (r, g, b)}): custom mode,
        then one write per listed key (keys not listed keep their colour)."""
        ids = self.key_ids()
        writes = []
        for idx, rgb in (colors_by_index or {}).items():
            k = ids.get(int(idx))
            if k is not None and rgb is not None:
                c = self._rgb(rgb)
                writes.append(pm.build_key_rgb(k, *c))
                self._sent[k] = c
        if not writes:
            raise ValueError("no valid key indices for this board")
        bri = max(0, min(pm.LIGHT_LEVEL_MAX, int(brightness)))
        self._send(pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=bri,
                                     speed=max(0, min(pm.LIGHT_LEVEL_MAX, int(speed))),
                                     **self._light_args()))
        self._send_all(writes)

    # ---- host effect stream ----
    def begin_host_stream(self):
        """Custom mode at full brightness (the engine bakes brightness into
        its colours); forget what was sent so the first frame paints every key."""
        self._sent = {}
        self._send(pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=pm.LIGHT_LEVEL_MAX,
                                     speed=pm.LIGHT_LEVEL_MAX, **self._light_args()))

    def stream_frame(self, colors_by_index, force=False):
        """One engine frame ({device index: (r, g, b)}; unlisted keys dark).
        Only the keys whose colour changed are sent, 14 to a frame
        (COMMUNITY-TESTED batch write); `force` resends all of them."""
        ids = self.key_ids()
        want = {k: (0, 0, 0) for k in ids.values()}
        for idx, rgb in (colors_by_index or {}).items():
            k = ids.get(int(idx))
            if k is not None and rgb is not None:
                want[k] = self._rgb(rgb)
        changed = [(k, c) for k, c in want.items() if force or self._sent.get(k) != c]
        if changed:
            self._send_all(pm.build_key_rgb_batch(changed))
            self._sent.update(want)

    # ---- actuation / dead band / SOCD (COMMUNITY-TESTED 0x23 and 0x2C writes) ----
    def set_actuation(self, indices, mode, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0):
        """The app's trigger modes: 0 fixed, 12 Standard rapid trigger, 13
        Continuous rapid trigger. Fixed mode leaves the stored rapid-trigger
        pair alone. Each key keeps its advanced-key binding."""
        mode = int(mode)
        keys = self._keys_for(indices)
        modes = self._require_key_modes()
        rapid = mode != pm.MODE_FIXED
        press = (rt_press_mm or 0.05) if rapid else None
        release = (rt_release_mm or rt_press_mm or 0.05) if rapid else None
        # A key leaving Standard RT gets its own dead band back; the pinned
        # value must not stay behind.
        dead = {k: self._dead.get(k, (pm.DEAD_DEFAULT_UM, pm.DEAD_DEFAULT_UM))
                for k in keys if k in self._standard}
        lo, hi = self._travel_range()
        recs = pm.actuation_records(keys, travel_mm, mode,
                                    adv_by_key={k: modes[k][1] for k in keys},
                                    press_mm=press, release_mm=release,
                                    dead_by_key=dead, lo_mm=lo, hi_mm=hi)
        self._send_all(pm.build_key_config_write(recs))
        touch = pm.TOUCH_RAPID if rapid else pm.TOUCH_FIXED
        act = pm.mm_to_um(travel_mm, lo, hi)
        for k in keys:
            self._modes[k] = (touch, modes[k][1])
            self._act_um[k] = act
            if mode == pm.MODE_RT_STANDARD:
                self._standard.add(k)
            else:
                self._standard.discard(k)

    def read_actuation(self, keymap):
        """{key name: travel mm} read from the board now. A key in the
        board-wide touch mode reports the board-wide travel."""
        act = self._read_prop(pm.PROP_ACTUATION)
        modes = self._read_prop(pm.PROP_MODE)
        if act is None or modes is None:
            raise RuntimeError(f"{self.name}: no reply to the actuation read")
        self._act_um = dict(act)
        self._modes = {k: pm.split_mode(v) for k, v in modes.items()}
        ids = self.key_ids()
        out = {}
        for idx, entry in keymap.by_index.items():
            k = ids.get(int(idx))
            if k is None:
                continue
            um = act[k]
            if self._modes[k][0] == pm.TOUCH_GLOBAL and self._global_travel_um:
                um = self._global_travel_um
            out[entry["name"]] = round(um / 1000.0, 2)
        return out

    def set_deadband(self, raw_by_index, top_mm=None, bottom_mm=None):
        """Per-key dead band; `raw_by_index` {index: (top, bottom)} in
        0.01 mm. A key in Standard RT keeps its pinned press dead band on
        the board; the value is remembered and written when it leaves."""
        ids = self.key_ids()
        dead = {}
        for idx, (top, bottom) in (raw_by_index or {}).items():
            k = ids.get(int(idx))
            if k is not None:
                dead[k] = (pm.dead_um(round(float(top) * 10)),
                           pm.dead_um(round(float(bottom) * 10)))
        if not dead:
            raise ValueError("no valid key indices for this board")
        self._require_key_modes()
        recs = pm.deadband_records(dead, skip_top=self._standard)
        self._send_all(pm.build_key_config_write(recs))
        self._dead.update(dead)

    def set_socd(self, prcs_list):
        """[{model, key1_hid, key2_hid[, bind, delay]}] (HID usage = this
        board's key id; `model` is the app's Model 1..4). The firmware
        accumulates pairs, so every key the board reports as SOCD-bound is
        unbound first; an empty list only clears. Nothing is written unless
        every pair is valid and the key table was read."""
        pairs = []
        for p in (prcs_list or []):
            k1, k2, model = int(p["key1_hid"]), int(p["key2_hid"]), int(p["model"])
            if model not in pm.SOCD_MODELS:
                raise ValueError(f"SOCD model must be 1..4, got {model}")
            if k1 not in pm.KEY_ORDER or k2 not in pm.KEY_ORDER or k1 == k2:
                raise ValueError(f"not a key pair on this board: {k1}, {k2}")
            pairs.append((k1, k2, model, int(p.get("bind", pm.SOCD_BIND_POSITION)),
                          int(p.get("delay", 0))))
        if self._version is not None and self._version < pm.PROTOCOL_SOCD_V4:
            raise RuntimeError(
                "%s: SOCD needs protocol 1.0.7 or later, the board reports %d.%d.%d"
                % ((self.name,) + tuple(self._version)))
        with self.transaction():
            modes = dict(self._require_key_modes(refresh=True))
            clear = [(k, pm.PROP_MODE, pm.mode_value(touch, pm.ADV_NONE))
                     for k, (touch, adv) in modes.items() if adv == pm.ADV_SOCD]
            frames = pm.build_key_config_write(clear)
            frames += [pm.build_socd(k1, k2, model, bind=bind, delay_ms=delay)
                       for k1, k2, model, bind, delay in pairs]
            if frames:
                self._send_all(frames)
            for k, _prop, _val in clear:
                self._modes[k] = (modes[k][0], pm.ADV_NONE)
            for k1, k2, _model, _bind, _delay in pairs:
                for k in (k1, k2):
                    self._modes[k] = (self._modes[k][0], pm.ADV_SOCD)

    # ---- experimental (SOURCE-ONLY) ----
    def make_live_reader(self, keymap, indices=None):
        self._require_experimental("travel_stream")
        return MagnetLiveReader(self.dev, keymap, indices)


class MagnetLiveReader:
    """Polls the 0x12 depth matrix (two halves) — the LiveReader contract the
    Api and effects use: start/stop/alive/snapshot/snapshot_by_index, plus the
    on_sample(idx, mm, t) and is_key_down hooks. Every poll returns every
    key's depth, so a release is an explicit 0 (no silence heuristics)."""

    POLL_S = 1 / 60
    REPLY_TIMEOUT_S = 0.03
    NOISE_MM = 0.05

    def __init__(self, device, keymap, indices=None):
        self.dev = device
        self.km = keymap
        self.indices = list(indices) if indices else list(keymap.indices())
        self.depths = {}              # code -> mm
        self._depths_idx = {}         # device index -> mm
        self.on_sample = None
        self.is_key_down = None       # accepted for parity; not needed here
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop,),
                                        name="aether-magnet-travel", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        th = self._thread
        if th is not None and th is not threading.current_thread():
            th.join(timeout=0.5)
        self.depths.clear()
        self._depths_idx.clear()

    def alive(self):
        th = self._thread
        return th is not None and th.is_alive() and not self._stop.is_set()

    def snapshot(self):
        return dict(self.depths)

    def snapshot_by_index(self):
        return dict(self._depths_idx)

    def _read(self, timeout_ms):
        r = self.dev.read_soft(65, timeout_ms=timeout_ms)
        if r and len(r) == 65 and r[0] == pm.REPORT_ID:
            r = r[1:]
        return list(r or [])

    def poll_half(self, half):
        """One request + reassembled reply -> {device index: mm}, or None."""
        self.dev.write(pm.to_report(pm.build_travel_request(half)))
        data = []
        deadline = time.monotonic() + self.REPLY_TIMEOUT_S
        while time.monotonic() < deadline and len(data) < pm.TRAVEL_REPLY_LEN:
            r = self._read(5)
            if not r:
                continue
            if not data:
                if pm.is_travel_reply_head(r):
                    data = r
            else:
                data += r
        if len(data) < pm.TRAVEL_REPLY_LEN:
            return None
        return pm.parse_travel_reply(data, half)

    def _apply(self, by_idx, now):
        wanted = set(self.indices)
        code_of = self.km.code_of
        on_sample = self.on_sample
        for idx, mm in by_idx.items():
            if idx not in wanted:
                continue
            code = code_of(idx)
            if not code:
                continue
            prev = self._depths_idx.get(idx, 0.0)
            if mm < self.NOISE_MM:
                mm = 0.0
                self.depths.pop(code, None)
                self._depths_idx.pop(idx, None)
            else:
                self.depths[code] = mm
                self._depths_idx[idx] = mm
            if on_sample is not None and mm != prev:
                try:
                    on_sample(idx, mm, now)
                except Exception:
                    pass

    def _run(self, stop_ev):
        fails = 0
        while not stop_ev.is_set():
            t0 = time.monotonic()
            try:
                got = {}
                for half in (1, 2):
                    part = self.poll_half(half)
                    if part is not None:
                        got.update(part)
                if got:
                    self._apply(got, time.monotonic())
                    self.dev.note_rx()
                fails = 0
            except Exception as e:
                fails += 1
                if fails > 50:
                    log.warning("WIN 68 HE Max travel reader stopping: %s", e)
                    self.dev.mark_dead("travel reader: reads keep failing")
                    break
                time.sleep(0.05)
                continue
            rest = self.POLL_S - (time.monotonic() - t0)
            if rest > 0:
                stop_ev.wait(rest)
