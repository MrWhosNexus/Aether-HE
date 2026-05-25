(() => {
/* WIN60 HE keyboard visualization with per-key live actuation. */
const { useState, useEffect, useRef, useMemo } = React;

/* 60% ANSI layout — each row totals 60 cols (each 0.25u = 1 col). */
/* Each entry: [label, units, code, fn?] — `units` is in 0.25u increments. */
const KB_ROWS = [
  [
    ["Esc", 4, "Escape", "`~"], ["1!", 4, "1", "F1"], ["2@", 4, "2", "F2"], ["3#", 4, "3", "F3"], ["$4", 4, "4", "F4"],
    ["5%", 4, "5", "F5"], ["6^", 4, "6", "F6"], ["7&", 4, "7", "F7"], ["8*", 4, "8", "F8"], ["9(", 4, "9", "F9"],
    ["0)", 4, "0", "F10"], ["-_", 4, "Minus", "F11"], ["=+", 4, "Equal", "F12"], ["Back", 8, "Backspace", "Del"]
  ],
  [
    ["Tab", 6, "Tab"], ["Q", 4, "Q", "PrtSc"], ["W", 4, "W", "↑"], ["E", 4, "E", "End"], ["R", 4, "R", "PgUp"],
    ["T", 4, "T", "Home"], ["Y", 4, "Y", ""], ["U", 4, "U", ""], ["I", 4, "I", "Ins"], ["O", 4, "O", ""],
    ["P", 4, "P", "Pause"], ["{[", 4, "Lbr", "Prev"], ["}]", 4, "Rbr", "Next"], ["\\|", 6, "Bsl", "Play"]
  ],
  [
    ["Caps", 7, "Caps"], ["A", 4, "A", "←"], ["S", 4, "S", "↓"], ["D", 4, "D", "→"], ["F", 4, "F", ""],
    ["G", 4, "G", ""], ["H", 4, "H", ""], ["J", 4, "J", ""], ["K", 4, "K", "Vol−"], ["L", 4, "L", "Vol+"],
    [";:", 4, "Semi", "Mute"], ["'\"", 4, "Quot", ""], ["Enter", 9, "Enter", ""]
  ],
  [
    ["L-Shift", 9, "LShift"], ["Z", 4, "Z", ""], ["X", 4, "X", ""], ["C", 4, "C", "Calc"], ["V", 4, "V", ""],
    ["B", 4, "B", ""], ["N", 4, "N", ""], ["M", 4, "M", ""], [",<", 4, "Comma", "Brt−"], [".>", 4, "Dot", "Brt+"],
    ["/?", 4, "Slash", ""], ["R-Shift", 11, "RShift"]
  ],
  [
    ["L-Ctrl", 5, "LCtrl"], ["L-Win", 5, "LWin", "WinLk"], ["L-Alt", 5, "LAlt"], ["Space", 25, "Space"],
    ["R-Alt", 5, "RAlt"], ["Menu", 5, "Menu"], ["R-Ctrl", 5, "RCtrl"], ["Fn", 5, "Fn", "Fn"]
  ]
];

/* Compute a fractional width string given units in 0.25u increments out of 60 cols. */
const ufrac = (u) => `${(u / 60) * 100}%`;

const Key = ({
  label, units, code, fnLabel,
  layer = "default",     // default | fn
  depth = 0,
  actuationPoint = 1.70,
  rtPress = 0.05,
  rtRelease = 0.05,
  selected = false,
  highlighted = false,
  mode = "keymap",
  ledColor = null,
  onClick = () => {},
  onContextMenu = () => {},
}) => {
  const actuated = depth >= actuationPoint && actuationPoint > 0;
  const progress = Math.min(1, depth / 4);

  // Background depending on mode
  let bg = "rgba(255,255,255,0.025)";
  if (mode === "lighting" && ledColor) {
    bg = `linear-gradient(180deg, ${ledColor}3a, ${ledColor}14 50%, rgba(255,255,255,0.02))`;
  }

  // Two-line labels (e.g. "1!" -> shifted/unshifted stack)
  const lines = label.length === 2 && !/^[a-zA-Z]+$/.test(label) && label !== "Fn"
      ? [label[0], label[1]]
      : null;

  const displayLabel = layer === "fn" && fnLabel ? fnLabel : label;
  const displayLines = layer === "fn" ? null : lines;

  return (
    <button
      onClick={onClick}
      onContextMenu={(e) => { e.preventDefault(); onContextMenu(e); }}
      style={{
        gridColumn: `span ${units}`,
        background: bg,
      }}
      data-code={code}
      className={`relative rounded-[5px] border text-left
                  px-1.5 pt-1 pb-0.5 h-[46px] overflow-hidden
                  transition-all duration-150
                  ${selected
                    ? "border-[var(--accent)]/80 shadow-[0_0_0_1px_var(--accent),0_0_18px_var(--accent-glow)]"
                    : actuated
                      ? "border-[var(--accent)]/60 shadow-[0_0_14px_var(--accent-glow)]"
                      : highlighted
                        ? "border-white/15"
                        : "border-white/[0.07] hover:border-white/20"
                  }`}>

      {/* Travel fill from bottom */}
      {mode !== "lighting" && depth > 0.02 && (
        <span aria-hidden className="absolute inset-x-0 bottom-0 pointer-events-none"
              style={{
                height: progress * 100 + "%",
                background: actuated
                  ? "linear-gradient(to top, var(--accent), transparent 90%)"
                  : "linear-gradient(to top, rgba(148,163,184,0.18), transparent 90%)",
                opacity: actuated ? 0.45 : 0.55,
                transition: "height 120ms linear",
              }}/>
      )}

      {/* Label */}
      <div className="relative z-10 flex items-start justify-between">
        {displayLines ? (
          <div className="flex flex-col leading-[1.0]">
            <span className="text-[10px] text-slate-200 font-medium">{displayLines[1]}</span>
            <span className="text-[10px] text-slate-400 font-medium">{displayLines[0]}</span>
          </div>
        ) : (
          <span className={`text-[11px] font-medium tracking-wide
                            ${layer === "fn" && fnLabel ? "text-[var(--accent)]" : actuated ? "text-white" : "text-slate-200"}`}>
            {displayLabel}
          </span>
        )}
      </div>

      {/* Bottom values — only in actuation mode */}
      {mode === "actuation" && (
        <div className="absolute bottom-0.5 inset-x-1 z-10 flex items-end justify-between">
          <span className="font-mono text-[8.5px] text-slate-300/90">{actuationPoint.toFixed(2)}</span>
          {(rtPress > 0 || rtRelease > 0) && (
            <div className="flex gap-1">
              <span className="font-mono text-[8.5px] text-rose-300/90">{rtPress.toFixed(2)}</span>
              <span className="font-mono text-[8.5px] text-emerald-300/90">{rtRelease.toFixed(2)}</span>
            </div>
          )}
        </div>
      )}

      {/* Live readout — show in actuation mode on hover via the fill, plus a tiny depth tag for WASD */}
      {mode === "actuation" && depth > 0.05 && (
        <span className="absolute top-1 right-1 z-10 font-mono text-[8px] text-[var(--accent)]/90">
          {depth.toFixed(2)}
        </span>
      )}
    </button>
  );
};

/* Top "WIN 60 HE" pill */
const DevicePill = ({ connected }) => (
  <div className="flex items-center gap-2 px-4 py-1.5 rounded-md bg-[var(--accent)]/15 border border-[var(--accent)]/40 text-[var(--accent)] shadow-[0_0_18px_var(--accent-glow)] whitespace-nowrap">
    <span className="relative inline-block w-1.5 h-1.5 rounded-full bg-[var(--accent)] pulse-ring text-[var(--accent)]"/>
    <span className="font-display font-semibold tracking-[0.18em] text-[12px]">WIN 60 HE</span>
    <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--accent)]/70 ml-1">
      {connected ? "Linked" : "Offline"}
    </span>
  </div>
);

