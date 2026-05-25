"""Host-driven PER-KEY lighting effects for the Aula WIN60 HE.

The firmware's built-in effects store only ONE foreground + ONE background color,
so they can't show a multi-color palette. We drive them from the host instead:
the board's per-key RGB mode (Custom, cmd 9) lets us push an individual color to
every key, and streaming a fresh frame ~18×/second reproduces Twinkle/Wave/etc.
with the user's whole palette.

The engine composites a list of ZONES — each a subset of keys running its own
effect/palette — so different areas of the board can run different effects at
once. A single full-board effect is just one zone covering every key.

Runs only while the app is connected (the host generates each frame).
"""
import math
import random
import threading
import time

FPS = 120  # maxed for smoothness — board sustains ~1200 fps of writes, so this is
           # far under the HID limit; motion is time-based so speed is unchanged.
# Per-frame spawn probabilities (rain/twinkle/frenzy) were tuned at 30 fps; scale
# them by this so spawn DENSITY stays the same regardless of frame rate.
_SPAWN_NORM = 30.0 / FPS


def _scale(rgb, f):
    return tuple(max(0, min(255, int(c * f))) for c in rgb)


# Per-channel gamma. The LEDs drive ~linearly, but perception (and the bright
# green channel) make mid-tones read too light — e.g. orange (255,165,0) looks
# like dark yellow. Gamma-correcting the OUTPUT pulls mid values down so mixed
# colors match the swatch. Pure R/G/B (0 and 255) are unchanged.
GAMMA = 2.2
_GAMMA_LUT = [round(((i / 255.0) ** GAMMA) * 255) for i in range(256)]


def _gamma(rgb):
    return (_GAMMA_LUT[rgb[0]], _GAMMA_LUT[rgb[1]], _GAMMA_LUT[rgb[2]])


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _palette_at(pal, pos):
    """Sample a looping palette at fractional position `pos` (blends neighbours)."""
    n = len(pal)
    if n == 1:
        return pal[0]
    pos = pos % n
    i = int(pos)
    return _lerp(pal[i], pal[(i + 1) % n], pos - i)


class Zone:
    def __init__(self, indices, mode, palette, bg, speed, bright, direction, orient="v"):
        self.indices = list(indices)
        self.mode = mode
        # Gamma-correct the foreground PALETTE only (so orange etc. read right).
        # The background stays linear so a chosen bg isn't crushed to near-black.
        self.palette = [_gamma(p) for p in (palette or [(255, 255, 255)])]
        self.bg = bg or (0, 0, 0)
        self.speed = max(0.0, min(1.0, float(speed)))
        self.bright = max(0.0, min(1.0, float(bright)))
        self.direction = int(direction)
        self.orient = orient        # striation: "v" | "h" | "both"
        self.state = {}   # per-zone effect state (twinkle / fireworks)


