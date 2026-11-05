"""drivers/magnet.py — Aula WIN 68 HE Max (1CA2:1901), magnet.aulastar.com protocol.

Frames come from protocol_magnet (see its docstring for provenance). This
driver only sends what a capture of the vendor driver confirms, unless the
board is in EXPERIMENTAL mode:

  always (CONFIRMED-BY-CAPTURE frames):
    * lighting   — the registry's mode 21 (static colour = custom mode +
                   every key that colour), per-key paint, lights off (power
                   flag 0); the firmware's unnamed effects 0..20 are refused;
    * per_key_rgb / host_effects — single-key 0x2A colour writes, the
                   host effect engine streams only the keys that changed.
  experimental only (SOURCE-ONLY, from the contributor fork; off by default,
  enabled for a bring-up tester by AETHER_EXPERIMENTAL=magnet, read in
  app_web.main and set on MagnetDriver.experimental):
    * actuation  — 0x23 per-key mode / actuation / rapid-trigger writes;
    * travel_stream — 0x12 depth-matrix polling (MagnetLiveReader);
    * socd       — 0x2C pairs.

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
    FEATURES = frozenset({"lighting", "per_key_rgb", "host_effects"})
    EXPERIMENTAL_FEATURES = frozenset({"actuation", "travel_stream", "socd"})
    #: Set True only for a hardware bring-up (app_web.main, AETHER_EXPERIMENTAL=magnet).
    experimental = False

    def __init__(self, profile, device, lock=None):
        super().__init__(profile, device, lock)
        self._key_ids = None          # device index -> vendor key id (lazy)
        self._sent = {}               # key id -> last colour streamed
        self._lights_on = True

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

    # ---- frame IO ----
    def _send(self, pkt):
        self._write(pm.to_report(pkt))

    def _send_all(self, frames):
        with self._lock:
            if not self.dev.is_open():
                self.dev.open()
            for f in frames:
                self.dev.write(pm.to_report(f))

    @staticmethod
    def _rgb(c):
        return tuple(int(v) & 0xFF for v in list(c)[:3])

    # ---- lighting ----
    def set_lighting(self, mode, fg, bg=(0, 0, 0), brightness=4, speed=4,
                     direction=0, full_color=0, power_on=True):
        bri = max(0, min(pm.LIGHT_LEVEL_MAX, int(brightness)))
        spd = max(0, min(pm.LIGHT_LEVEL_MAX, int(speed)))
        if not power_on or bri == 0:
            self._lights_on = False
            self._send(pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=0, speed=spd,
                                         power=False))
            return
        if int(mode) != pm.LIGHT_MODE_CUSTOM:
            # The UI sends this board's OWN registry byte; the only one
            # declared is 21 (static and custom both map to it). The
            # firmware's effects 0..20 are not named yet: refuse rather than
            # light something nobody chose.
            self._unsupported("lighting_mode")
        self._lights_on = True
        self._send(pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=bri, speed=spd,
                                     direction=bool(direction)))
        # Static colour = custom mode with every key that colour (a per-key
        # paint sent next overrides the keys it lists).
        rgb = self._rgb(fg or (255, 255, 255))
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
                                     speed=max(0, min(pm.LIGHT_LEVEL_MAX, int(speed)))))
        self._send_all(writes)

    # ---- host effect stream ----
    def begin_host_stream(self):
        """Custom mode at full brightness (the engine bakes brightness into
        its colours); forget what was sent so the first frame paints every key."""
        self._sent = {}
        self._send(pm.build_lighting(pm.LIGHT_MODE_CUSTOM, brightness=pm.LIGHT_LEVEL_MAX,
                                     speed=pm.LIGHT_LEVEL_MAX))

    def stream_frame(self, colors_by_index, force=False):
        """One engine frame ({device index: (r, g, b)}; unlisted keys dark).
        Each key costs a frame on this board (only single-key writes are
        captured), so only the keys whose colour changed are sent; `force`
        resends all of them."""
        ids = self.key_ids()
        want = {k: (0, 0, 0) for k in ids.values()}
        for idx, rgb in (colors_by_index or {}).items():
            k = ids.get(int(idx))
            if k is not None and rgb is not None:
                want[k] = self._rgb(rgb)
        frames = [pm.build_key_rgb(k, *c) for k, c in want.items()
                  if force or self._sent.get(k) != c]
        if frames:
            self._send_all(frames)
            self._sent.update(want)

    # ---- experimental (SOURCE-ONLY) ----
    def set_actuation(self, indices, mode, travel_mm, rt_press_mm=0.0, rt_release_mm=0.0):
        """Win60 trigger modes: 0 fixed, 12/13 rapid trigger (press/release)."""
        self._require_experimental("actuation")
        ids = self.key_ids()
        keys = [ids[int(i)] for i in (indices or ids) if int(i) in ids]
        if not keys:
            raise ValueError("no valid key indices for this board")
        rapid = int(mode) in (12, 13)
        recs = pm.actuation_records(keys, travel_mm, rapid=rapid,
                                    press_mm=rt_press_mm or 0.05,
                                    release_mm=rt_release_mm or rt_press_mm or 0.05)
        self._send_all(pm.build_key_config_write(recs))

    def set_socd(self, prcs_list):
        """[{model, key1_hid, key2_hid}] (HID usage = this board's key id)."""
        self._require_experimental("socd")
        frames = [pm.build_socd(int(p["key1_hid"]), int(p["key2_hid"]), int(p["model"]))
                  for p in (prcs_list or [])]
        if frames:
            self._send_all(frames)

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