/* The full keyboard panel — handles live actuation telemetry and selection */
const KeyboardPanel = ({
  mode, layer = "default", selectedKeys, setSelectedKeys, actuationPoint, rtPress, rtRelease,
  perKeyOverride, ledMap, accent, leftSlot, rightSlot, showPill = true, compact = false
}) => {
  // Live depth state for every key
  const [depths, setDepths] = useState({});
  const targetsRef = useRef({});
  const tickRef = useRef(0);

  // Initialize targets to 0
  useEffect(() => {
    const all = {};
    KB_ROWS.flat().forEach(([_, __, code]) => { all[code] = 0; });
    targetsRef.current = all;
    setDepths(all);
  }, []);

  // Simulate live key presses — WASD on a loop, plus a sprinkling of other keys
  useEffect(() => {
    const wasdSeq = ["W", "A", "S", "D"];
    let i = 0;
    const heavy = setInterval(() => {
      const k = wasdSeq[i % wasdSeq.length];
      i++;
      // Press it
      targetsRef.current[k] = 2.4 + Math.random() * 1.2;
      setTimeout(() => { targetsRef.current[k] = 0; }, 220 + Math.random() * 180);
    }, 330);

    const random = setInterval(() => {
      const all = KB_ROWS.flat().map(([_, __, c]) => c).filter(c => !wasdSeq.includes(c));
      // Press 1-2 random keys
      const n = 1 + Math.floor(Math.random() * 2);
      for (let j = 0; j < n; j++) {
        const code = all[Math.floor(Math.random() * all.length)];
        targetsRef.current[code] = 1.5 + Math.random() * 2;
        setTimeout(() => { targetsRef.current[code] = 0; }, 180 + Math.random() * 220);
      }
    }, 900);

    // Smoothly animate depths toward targets
    const frame = setInterval(() => {
      tickRef.current++;
      setDepths(prev => {
        const next = { ...prev };
        for (const k of Object.keys(prev)) {
          const t = targetsRef.current[k] ?? 0;
          const d = t - prev[k];
          next[k] = Math.max(0, Math.min(4, prev[k] + d * 0.45 + (Math.random() - 0.5) * 0.02));
          if (Math.abs(next[k]) < 0.01 && t === 0) next[k] = 0;
        }
        return next;
      });
    }, 60);

    return () => { clearInterval(heavy); clearInterval(random); clearInterval(frame); };
  }, []);

  const toggleSelect = (code, e) => {
    setSelectedKeys(prev => {
      const cur = new Set(prev);
      if (e.shiftKey || e.metaKey || e.ctrlKey) {
        cur.has(code) ? cur.delete(code) : cur.add(code);
      } else {
        if (cur.has(code) && cur.size === 1) cur.clear();
        else { cur.clear(); cur.add(code); }
      }
      return cur;
    });
  };

  return (
    <div className="relative">
      {/* Device pill centered above (optional) */}
      {showPill && (
        <div className="flex justify-center mb-4">
          <DevicePill connected />
        </div>
      )}

      {/* Side slots + keyboard */}
      <div className="flex items-start justify-center gap-4">
        <div className="shrink-0 w-[110px] pt-2 flex flex-col gap-1.5">
          {leftSlot}
        </div>

        {/* Keyboard board */}
        <div className="relative w-full max-w-[720px] rounded-2xl border border-white/[0.06] bg-gradient-to-b from-white/[0.025] to-black/30 p-3.5 shadow-[0_24px_60px_-24px_rgba(0,0,0,0.8)]">
          <span className="pointer-events-none absolute -top-px left-12 right-12 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
          <div className="flex flex-col gap-[3px]">
            {KB_ROWS.map((row, ri) => (
              <div key={ri} className="grid w-full gap-[3px]" style={{ gridTemplateColumns: "repeat(60, minmax(0, 1fr))" }}>
                {row.map(([label, units, code, fnLabel]) => {
                  const override = perKeyOverride?.[code] || {};
                  return (
                    <Key
                      key={code}
                      label={label} units={units} code={code} fnLabel={fnLabel}
                      layer={layer}
                      depth={depths[code] || 0}
                      actuationPoint={override.actuation ?? actuationPoint}
                      rtPress={override.rtPress ?? rtPress}
                      rtRelease={override.rtRelease ?? rtRelease}
                      selected={selectedKeys.has(code)}
                      mode={mode}
                      ledColor={ledMap?.[code] || null}
                      onClick={(e) => toggleSelect(code, e)}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        <div className="shrink-0 w-[110px] pt-2 flex flex-col gap-1.5 items-end">
          {mode === "actuation" && (
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500 whitespace-nowrap">
              Actuation · <span className="text-slate-200">{actuationPoint.toFixed(2)}mm</span>
            </span>
          )}
          {rightSlot}
        </div>
      </div>

      {/* Below-keyboard refresh */}
      <div className="flex flex-col items-center mt-3 gap-1">
        <button className="grid place-items-center w-7 h-7 rounded-full border border-white/[0.06] bg-white/[0.02] text-slate-400 hover:text-slate-100 hover:border-white/20 transition-colors"
                title="Refresh device state">
          <window.AetherIcons.IRefresh size={13}/>
        </button>
        {mode === "socd" && (
          <span className="font-mono text-[10px] text-slate-500 uppercase tracking-[0.18em]">
            Right-click to uncheck all keys
          </span>
        )}
      </div>
    </div>
  );
};

window.AetherKeyboard = { KeyboardPanel, KB_ROWS, DevicePill };
})();
