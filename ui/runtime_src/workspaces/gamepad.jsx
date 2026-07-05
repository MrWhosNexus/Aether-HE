(() => {
/* ============================================================
   Gamepad workspace — window.AetherWorkspaces.GAMEPAD_WIDGETS.
   Reuses GamepadSection JSX verbatim (split into 3 widgets) from
   ui/runtime_src/src/sections.jsx — no re-implementation of the
   virtual-pad capture / mapping UI, only layout is split.
   ============================================================ */
const I = window.AetherIcons || {};
const { IZap, IRefresh, IPlus, ITrash } = I;

const PAD_KEYS = [
  "A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P","Q","R","S","T",
  "U","V","W","X","Y","Z","Space","Enter","L-Shift","L-Ctrl","Up","Down","Left","Right"
];
const PAD_AXES = [
  { id: "LX", label: "Left Stick X", stick: true },
  { id: "LY", label: "Left Stick Y", stick: true },
  { id: "RX", label: "Right Stick X", stick: true },
  { id: "RY", label: "Right Stick Y", stick: true },
  { id: "LT", label: "Left Trigger", stick: false },
  { id: "RT", label: "Right Trigger", stick: false },
  { id: "BTN_A", label: "Button A", stick: false, btn: true },
  { id: "BTN_B", label: "Button B", stick: false, btn: true },
  { id: "BTN_X", label: "Button X", stick: false, btn: true },
  { id: "BTN_Y", label: "Button Y", stick: false, btn: true },
  { id: "BTN_LB", label: "Bumper L", stick: false, btn: true },
  { id: "BTN_RB", label: "Bumper R", stick: false, btn: true },
];
const axisMeta = (id) => PAD_AXES.find(a => a.id === id) || PAD_AXES[0];

/* ===== Enable / Status widget ===== */
function EnableStatusWidget(ctx) {
  const { connected, gamepadOn, handleGamepadToggle, gamepadError, handleInstallVigem } = ctx;
  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <div className="font-display text-[13px] uppercase tracking-[0.18em] text-[var(--text)] flex items-center gap-2">
            {IZap && <IZap size={15}/>} Virtual Gamepad
          </div>
          <p className="text-[12px] text-[var(--text-dim)] mt-1.5 max-w-xl">
            Streams live key travel into a system gamepad — press a key deeper for more throttle / steering.
            Maps below drive the analog axes &amp; buttons. {!connected && <span className="text-amber-400/80">Connect the board to capture.</span>}
          </p>
        </div>
        <button onClick={() => handleGamepadToggle(!gamepadOn)} disabled={!connected}
          className={`relative w-12 h-6 rounded-full border transition-colors shrink-0 ml-4
                      ${!connected ? "opacity-40 cursor-not-allowed" : ""}
                      ${gamepadOn ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-[rgba(5,11,14,0.5)] border-[var(--line)]"}`}>
          <span className={`absolute top-0.5 w-4.5 h-4.5 rounded-full transition-all
                            ${gamepadOn ? "left-[26px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-[var(--text-faint)]"}`}
                style={{ width: 18, height: 18 }}/>
        </button>
      </div>
      <div className="mt-3 font-mono text-[11px]">
        {gamepadOn
          ? <span className="text-emerald-400">● Capturing → "Aula Win60 HE Virtual Gamepad"</span>
          : <span className="text-[var(--text-faint)]">○ Idle</span>}
      </div>
      {gamepadError && (
        <div className="mt-3 rounded-md border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11.5px] text-rose-100 flex items-center justify-between gap-3">
          <span className="font-mono">{gamepadError.msg}</span>
          {gamepadError.needsDriver && (
            <button onClick={handleInstallVigem}
              className="shrink-0 px-3 h-7 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25">
              Install ViGEmBus
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ===== Axis Mapping widget ===== */
function AxisMappingWidget(ctx) {
  const { gamepadMap, handleGamepadMapApply, DEFAULT_PAD_MAP } = ctx;
  const rows = gamepadMap || [];
  const setRow = (i, patch) => handleGamepadMapApply(rows.map((r, j) => j === i ? { ...r, ...patch } : r));
  const addRow = () => handleGamepadMapApply([...rows, { key: "W", axis: "RT", direction: 1, threshold_mm: 1.5 }]);
  const removeRow = (i) => handleGamepadMapApply(rows.filter((_, j) => j !== i));

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Key → Control Mapping</span>
        <div className="flex gap-2">
          <button onClick={() => handleGamepadMapApply((DEFAULT_PAD_MAP || []).map(r => ({ ...r })))}
            className="px-3 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] flex items-center gap-1.5">
            {IRefresh && <IRefresh size={12}/>} Driving Defaults
          </button>
          <button onClick={addRow}
            className="px-3 h-8 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25 flex items-center gap-1.5">
            {IPlus && <IPlus size={12}/>} Add
          </button>
        </div>
      </div>

      <div className="grid grid-cols-[1fr_1.4fr_1.2fr_28px] gap-2 px-1 mb-1.5 font-mono text-[9.5px] uppercase tracking-[0.18em] text-[var(--text-faint)]">
        <span>Key</span><span>Control</span><span>Behaviour</span><span/>
      </div>

      <div className="flex flex-col gap-2">
        {rows.map((r, i) => {
          const meta = axisMeta(r.axis);
          return (
            <div key={i} className="grid grid-cols-[1fr_1.4fr_1.2fr_28px] gap-2 items-center">
              <select value={r.key} onChange={(e) => setRow(i, { key: e.target.value })}
                className="h-9 rounded-md bg-[rgba(5,11,14,0.5)] border border-[var(--line)] px-2 font-mono text-[12px] text-[var(--text)] outline-none focus:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]">
                {PAD_KEYS.map(k => <option key={k} value={k}>{k}</option>)}
              </select>
              <select value={r.axis} onChange={(e) => setRow(i, { axis: e.target.value })}
                className="h-9 rounded-md bg-[rgba(5,11,14,0.5)] border border-[var(--line)] px-2 font-mono text-[12px] text-[var(--text)] outline-none focus:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]">
                {PAD_AXES.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
              </select>
              {meta.stick ? (
                <div className="flex gap-1">
                  {[["−", -1], ["+", 1]].map(([lbl, val]) => (
                    <button key={val} onClick={() => setRow(i, { direction: val })}
                      className={`flex-1 h-9 rounded-md border font-mono text-[13px] transition-all
                                  ${(r.direction || 1) === val
                                    ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)]"
                                    : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
                      {lbl}
                    </button>
                  ))}
                </div>
              ) : meta.btn ? (
                <div className="flex items-center gap-2">
                  <input type="range" className="aether flex-1" min={0.2} max={4.0} step={0.1}
                         value={r.threshold_mm ?? 1.5}
                         style={{ "--pct": (((r.threshold_mm ?? 1.5) - 0.2) / 3.8) * 100 + "%" }}
                         onChange={(e) => setRow(i, { threshold_mm: parseFloat(e.target.value) })}/>
                  <span className="font-mono text-[10px] text-[var(--text-dim)] w-12 text-right">{(r.threshold_mm ?? 1.5).toFixed(1)}mm</span>
                </div>
              ) : (
                <span className="font-mono text-[10px] text-[var(--text-faint)] pl-1">analog 0→max</span>
              )}
              <button onClick={() => removeRow(i)}
                className="w-7 h-7 grid place-items-center rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-faint)] hover:text-rose-300 hover:border-rose-400/30">
                {ITrash && <ITrash size={12}/>}
              </button>
            </div>
          );
        })}
        {!rows.length && <div className="text-[12px] text-[var(--text-faint)] py-4 text-center">No mappings — add one or load driving defaults.</div>}
      </div>

      <p className="text-[11px] text-[var(--text-faint)] mt-4 leading-relaxed">
        Sticks combine opposing keys (e.g. A=− and D=+ on Left Stick X). Triggers &amp; sticks are analog —
        deeper press = larger value. Buttons fire past their threshold. Changes apply live while capturing.
      </p>
    </div>
  );
}

/* ===== Driver Install widget (ViGEmBus) ===== */
function DriverInstallWidget(ctx) {
  const { handleInstallVigem, gamepadError } = ctx;
  const needsDriver = !!(gamepadError && gamepadError.needsDriver);
  return (
    <div>
      <div className="font-display text-[12px] uppercase tracking-[0.18em] text-[var(--text)] mb-3">Driver</div>
      <p className="text-[12px] text-[var(--text-dim)] mb-5 leading-relaxed">
        The virtual gamepad is emulated through <span className="text-[var(--text)]">ViGEmBus</span> — a
        kernel driver that exposes an Xbox 360-compatible controller to Windows. Install it once; no reboot
        is normally required.
      </p>
      <button onClick={handleInstallVigem}
        className="px-5 h-10 rounded-md border border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] font-display text-[12px] uppercase tracking-[0.18em] shadow-[0_0_18px_var(--accent-glow)] mb-4">
        Install ViGEmBus
      </button>
      <div className="font-mono text-[11px]">
        {needsDriver
          ? <span className="text-amber-400/80">Driver missing — install required before capture will work.</span>
          : <span className="text-[var(--text-faint)]">No driver issue detected.</span>}
      </div>
    </div>
  );
}

const GAMEPAD_WIDGETS = [
  { id: "enable",  title: "Enable / Status", default: { x: 40,  y: 32,  w: 620, h: 300 }, min: { w: 380, h: 220 }, render: EnableStatusWidget },
  { id: "axes",    title: "Axis Mapping",    default: { x: 680, y: 32,  w: 640, h: 520 }, min: { w: 460, h: 340 }, render: AxisMappingWidget },
  { id: "driver",  title: "Driver Install",  default: { x: 40,  y: 352, w: 500, h: 300 }, min: { w: 340, h: 240 }, render: DriverInstallWidget },
];

window.AetherWorkspaces = window.AetherWorkspaces || {};
window.AetherWorkspaces.GAMEPAD_WIDGETS = GAMEPAD_WIDGETS;
})();
