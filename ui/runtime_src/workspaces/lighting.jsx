(() => {
/* ============================================================
   Lighting workspace — window.AetherWorkspaces.LIGHTING_WIDGETS.
   Control JSX ported verbatim from the old LightingSection (sections.jsx)
   and split across four widget bodies. Color values (hex swatches, style=
   {{background:c}}, PatternPreview) are byte-identical — these are real
   device RGB values, never re-tokenized.
   ============================================================ */
const { useState, useRef, useEffect } = React;
const S = window.AetherSections || {};
const Slider = S.Slider, Chip = S.Chip, SubTabs = S.SubTabs, ToolbarButton = S.ToolbarButton;
const I = window.AetherIcons || {};
const IPlus = I.IPlus;

/* ===== shared static data (verbatim from sections.jsx) ===== */
const LIGHT_MODES = [
  { id: "wave",     label: "Wave",          icon: "〰" },
  { id: "neon",     label: "Neon",          icon: "◎" },
  { id: "radar",    label: "Radar",         icon: "◒" },
  { id: "cross",    label: "Cross",         icon: "✚" },
  { id: "breath",   label: "Breath",        icon: "○" },
  { id: "static",   label: "Static",        icon: "■" },
  { id: "aurora",   label: "Aurora",        icon: "◐" },
  { id: "ripple",   label: "Ripple",        icon: "◎" },
  { id: "twinkle",  label: "Twinkle",       icon: "✸" },
  { id: "reactive", label: "Reactive",      icon: "☼" },
  { id: "striation",label: "Striation",     icon: "⦹" },
  { id: "fireworks",label: "Fireworks",     icon: "✻" },
  { id: "frenzy",   label: "Frenzy",        icon: "✺" },
  { id: "autorip",  label: "Auto Ripple",   icon: "◈" },
  { id: "speedres", label: "Speed Respond", icon: "⦿" },
  { id: "rain",     label: "Rain",          icon: "☂" },
  { id: "comet",    label: "Comet",         icon: "☄" },
  { id: "tide",     label: "Tide",          icon: "≈" },
  { id: "custom",   label: "Custom",        icon: "◇" },
];

const ZONE_MODES = [
  { id: "twinkle", label: "Twinkle" }, { id: "wave", label: "Wave" },
  { id: "striation", label: "Striation" }, { id: "radar", label: "Radar" },
  { id: "ripple", label: "Ripple" }, { id: "cross", label: "Cross" },
  { id: "fireworks", label: "Fireworks" }, { id: "aurora", label: "Aurora" },
  { id: "breath", label: "Breath" }, { id: "static", label: "Static" },
  { id: "rain", label: "Rain" }, { id: "comet", label: "Comet" },
  { id: "tide", label: "Tide" },
];

const PRESET_PALETTES = [
  ["#9d4edd"],
  ["#00f5ff"],
  ["#ff3d6e"],
  ["#39ff8a"],
  ["#9d4edd","#00f5ff"],
  ["#ff7a59","#ffaa1f"],
  ["#ff3d6e","#ffaa1f","#39ff8a"],
  ["#ff3d6e","#ffaa1f","#39ff8a","#3b82f6"],
];

const BG_SWATCHES = ["#000000","#0b0f19","#1a0833","#001318","#0a1f10","#241400","#2a0814","#ffffff"];

/* ============================================================
   Board-awareness helpers (additive — PER_BOARD_PARITY_PLAN step 5).
   Every helper falls back to today's hardcoded behaviour when the board
   declares nothing, so the Win60 (and any unknown board) renders exactly
   as before. ctx.board is the board-context value from
   components/board-context.jsx (locked contract).
   ============================================================ */
const boardCtxOf = (ctx) =>
  (ctx && ctx.board)
  || (window.AetherBoard && window.AetherBoard.UNKNOWN_BOARD)
  || { board: null, lighting: null, actuation: null,
       cap: () => undefined, capState: () => "unknown", isSupported: () => true };

/* Icons for registry-declared firmware modes today's hardcoded grid doesn't
   know about (e.g. the HFD boards' own effect set). Fallback glyph: ▣ */
const DATA_MODE_ICONS = {
  "reactive-single": "☼", "extinguish-single": "◌", "starry-sky": "✦",
  "snowfall": "❆", "blossoming": "✻", "dynamic-breathing": "○",
  "spectrum-cycle": "◎", "color-spring": "↟", "colorful-cross": "✚",
  "drifting": "〰", "twisting-path": "∿", "double-tap": "◉",
  "ripple-spread": "◎", "flowing": "≈", "mountain-peaks": "⋀",
  "gentle-rain": "☂", "shuttle": "⇄",
};

/* Per-mode control rule from the board's registry mode table (or null). */
const modeRuleFor = (bl, id) =>
  (bl && Array.isArray(bl.modes) && bl.modes.find(m => m.id === id)) || null;

/* Build the mode grid for the active board.
   - No board lighting data  -> today's hardcoded LIGHT_MODES (fail-open).
   - hostEngine board (Win60 family) -> today's grid IS the product (host
     effects + firmware modes share it); only append registry modes the grid
     doesn't already know. For the Win60 the registry ids are a strict subset
     of LIGHT_MODES, so this returns LIGHT_MODES unchanged.
   - firmware-only board (hostEngine === false) -> the registry mode table is
     the whole truth: host-animated entries (rain/comet/tide/…) are not
     offered, because they stream per-key RGB frames from the PC and that
     path is unproven on such boards (see the note rendered under the grid). */
const modeGridFor = (bl) => {
  if (!bl || !Array.isArray(bl.modes) || bl.modes.length === 0) return LIGHT_MODES;
  if (bl.hostEngine !== false) {
    const known = new Set(LIGHT_MODES.map(m => m.id));
    const extra = bl.modes.filter(m => !known.has(m.id)).map(m => ({
      id: m.id, label: m.name || m.id, icon: DATA_MODE_ICONS[m.id] || "▣",
    }));
    return extra.length ? LIGHT_MODES.concat(extra) : LIGHT_MODES;
  }
  return bl.modes.map(m => {
    const legacy = LIGHT_MODES.find(x => x.id === m.id);
    return {
      id: m.id,
      label: m.name || (legacy && legacy.label) || m.id,
      icon: DATA_MODE_ICONS[m.id] || (legacy && legacy.icon) || "▣",
    };
  });
};

/* ============================================================
   Host-engine frame-rate awareness (additive).
   The host effect engine runs at 60 fps (effects.FPS — a 120 bump was
   reverted because it saturated the USB pipe; keep the constant below in
   step with effects.FPS). A board that sustains the per-key stream at a
   lower rate declares `hostEngineMaxFps` in its registry lighting block
   (e.g. the MINI 60 HE PRO: measured 28). A MISSING hostEngineMaxFps means
   "no cap / full speed", so a board that does not declare it — and the
   fail-open no-board path — renders exactly as today.

   Motion-rate classification is owned HERE (the registry does not carry
   it). Press-reactive effects need live key travel and fast response, so
   they read as choppy on a low-fps board; the ambient/slow set looks right
   even at ~28 fps. From CLAUDE.md + effects.py:
     press-reactive: reactive, ripple, speedres, cross, fireworks
     ambient/slow:   rain, aurora, autorip, striation, twinkle, breath,
                     frenzy, comet, tide
   wave / neon / radar are classified ambient here as well (slow sweeps /
   pulses, no press input); static has no motion; custom is the zone
   container (its zone modes carry the same ≈ marker in the Effect Preview
   widget — the fps fact itself is stated ONCE, under the mode grid). */
const HOST_ENGINE_TARGET_FPS = 60;
const HOST_FX_FAST = new Set(["reactive", "ripple", "speedres", "cross", "fireworks"]);
/* Declared cap in fps, or null when the board declares none (= full speed). */
const hostFpsCapOf = (bl) =>
  (bl && bl.hostEngine !== false && typeof bl.hostEngineMaxFps === "number" && bl.hostEngineMaxFps > 0)
    ? bl.hostEngineMaxFps : null;
/* The cap, but only when it is meaningfully below the engine target
   (< 75% of 60 fps) — otherwise null, i.e. nothing worth surfacing. */
const hostFpsLimited = (bl) => {
  const cap = hostFpsCapOf(bl);
  return cap != null && cap < HOST_ENGINE_TARGET_FPS * 0.75 ? cap : null;
};

/* ============================================================
   Per-board lighting dispatch (firmware set_light vs host start_multicolor).

   THE BUG THIS FIXES: app.jsx used to decide with
       useHost = power && !fullColor && pattern !== "static";
       else set_light(MODE_BYTE[pattern] ?? 0, ...)
   where MODE_BYTE is the hardcoded Win60 cmd-7 table. On any other board that
   is wrong twice over: the board's own firmware modes (e.g. the MINI 60 HE
   PRO's starry-sky/snowfall/...) are missing from that table, so `?? 0`
   silently sends byte 0 — which on the MINI means LIGHTS OFF — and shared ids
   resolve to the WRONG byte (static is 0 on the Win60 but 1 on the MINI).

   THE RULE LANDED HERE (single source of truth, used by app.jsx at send time
   and by the verification harness against raw registry data):
     1. Boards with a registry mode table (board.lighting.modes) resolve the
        selected id against THAT table. While powered and not in Full-RGB, an
        id the host engine can generate (HOST_FX_IDS == effects.py's table)
        runs on the host when the board allows it (hostEngine !== false) —
        the exact precedence the shipped Win60 build has always used.
        Everything else is a firmware set_light with THIS board's byte.
     2. An unknown id NEVER falls back to `?? 0`: it resolves to the board's
        own declared static mode (never a byte that can mean OFF) and carries
        a `notice` string so the UI can say so out loud.
     3. Power-off prefers the board's declared offModeByte (MINI: 0). Boards
        that don't declare one (Win60) keep today's byte-identical behaviour:
        the resolved mode byte with the power flag low.
     4. Per-mode registry rules are honoured when building the set_light args:
        brightness/speed scale to the board's brightnessMax/speedMax (Win60
        4 == the legacy constants, so its bytes are unchanged; MINI is 0..5),
        and a `direction: true` rule (2-way byte) clamps the 4-way dial to 0/1.
     5. No registry table at all (no bridge / no board data) -> call:"legacy",
        and app.jsx falls through to exactly today's shipped code path.
   ============================================================ */
/* Host-engine effect generators that exist in effects.py (its `gens` table),
   minus the internal 'static'/'calibrate' entries — static dispatches to
   firmware (today's rule) and calibrate is engine-internal. Keep in step with
   effects.py; ids sent to start_multicolor MUST come from this set so the
   engine never silently falls back on an id it doesn't know. */
const HOST_FX_IDS = new Set([
  "wave", "neon", "radar", "cross", "breath", "aurora", "ripple", "twinkle",
  "reactive", "striation", "fireworks", "frenzy", "autorip", "speedres",
  "rain", "comet", "tide",
]);

/* Local copies of app.jsx's color/step helpers (this file loads first, so it
   cannot import them; keep in step). briByteFor/spdByteFor generalise the
   legacy briByte/spdByte to a per-board max — with max 4 they are the same
   function, so Win60 bytes are provably unchanged. */
const hexToRgb = (hex) => {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 0, 0];
};
const briByteFor = (pct, max) => (pct <= 0 ? 0 : Math.max(1, Math.min(max, Math.ceil((pct / 100) * max))));
const spdByteFor = (pct, max) => Math.max(1, Math.min(max, Math.round((pct / 100) * (max - 1)) + 1));

/* resolveLightDispatch(bl, {pattern, power, fullColor}) -> decision.
   bl = board.lighting (registry block) or null. Returns one of:
     { call:"legacy" }                          no mode table -> today's code
     { call:"host", id }                        start_multicolor(id, ...)
     { call:"fw", byte, rule, off? , fallback?, reason? }
                                                set_light(byte, ...) with THIS
                                                board's byte; `fallback` marks
                                                the honest static substitution */
const resolveLightDispatch = (bl, { pattern, power, fullColor }) => {
  const modes = (bl && Array.isArray(bl.modes) && bl.modes.length) ? bl.modes : null;
  if (!modes) return { call: "legacy" };
  const rule = modes.find(m => m.id === pattern) || null;
  const hostOk = bl.hostEngine !== false;
  if (power && !fullColor && pattern !== "static" && hostOk && HOST_FX_IDS.has(pattern))
    return { call: "host", id: pattern };
  if (!power && bl.offModeByte != null)
    return { call: "fw", byte: bl.offModeByte, rule: null, off: true };
  if (rule) return { call: "fw", byte: rule.byte, rule };
  // Unknown on this board (or a host-only id while Full-RGB / host-less):
  // NEVER guess a raw byte — 0 means OFF on some boards. Fall back to the
  // board's own declared static mode. (On the Win60 static IS byte 0, so the
  // legacy `?? 0` bytes are reproduced exactly there.)
  const off = bl.offModeByte;
  const fb = modes.find(m => m.id === "static")
          || modes.find(m => off == null || m.byte !== off) || modes[0];
  return { call: "fw", byte: fb.byte, rule: fb, fallback: "static",
           reason: `"${pattern}" is not available on this board` };
};

/* buildLightCalls(bl, s) -> null | { dispatch, notice, calls:[[api, ...args]] }.
   The COMPLETE per-board send for one lighting state — app.jsx executes the
   list verbatim; the harness asserts it against every board's registry data.
   s: { pattern, power, fullColor, colors:[hex], bgColor:hex, brightness,
        speed, direction, striOrient }. Returns null for call:"legacy" (the
   caller keeps today's exact MODE_BYTE code path). */
const buildLightCalls = (bl, s) => {
  const d = resolveLightDispatch(bl, s);
  if (d.call === "legacy") return null;
  if (d.call === "host") {
    return { dispatch: d, notice: null, calls: [
      ["start_multicolor", d.id, (s.colors || []).map(hexToRgb), hexToRgb(s.bgColor),
       s.brightness, s.speed, s.direction, s.striOrient],
    ] };
  }
  const briMax = bl.brightnessMax || 4;
  const spdMax = bl.speedMax || 4;
  const [r, g, b] = hexToRgb((s.colors && s.colors[0]) || "#ffffff");
  const [br, bg2, bb] = hexToRgb(s.bgColor);
  // 2-way direction rule (registry `direction: true`): the firmware takes a
  // plain 0/1 byte, so clamp the 4-way dial value. Directional *kinds*
  // ("lr"/"all"/...) and rule-less modes pass the dial byte through untouched
  // (the Win60's rules are all kinds or absent -> byte-identical).
  const dirOut = (d.rule && d.rule.direction === true) ? (s.direction === 1 ? 1 : 0) : s.direction;
  return {
    dispatch: d,
    // Only the powered, non-Full-RGB substitution is worth saying out loud:
    // power-off lands on off/static intentionally, and Full-RGB over a
    // host-only id has always quietly used the static slot (Win60 shipped
    // behaviour — keep it silent there too).
    notice: (d.fallback && s.power && !s.fullColor)
      ? `${d.reason} — showing ${(d.rule && d.rule.name) || "Static"} instead`
      : null,
    calls: [
      ["stop_multicolor"],
      ["set_light", d.byte, r, g, b, briByteFor(s.brightness, briMax),
       spdByteFor(s.speed, spdMax), br, bg2, bb, dirOut, s.power, s.fullColor ? 1 : 0],
    ],
  };
};

/* ============================================================
   Schematic-preview color honesty (the "yellow in my purple twinkle" fix).

   previewSimColor(bl, s, idx) -> the hex color the Live Keyboard's STATIC
   fallback schematic paints on flat key index `idx` whenever there is no
   live host frame to mirror (board-firmware effects, disconnected, engine
   stopped). app.jsx's ledMap memo calls this per key.

   THE BUG THIS FIXES: the old inline sim painted EVERY non-static pattern as
       hit ? colors[idx % colors.length] : bgColor
   i.e. it scattered the WHOLE palette across the board. A mode that
   dispatches to the board's own firmware (the MINI 60 HE PRO's
   starry-sky/snowfall/... and everything on a firmware-only board) only ever
   receives colors[0] + bgColor — set_light carries ONE foreground. So the
   schematic showed palette slots the effect can never display; with the
   out-of-the-box palette seed (which contains #ffd400) a purple firmware
   twinkle over white gained a literal YELLOW key that exists nowhere on the
   hardware. Modes whose registry rule says `color: false` are worse: the
   firmware picks its own colors, so ANY foreground we draw is a guess —
   only the user's background is honest.

   Legacy grid ids on host-engine boards (the whole shipped Win60 surface,
   and the no-board fail-open path) keep the old scatter BYTE-IDENTICAL:
   the fw branch below only fires where resolveLightDispatch sends the
   powered pattern to firmware — ids beyond the legacy grid, or any id on a
   hostEngine:false board — never for static/custom. */
const previewSimColor = (bl, s, idx) => {
  const colors = s.colors || [];
  if (s.pattern === "static") return colors[0];
  const rule = modeRuleFor(bl, s.pattern);
  const legacyId = LIGHT_MODES.some(m => m.id === s.pattern);
  if (rule && s.pattern !== "custom" && (!legacyId || bl.hostEngine === false)) {
    if (rule.color === false) return s.bgColor;           // firmware-chosen colors — show only the user's bg
    return idx % 6 === 0 ? (colors[0] || "#ffffff") : s.bgColor;  // exactly the fg byte sent (buildLightCalls)
  }
  const hit = (idx % 6 === 0) || colors.length === 1;
  return hit ? colors[idx % colors.length] : s.bgColor;
};

/* PatternPreview — verbatim from sections.jsx (real RGB color prop). */
const PatternPreview = ({ kind, color }) => (
  <svg viewBox="0 0 100 30" className="w-full h-8 mt-3" preserveAspectRatio="none">
    {kind === "static" && Array.from({length: 8}).map((_,i) => (
      <rect key={i} x={i*13+2} y={6} width="10" height="18" rx="2" fill={color} opacity="0.7"/>
    ))}
    {kind === "wave" && Array.from({length: 8}).map((_,i) => (
      <rect key={i} x={i*13+2} y={6} width="10" height="18" rx="2" fill={color} opacity={0.2 + (Math.sin(i)+1)*0.4}/>
    ))}
    {kind === "react" && Array.from({length: 8}).map((_,i) => (
      <rect key={i} x={i*13+2} y={6} width="10" height="18" rx="2" fill={color} opacity={i === 3 ? 1 : 0.15}/>
    ))}
    {kind === "ripple" && [10, 18, 26].map((r,i) => (
      <circle key={i} cx="50" cy="15" r={r} fill="none" stroke={color} strokeWidth="0.8" opacity={1 - i*0.3}/>
    ))}
    {kind === "breathe" && (
      <rect x="2" y="6" width="96" height="18" rx="3" fill={color} opacity="0.5"/>
    )}
    {kind === "rain" && Array.from({length: 6}).map((_,i) => (
      <line key={i} x1={i*18+8} x2={i*18+8} y1={i*4} y2={i*4+12} stroke={color} strokeWidth="1.5"/>
    ))}
  </svg>
);

/* Preview "kind" for a given firmware pattern id (best-effort mapping). */
const previewKindFor = (pattern) => {
  if (pattern === "static") return "static";
  if (pattern === "wave" || pattern === "aurora" || pattern === "tide" || pattern === "comet") return "wave";
  if (pattern === "reactive" || pattern === "cross" || pattern === "speedres") return "react";
  if (pattern === "ripple" || pattern === "autorip" || pattern === "radar") return "ripple";
  if (pattern === "breath" || pattern === "neon") return "breathe";
  if (pattern === "rain" || pattern === "twinkle" || pattern === "fireworks" || pattern === "frenzy" || pattern === "striation") return "rain";
  return "static";
};

/* ===== Effect zones panel (custom mode) — verbatim behavior from sections.jsx.
   `degraded` (Set|null): press-reactive mode ids to mark ≈ on fps-capped boards —
   same marker idiom as the Mode Picker grid, whose footnote explains it. Null on
   uncapped boards, so labels render exactly as before. ===== */
const ZonesPanel = ({ zones, selectedKeys, onAdd, onUpdate, onRemove, degraded }) => (
  <div className="glass p-4">
    <div className="flex items-center justify-between mb-3">
      <div>
        <div className="font-display text-[12px] uppercase tracking-[0.18em] text-[var(--text)]">Effect Zones</div>
        <div className="font-mono text-[10px] text-[var(--text-faint)] mt-0.5">Select keys on the board, add a zone, give it its own effect</div>
      </div>
      <button onClick={onAdd} disabled={!selectedKeys || selectedKeys.size === 0}
        className="px-2.5 h-8 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] disabled:opacity-40 font-display text-[10.5px] uppercase tracking-[0.16em]">
        + Zone ({selectedKeys?.size ?? 0})
      </button>
    </div>
    {(!zones || zones.length === 0) && (
      <div className="font-mono text-[11px] text-[var(--text-faint)]">No zones yet — select keys, then click "+ Zone". Keys outside every zone stay off.</div>
    )}
    <div className="flex flex-col gap-2">
      {(zones || []).map(z => (
        <div key={z.id} className="rounded-lg border border-[var(--line)] bg-[rgba(5,11,14,0.35)] p-2.5">
          <div className="flex items-center gap-2 mb-2">
            <select value={z.mode} onChange={(e) => onUpdate(z.id, { mode: e.target.value })}
              className="flex-1 h-8 rounded-md bg-[rgba(5,11,14,0.5)] border border-[var(--line)] text-[var(--text)] font-display text-[11px] uppercase tracking-[0.12em] px-2 outline-none">
              {ZONE_MODES.map(m => <option key={m.id} value={m.id}>{degraded && degraded.has(m.id) ? m.label + " ≈" : m.label}</option>)}
            </select>
            <span className="font-mono text-[10px] text-[var(--text-faint)] whitespace-nowrap">{z.codes.length} keys</span>
            <button onClick={() => onRemove(z.id)} title="Remove zone"
              className="w-7 h-7 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-rose-300 hover:border-rose-400/40">✕</button>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              {(z.colors || []).map((c, i) => (
                <div key={i} className="relative w-7 h-7">
                  <div className="w-full h-full rounded-md ring-1 ring-white/10" style={{ background: c }}>
                    <input type="color" value={c}
                      onChange={(e) => { const cs = [...z.colors]; cs[i] = e.target.value; onUpdate(z.id, { colors: cs }); }}
                      className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"/>
                  </div>
                  {z.colors.length > 1 && (
                    <button onClick={() => onUpdate(z.id, { colors: z.colors.filter((_, j) => j !== i) })}
                      className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-slate-900 ring-1 ring-white/20 text-[var(--text-dim)] hover:text-rose-300 grid place-items-center text-[9px]">✕</button>
                  )}
                </div>
              ))}
              {(z.colors || []).length < 4 && (
                <button onClick={() => onUpdate(z.id, { colors: [...(z.colors || []), "#ffffff"] })}
                  className="w-7 h-7 rounded-md border-2 border-dashed border-[var(--line)] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] grid place-items-center text-[12px]">+</button>
              )}
            </div>
            <div className="flex-1 flex items-center gap-2">
              <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]">Spd</span>
              <input type="range" className="aether flex-1" min={0} max={100} step={1}
                value={z.speed != null ? z.speed : 60} style={{ "--pct": (z.speed != null ? z.speed : 60) + "%" }}
                onChange={(e) => onUpdate(z.id, { speed: parseFloat(e.target.value) })}/>
            </div>
          </div>
        </div>
      ))}
    </div>
  </div>
);

