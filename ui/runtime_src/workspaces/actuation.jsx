(() => {
/* ============================================================
   Actuation workspace — the REFERENCE workspace for the desktop-widget shell.
   Exports window.AetherWorkspaces.ACTUATION_WIDGETS — an array of widget descriptors:
     { id, title, default:{x,y,w,h}, min:{w,h}, render:(ctx)=>JSX }
   Each render() reads/calls ONLY ctx.* (state + handlers app.jsx passes down).
   Control JSX + telemetry (SwitchRender depth math, live depth) reused verbatim
   from the old ActuationSection via window.AetherSections shared primitives.
   ============================================================ */
const { useState } = React;
const S = window.AetherSections || {};
const Slider = S.Slider, Chip = S.Chip, SwitchRender = S.SwitchRender;
const I = window.AetherIcons || {};
const ICheck = I.ICheck, ICrosshair = I.ICrosshair;

/* Shared apply-button class + confirm toast (from ActuationSection). */
const applyBtnCls = (enabled) =>
  `px-4 h-9 rounded-md border font-display text-[12px] uppercase tracking-[0.16em] transition-all ${
    enabled
      ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_18px_var(--accent-glow)] hover:brightness-110"
      : "border-[var(--line)] bg-white/[0.02] text-[var(--text-faint)] cursor-not-allowed"
  }`;
const useFlash = () => {
  const [confirm, setConfirm] = useState(null);
  const flash = (msg) => { setConfirm(msg); setTimeout(() => setConfirm(null), 2400); };
  return [confirm, flash];
};
const ConfirmToast = ({ confirm }) => confirm ? (
  <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--accent)]">✓ {confirm}</span>
) : null;

/* ============================================================
   Board-awareness helpers (additive — PER_BOARD_PARITY_PLAN step 6).
   ctx.board is the board-context value from components/board-context.jsx
   (locked contract). Everything falls back to today's hardcoded values when
   the board declares nothing, so the Win60 (and any unknown board) renders
   exactly as before.
   ============================================================ */
const boardCtxOf = (ctx) =>
  (ctx && ctx.board)
  || (window.AetherBoard && window.AetherBoard.UNKNOWN_BOARD)
  || { board: null, lighting: null, actuation: null,
       cap: () => undefined, capState: () => "unknown", isSupported: () => true };

/* [min, max] from a registry range with a hardcoded fallback (today's values). */
const rangeOr = (r, fallback) =>
  (Array.isArray(r) && r.length === 2 && isFinite(r[0]) && isFinite(r[1])) ? r : fallback;