class PerKeyEffectEngine:
    """Streams per-key color frames, compositing one or more effect zones.

    `send_frame(colors_by_index)` pushes a {device_index: (r,g,b)} frame to the
    board. Positions come from the KeyMap so spatial effects flow across the
    physical layout (normalized over the whole board, not per-zone).
    """

    def __init__(self, km, send_frame):
        self.km = km
        self._send = send_frame
        self._thread = None
        self._stop = threading.Event()
        self.zones = []
        self.base = {}            # static per-key colors under the zones
        self.global_bg = (0, 0, 0)
        self.get_depths = None    # optional () -> {device_index: mm} for reactive
        self._depths = {}
        self.get_calibrated = None  # optional () -> iterable of design codes (calibration)
        self.last_frame = {}      # most recent frame (for the in-app keyboard mirror)

        self.indices = sorted(km.by_index.keys())
        xs = [km.by_index[i]["x"] for i in self.indices]
        ys = [km.by_index[i]["y"] for i in self.indices]
        self._minx, self._maxx = min(xs), max(xs)
        self._miny, self._maxy = min(ys), max(ys)
        self._cx = (self._minx + self._maxx) / 2
        self._cy = (self._miny + self._maxy) / 2

    # normalized 0..1 position helpers (board-wide)
    def _nx(self, idx):
        w = self._maxx - self._minx or 1
        return (self.km.by_index[idx]["x"] - self._minx) / w

    def _ny(self, idx):
        h = self._maxy - self._miny or 1
        return (self.km.by_index[idx]["y"] - self._miny) / h

    def _flow(self, z, idx):
        d = z.direction
        if d in (2, 3):
            p = self._ny(idx)
            return (1 - p) if d == 2 else p
        p = self._nx(idx)
        return (1 - p) if d == 1 else p

    # ---- lifecycle ----
    def start(self, mode, palette, bg, speed, bright, direction=0, orient="v"):
        """Single full-board effect (one zone over every key)."""
        self.start_zones([{
            "indices": self.indices, "mode": mode, "palette": palette,
            "bg": bg, "speed": speed, "bright": bright, "direction": direction,
            "orient": orient,
        }], global_bg=bg, base={})

    def start_zones(self, zones, global_bg=(0, 0, 0), base=None):
        self.stop()
        self.global_bg = tuple(int(c) for c in (global_bg or (0, 0, 0))[:3])
        self.base = {int(i): tuple(int(c) for c in rgb[:3]) for i, rgb in (base or {}).items()}
        self.zones = [Zone(
            z["indices"], z["mode"],
            [tuple(int(c) for c in p[:3]) for p in (z.get("palette") or [])] or [(255, 255, 255)],
            tuple(int(c) for c in (z.get("bg") or (0, 0, 0))[:3]),
            z.get("speed", 0.5), z.get("bright", 1.0), z.get("direction", 0),
            z.get("orient", "v"),
        ) for z in zones if z.get("indices")]
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        self._thread = None

    def _run(self):
        gens = {
            "twinkle": self._g_twinkle, "wave": self._g_wave, "breath": self._g_breath,
            "ripple": self._g_ripple, "autorip": self._g_ripple, "aurora": self._g_aurora,
            "striation": self._g_striation, "radar": self._g_radar, "cross": self._g_cross,
            "fireworks": self._g_fireworks, "frenzy": self._g_frenzy,
            "reactive": self._g_reactive,
            "neon": self._g_breath, "speedres": self._g_speedres, "static": self._g_static,
            "rain": self._g_rain, "comet": self._g_comet, "tide": self._g_slopewave,
            "autorip": self._g_autorip, "striation": self._g_striation,
            "calibrate": self._g_calibrate,
        }
        t0 = time.time()
        while not self._stop.is_set():
            t = time.time() - t0
            # Live key-travel (mm) for press-reactive effects (reactive). Cheap no-op
            # callable returning {device_index: mm}; empty when no reader is attached.
            self._depths = self.get_depths() if self.get_depths else {}
            frame = {i: self.global_bg for i in self.indices}
            frame.update(self.base)
            for z in self.zones:
                gens.get(z.mode, self._g_wave)(z, t, frame)
            self.last_frame = frame   # for the in-app keyboard mirror
            try:
                self._send(frame)      # palette already gamma-corrected; bg left linear
            except Exception:
                break
            time.sleep(1.0 / FPS)

    # ---- zone generators: (zone, t, frame) -> writes frame[idx] for idx in zone ----
    def _g_static(self, z, t, frame):
        for i, idx in enumerate(z.indices):
            frame[idx] = _scale(_palette_at(z.palette, i / max(1, len(z.indices)) * len(z.palette)), z.bright)

    def _g_twinkle(self, z, t, frame):
        life = 1.4 - z.speed
        for idx in z.indices:
            if idx not in z.state and random.random() < (0.10 + z.speed * 0.35) / max(1, len(z.indices)) * 6 * _SPAWN_NORM:
                z.state[idx] = (t, random.choice(z.palette))
        for idx in z.indices:
            tw = z.state.get(idx)
            if tw:
                age = (t - tw[0]) / life
                if age >= 1.0:
                    del z.state[idx]
                    frame[idx] = _scale(z.bg, z.bright)
                else:
                    frame[idx] = _scale(_lerp(z.bg, tw[1], math.sin(age * math.pi)), z.bright)
            else:
                frame[idx] = _scale(z.bg, z.bright)

    def _g_wave(self, z, t, frame):
        flow = 0.15 + z.speed * 1.1
        span = max(1, len(z.palette))
        for idx in z.indices:
            frame[idx] = _scale(_palette_at(z.palette, self._flow(z, idx) * span + t * flow), z.bright)

    def _g_striation(self, z, t, frame):
        # Shooting stars: bright heads fly horizontally across rows leaving a
        # fading trail, in random palette colors, over the background. New stars
        # spawn on random rows; faster Speed = quicker, more frequent stars.
        # direction 1 = right->left, otherwise left->right.
        st = z.state
        if "rows" not in st:
            rows = {}
            for idx in z.indices:
                rows.setdefault(idx // 22, []).append(idx)
            st["rows"] = rows
            st["row_keys"] = list(rows.keys())
            st["last_spawn"] = t
        rows = st["rows"]
        stars = st.setdefault("stars", [])

        spawn_int = max(0.07, 0.45 - z.speed * 0.36)   # gap between new stars
        if t - st["last_spawn"] >= spawn_int:
            st["last_spawn"] = t
            stars.append([t, random.choice(st["row_keys"]), random.choice(z.palette)])

        for idx in z.indices:
            frame[idx] = _scale(z.bg, z.bright)

        vx = 0.7 + z.speed * 2.2        # board-widths / second
        trail = 0.30
        rtl = (z.direction == 1)
        alive = []
        for star in stars:
            t0, r, col = star
            head = (t - t0) * vx
            if head - trail > 1.1:
                continue
            alive.append(star)
            for idx in rows[r]:
                x = self._nx(idx)
                d = (head - (1.0 - x)) if rtl else (head - x)   # distance behind head
                if 0.0 <= d < trail:
                    g = 1.0 - d / trail
                    frame[idx] = _scale(_lerp(frame[idx], col, g * g), z.bright)
        st["stars"] = alive

    def _g_slopewave(self, z, t, frame):
        # Wave-like: vertical color bands with a slope, scrolling horizontally so
        # they read as diagonal stripes flowing across the board. Smooth (samples
        # the palette continuously), multi-color, and direction-aware. Used by
        # Striation / Tide / Auto-Ripple. Slope varies a touch per mode so they
        # aren't identical.
        slope = {"striation": 0.55, "tide": 0.30, "autorip": 0.95}.get(z.mode, 0.5)
        span = max(1, len(z.palette))
        flow = 0.35 + z.speed * 1.9
        d = z.direction
        if d in (2, 3):                       # up/down → bands flow vertically
            sign = -1 if d == 2 else 1
            for idx in z.indices:
                pos = (self._ny(idx) + slope * self._nx(idx)) * span
                frame[idx] = _scale(_palette_at(z.palette, pos + sign * t * flow), z.bright)
        else:                                 # left/right → bands flow horizontally
            sign = -1 if d == 1 else 1
            for idx in z.indices:
                pos = (self._nx(idx) + slope * self._ny(idx)) * span
                frame[idx] = _scale(_palette_at(z.palette, pos + sign * t * flow), z.bright)

    def _g_aurora(self, z, t, frame):
        # Soft diagonal palette drift fading in/out over the background.
        flow = 0.05 + z.speed * 0.4
        span = max(1, len(z.palette))
        for idx in z.indices:
            pos = (self._nx(idx) * 0.6 + self._ny(idx) * 0.4) * span + t * flow
            wob = 0.45 + 0.55 * (math.sin(t * 0.7 + self._ny(idx) * 3) * 0.5 + 0.5)
            col = _palette_at(z.palette, pos)
            frame[idx] = _scale(_lerp(z.bg, col, wob), z.bright)

    def _g_breath(self, z, t, frame):
        # Breathe between the background color and the cycling palette color, so
        # the background takes part in the breath instead of sitting static.
        base = _palette_at(z.palette, t * (0.1 + z.speed * 0.7))
        env = 0.06 + 0.94 * (math.sin(t * (0.6 + z.speed * 3.0)) * 0.5 + 0.5)
        col = _scale(_lerp(z.bg, base, env), z.bright)
        for idx in z.indices:
            frame[idx] = col

    def _g_ripple(self, z, t, frame):
        # Press-reactive: each key press spawns an expanding ring from that key.
        rips = z.state.setdefault("rips", [])
        pressed = z.state.setdefault("pressed", set())
        for idx in z.indices:
            mm = self._depths.get(idx, 0.0)
            if mm > 0.6 and idx not in pressed:
                pressed.add(idx)
                rips.append((t, self._nx(idx), self._ny(idx), random.choice(z.palette)))
            elif mm < 0.3 and idx in pressed:
                pressed.discard(idx)
        for idx in z.indices:
            frame[idx] = _scale(z.bg, z.bright)
        flow = 0.4 + z.speed * 2.5
        alive = []
        for (t0, bx, by, col) in rips:
            radius = (t - t0) * flow * 0.35
            if radius > 1.4:
                continue
            alive.append((t0, bx, by, col))
            for idx in z.indices:
                d = math.hypot(self._nx(idx) - bx, self._ny(idx) - by)
                if abs(d - radius) < 0.12:
                    g = max(0.0, 1.0 - radius / 1.4)
                    frame[idx] = _scale(_lerp(frame[idx], col, g), z.bright)
        z.state["rips"] = alive

    def _g_autorip(self, z, t, frame):
        # Auto Ripple: vertical wavefronts born at the CENTER that travel outward
        # to both sides (left & right), running across the board, then fade as they
        # reach the edges. New ripples spawn automatically; multi-color over the bg.
        # direction picks the axis/origin: default = horizontal from center;
        #   1 = horizontal toward center (edges -> middle)
        #   2 = vertical from center (out top & bottom)
        #   3 = vertical toward center
        rips = z.state.setdefault("rips", [])
        gap = max(0.7, 1.8 - z.speed * 1.0)        # fewer drops by default (pond-like)
        if t - z.state.get("last_spawn", 0.0) >= gap:
            z.state["last_spawn"] = t
            rips.append((t, random.choice(z.palette)))
        for idx in z.indices:
            frame[idx] = _scale(z.bg, z.bright)
        flow = 0.14 + z.speed * 0.7                # slower spread by default
        band = 0.21                                # wavefront ~3 keys wider (larger groups)
        vertical = z.direction in (2, 3)
        inward = z.direction in (1, 3)
        alive = []
        for (t0, col) in rips:
            r = (t - t0) * flow
            if r > 0.62:
                continue
            alive.append((t0, col))
            rr = (0.5 - r) if inward else r          # toward-center vs from-center
            g0 = max(0.0, 1.0 - r / 0.58)
            for idx in z.indices:
                p = self._ny(idx) if vertical else self._nx(idx)
                d = min(abs(p - (0.5 + rr)), abs(p - (0.5 - rr)))  # two fronts off center
                if d < band:
                    frame[idx] = _scale(_lerp(frame[idx], col, g0 * (1.0 - d / band)), z.bright)
        z.state["rips"] = alive

    def _g_speedres(self, z, t, frame):
        # Speed Respond: the board fills row-by-row along the chosen direction, and
        # the fill LEVEL rises the faster you click. Each fresh key press bumps the
        # level up; it decays continuously, so a burst of presses drives the fill
        # toward 100% (whole board lit) while idle hands let it recede to nothing.
        st = z.state
        pressed = st.setdefault("pressed", set())
        last_t = st.get("last_t", t)
        dt = max(0.0, t - last_t)
        st["last_t"] = t

        # Count NEW presses this frame (rising edges). Low threshold so even light
        # taps register (keys may be configured down near 0.1 mm actuation).
        new_hits = 0
        for idx in z.indices:
            mm = self._depths.get(idx, 0.0)
            if mm > 0.35 and idx not in pressed:
                pressed.add(idx)
                new_hits += 1
            elif mm < 0.2 and idx in pressed:
                pressed.discard(idx)

        level = st.get("level", 0.0)
        level += new_hits * (0.22 + z.speed * 0.10)     # each press builds the fill up (fast)
        level -= dt * (0.34 + (1.0 - z.speed) * 0.30)   # recedes when you stop typing
        level = max(0.0, min(1.0, level))               # more typing -> more lights
        st["level"] = level

        col = _palette_at(z.palette, t * (0.3 + z.speed))
        # Light keys whose position along the fill direction is under the level,
        # with a soft leading edge so the front row glows brighter as it advances.
        for idx in z.indices:
            p = self._flow(z, idx)        # 0..1 along the chosen direction
            if p <= level:
                edge = 1.0 - max(0.0, level - p) * 4.0   # brighter near the front
                glow = 0.55 + 0.45 * max(0.0, min(1.0, edge))
                frame[idx] = _scale(_lerp(z.bg, col, glow), z.bright)
            else:
                frame[idx] = _scale(z.bg, z.bright)

    def _g_radar(self, z, t, frame):
        spin = (0.3 + z.speed * 2.2) * (-1 if z.direction == 1 else 1)
        n = max(1, len(z.palette))
        for idx in z.indices:
            ang = math.atan2(self._ny(idx) - 0.5, self._nx(idx) - 0.5) / (2 * math.pi) + 0.5
            col = _palette_at(z.palette, ang * n)
            sweep = (ang - (t * spin) % 1.0) % 1.0
            frame[idx] = _scale(_lerp(z.bg, col, min(1.0, max(0.12, 1.0 - sweep * 3.0))), z.bright)

    def _g_cross(self, z, t, frame):
        # Press-reactive: pressing a key lights exactly ITS row and ITS column
        # (one row + one column, by device row/col index), fading over a short life.
        crosses = z.state.setdefault("crosses", [])   # (t0, prow, pcol, col)
        pressed = z.state.setdefault("pressed", set())
        for idx in z.indices:
            mm = self._depths.get(idx, 0.0)
            if mm > 0.5 and idx not in pressed:
                pressed.add(idx)
                crosses.append((t, idx // 22, idx % 22, random.choice(z.palette)))
            elif mm < 0.25 and idx in pressed:
                pressed.discard(idx)
        for idx in z.indices:
            frame[idx] = _scale(z.bg, z.bright)
        life = 0.45 + (1.0 - z.speed) * 0.7
        alive = []
        for (t0, prow, pcol, col) in crosses:
            age = (t - t0) / life
            if age >= 1.0:
                continue
            alive.append((t0, prow, pcol, col))
            g = 1.0 - age
            for idx in z.indices:
                if idx // 22 == prow or idx % 22 == pcol:
                    frame[idx] = _scale(_lerp(frame[idx], col, g), z.bright)
        z.state["crosses"] = alive

    def _g_frenzy(self, z, t, frame):
        # Automatic continuous bursts popping all over the board as expanding rings
        # of color that fade — a busy, energetic ambient effect (no key press).
        for idx in z.indices:
            frame[idx] = _scale(z.bg, z.bright)
        bursts = z.state.setdefault("bursts", [])
        if not bursts and not z.state.get("seeded"):
            z.state["seeded"] = True
            bursts.append((t, random.choice(z.palette), random.random(), random.random()))
        if random.random() < (0.22 + z.speed * 0.35) * _SPAWN_NORM:
            bursts.append((t, random.choice(z.palette), random.random(), random.random()))
        alive = []
        for (t0, col, bx, by) in bursts:
            age = (t - t0) / (0.7 + (1 - z.speed) * 0.8)
            if age >= 1.0:
                continue
            alive.append((t0, col, bx, by))
            radius = age * 0.5
            for idx in z.indices:
                d = math.hypot(self._nx(idx) - bx, self._ny(idx) - by)
                if abs(d - radius) < 0.09:
                    frame[idx] = _scale(_lerp(frame[idx], col, 1.0 - age), 1.0)
        z.state["bursts"] = alive

    def _g_fireworks(self, z, t, frame):
        # Press-reactive explosion: pressing a key detonates a burst that expands
        # outward through the surrounding keys then fades — like an explosion at
        # that key. Random palette color per press, over the background.
        bursts = z.state.setdefault("bursts", [])
        pressed = z.state.setdefault("pressed", set())
        for idx in z.indices:
            mm = self._depths.get(idx, 0.0)
            if mm > 0.5 and idx not in pressed:
                pressed.add(idx)
                bursts.append((t, random.choice(z.palette), self._nx(idx), self._ny(idx)))
            elif mm < 0.25 and idx in pressed:
                pressed.discard(idx)
        for idx in z.indices:
            frame[idx] = _scale(z.bg, z.bright)
        life = 0.6 + (1.0 - z.speed) * 0.6
        alive = []
        for (t0, col, bx, by) in bursts:
            age = (t - t0) / life
            if age >= 1.0:
                continue
            alive.append((t0, col, bx, by))
            radius = age * 0.6                  # explosion front expands outward
            fade = 1.0 - age
            for idx in z.indices:
                d = math.hypot(self._nx(idx) - bx, self._ny(idx) - by)
                if d <= radius + 0.06:
                    # bright at the wavefront, softer toward the (already-passed) core
                    edge = 1.0 - abs(d - radius) * 4.0
                    g = max(0.15 * fade, max(0.0, edge) * fade)
                    frame[idx] = _scale(_lerp(frame[idx], col, g), z.bright)
        z.state["bursts"] = alive

    def _g_rain(self, z, t, frame):
        # Matrix curtain: many columns stream downward at once, each drop a bright
        # (near-white) head with a long fading tail in a palette color. Dense spawn
        # so it reads like falling code. Spawn is FPS-independent; direction 2 = up.
        for idx in z.indices:
            frame[idx] = _scale(z.bg, z.bright)
        cols = z.state.get("cols")
        if cols is None:
            cols = {}
            for idx in z.indices:
                cols.setdefault(round(self._nx(idx) * 21), []).append(idx)  # ~per column
            for k in cols:
                cols[k].sort(key=lambda i: self._ny(i))
            z.state["cols"] = cols
        drops = z.state.setdefault("drops", [])
        fall = 2.6 + z.speed * 7.0                          # cells / second
        TRAIL = 5.0                                         # long fading tail
        if random.random() < (0.55 + z.speed * 0.9) * _SPAWN_NORM:   # dense curtain
            ck = random.choice(list(cols.keys()))
            drops.append([t, ck, random.choice(z.palette)])
        up = z.direction == 2
        alive = []
        for d in drops:
            t0, ck, col = d
            col_keys = cols[ck]
            head = (t - t0) * fall
            if head - TRAIL > len(col_keys):
                continue
            alive.append(d)
            for pos, idx in enumerate(col_keys):
                p = pos if not up else (len(col_keys) - 1 - pos)
                dist = head - p
                if 0.0 <= dist < TRAIL:
                    if dist < 0.7:                          # bright leading head
                        c = _lerp(col, (255, 255, 255), 0.6)
                        frame[idx] = _scale(c, z.bright)
                    else:                                   # fading tail
                        g = (1.0 - dist / TRAIL) ** 1.6
                        frame[idx] = _scale(_lerp(frame[idx], col, g), z.bright)
        z.state["drops"] = alive

    def _g_comet(self, z, t, frame):
        # A bright comet head sweeps across the board (direction-aware) leaving a
        # fading trail; the head color cycles through the palette each pass.
        for idx in z.indices:
            frame[idx] = _scale(z.bg, z.bright)
        speed = 0.12 + z.speed * 0.55
        head = (t * speed) % 1.0
        col = _palette_at(z.palette, t * (0.2 + z.speed * 0.8))
        tail = 0.28
        for idx in z.indices:
            p = self._flow(z, idx)
            d = (head - p) % 1.0          # distance behind the head along flow
            if d < tail:
                g = 1.0 - d / tail
                frame[idx] = _scale(_lerp(frame[idx], col, g * g), z.bright)

    def _g_tide(self, z, t, frame):
        # A waterline rises and falls; keys below it are lit in a slowly cycling
        # palette color (with a soft surface glow), keys above sit at background.
        level = math.sin(t * (0.2 + z.speed * 1.0)) * 0.5 + 0.5
        col = _palette_at(z.palette, t * (0.15 + z.speed * 0.5))
        up = z.direction != 2            # default: fills from bottom up
        for idx in z.indices:
            p = self._ny(idx)
            height = (1.0 - p) if up else p
            if height <= level:
                frame[idx] = _scale(col, z.bright)
            elif height - level < 0.10:   # surface glow band
                g = 1.0 - (height - level) / 0.10
                frame[idx] = _scale(_lerp(z.bg, col, g), z.bright)
            else:
                frame[idx] = _scale(z.bg, z.bright)

    def _g_calibrate(self, z, t, frame):
        # Calibration feedback: each calibrated key is solid green, the rest dim.
        # Kept STATIC (no per-frame animation) so the diff-based sender only writes
        # to the board when a new key is calibrated — no constant LED traffic
        # fighting the calibration reader for the device lock (avoids input lag).
        codes = self.get_calibrated() if self.get_calibrated else []
        green = (0, 255, 0)
        dim = (6, 10, 8)
        lit = set()
        for c in codes:
            idx = self.km.index_of_code.get(c)
            if idx is not None:
                lit.add(idx)
        for idx in z.indices:
            frame[idx] = green if idx in lit else dim

    def _g_reactive(self, z, t, frame):
        # Press = snap to full color, then fade out over time. Depth no longer
        # modulates brightness (which read as "dim down" while easing off the key).
        # Faster `z.speed` shortens the fade.
        n = max(1, len(z.palette))
        st = z.state                  # idx -> {"f": fade fraction, "pressed": bool}
        press_mm = 0.5                # depth at which a press fires
        release_mm = 0.25             # hysteresis so light taps still trigger once
        decay = 0.015 + z.speed * 0.04   # per-frame fade @ 120fps (~0.4..2s)
        for i, idx in enumerate(z.indices):
            mm = self._depths.get(idx, 0.0)
            s = st.get(idx) or {"f": 0.0, "pressed": False}
            if not s["pressed"] and mm >= press_mm:
                s["pressed"] = True
                s["f"] = 1.0
            elif s["pressed"] and mm < release_mm:
                s["pressed"] = False
            if not s["pressed"]:
                s["f"] = max(0.0, s["f"] - decay)
            st[idx] = s
            col = z.palette[i % n] if n > 1 else z.palette[0]
            frame[idx] = _scale(_lerp(z.bg, col, s["f"]), z.bright)


# Back-compat alias for stale imports.
EffectEngine = PerKeyEffectEngine