/* ============================================================
   Widget 1 — Mode Picker: firmware pattern grid, power/full-RGB,
   brightness/speed sliders, direction, striation orientation.
   ============================================================ */
/* DirectionDial — an angle picker for effect flow direction. The firmware
   supports 4 cardinal directions (right0 left1 up2 down3), so the dial snaps
   to the nearest. Drag or click anywhere on the ring to set the angle. */
const DIR_BYTE_AT = [0, 2, 1, 3];                 // round(angle/90)%4 -> byte
const DIR_ANGLE_OF = { 0: 0, 2: 90, 1: 180, 3: 270 };
const DIR_NAME = { 0: "Right", 1: "Left", 2: "Up", 3: "Down" };
function DirectionDial({ direction, setDirection }) {
  const ref = useRef(null);
  const angle = DIR_ANGLE_OF[direction] != null ? DIR_ANGLE_OF[direction] : 0;
  const pick = (e) => {
    const el = ref.current; if (!el) return;
    const r = el.getBoundingClientRect();
    let a = Math.atan2((r.top + r.height / 2) - e.clientY, e.clientX - (r.left + r.width / 2)) * 180 / Math.PI;
    if (a < 0) a += 360;
    setDirection(DIR_BYTE_AT[Math.round(a / 90) % 4]);
  };
  const marks = [
    ["→", 0, { right: 6, top: "50%", transform: "translateY(-50%)" }],
    ["↑", 2, { top: 6, left: "50%", transform: "translateX(-50%)" }],
    ["←", 1, { left: 6, top: "50%", transform: "translateY(-50%)" }],
    ["↓", 3, { bottom: 6, left: "50%", transform: "translateX(-50%)" }],
  ];
  return (
    <div className="flex items-center gap-4">
      <div ref={ref} onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pick(e); }}
           onPointerMove={(e) => e.buttons && pick(e)}
           style={{ width: 112, height: 112, cursor: "pointer", touchAction: "none" }}
           className="relative rounded-full border border-[var(--line)] bg-white/[0.02]">
        {marks.map(([glyph, byte, css]) => (
          <span key={byte} style={{
            position: "absolute", fontSize: 11, ...css,
            color: direction === byte ? "var(--accent)" : "var(--text-faint)",
          }}>{glyph}</span>
        ))}
        {/* pointer arm */}
        <div style={{
          position: "absolute", left: "50%", top: "50%", width: 44, height: 3, borderRadius: 3,
          background: "linear-gradient(90deg, transparent, var(--accent))",
          transformOrigin: "left center", transform: `rotate(${-angle}deg)`,
          boxShadow: "0 0 10px var(--accent-glow)", transition: "transform 0.2s var(--ease-out)"
        }} />
        <div style={{ position: "absolute", left: "50%", top: "50%", width: 8, height: 8, marginLeft: -4, marginTop: -4, borderRadius: "50%", background: "var(--accent)" }} />
      </div>
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-faint)]">Angle</div>
        <div className="font-title text-[20px] text-[var(--text)] leading-tight">{DIR_NAME[direction] || "Right"}</div>
        <div className="font-mono text-[10px] text-[var(--text-faint)] mt-0.5">{angle}° · snaps to 4-way</div>
      </div>
    </div>
  );
}