/* ===== Travel widget (actuation point + rapid trigger + live switch render) ===== */
function TravelWidget(ctx) {
  const {
    actuation, setActuation, rtPress, setRtPress, rtRelease, setRtRelease,
    rtEnabled, setRtEnabled, travelTest, setTravelTest, liveMax = 0,
    selectedKeys, applyActuation,
  } = ctx;
  const selectedCount = selectedKeys ? selectedKeys.size : 0;
  const scope = selectedCount > 0 ? `${selectedCount} selected key${selectedCount > 1 ? "s" : ""}` : "no keys (select some)";
  const canApply = selectedCount > 0;
  const [confirm, flash] = useFlash();

  /* Board awareness (additive): ranges from the registry actuation block when
     present (the Win60's block equals today's hardcoded values), rapid-trigger
     gated on the capability flag ("wip" = source-only = unavailable; unknown =
     fail-open = render as today). */
  const bctx = boardCtxOf(ctx);
  const bact = bctx.actuation;
  const boardName = (bctx.board && bctx.board.name) || "this board";
  const [travelMin, travelMax] = rangeOr(bact && bact.travelRange, [0.1, 3.4]);
  const [rtMin, rtMax] = rangeOr(bact && bact.rtRange, [0.05, 2.0]);
  const rtState = bctx.capState ? bctx.capState("rapidTrigger") : "unknown";
  const rtAvailable = rtState === "yes" || rtState === "unknown";
  const handleApplyTravel = () => {
    if (!canApply || !applyActuation) return;
    applyActuation();
    const rt = (rtEnabled && rtAvailable) ? ` · RT press ${rtPress.toFixed(2)}mm / release ${rtRelease.toFixed(2)}mm` : "";
    flash(`Wrote ${actuation.toFixed(2)}mm to ${selectedCount} key${selectedCount === 1 ? "" : "s"}${rt}`);
  };
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-5">
      {/* Live switch render */}
      <div className="glass p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Travel Test</span>
          <button onClick={() => setTravelTest(!travelTest)}
            className={`relative w-10 h-5 rounded-full border transition-colors
                        ${travelTest ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-[var(--line)]"}`}>
            <span className={`absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                              ${travelTest ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`}/>
          </button>
        </div>
        <SwitchRender depth={travelTest ? liveMax : actuation} actuation={actuation}/>
      </div>
      {/* Controls */}
      <div>
        <p className="text-[12px] text-[var(--text-dim)] mb-3">
          Select keys on the board, set the actuation point, then press <span className="text-[var(--accent)]">Apply</span> — only the selected keys are written. Nothing is sent while you move the slider.
        </p>
        <div className="mb-5 inline-flex items-center gap-2 px-3 h-7 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/[0.06]">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Applying to</span>
          <span className="font-display text-[11px] uppercase tracking-[0.16em] text-[var(--accent)]">{scope}</span>
        </div>
        <div className="mb-5">
          <Slider label="Key Trigger Travel" value={actuation} min={travelMin} max={travelMax} step={0.05} unit="mm" onChange={setActuation}/>
          <div className="flex items-center gap-2 mt-2">
            <button onClick={() => setActuation(Math.max(0.1, actuation - 0.05))}
              className="w-7 h-7 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]">−</button>
            <div className="px-3 h-7 rounded-md border border-[var(--line)] bg-white/[0.02] grid place-items-center font-mono text-[12px] text-[var(--text)]">
              {actuation.toFixed(2)} mm
            </div>
            <button onClick={() => setActuation(Math.min(4.0, actuation + 0.05))}
              className="w-7 h-7 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]">+</button>
          </div>
        </div>
        {rtAvailable ? (
          <>
            <label className="flex items-center gap-2 cursor-pointer select-none mb-3">
              <span className={`w-4 h-4 rounded border grid place-items-center transition
                                ${rtEnabled ? "border-[var(--accent)] bg-[var(--accent)]/20" : "border-[var(--line)] bg-white/[0.02]"}`}
                    onClick={() => setRtEnabled(!rtEnabled)}>
                {rtEnabled && ICheck && <ICheck size={10} className="text-[var(--accent)]"/>}
              </span>
              <input type="checkbox" checked={rtEnabled} onChange={(e) => setRtEnabled(e.target.checked)} className="sr-only"/>
              <span className="font-display text-[11.5px] uppercase tracking-[0.16em] text-[var(--text)]">Rapid Trigger</span>
              {Chip && <Chip color="accent">RT</Chip>}
            </label>
            <p className="text-[11.5px] text-[var(--text-faint)] leading-relaxed mb-4">
              Rapid Trigger dynamically actuates and resets your key based on your intent — perfect for counter-strafing and rebound presses.
            </p>
            {rtEnabled && (
              <div className="grid grid-cols-2 gap-5 mt-4 p-4 rounded-lg border border-[var(--accent)]/20 bg-[var(--accent)]/[0.05]">
                <Slider label="Press Sensitivity" value={rtPress} min={rtMin} max={rtMax} step={0.05} unit="mm" onChange={setRtPress}/>
                <Slider label="Release Sensitivity" value={rtRelease} min={rtMin} max={rtMax} step={0.05} unit="mm" onChange={setRtRelease}/>
              </div>
            )}
          </>
        ) : (
          /* Unavailable — same info-box idiom as Dead Band / Switch / Calibration
             (and the pre-existing Polling readout): bordered ink card, mono body. */
          <div className="mb-4 p-4 rounded-lg border border-[var(--line)] bg-[rgba(5,11,14,0.5)]">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="font-display text-[11.5px] uppercase tracking-[0.16em] text-[var(--text-dim)]">Rapid Trigger</span>
              {Chip && <Chip color="accent">RT</Chip>}
            </div>
            <p className="font-mono text-[11px] text-[var(--text-dim)] leading-relaxed">
              {rtState === "wip"
                ? `Rapid trigger is not yet available on ${boardName} — its protocol is known only from vendor driver source and has not been verified on hardware, so Aether will not drive it.`
                : `${boardName} does not support rapid trigger.`}
            </p>
          </div>
        )}
        <div className="mt-6 flex items-center gap-3">
          <button onClick={handleApplyTravel} disabled={!canApply} className={applyBtnCls(canApply)}>
            Apply to {selectedCount || 0} key{selectedCount === 1 ? "" : "s"}
          </button>
          {confirm ? <ConfirmToast confirm={confirm}/>
            : <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--text-faint)]">
                {canApply ? "writes only the selected keys" : "select keys on the board to enable"}
              </span>}
        </div>
      </div>
    </div>
  );
}

