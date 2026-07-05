(() => {
/* ============================================================
   Lighting workspace — window.AetherWorkspaces.LIGHTING_WIDGETS.
   Control JSX ported verbatim from the old LightingSection (sections.jsx)
   and split across four widget bodies. Color values (hex swatches, style=
   {{background:c}}, PatternPreview) are byte-identical — these are real
   device RGB values, never re-tokenized.
   ============================================================ */
const { useState } = React;
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

/* ===== Effect zones panel (custom mode) — verbatim behavior from sections.jsx ===== */
const ZonesPanel = ({ zones, selectedKeys, onAdd, onUpdate, onRemove }) => (
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
              {ZONE_MODES.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
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
function ModePickerWidget(ctx) {
  const {
    pattern, setPattern, brightness, setBrightness, speed, setSpeed,
    power, setPower, fullColor, setFullColor, direction, setDirection,
    striOrient, setStriOrient,
  } = ctx;
  const fullColorOk = pattern !== "static" && pattern !== "custom";

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
          {LIGHT_MODES.map(m => {
            const active = pattern === m.id;
            return (
              <button key={m.id} onClick={() => setPattern(m.id)}
                className={`h-9 rounded-lg border font-display text-[11px] tracking-[0.06em] flex items-center justify-center gap-1.5 transition-all
                            ${active
                              ? "border-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]"
                              : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}
                style={ active ? { background: "var(--accent-gradient, var(--accent))" } : {} }>
                <span className="text-[12px]">{m.icon}</span> {m.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-5">
        <div>
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Brightness</span>
            <span className="font-mono text-[12px] text-[var(--accent)]">{Math.round(brightness)}%</span>
          </div>
          <input type="range" className="aether w-full"
            min={0} max={100} step={1} value={brightness}
            style={{ "--pct": brightness + "%" }}
            onChange={(e) => setBrightness(parseFloat(e.target.value))}/>
        </div>
        <div>
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Speed</span>
            <span className="font-mono text-[12px] text-[var(--accent)]">{Math.round(speed)}%</span>
          </div>
          <input type="range" className="aether w-full"
            min={0} max={100} step={1} value={speed}
            style={{ "--pct": speed + "%" }}
            onChange={(e) => setSpeed(parseFloat(e.target.value))}/>
        </div>
      </div>

      <div>
        <div className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2">Direction</div>
        <div className="grid grid-cols-4 gap-1.5 max-w-[220px]">
          {[["→", 0], ["←", 1], ["↑", 2], ["↓", 3]].map(([arrow, val]) => {
            const active = direction === val;
            return (
              <button key={val} onClick={() => setDirection(val)}
                className={`h-9 rounded-lg border text-[15px] transition-all
                            ${active
                              ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)]"
                              : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
                {arrow}
              </button>
            );
          })}
        </div>
      </div>

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
      {pattern !== "custom" ? (
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
          <input type="text" value={bgColor.toUpperCase()}
                 onChange={(e) => { const v = e.target.value; if (/^#[0-9a-fA-F]{6}$/.test(v)) setBgColor(v); else setBgColor(v); }}
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

  return (
    <div className="flex flex-col gap-4">
      <div className="glass p-4">
        <div className="flex items-baseline justify-between mb-1">
          <span className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Preview</span>
          <span className="font-mono text-[10px] text-[var(--text-faint)] uppercase tracking-[0.16em]">{pattern}</span>
        </div>
        <PatternPreview kind={kind} color={previewColor}/>
      </div>
      {pattern === "custom" && (
        <ZonesPanel zones={zones} selectedKeys={selectedKeys}
                    onAdd={addZone} onUpdate={updateZone} onRemove={removeZone}/>
      )}
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
   Layout — two columns on an ~1400px desktop, no overlap.
   ============================================================ */
const LIGHTING_WIDGETS = [
  { id: "mode",     title: "Mode Picker",    default: { x: 40,  y: 32,  w: 460, h: 560 }, min: { w: 340, h: 420 }, render: ModePickerWidget },
  { id: "palette",  title: "Color Palette",  default: { x: 520, y: 32,  w: 460, h: 460 }, min: { w: 340, h: 340 }, render: ColorPaletteWidget },
  { id: "preview",  title: "Effect Preview", default: { x: 1000,y: 32,  w: 380, h: 460 }, min: { w: 300, h: 300 }, render: EffectPreviewWidget },
  { id: "perkey",   title: "Per-key Paint",  default: { x: 520, y: 512, w: 460, h: 320 }, min: { w: 340, h: 260 }, render: PerKeyPaintWidget },
];

window.AetherWorkspaces = window.AetherWorkspaces || {};
window.AetherWorkspaces.LIGHTING_WIDGETS = LIGHTING_WIDGETS;
})();