/* Two-way direction toggle — for firmware-only boards whose registry declares
   `direction: true` (a plain 0/1 byte) for the current mode. Boards with a
   directional *kind* ("lr"/"ud"/…) keep the DirectionDial. */
function DirectionToggle({ direction, setDirection }) {
  return (
    <div className="grid grid-cols-2 gap-1.5 max-w-[260px]">
      {[["Forward", 0, "→"], ["Reverse", 1, "←"]].map(([lbl, val, ic]) => {
        const active = (direction === 1 ? 1 : 0) === val;
        return (
          <button key={val} onClick={() => setDirection(val)}
            className={`h-9 rounded-lg border text-[11px] uppercase tracking-[0.12em] flex items-center justify-center gap-1.5 transition-all
                        ${active
                          ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)]"
                          : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
            <span className="text-[14px]">{ic}</span>{lbl}
          </button>
        );
      })}
    </div>
  );
}

function ModePickerWidget(ctx) {
  const {
    pattern, setPattern, brightness, setBrightness, speed, setSpeed,
    power, setPower, fullColor, setFullColor, direction, setDirection,
    striOrient, setStriOrient,
  } = ctx;
  const fullColorOk = pattern !== "static" && pattern !== "custom";

  /* Board awareness (additive). firmwareOnly === false for the Win60 (its
     registry sets hostEngine true) and whenever no board data is available,
     so every branch below falls back to today's exact rendering. */
  const bctx = boardCtxOf(ctx);
  const bl = bctx.lighting;
  const boardName = (bctx.board && bctx.board.name) || "this board";
  const modeGrid = modeGridFor(bl);
  const firmwareOnly = !!bl && bl.hostEngine === false;
  const rule = firmwareOnly ? modeRuleFor(bl, pattern) : null;
  // A host-engine board's OWN firmware mode beyond the legacy grid (e.g. the
  // MINI's starry-sky): its registry rule drives the direction control below.
  // null for every legacy grid id and whenever there is no board data, so the
  // Win60 (whose ids are all legacy) renders exactly as before.
  const hfdRule = (!firmwareOnly && bl && !LIGHT_MODES.some(m => m.id === pattern))
    ? modeRuleFor(bl, pattern) : null;
  // Discrete firmware brightness/speed levels — only on firmware-only boards
  // (on host-engine boards the % is genuinely continuous in the host engine).
  const briMax = (firmwareOnly && bl.brightnessMax) || 0;
  const spdMax = (firmwareOnly && bl.speedMax) || 0;
  const speedOff = !!(firmwareOnly && rule && rule.speed === false);
  // Host-engine fps cap — null unless the board declares one meaningfully
  // below the 60fps engine rate (missing hostEngineMaxFps => null => no change).
  const fpsCap = !firmwareOnly ? hostFpsLimited(bl) : null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-end gap-4 mb-1">
        {fullColorOk && (
          <div className="flex items-center gap-2" title="Cycle the full RGB spectrum (rainbow) instead of the chosen colors">
            <span className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Full RGB</span>
            <button onClick={() => setFullColor(!fullColor)}
              className={`relative w-10 h-5 rounded-full border transition-colors
                          ${fullColor ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-[var(--line)]"}`}>
              <span className={`absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                                ${fullColor ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`}/>
            </button>
          </div>
        )}
        <div className="flex items-center gap-2">
          <span className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Power</span>
          <button onClick={() => setPower(!power)}
            className={`relative w-10 h-5 rounded-full border transition-colors
                        ${power ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-[var(--line)]"}`}>
            <span className={`absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                              ${power ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`}/>
          </button>
        </div>
      </div>

      <div>
        <div className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2">Light Mode</div>
        <div className="grid grid-cols-3 gap-1.5">
          {modeGrid.map(m => {
            const active = pattern === m.id;
            // Press-reactive host effect on a low-fps board: mark it (≈) so the
            // footnote below can be specific. degraded is always false when the
            // board declares no cap, so nothing changes on such boards.
            const degraded = fpsCap != null && HOST_FX_FAST.has(m.id);
            return (
              <button key={m.id} onClick={() => setPattern(m.id)}
                title={degraded ? `Press-reactive — ${boardName} sustains ~${fpsCap} fps, so this effect will look choppy` : undefined}
                className={`h-9 rounded-lg border font-display text-[11px] tracking-[0.06em] flex items-center justify-center gap-1.5 transition-all
                            ${active
                              ? "border-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]"
                              : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}
                style={ active ? { background: "var(--accent-gradient, var(--accent))" } : {} }>
                <span className="text-[12px]">{m.icon}</span> {m.label}
                {degraded && <span className="font-mono text-[9px] opacity-70">≈</span>}
              </button>
            );
          })}
        </div>
        {firmwareOnly && (
          <div className="mt-2 font-mono text-[10px] text-[var(--text-faint)] leading-relaxed">
            This is {boardName}'s own firmware effect set. Aether's host-animated effects
            (Rain, Comet, Tide, Aurora and the rest) stream per-key RGB frames from the PC,
            and that streaming path is not yet proven on this board — so they are not
            offered. Static per-key painting still works.
          </div>
        )}
        {/* The ~fps fact is stated once, here; everywhere else it is only the
            ≈ marker (grid buttons, zone modes) with a tooltip on the buttons. */}
        {fpsCap != null && (
          <div className="mt-2 font-mono text-[10px] text-[var(--text-faint)] leading-relaxed">
            Host-animated effects stream from this PC at ~{fpsCap} fps on {boardName} (engine
            target ~{HOST_ENGINE_TARGET_FPS} fps). Ambient effects like Rain, Aurora, Comet
            and Tide look right at that rate; press-reactive effects — marked ≈ — need
            faster updates and will look choppy.
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-5">
        <div>
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Brightness</span>
            <span className="font-mono text-[12px] text-[var(--accent)]">
              {briMax > 0 ? `${Math.round((brightness / 100) * briMax)} / ${briMax}` : <>{Math.round(brightness)}%</>}
            </span>
          </div>
          <input type="range" className="aether w-full"
            min={0} max={100} step={briMax > 0 ? 100 / briMax : 1} value={brightness}
            style={{ "--pct": brightness + "%" }}
            onChange={(e) => setBrightness(parseFloat(e.target.value))}/>
        </div>
        {!speedOff ? (
          <div>
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Speed</span>
              <span className="font-mono text-[12px] text-[var(--accent)]">
                {spdMax > 0 ? `${Math.round((speed / 100) * spdMax)} / ${spdMax}` : <>{Math.round(speed)}%</>}
              </span>
            </div>
            <input type="range" className="aether w-full"
              min={0} max={100} step={spdMax > 0 ? 100 / spdMax : 1} value={speed}
              style={{ "--pct": speed + "%" }}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}/>
          </div>
        ) : (
          <div>
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Speed</span>
              <span className="font-mono text-[10px] text-[var(--text-faint)]">n/a</span>
            </div>
            <div className="font-mono text-[10px] text-[var(--text-faint)] leading-relaxed">
              This mode has no speed control on {boardName}.
            </div>
          </div>
        )}
      </div>

      {!firmwareOnly ? (
        // Host-engine board. A board-specific firmware mode (hfdRule) honours
        // its own registry rule: `direction: true` is a 2-way 0/1 byte ->
        // toggle; no direction declared -> no control (the firmware ignores
        // it). Legacy grid ids (hfdRule null) keep today's 4-way dial.
        hfdRule ? (
          hfdRule.direction === true ? (
            <div>
              <div className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2">Direction</div>
              <DirectionToggle direction={direction} setDirection={setDirection}/>
              <div className="font-mono text-[10px] text-[var(--text-faint)] mt-1.5">
                This effect takes a 2-way direction on {boardName}.
              </div>
            </div>
          ) : null
        ) : (
        <div>
          <div className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2">Direction</div>
          <DirectionDial direction={direction} setDirection={setDirection}/>
        </div>
        )
      ) : (rule && rule.direction) ? (
        <div>
          <div className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2">Direction</div>
          {rule.direction === true
            ? <DirectionToggle direction={direction} setDirection={setDirection}/>
            : <DirectionDial direction={direction} setDirection={setDirection}/>}
          {rule.direction === true && (
            <div className="font-mono text-[10px] text-[var(--text-faint)] mt-1.5">
              This effect takes a 2-way direction on {boardName}.
            </div>
          )}
        </div>
      ) : null}

      {pattern === "striation" && (
        <div>
          <div className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2">Stripe Orientation</div>
          <div className="grid grid-cols-3 gap-1.5 max-w-[260px]">
            {[["Vertical", "v", "▥"], ["Horizontal", "h", "▤"], ["Both", "both", "▦"]].map(([lbl, val, ic]) => {
              const active = (striOrient || "v") === val;
              return (
                <button key={val} onClick={() => setStriOrient && setStriOrient(val)}
                  className={`h-9 rounded-lg border text-[11px] uppercase tracking-[0.12em] flex items-center justify-center gap-1.5 transition-all
                              ${active
                                ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)]"
                                : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
                  <span className="text-[14px]">{ic}</span>{lbl}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   Widget 2 — Color Palette: effect-colors palette + presets + background color.
   ============================================================ */
function ColorPaletteWidget(ctx) {
  const { colors, setColors, bgColor, setBgColor, pattern } = ctx;
  const palette = colors || [];
  const [activeSlot, setActiveSlot] = useState(0);
  // Draft for the bg hex text field: lets the user type intermediate values
  // without committing an invalid color (which would stream black to the
  // device). Only a full valid #RRGGBB is pushed to bgColor; external changes
  // (picker, swatches, Off) sync back into the field.
  const [bgText, setBgText] = useState(bgColor);
  useEffect(() => { setBgText(bgColor); }, [bgColor]);

  /* Board awareness (additive): some boards' firmware forces random colors
     for certain modes (registry rule `color: false`) — the picker cannot
     apply. The Win60 declares no such mode, so this never triggers there. */
  const bctx = boardCtxOf(ctx);
  const boardName = (bctx.board && bctx.board.name) || "this board";
  const colorRule = modeRuleFor(bctx.lighting, pattern);
  const colorLocked = !!(colorRule && colorRule.color === false);

  const setSlot = (i, value) => {
    const p = [...palette]; p[i] = value;
    setColors(p);
  };
  const addSlot = () => {
    if (palette.length >= 4) return;
    const seeds = ["#663390","#009fa6","#a62848","#a66e14"];
    const next = seeds[palette.length] || "#a6a6a6";
    setColors([...palette, next]);
    setActiveSlot(palette.length);
  };
  const removeSlot = (i) => {
    if (palette.length <= 0) return;
    const p = palette.filter((_, idx) => idx !== i);
    setColors(p);
    if (activeSlot >= p.length) setActiveSlot(p.length - 1);
  };

  return (
    <div className="flex flex-col gap-4">
      {pattern !== "custom" && colorLocked ? (
        <div className="font-mono text-[11px] text-[var(--text-faint)] leading-relaxed">
          "{(colorRule && colorRule.name) || pattern}" uses firmware-forced random colors on
          {" "}{boardName} — the effect color picker does not apply while it is active. The
          other controls still work.
        </div>
      ) : pattern !== "custom" ? (
        <div>
          <div className="flex items-baseline justify-between mb-2">
            <span className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Effect colors · {palette.length}/4</span>
            <div className="flex items-center gap-3">
              {palette.length > 0 && (
                <button onClick={() => setColors([])}
                  className="font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--text-dim)] hover:text-rose-300">
                  Clear all
                </button>
              )}
              <span className="font-mono text-[10px] text-[var(--text-faint)]">click slot to recolor</span>
            </div>
          </div>
          <div className="flex items-stretch gap-2 mb-3">
            {palette.map((c, i) => {
              const isActive = activeSlot === i;
              return (
                <div key={i} className="relative flex-1 min-w-0 group">
                  <button onClick={() => setActiveSlot(i)}
                    className={`relative w-full h-16 rounded-2xl overflow-hidden ring-1 transition-all
                                ${isActive ? "ring-2 ring-white/80 scale-[1.02]" : "ring-white/10 hover:scale-[1.01]"}`}
                    style={{ background: c, boxShadow: `0 0 24px ${c}55, inset 0 0 0 1px rgba(255,255,255,0.06)` }}>
                    <span className="absolute bottom-1.5 left-2 text-[10px] font-mono text-white/85"
                          style={{ textShadow: "0 1px 4px rgba(0,0,0,0.6)" }}>
                      {c.toUpperCase()}
                    </span>
                    <input type="color" value={c} onChange={(e) => setSlot(i, e.target.value)}
                           onClick={(e) => e.stopPropagation()}
                           className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"/>
                  </button>
                  {palette.length > 0 && (
                    <button onClick={(e) => { e.stopPropagation(); removeSlot(i); }}
                            title="Remove"
                            className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-slate-900 ring-1 ring-white/20 text-slate-300 hover:text-rose-300 grid place-items-center text-[10px] opacity-0 group-hover:opacity-100 transition-opacity">
                      ✕
                    </button>
                  )}
                </div>
              );
            })}
            {palette.length < 4 && (
              <button onClick={addSlot}
                className="flex-1 min-w-0 h-16 rounded-2xl border-2 border-dashed border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] hover:bg-white/[0.04] hover:text-white grid place-items-center transition-all">
                <span className="flex items-center gap-1.5 font-display text-[11px] uppercase tracking-[0.18em]">
                  {IPlus && <IPlus size={13}/>} Add
                </span>
              </button>
            )}
          </div>

          <div className="grid grid-cols-4 gap-2">
            {PRESET_PALETTES.map((p, i) => (
              <button key={i} onClick={() => { setColors([...p]); setActiveSlot(0); }}
                className="h-7 rounded-lg ring-1 ring-white/10 hover:scale-[1.02] transition-transform overflow-hidden"
                title={p.join(", ")}>
                <div className="w-full h-full flex">
                  {p.map((c, j) => <span key={j} className="flex-1" style={{ background: c }}/>)}
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="font-mono text-[11px] text-[var(--text-faint)]">
          Custom mode drives colors per Effect Zone (see the Effect Preview widget) — the shared palette is hidden while Custom is active.
        </div>
      )}

      <div className="glass p-4">
        <div className="flex items-baseline justify-between mb-2.5">
          <span className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Background color</span>
          <span className="font-mono text-[10px] text-[var(--text-faint)]">underlies the effect</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative w-14 h-12 rounded-xl overflow-hidden ring-1 ring-white/10"
               style={{ background: bgColor, boxShadow: `0 0 18px ${bgColor}55` }}>
            <input type="color" value={bgColor} onChange={(e) => setBgColor(e.target.value)}
                   className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"/>
          </div>
          <input type="text" value={(bgText || "").toUpperCase()}
                 onChange={(e) => { const v = e.target.value; setBgText(v); if (/^#[0-9a-fA-F]{6}$/.test(v)) setBgColor(v); }}
                 className="flex-1 h-10 px-3 rounded-lg bg-[rgba(5,11,14,0.5)] border border-[var(--line)] font-mono text-[12px] text-[var(--text)] outline-none focus:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"/>
          <button onClick={() => setBgColor("#000000")}
            className="px-2.5 h-10 rounded-lg border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-white hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] font-display text-[10.5px] uppercase tracking-[0.16em]">
            Off
          </button>
        </div>
        <div className="flex items-center gap-1.5 mt-2.5">
          {BG_SWATCHES.map(c => (
            <button key={c} onClick={() => setBgColor(c)}
              className={`w-6 h-6 rounded-md ring-1 ${bgColor.toLowerCase() === c.toLowerCase() ? "ring-white scale-110" : "ring-white/15 hover:scale-105"} transition-transform`}
              style={{ background: c }}
              title={c}/>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   Widget 3 — Effect Preview: live SVG pattern preview + Custom effect zones.
   ============================================================ */
function EffectPreviewWidget(ctx) {
  const { pattern, colors, bgColor, zones, addZone, updateZone, removeZone, selectedKeys } = ctx;
  const palette = colors || [];
  const previewColor = palette[0] || bgColor || "#9d4edd";
  const kind = previewKindFor(pattern);

  /* Board awareness (additive): Effect Zones animate via the host streaming
     engine, so they are only offered when the board allows it (hostEngine
     true, or no board data — fail-open, exactly today's behaviour). */
  const bctx = boardCtxOf(ctx);
  const hostFx = !bctx.lighting || bctx.lighting.hostEngine !== false;
  const boardName = (bctx.board && bctx.board.name) || "this board";
  // Streaming fps cap — drives the ≈ markers on zone modes (null = no cap).
  const fpsCap = hostFx ? hostFpsLimited(bctx.lighting) : null;

  /* Dispatch honesty: a mode that is one of THIS board's own firmware effects
     (beyond the legacy host grid — e.g. the MINI's starry-sky) runs on the
     keyboard itself, so the host-animation schematic would be a lie. Show
     what actually happens instead. Legacy grid ids (and the no-board path)
     render exactly today's preview. */
  const fwRule = modeRuleFor(bctx.lighting, pattern);
  const fwOnlyMode = !!fwRule && !LIGHT_MODES.some(m => m.id === pattern);

  return (
    <div className="flex flex-col gap-4">
      <div className="glass p-4">
        <div className="flex items-baseline justify-between mb-1">
          <span className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Preview</span>
          <span className="font-mono text-[10px] text-[var(--text-faint)] uppercase tracking-[0.16em]">{fwOnlyMode ? pattern + " · firmware" : pattern}</span>
        </div>
        {fwOnlyMode ? (
          <div className="font-mono text-[10px] text-[var(--text-faint)] leading-relaxed mt-2">
            "{fwRule.name || pattern}" is one of {boardName}'s built-in firmware effects —
            the animation runs on the keyboard itself, not through Aether's host engine,
            so there is no host preview to mirror here. The board plays it live.
          </div>
        ) : (
          <PatternPreview kind={kind} color={previewColor}/>
        )}
      </div>
      {/* The ~fps fact lives under the Mode Picker grid; here capped boards only
          get the same ≈ marker on press-reactive zone modes — no repeated note. */}
      {pattern === "custom" && (hostFx ? (
        <ZonesPanel zones={zones} selectedKeys={selectedKeys}
                    onAdd={addZone} onUpdate={updateZone} onRemove={removeZone}
                    degraded={fpsCap != null ? HOST_FX_FAST : null}/>
      ) : (
        <div className="glass p-4 font-mono text-[11px] text-[var(--text-dim)] leading-relaxed">
          Effect Zones animate through Aether's host streaming engine, and that streaming
          path is not yet proven on {boardName} — so zones are not offered. Static per-key
          colors still work: use the Per-key Paint widget.
        </div>
      ))}
      {pattern !== "custom" && (
        <div className="font-mono text-[11px] text-[var(--text-faint)]">
          Switch Light Mode to "Custom" (Mode Picker widget) to build per-zone effects here.
        </div>
      )}
    </div>
  );
}

/* ============================================================
   Widget 4 — Per-key Paint: assign/clear the active palette color to
   the current key selection.
   ============================================================ */
function PerKeyPaintWidget(ctx) {
  const { colors, perKeyColors, setPerKeyColors, selectedKeys, setSelectedKeys, ledMap } = ctx;
  const palette = colors || [];
  const [activeSlot, setActiveSlot] = useState(0);
  const selCount = selectedKeys ? selectedKeys.size : 0;

  const assignToSelection = () => {
    if (!selectedKeys || selectedKeys.size === 0) return;
    const c = palette[activeSlot] || palette[0] || "#ffffff";
    const next = { ...(perKeyColors || {}) };
    selectedKeys.forEach(code => { next[code] = c; });
    setPerKeyColors(next);
  };
  const clearPerKeyForSelection = () => {
    if (!selectedKeys || selectedKeys.size === 0) return;
    const next = { ...(perKeyColors || {}) };
    selectedKeys.forEach(code => { delete next[code]; });
    setPerKeyColors(next);
  };
  const selectAll = () => {
    if (!setSelectedKeys) return;
    setSelectedKeys(new Set(Object.keys(ledMap || {})));
  };
  const clearSelection = () => {
    if (!setSelectedKeys) return;
    setSelectedKeys(new Set());
  };

  return (
    <div className="flex flex-col gap-4">
      {palette.length > 0 && (
        <div>
          <div className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2">Active slot</div>
          <div className="flex items-center gap-2">
            {palette.map((c, i) => (
              <button key={i} onClick={() => setActiveSlot(i)}
                className={`w-9 h-9 rounded-lg ring-1 transition-all ${activeSlot === i ? "ring-2 ring-white/80 scale-110" : "ring-white/10 hover:scale-105"}`}
                style={{ background: c, boxShadow: `0 0 12px ${c}55` }}
                title={c.toUpperCase()}/>
            ))}
          </div>
        </div>
      )}
      <div className="glass p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="font-display text-[12px] uppercase tracking-[0.18em] text-[var(--text)]">Per-key colors</div>
            <div className="font-mono text-[10px] text-[var(--text-faint)] mt-0.5">
              {selCount} key{selCount === 1 ? "" : "s"} selected · Ctrl/⌘-click to toggle
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button onClick={selectAll}
              className="px-2.5 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-white hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] font-display text-[10.5px] uppercase tracking-[0.16em]">
              Select all
            </button>
            <button onClick={clearSelection}
              className="px-2.5 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-white hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] font-display text-[10.5px] uppercase tracking-[0.16em]">
              Clear
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={assignToSelection}
            disabled={!selectedKeys || selectedKeys.size === 0}
            className="flex-1 h-10 rounded-lg font-display text-[12px] uppercase tracking-[0.18em] text-[var(--accent-fg)] disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:brightness-110"
            style={{
              background: "var(--accent-gradient, var(--accent))",
              boxShadow: "0 8px 24px -8px var(--accent-glow)"
            }}>
            Paint selected with slot {activeSlot + 1}
          </button>
          <button onClick={clearPerKeyForSelection}
            disabled={!selectedKeys || selectedKeys.size === 0}
            className="px-3 h-10 rounded-lg border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-white hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] disabled:opacity-40 font-display text-[11.5px] uppercase tracking-[0.18em]">
            Reset
          </button>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   Widget 5 — Live Keyboard: the real board painted with the live animated
   effect frame (ctx.ledMapLive, polled from get_light_frame on the Lighting
   tab). Click keys to build a selection for Per-key Paint. This is the
   animated keyboard preview from the previous UI.
   ============================================================ */
function LiveKeyboardWidget(ctx) {
  const KB = window.AetherKeyboard || {};
  const KeyboardPanel = KB.KeyboardPanel;
  const { ledMap, ledMapLive, perKeyColors, selectedKeys, setSelectedKeys, connected, pattern } = ctx;
  /* Board awareness (additive): a mode that runs on the BOARD's firmware has
     no host frames to mirror, so the keyboard below shows the static
     schematic (fg/bg only). Say so, instead of letting the still image read
     as a broken animation. Never fires for legacy grid ids on host-engine
     boards (the shipped Win60 surface) or without board data. */
  const bctx = boardCtxOf(ctx);
  const fwRule = modeRuleFor(bctx.lighting, pattern);
  const fwLive = !!fwRule && pattern !== "static" && pattern !== "custom" &&
    (!LIGHT_MODES.some(m => m.id === pattern) || (bctx.lighting && bctx.lighting.hostEngine === false));
  if (typeof KeyboardPanel !== "function") {
    return <div className="font-mono text-[11px] text-[var(--text-faint)] p-2">keyboard layout unavailable</div>;
  }
  return (
    <div className="flex flex-col gap-2">
      {!connected && (
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)]">
          connect the board to see the live effect
        </div>
      )}
      {fwLive && (
        <div className="font-mono text-[10px] text-[var(--text-faint)] leading-relaxed text-center">
          "{fwRule.name || pattern}" animates on the keyboard's own firmware — the board plays
          it live. Keys below show {fwRule.color === false
            ? "your background color only (this effect uses firmware-chosen colors)"
            : "the exact colors sent (effect color over your background)"}, not the animation.
        </div>
      )}
      <div className="flex justify-center">
        {React.createElement(KeyboardPanel, {
          mode: "lighting",
          layer: "default",
          ledMap: ledMapLive || ledMap,
          perKeyOverride: perKeyColors,
          selectedKeys: selectedKeys || new Set(),
          setSelectedKeys: setSelectedKeys || (() => {}),
          showPill: false,
        })}
      </div>
    </div>
  );
}

/* ============================================================
   Layout — Live Keyboard is the hero (wide, top); controls below/around.
   ============================================================ */
const LIGHTING_WIDGETS = [
  { id: "live",     title: "Live Keyboard",  default: { x: 40,  y: 32,  w: 1000, h: 330 }, min: { w: 560, h: 240 }, render: LiveKeyboardWidget },
  { id: "mode",     title: "Mode Picker",    default: { x: 40,  y: 382, w: 460, h: 520 }, min: { w: 340, h: 420 }, render: ModePickerWidget },
  { id: "palette",  title: "Color Palette",  default: { x: 520, y: 382, w: 460, h: 460 }, min: { w: 340, h: 340 }, render: ColorPaletteWidget },
  { id: "preview",  title: "Effect Preview", default: { x: 1000,y: 382, w: 380, h: 460 }, min: { w: 300, h: 300 }, render: EffectPreviewWidget },
  { id: "perkey",   title: "Per-key Paint",  default: { x: 1060,y: 32,  w: 380, h: 330 }, min: { w: 340, h: 260 }, render: PerKeyPaintWidget },
];

window.AetherWorkspaces = window.AetherWorkspaces || {};
window.AetherWorkspaces.LIGHTING_WIDGETS = LIGHTING_WIDGETS;
// Pure board-awareness helpers. app.jsx reads resolveLightDispatch /
// buildLightCalls at send time (this file loads before app.jsx — see
// build_runtime.py's dependency order); the rest is for verification.
window.AetherWorkspaces.LIGHTING_BOARD = {
  LIGHT_MODES, modeGridFor, modeRuleFor, boardCtxOf,
  HOST_ENGINE_TARGET_FPS, HOST_FX_FAST, hostFpsCapOf, hostFpsLimited,
  HOST_FX_IDS, resolveLightDispatch, buildLightCalls, briByteFor, spdByteFor,
  previewSimColor,
};
})();