/* ===== Dead Band widget ===== */
function DeadBandWidget(ctx) {
  const { deadTop, setDeadTop, deadBottom, setDeadBottom, selectedKeys, applyDeadband } = ctx;
  const selectedCount = selectedKeys ? selectedKeys.size : 0;
  const [confirm, flash] = useFlash();

  /* Board awareness (additive). deadzoneScope "global" means the dead zones
     live in ONE whole-board config table — a per-key control CANNOT work on
     that hardware, so the widget becomes a single board-wide control. The
     Win60 declares "per-key" (and unknown boards declare nothing), so both
     take the original per-key path unchanged. */
  const bctx = boardCtxOf(ctx);
  const bact = bctx.actuation;
  const boardName = (bctx.board && bctx.board.name) || "this board";
  const globalScope = !!(bact && bact.deadzoneScope === "global");
  const [dzMin, dzMax] = rangeOr(bact && bact.deadzoneRange, [0.0, 0.5]);
  const dzState = bctx.capState ? bctx.capState("deadzone") : "unknown";
  const canApply = globalScope ? true : selectedCount > 0;

  const handleApplyDead = () => {
    if (!canApply || !applyDeadband) return;
    applyDeadband();
    flash(`Wrote dead band ${(deadTop ?? 0.04).toFixed(2)}/${(deadBottom ?? 0.05).toFixed(2)}mm to ${globalScope ? "the whole board" : `${selectedCount} key${selectedCount === 1 ? "" : "s"}`}`);
  };

  /* Capability gate: "wip" = decoded from vendor source only, never proven on
     hardware — do not drive it. The Win60 flag is a hard true (and unknown
     boards fail open), so this branch never renders there. */
  if (dzState === "wip" || dzState === "no") {
    return (
      <div>
        <p className="text-[12px] text-[var(--text-dim)] mb-4">
          Configure the dead-band region near the keycap's rest and bottom-out positions — noise inside this band is ignored.
        </p>
        <div className="p-4 rounded-lg border border-[var(--line)] bg-[rgba(5,11,14,0.5)] font-mono text-[11px] text-[var(--text-dim)] leading-relaxed">
          {dzState === "wip"
            ? `Dead-band control is not yet available on ${boardName} — its protocol is known only from vendor driver source and has not been verified on hardware, so Aether will not drive it.`
            : `${boardName} does not support dead-band configuration.`}
        </div>
      </div>
    );
  }

  return (
    <div>
      <p className="text-[12px] text-[var(--text-dim)] mb-5">
        {globalScope ? (
          <>Configure the dead-band region near the keycap's rest and bottom-out positions — noise inside this band is ignored. On {boardName} the dead zones are a <span className="text-[var(--accent)]">single board-wide setting</span>: per-key dead bands are not possible on this hardware, so these values apply to every key at once.</>
        ) : (
          <>Configure the dead-band region near the keycap's rest and bottom-out positions — noise inside this band is ignored. Press <span className="text-[var(--accent)]">Apply</span> to write to the selected keys.</>
        )}
      </p>
      {globalScope && (
        <div className="mb-5 inline-flex items-center gap-2 px-3 h-7 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/[0.06]">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Scope</span>
          <span className="font-display text-[11px] uppercase tracking-[0.16em] text-[var(--accent)]">Whole board · every key</span>
        </div>
      )}
      <div className="grid grid-cols-2 gap-6">
        <Slider label="Top Dead Band" value={deadTop ?? 0.04} min={dzMin} max={dzMax} step={0.01} unit="mm" onChange={setDeadTop}/>
        <Slider label="Bottom Dead Band" value={deadBottom ?? 0.05} min={dzMin} max={dzMax} step={0.01} unit="mm" onChange={setDeadBottom}/>
      </div>
      <div className="mt-6 flex items-center gap-3">
        <button onClick={handleApplyDead} disabled={!canApply} className={applyBtnCls(canApply)}>
          {globalScope ? "Apply to whole board" : <>Apply to {selectedCount || 0} key{selectedCount === 1 ? "" : "s"}</>}
        </button>
        {confirm ? <ConfirmToast confirm={confirm}/>
          : <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--text-faint)]">
              {globalScope ? "one pair of values for every key — key selection is ignored"
                : canApply ? "writes only the selected keys" : "select keys on the board to enable"}
            </span>}
      </div>
    </div>
  );
}

