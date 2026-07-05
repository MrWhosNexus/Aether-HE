(() => {
/* SOCD Workspace: 3-widget layout for key pair editor, hotkey control, and active pairs list */
const { useState, useEffect } = React;
const {
  IPlus, ITrash, IUnlink, ICheck
} = window.AetherIcons;
const { Chip, ToolbarButton } = window.AetherSections;

const BASIC_KEYS = [
  "A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U",
  "V","W","X","Y","Z","1!","2@","3#","$4","5%","6^","7&","8*","9(","0)","-_","=+","{[","}]","\\|","<>",";:","'\"","`~",",<",".>","/?"
];
const EXTENDED_KEYS = [
  "Esc","Tab","Caps","Back","Enter","Space","L-Ctrl","R-Ctrl","L-Shift","R-Shift","L-Alt","R-Alt","L-Win","R-Win","Menu","Left","Up","Right","Down",
  "PrtSc","ScrLk","Pause","Ins","Home","Del","End","PgUp","PgDn","F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12"
];

/* ===== KeyGrid: collapsible key picker ===== */
const KeyGrid = ({ title, keys, picked, onPick }) => {
  const [open, setOpen] = useState(true);
  const IChevronD = window.AetherIcons?.IChevronD;
  return (
    <div>
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 mb-2 text-[var(--text-dim)] hover:text-[var(--text)]">
        {IChevronD && <IChevronD size={12} className={open ? "" : "-rotate-90"}/>}
        <span className="font-display text-[12px] uppercase tracking-[0.18em]">{title}</span>
      </button>
      {open && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(46px,1fr))] gap-1.5 mb-3">
          {keys.map(k => {
            const active = picked === k;
            return (
              <button key={k} onClick={() => onPick(k)}
                className={`h-9 rounded-md border font-mono text-[11px] transition-all
                            ${active
                              ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)]"
                              : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] hover:text-[var(--text)]"}`}>
                {k}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

/* ===== Pair Editor Widget ===== */
const PairEditorWidget = (ctx) => {
  const { socdProfiles, setSocdProfiles, socdActive, setSocdActive } = ctx;
  const [editTarget, setEditTarget] = useState("k1"); // "k1" or "k2"
  const cur = socdProfiles.find(p => p.id === socdActive) || socdProfiles[0];

  const updateActive = (patch) => {
    setSocdProfiles(ps => ps.map(p => p.id === socdActive ? { ...p, ...patch } : p));
  };
  const addProfile = () => {
    const next = `SOCD${socdProfiles.length + 1}`;
    setSocdProfiles([...socdProfiles, { id: next, k1: "", k2: "", mode: 1 }]);
    setSocdActive(next);
  };
  const delActive = () => {
    if (socdProfiles.length <= 1) return;
    const remaining = socdProfiles.filter(p => p.id !== socdActive);
    setSocdProfiles(remaining);
    setSocdActive(remaining[0].id);
  };

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto">
      {/* Key pair display */}
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--text-faint)] mb-1">Key 1</div>
          <button onClick={() => setEditTarget("k1")}
            className={`w-full h-9 rounded-md border grid place-items-center font-mono text-[14px] transition-colors
                         ${editTarget === "k1"
                           ? "border-[var(--accent)]/50 text-[var(--accent)] bg-[var(--accent)]/10 shadow-[0_0_8px_var(--accent-glow)]"
                           : cur?.k1
                             ? "border-[var(--accent)]/30 text-[var(--accent)] bg-[var(--accent)]/10 hover:shadow-[0_0_8px_var(--accent-glow)]"
                             : "border-[var(--line)] text-[var(--text-faint)] bg-white/[0.02] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
            {cur?.k1 || "—"}
          </button>
        </div>
        <div className="text-[var(--text-faint)] mt-5">{IUnlink && <IUnlink size={14}/>}</div>
        <div className="flex-1">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--text-faint)] mb-1">Key 2</div>
          <button onClick={() => setEditTarget("k2")}
            className={`w-full h-9 rounded-md border grid place-items-center font-mono text-[14px] transition-colors
                         ${editTarget === "k2"
                           ? "border-[var(--accent)]/50 text-[var(--accent)] bg-[var(--accent)]/10 shadow-[0_0_8px_var(--accent-glow)]"
                           : cur?.k2
                             ? "border-[var(--accent)]/30 text-[var(--accent)] bg-[var(--accent)]/10 hover:shadow-[0_0_8px_var(--accent-glow)]"
                             : "border-[var(--line)] text-[var(--text-faint)] bg-white/[0.02] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
            {cur?.k2 || "—"}
          </button>
        </div>
      </div>

      {/* Mode selection */}
      <div className="grid grid-cols-2 gap-1.5">
        {[1,2,3,4].map(m => (
          <button key={m} onClick={() => updateActive({ mode: m })}
            className={`flex items-center gap-2 px-3 h-9 rounded-md border font-mono text-[12px] transition-all
                        ${cur?.mode === m
                          ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 text-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]"
                          : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
            <span className={`w-3 h-3 rounded-full border ${cur?.mode === m ? "border-[var(--accent)] bg-[var(--accent)]" : "border-[var(--text-faint)]"}`}/>
            Model {m}
          </button>
        ))}
      </div>

      {/* Key picker grids */}
      {editTarget === "k1" && (
        <div className="p-3 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/[0.05]">
          <div className="font-display text-[10px] uppercase tracking-[0.16em] text-[var(--accent)] mb-2">Select Key 1</div>
          <KeyGrid title="Basic Keys" keys={BASIC_KEYS} picked={cur?.k1} onPick={(k) => { updateActive({ k1: k }); setEditTarget("k2"); }}/>
          <KeyGrid title="Extended Keys" keys={EXTENDED_KEYS} picked={cur?.k1} onPick={(k) => { updateActive({ k1: k }); setEditTarget("k2"); }}/>
        </div>
      )}
      {editTarget === "k2" && (
        <div className="p-3 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/[0.05]">
          <div className="font-display text-[10px] uppercase tracking-[0.16em] text-[var(--accent)] mb-2">Select Key 2</div>
          <KeyGrid title="Basic Keys" keys={BASIC_KEYS} picked={cur?.k2} onPick={(k) => { updateActive({ k2: k }); setEditTarget(null); }}/>
          <KeyGrid title="Extended Keys" keys={EXTENDED_KEYS} picked={cur?.k2} onPick={(k) => { updateActive({ k2: k }); setEditTarget(null); }}/>
        </div>
      )}

      {/* Mode descriptions */}
      <div className="rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] p-3 text-[11.5px] text-[var(--text-dim)] leading-relaxed">
        <div className="text-[var(--text)] font-display uppercase tracking-[0.18em] text-[10.5px] mb-2">When both Key1 and Key2 fire:</div>
        <div className="space-y-1.5 font-mono text-[10px]">
          <div><span className="text-[var(--accent)]">Model 1</span> · First press wins; second is interrupted.</div>
          <div><span className="text-[var(--accent)]">Model 2</span> · Key1 interrupts Key2.</div>
          <div><span className="text-[var(--accent)]">Model 3</span> · Key2 interrupts Key1.</div>
          <div><span className="text-[var(--accent)]">Model 4</span> · Later-triggered key wins (Snap Tap).</div>
        </div>
      </div>

      {/* Create/Delete buttons */}
      <div className="flex gap-2">
        <button onClick={addProfile} className="flex-1 flex items-center justify-center gap-1 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] font-display text-[11px] uppercase tracking-[0.16em]">
          {IPlus && <IPlus size={12}/>} New
        </button>
        <button onClick={delActive} className="flex-1 flex items-center justify-center gap-1 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-rose-400/40 hover:text-rose-300 font-display text-[11px] uppercase tracking-[0.16em]">
          {ITrash && <ITrash size={12}/>} Delete
        </button>
      </div>
    </div>
  );
};

/* ===== Hotkey Widget ===== */
const HotkeyWidget = (ctx) => {
  const { hotkey, hotkeyEnabled, setHotkeyEnabled, handleSocdApply, socdProfiles } = ctx;

  return (
    <div className="flex flex-col gap-4 h-full">
      <div>
        <div className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)] mb-2">Switch hotkey</div>
        <button onClick={() => setHotkeyEnabled(!hotkeyEnabled)}
          className={`relative w-10 h-5 rounded-full border transition-colors w-full flex items-center justify-between px-3
                      ${hotkeyEnabled ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-[rgba(5,11,14,0.5)] border-[var(--line)]"}`}>
          <span className={`absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                            ${hotkeyEnabled ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-[var(--text-faint)]"}`}/>
        </button>
      </div>

      <div className="rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] p-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)] mb-1">Active hotkey</div>
        <div className="font-mono text-[13px] text-[var(--accent)]">{hotkey || "—"}</div>
      </div>

      <div className="rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)] p-3 flex-1 flex flex-col">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)] mb-2">Status</div>
        <div className="flex-1 flex flex-col justify-center">
          {hotkeyEnabled ? (
            <div className="text-[11.5px] text-[var(--text)]">
              <div className="font-display uppercase tracking-[0.16em] text-[var(--accent)] mb-1">Enabled</div>
              <div className="text-[10.5px] text-[var(--text-dim)]">
                Press <span className="font-mono text-[var(--accent)]">{hotkey}</span> to cycle SOCD profiles
              </div>
            </div>
          ) : (
            <div className="text-[11.5px] text-[var(--text-dim)]">
              <div className="font-display uppercase tracking-[0.16em] mb-1">Disabled</div>
              <div className="text-[10.5px]">Toggle to enable hotkey switching</div>
            </div>
          )}
        </div>
      </div>

      <button onClick={() => handleSocdApply && handleSocdApply(socdProfiles, hotkeyEnabled)}
        className="px-4 h-9 rounded-md border border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] font-display text-[12px] uppercase tracking-[0.16em] shadow-[0_0_18px_var(--accent-glow)] hover:brightness-110">
        Apply
      </button>
    </div>
  );
};

/* ===== Active Pairs Widget ===== */
const ActivePairsWidget = (ctx) => {
  const { socdProfiles, socdActive, setSocdActive } = ctx;

  return (
    <div className="flex flex-col gap-3 h-full">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--text-faint)] mb-2">{socdProfiles.length}/20 pairs</div>
      </div>

      <div className="flex flex-col gap-1.5 flex-1 overflow-y-auto">
        {socdProfiles.map(p => (
          <button key={p.id} onClick={() => setSocdActive(p.id)}
            className={`flex flex-col px-3 py-2 rounded-md border font-mono text-[12px] transition-all
                        ${socdActive === p.id
                          ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 text-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]"
                          : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
            <div className="font-display text-[11px] uppercase tracking-[0.16em]">{p.id}</div>
            {p.k1 && p.k2 ? (
              <div className="text-[10px] text-[var(--text-faint)] mt-1">
                {p.k1} <span className="text-[var(--text-faint)]">↔</span> {p.k2}
                <span className="ml-2 font-display text-[9px]">M{p.mode}</span>
              </div>
            ) : (
              <div className="text-[10px] text-[var(--text-faint)] mt-1">unconfigured</div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
};

/* ===== Widget Array Export ===== */
window.AetherWorkspaces = window.AetherWorkspaces || {};
window.AetherWorkspaces.SOCD_WIDGETS = [
  {
    id: "pair-editor",
    title: "Pair Editor",
    default: { x: 20, y: 20, w: 440, h: 520 },
    min: { w: 320, h: 400 },
    render: PairEditorWidget
  },
  {
    id: "hotkey",
    title: "Hotkey",
    default: { x: 480, y: 20, w: 360, h: 160 },
    min: { w: 280, h: 120 },
    render: HotkeyWidget
  },
  {
    id: "active-pairs",
    title: "Active Pairs",
    default: { x: 480, y: 200, w: 360, h: 340 },
    min: { w: 280, h: 240 },
    render: ActivePairsWidget
  }
];
})();
