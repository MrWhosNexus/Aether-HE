(() => {
const { useState, useEffect, useRef } = React;
const api = () => (window.pywebview && window.pywebview.api) || {};
const ISSUE_BASE = "https://github.com/MrWhosNexus/Aether-HE/issues/new";

function buildIssueUrl(meta, dev) {
  // Pre-fills the add-a-board.yml form fields via query params.
  const p = new URLSearchParams({
    template: "add-a-board.yml",
    title: `[Board] ${meta.brand} ${meta.model} — add support`,
  });
  p.append("brand-model", `${meta.brand} ${meta.model}`);
  p.append("switch-type", meta.switch_type || "");
  p.append("form-factor", meta.form_factor || "");
  p.append("vid-pid", `${dev.vid}:${dev.pid}`);
  return `${ISSUE_BASE}?${p.toString()}`;
}

function BoardSubmit({ open, onClose }) {
  const [step, setStep] = useState(0);              // 0 detect,1 meta,2 capture,3 submit
  const [devices, setDevices] = useState([]);
  const [dev, setDev] = useState(null);
  const [meta, setMeta] = useState({ brand: "", model: "", switch_type: "Hall-effect", form_factor: "", size: "60" });
  const [reports, setReports] = useState([]);
  const [capturing, setCapturing] = useState(false);
  const [keysSeen, setKeysSeen] = useState(0);
  const [result, setResult] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => { if (open) { setStep(0); api().list_hid_devices?.().then(r => r && r.ok && setDevices(r.devices)); } }, [open]);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); api().stop_capture?.(); }, []);
  if (!open) return null;

  const startCapture = async () => {
    setReports([]); setKeysSeen(0);
    await api().open_capture?.(dev.path);
    setCapturing(true);
    pollRef.current = setInterval(async () => {
      const r = await api().read_capture?.();
      if (r && r.ok && r.count) {
        setReports(prev => {
          const next = prev.concat(r.reports);
          setKeysSeen(new Set(next.map(x => x.hex.slice(0, 6))).size);
          return next;
        });
      }
    }, 200);
  };
  const stopCapture = async () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setCapturing(false);
    await api().stop_capture?.();
  };

  const submit = async () => {
    const obj = {
      schema: "aether-board-submission/1",
      submitted_at: new Date().toISOString(),
      app_version: (window.__resources && window.__resources.version) || "0.2.0",
      device: dev, meta, size_template: `generic-${meta.size}`,
      input_capture: { duration_ms: reports.length ? reports[reports.length - 1].t : 0,
                       report_len: 64, reports, keys_seen: keysSeen },
      output_pcap: { attached: false, filename: null }, notes: "",
    };
    const r = await api().save_submission?.(obj);
    setResult(r);
    if (r && r.ok) await api().open_submission_url?.(buildIssueUrl(meta, dev));
  };

  // --- render: a glass modal with the 4 steps (detect / meta / capture / submit) ---
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 9999, display: "grid", placeItems: "center",
                  background: "rgba(3,7,9,0.6)", backdropFilter: "blur(6px)" }}>
      <div className="glass" style={{ width: "min(760px,94vw)", maxHeight: "90vh", overflow: "auto", padding: 24 }}>
        <div className="flex items-center justify-between mb-4">
          <span className="font-title" style={{ fontSize: 24 }}>SUBMIT YOUR BOARD</span>
          <button className="btn" onClick={() => { stopCapture(); onClose(); }}>✕</button>
        </div>

        {step === 0 && (
          <div>
            <p className="font-mono text-[11px] text-[var(--text-faint)] mb-3">Pick your keyboard from connected HID devices.</p>
            <div className="flex flex-col gap-1.5" style={{ maxHeight: 320, overflow: "auto" }}>
              {devices.map((d, i) => (
                <button key={i} onClick={() => setDev(d)}
                  className={`btn ${dev && dev.path === d.path ? "on" : ""}`} style={{ textAlign: "left" }}>
                  {d.product || "(unknown)"} · {d.vid}:{d.pid} · iface {d.interface_number}
                </button>
              ))}
            </div>
            <div className="flex justify-end mt-4"><button className="btn accent" disabled={!dev} onClick={() => setStep(1)}>Next</button></div>
          </div>
        )}

        {step === 1 && (
          <div className="flex flex-col gap-3">
            {[["brand","Brand"],["model","Model"],["form_factor","Form factor"]].map(([k,lbl]) => (
              <label key={k} className="flex flex-col gap-1">
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-faint)]">{lbl}</span>
                <input className="input" value={meta[k]} onChange={e => setMeta({ ...meta, [k]: e.target.value })}/>
              </label>
            ))}
            <div className="flex gap-2">
              {["60","65","75","tkl"].map(s => (
                <button key={s} className={`btn ${meta.size===s?"on":""}`} onClick={() => setMeta({ ...meta, size: s })}>{s.toUpperCase()}</button>
              ))}
            </div>
            <div className="flex justify-between mt-3">
              <button className="btn" onClick={() => setStep(0)}>Back</button>
              <button className="btn accent" disabled={!meta.brand || !meta.model} onClick={() => setStep(2)}>Next</button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <p className="font-mono text-[11px] text-[var(--text-dim)] mb-2">
              We’ll record what the board <b>sends</b> (read-only — we never write to it).
              Press every key once, then a few keys slowly.
            </p>
            <div className="glass p-4 mb-3">
              <div className="font-title text-[28px] text-[var(--accent)]">{keysSeen}</div>
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-faint)]">distinct reports · {reports.length} total</div>
            </div>
            {!capturing
              ? <button className="btn accent" onClick={startCapture}>Start capture</button>
              : <button className="btn danger" onClick={stopCapture}>Stop capture</button>}
            <div className="flex justify-between mt-4">
              <button className="btn" onClick={() => { stopCapture(); setStep(1); }}>Back</button>
              <button className="btn accent" disabled={reports.length === 0} onClick={() => { stopCapture(); setStep(3); }}>Next</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div>
            <p className="font-mono text-[11px] text-[var(--text-dim)] mb-3">
              Submitting saves a file locally and opens a pre-filled GitHub issue. <b>Attach the saved file</b> to the issue.
              (Optional: record a USBPcap capture for lighting and attach it too.)
            </p>
            <button className="btn accent" onClick={submit}>Save & open GitHub issue</button>
            {result && result.ok && <p className="font-mono text-[11px] text-[var(--good)] mt-3">Saved: {result.path}</p>}
            {result && !result.ok && <p className="font-mono text-[11px] text-[var(--bad)] mt-3">{(result.errors||[result.error]).join("; ")}</p>}
            <div className="flex justify-start mt-4"><button className="btn" onClick={() => setStep(2)}>Back</button></div>
          </div>
        )}
      </div>
    </div>
  );
}

window.AetherBoardSubmit = { BoardSubmit };
})();