/* ===== Switch widget ===== */
const SWITCHES = [
  { id: "hm1", name: "HM1", sub: "Magnetic Switch", dot: "#3b82f6",
    maker: "Gateron", travel: "4.0 mm", force: "30 gf", range: "0.1 – 4.0 mm", poles: "Single", life: "100 M" },
  { id: "hh1", name: "HH1", sub: "Magnetic Switch", dot: "#a3a300",
    maker: "Gateron", travel: "3.5 mm", force: "40 gf", range: "0.1 – 3.5 mm", poles: "Single", life: "100 M" },
  { id: "cy1", name: "CY1", sub: "Magnetic Switch", dot: "#cbd5e1",
    maker: "KZZI",    travel: "3.4 mm", force: "35 gf", range: "0.1 – 3.4 mm", poles: "Single", life: "80 M" },
  { id: "tc1", name: "TC1", sub: "TTC Kom",         dot: "#c026d3",
    maker: "TTC",     travel: "3.6 mm", force: "45 gf", range: "0.2 – 3.6 mm", poles: "Dual",   life: "100 M" },
];
function SwitchWidget(ctx) {
  const { switchId, handlePickSwitch } = ctx;

  /* Board awareness (additive): the switch/axis list comes from the registry
     actuation block when the board declares one. The Win60's registry list
     carries the same four ids as the hardcoded list below, and matching ids
     keep the hardcoded display fields verbatim — so the Win60 renders
     byte-identically. A board that declares an EMPTY list (axis ids never
     verified on hardware) gets an honest explanation instead of a picker.
     No board data at all -> today's hardcoded list (fail-open). */
  const bctx = boardCtxOf(ctx);
  const bact = bctx.actuation;
  const boardName = (bctx.board && bctx.board.name) || "this board";
  let switchList = SWITCHES;
  if (bact && Array.isArray(bact.switches)) {
    if (bact.switches.length === 0) {
      return (
        <div>
          <p className="text-[12px] text-[var(--text-dim)] mb-5">
            Select the magnetic switch profile installed in your board. Calibration curves load automatically.
          </p>
          <div className="p-4 rounded-lg border border-[var(--line)] bg-[rgba(5,11,14,0.5)] font-mono text-[11px] text-[var(--text-dim)] leading-relaxed">
            No verified switch list for {boardName} yet — this board selects its magnetic
            axis per key by an id that has never been read back from hardware. Aether
            will not guess axis ids, so the switch picker stays disabled.
          </div>
        </div>
      );
    }
    switchList = bact.switches.map(s => {
      const legacy = SWITCHES.find(x => x.id === s.id);
      return legacy ? { ...s, ...legacy } : s;
    });
  }
  const defaultId = (switchList[0] && switchList[0].id) || "hm1";
  const cur = switchList.find(s => s.id === (switchId || defaultId)) || switchList[0];
  return (
    <div>
      <p className="text-[12px] text-[var(--text-dim)] mb-5">
        Select the magnetic switch profile installed in your board. Calibration curves load automatically.
      </p>
      <div className="grid grid-cols-2 gap-3 mb-5">
        {switchList.map(s => {
          const active = (switchId || defaultId) === s.id;
          return (
          <button key={s.id} onClick={() => handlePickSwitch && handlePickSwitch(s.id)}
            className={`text-left rounded-lg border p-3 transition-all
                        ${active
                          ? "border-[var(--accent)]/50 bg-[var(--accent)]/[0.06] shadow-[0_0_14px_var(--accent-glow)]"
                          : "border-[var(--line)] bg-white/[0.02] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
            <div className="flex items-center gap-2">
              <div className="font-display text-[14px] text-[var(--text)]">{s.name}</div>
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: s.dot, boxShadow: `0 0 8px ${s.dot}` }}/>
            </div>
            <div className="font-mono text-[10px] text-[var(--text-faint)] uppercase tracking-[0.18em] mt-0.5">{s.sub}</div>
          </button>
          );
        })}
      </div>
      <div className="rounded-xl border border-[var(--line)] bg-[rgba(5,11,14,0.5)] p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: cur.dot, boxShadow: `0 0 8px ${cur.dot}` }}/>
          <span className="font-display text-[13px] text-[var(--text)]">{cur.name}</span>
          <span className="font-mono text-[10px] text-[var(--text-faint)] uppercase tracking-[0.18em]">{cur.maker} · {cur.sub}</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3 font-mono text-[11px]">
          {[
            ["Total Travel", cur.travel || "—"], ["Actuation Range", cur.range || "—"],
            ["Initial Force", cur.force || "—"], ["Sensing", cur.poles ? cur.poles + " Hall" : "—"],
            ["Rated Life", cur.life ? cur.life + " presses" : "—"], ["Tech", "Magnetic / Analog"],
          ].map(([k, v]) => (
            <div key={k}>
              <div className="text-[var(--text-faint)] uppercase tracking-[0.14em] text-[9.5px]">{k}</div>
              <div className="text-[var(--text)] mt-0.5">{v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ===== Polling Rate widget ===== */
function PollingWidget(ctx) {
  const { polling, handleSetPolling } = ctx;
  return (
    <div>
      <p className="text-[12px] text-[var(--text-dim)] mb-5">
        Switch the polling rate of the device. The keyboard will restart and disconnect briefly after switching.
      </p>
      <div className="flex flex-wrap gap-2">
        {[1, 2, 4, 8].map(p => (
          <button key={p} onClick={() => handleSetPolling(p)}
            className={`px-4 h-9 rounded-md border font-display text-[12px] uppercase tracking-[0.16em] transition-all
                        ${polling === p
                          ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_18px_var(--accent-glow)]"
                          : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`}>
            {p}KHz
          </button>
        ))}
      </div>
      <div className="mt-6 p-4 rounded-lg border border-[var(--line)] bg-[rgba(5,11,14,0.5)] font-mono text-[11px] text-[var(--text-dim)] leading-relaxed">
        <div><span className="text-[var(--text-faint)]">current</span> · <span className="text-[var(--accent)]">{polling}000 Hz</span> · {(1000/polling).toFixed(2)}ms tick</div>
        <div><span className="text-[var(--text-faint)]">latency</span> · ~{(0.5 + 1/polling).toFixed(2)}ms end-to-end</div>
      </div>
    </div>
  );
}

/* ===== Calibration widget ===== */
function CalibrationWidget(ctx) {
  const { calibrating, handleCalibrate } = ctx;

  /* Board awareness (additive): gate on the calibration capability. "wip"
     means the commands are only known from vendor driver source — never
     verified on hardware — and must not be driven. The Win60 flag is a hard
     true (and unknown boards fail open), so it renders exactly as today. */
  const bctx = boardCtxOf(ctx);
  const calState = bctx.capState ? bctx.capState("calibration") : "unknown";
  if (calState === "wip" || calState === "no") {
    const boardName = (bctx.board && bctx.board.name) || "this board";
    return (
      <div>
        <div className="font-display text-[12px] uppercase tracking-[0.18em] text-[var(--text)] mb-3">Key Calibration</div>
        <div className="p-4 rounded-lg border border-[var(--line)] bg-[rgba(5,11,14,0.5)] font-mono text-[11px] text-[var(--text-dim)] leading-relaxed max-w-2xl">
          {calState === "wip"
            ? `Calibration is not yet available on ${boardName} — its protocol is known only from vendor driver source and has not been verified on hardware, so Aether will not drive it.`
            : `${boardName} does not support key calibration.`}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="font-display text-[12px] uppercase tracking-[0.18em] text-[var(--text)] mb-3">Key Calibration</div>
      <button onClick={() => handleCalibrate && handleCalibrate(!calibrating)}
        className="px-5 h-10 rounded-md border border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] font-display text-[12px] uppercase tracking-[0.18em] shadow-[0_0_18px_var(--accent-glow)] mb-5">
        {calibrating ? "Stop Calibration" : "Start Calibration"}
      </button>
      <div className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)] mb-2">Calibration steps:</div>
      <ol className="space-y-2 text-[12px] text-[var(--text-dim)] max-w-2xl">
        {[
          "Click the Start Calibration button",
          "Press the required key (Hit bottom)",
          "Wait for the corresponding key to change color, and the key calibration is complete",
          "Click the Stop Calibration button"
        ].map((step, i) => (
          <li key={i} className="flex items-start gap-3">
            <span className="shrink-0 grid place-items-center w-5 h-5 rounded border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent)] font-mono text-[10px]">{i+1}</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

const ACTUATION_WIDGETS = [
  { id: "travel",  title: "Travel",       default: { x: 40,  y: 32,  w: 680, h: 430 }, min: { w: 420, h: 320 }, render: TravelWidget },
  { id: "dead",    title: "Dead Band",    default: { x: 736, y: 32,  w: 460, h: 300 }, min: { w: 320, h: 240 }, render: DeadBandWidget },
  { id: "switch",  title: "Switch",       default: { x: 736, y: 352, w: 460, h: 430 }, min: { w: 340, h: 300 }, render: SwitchWidget },
  { id: "poll",    title: "Polling Rate", default: { x: 40,  y: 488, w: 380, h: 300 }, min: { w: 300, h: 240 }, render: PollingWidget },
  { id: "calib",   title: "Calibration",  default: { x: 440, y: 488, w: 456, h: 360 }, min: { w: 340, h: 280 }, render: CalibrationWidget },
];

window.AetherWorkspaces = window.AetherWorkspaces || {};
window.AetherWorkspaces.ACTUATION_WIDGETS = ACTUATION_WIDGETS;
// Pure board-awareness helpers exported for verification (no UI reads these).
window.AetherWorkspaces.ACTUATION_BOARD = { SWITCHES, rangeOr, boardCtxOf };
})();
