(() => {
/* ============================================================
   Keymap workspace — mirrors the Actuation reference workspace shape.
   Exports window.AetherWorkspaces.KEYMAP_WIDGETS — an array of widget descriptors:
     { id, title, default:{x,y,w,h}, min:{w,h}, render:(ctx)=>JSX }
   Each render() reads/calls ONLY ctx.* (state + handlers app.jsx passes down).
   Reuses KeyGrid JSX from sections.jsx's KeymapSection (basic/extended key picker)
   and the existing keyboard.jsx KeyboardPanel for the selectable board — its
   per-key device-color/actuation styling stays byte-identical, untouched here.
   ============================================================ */
const { useState } = React;
const S = window.AetherSections || {};
const { Chip, ToolbarButton, LayerPicker } = S;
const KB = window.AetherKeyboard || {};
const KeyboardPanel = KB.KeyboardPanel;

/* ===== Key label sets (verbatim from sections.jsx KeymapSection) ===== */
const BASIC_KEYS = [
  "A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T","U",
  "V","W","X","Y","Z","1!","2@","3#","$4","5%","6^","7&","8*","9(","0)","-_","=+","{[","}]","\\|","<>",";:","'\"","`~",",<",".>","/?"
];
const EXTENDED_KEYS = [
  "Esc","Tab","Caps","Back","Enter","Space","L-Ctrl","R-Ctrl","L-Shift","R-Shift","L-Alt","R-Alt","L-Win","R-Win","Menu","Left","Up","Right","Down",
  "PrtSc","ScrLk","Pause","Ins","Home","Del","End","PgUp","PgDn","F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12"
];

/* KeyGrid — collapsible label picker (verbatim JSX from sections.jsx). */
const KeyGrid = ({ title, keys, picked, onPick }) => {
  const [open, setOpen] = useState(true);
  const I = window.AetherIcons || {};
  const IChevronD = I.IChevronD;
  return (
    <div>
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 mb-2 text-[var(--text-dim)] hover:text-[var(--text)]">
        {IChevronD && <IChevronD size={12} className={open ? "" : "-rotate-90"}/>}
        <span className="font-display text-[12px] uppercase tracking-[0.18em]">{title}</span>
      </button>
      {open && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(46px,1fr))] gap-1.5">
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

/* ===== Key Grid widget — the selectable keyboard board ===== */
function KeyGridWidget(ctx) {
  const {
    selectedKeys, setSelectedKeys, layer, ledMap, calibrating, calibratedKeys, liveDepths,
  } = ctx;
  return (
    <div className="flex justify-center">
      {KeyboardPanel
        ? React.createElement(KeyboardPanel, {
            mode: "keymap",
            layer: layer || "default",
            selectedKeys, setSelectedKeys,
            ledMap,
            showPill: false,
            compact: true,
            calibrating: !!calibrating,
            calibratedCodes: calibratedKeys,
            liveDepths,
          })
        : <div className="font-mono text-[11px] text-[var(--text-faint)]">Keyboard render unavailable.</div>}
    </div>
  );
}

/* ===== Remap Editor widget — assign HID to selected keys ===== */
function RemapEditorWidget(ctx) {
  const { selectedKeys, selectedKey, HID_BY_LABEL, remapSelected, resetRemapSelected } = ctx;
  const [picked, setPicked] = useState(null);
  const [flash, setFlash] = useState(null);
  const showFlash = (kind) => { setFlash(kind); setTimeout(() => setFlash(null), 1400); };
  const selectedCount = selectedKeys ? selectedKeys.size : 0;
  const curLabel = selectedKey || (selectedCount ? `${selectedCount} keys` : "None");

  const doApply = () => {
    if (!picked || !selectedCount || !remapSelected) return;
    remapSelected(picked);
    showFlash("applied");
  };
  const doReset = () => {
    if (resetRemapSelected) resetRemapSelected();
    setPicked(null);
    showFlash("reset");
  };

  return (
    <div>
      <ol className="text-[12px] text-[var(--text-dim)] leading-relaxed space-y-2 mb-4 font-mono">
        <li><span className="text-[var(--accent)]">01.</span> Click a key on the Key Grid widget.</li>
        <li><span className="text-[var(--accent)]">02.</span> Pick the new mapping below.</li>
        <li><span className="text-[var(--accent)]">03.</span> Hit <span className="text-[var(--text)]">Apply</span> to flash.</li>
      </ol>

      <div className="flex items-stretch gap-2 mb-3">
        <div className="grid place-items-center px-3 min-w-[64px] rounded-md border border-[var(--line)] bg-white/[0.02] font-mono text-[11px] text-[var(--text-dim)]">
          {curLabel}
        </div>
        <div className="grid place-items-center text-[var(--text-faint)]">→</div>
        <div className="flex-1 rounded-md border border-[var(--line)] bg-white/[0.02] px-3 grid place-items-start py-2">
          <span className="font-mono text-[12px] text-[var(--text)]">{picked || "—"}</span>
          <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]">remap target</span>
        </div>
      </div>

      <div className="flex gap-2 mb-2">
        <button onClick={doReset}
          className="flex-1 h-9 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] font-display text-[11px] uppercase tracking-[0.18em] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]">
          Default
        </button>
        <button
          disabled={!picked || !selectedCount}
          onClick={doApply}
          className={`flex-1 h-9 rounded-md border font-display text-[11px] uppercase tracking-[0.18em] transition-all
                      ${(!picked || !selectedCount)
                        ? "border-[var(--line)] bg-white/[0.02] text-[var(--text-faint)] cursor-not-allowed"
                        : "border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25 shadow-[0_0_12px_var(--accent-glow)]"}`}>
          Apply
        </button>
      </div>
      <div className="h-5 mb-3 text-[11px] font-mono tracking-[0.14em]">
        {!selectedCount && <span className="text-amber-400/80">Select a key on the Key Grid first.</span>}
        {flash === "applied" && <span className="text-[var(--accent)]">✓ Remapped {selectedCount} key{selectedCount > 1 ? "s" : ""} → {picked}</span>}
        {flash === "reset" && <span className="text-[var(--text-dim)]">↩ Restored default mapping</span>}
      </div>

      <div className="flex flex-col gap-4">
        <KeyGrid title="Basic Keys" keys={BASIC_KEYS} picked={picked} onPick={setPicked}/>
        <KeyGrid title="Extended Keys" keys={EXTENDED_KEYS} picked={picked} onPick={setPicked}/>
      </div>
    </div>
  );
}

/* ===== Layer Picker widget ===== */
function LayerPickerWidget(ctx) {
  const { layer, setLayer, selectAllKeys, selectInvertKeys, deselectAllKeys } = ctx;
  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2">Active Layer</div>
        {LayerPicker
          ? <div className="flex flex-row lg:flex-col gap-2">
              {React.createElement(LayerPicker, { layer, setLayer })}
            </div>
          : <div className="font-mono text-[11px] text-[var(--text-faint)]">Layer picker unavailable.</div>}
      </div>
      <div>
        <div className="font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2">Selection</div>
        <div className="flex flex-col gap-1.5">
          {ToolbarButton
            ? [
                { label: "Select All",    onClick: selectAllKeys },
                { label: "Select Invert", onClick: selectInvertKeys },
                { label: "Deselect All",  onClick: deselectAllKeys },
              ].map(b => (
                <div key={b.label}>{React.createElement(ToolbarButton, { onClick: b.onClick }, b.label)}</div>
              ))
            : <div className="font-mono text-[11px] text-[var(--text-faint)]">Toolbar unavailable.</div>}
        </div>
      </div>
      {Chip && (
        <div>
          {React.createElement(Chip, { color: "accent" }, layer === "fn" ? "Fn Layer" : "Default Layer")}
        </div>
      )}
    </div>
  );
}

const KEYMAP_WIDGETS = [
  { id: "keygrid", title: "Key Grid",     default: { x: 40,  y: 32,  w: 760, h: 460 }, min: { w: 520, h: 360 }, render: KeyGridWidget },
  { id: "remap",   title: "Remap Editor", default: { x: 820, y: 32,  w: 460, h: 460 }, min: { w: 340, h: 340 }, render: RemapEditorWidget },
  { id: "layer",   title: "Layer Picker", default: { x: 40,  y: 516, w: 320, h: 300 }, min: { w: 260, h: 240 }, render: LayerPickerWidget },
];

window.AetherWorkspaces = window.AetherWorkspaces || {};
window.AetherWorkspaces.KEYMAP_WIDGETS = KEYMAP_WIDGETS;
})();
