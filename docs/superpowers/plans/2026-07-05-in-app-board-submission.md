# In-App Board Submission (sub-project A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user submit an unsupported keyboard from inside AetherHE — the app detects the device, captures identity + HID descriptor + guided INPUT reports (read-only) + a size template, writes a schema-valid submission JSON, and opens a pre-filled GitHub add-a-board issue.

**Architecture:** New `Api` methods in `app_web.py` (device list, read-only capture, save submission, open URL) built on the existing `hidapi`; a shared submission schema + validator in `tools/board_submission.py` (mirrors `tools/validate_keymap.py`); a new frontend flow `ui/runtime_src/src/board-submit.jsx` wired from the setup wizard and Settings. No MiniMax calls anywhere in this sub-project.

**Tech Stack:** Python 3.12 + `hidapi` (`import hid`), pywebview bridge, vendored React (no bundler) compiled by `ui/runtime_src/build_runtime.py`, pytest.

## Global Constraints

- **No key anywhere in this sub-project.** A makes ZERO MiniMax calls and carries no key — nothing to extract via network inspection or RE. (The key lives only in sub-project B, owner-side.)
- **Capture is READ-ONLY on unknown devices.** The capture path calls only `hid.device.read()` — never `write()`, `send_feature_report()`, or any output. The app must never send a command to a board it has no verified protocol for.
- **Submission schema id = `aether-board-submission/1`** (exact string).
- **No new dependencies** — stdlib + existing `hidapi` only. Hand-rolled validator (no `jsonschema`), mirroring `tools/validate_keymap.py`'s `validate(data) -> list[str]` style (never raises).
- **Submission dir:** `<LOCALAPPDATA or platform equiv>/AetherHE/submissions/` (reuse the `_settings_path()` root logic).
- **Api pattern:** methods return plain dicts (`{"ok": True, ...}` or `{"ok": False, "error": "..."}`), matching existing `app_web.Api`.
- **This feature intentionally ADDS backend** — the earlier "backend frozen" goal was scoped to the UI overhaul (shipped as v0.2.0); this is a separate, approved effort.

## File Structure

| File | Responsibility |
|---|---|
| `tools/board_submission.py` (new) | `SCHEMA_ID`, `validate_submission(obj) -> list[str]`, `new_submission_skeleton(...)`. Shared by A (pre-save) and B (ingest). |
| `tests/test_board_submission.py` (new) | Unit tests for the validator + skeleton. |
| `tests/test_api_submission.py` (new) | Unit tests for the new Api methods (hid enumerate mocked; capture state machine; save writes valid file; read-only guarantee). |
| `app_web.py` (modify) | New Api methods: `list_hid_devices`, `open_capture`, `read_capture`, `stop_capture`, `save_submission`, `open_submission_url`. New `_submissions_dir()` helper. |
| `ui/runtime_src/src/board-submit.jsx` (new) | The submit flow component `window.AetherBoardSubmit = { BoardSubmit }` — detect → metadata → consent+capture → optional pcap → submit. |
| `ui/runtime_src/src/wizard.jsx` (modify) | Board-selection step: "My board isn't listed → Submit it" opens BoardSubmit. |
| `ui/runtime_src/workspaces/settings.jsx` (modify) | Add a "Submit a board" action opening BoardSubmit. |
| `ui/runtime_src/src/app.jsx` (modify) | Mount `<BoardSubmit>` + `ctx.setSubmitOpen`; build order includes board-submit.jsx. |
| `ui/runtime_src/build_runtime.py` (modify) | Add `src/board-submit.jsx` to the compile list (before app.jsx). |

---

### Task 1: Submission schema + validator

**Files:**
- Create: `tools/board_submission.py`
- Test: `tests/test_board_submission.py`

**Interfaces:**
- Produces: `SCHEMA_ID = "aether-board-submission/1"`; `validate_submission(obj: dict) -> list[str]` (empty list = valid, never raises); `new_submission_skeleton(app_version: str) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_submission.py
import tools.board_submission as bs

def _valid():
    s = bs.new_submission_skeleton("0.2.0")
    s["device"].update({"vid": "0x2E3C", "pid": "0xC365", "usage_page": "0xFF1B",
                         "hid_descriptor_b64": "AA=="})
    s["meta"].update({"brand": "Aula", "model": "Win60 HE", "switch_type": "Hall-effect",
                      "form_factor": "60%", "size": "60"})
    s["size_template"] = "generic-60"
    s["input_capture"] = {"duration_ms": 100, "report_len": 64,
                          "reports": [{"t": 5, "hex": "01ab"}], "keys_seen": 1}
    return s

def test_skeleton_has_schema_id():
    assert bs.new_submission_skeleton("0.2.0")["schema"] == "aether-board-submission/1"

def test_valid_submission_passes():
    assert bs.validate_submission(_valid()) == []

def test_missing_device_vid_fails():
    s = _valid(); s["device"]["vid"] = ""
    assert any("vid" in e for e in bs.validate_submission(s))

def test_bad_size_fails():
    s = _valid(); s["meta"]["size"] = "42"
    assert any("size" in e for e in bs.validate_submission(s))

def test_reports_must_be_hex():
    s = _valid(); s["input_capture"]["reports"] = [{"t": 1, "hex": "zz"}]
    assert any("hex" in e for e in bs.validate_submission(s))

def test_never_raises_on_garbage():
    for junk in [None, 5, "x", [], {"schema": 1}]:
        assert isinstance(bs.validate_submission(junk), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_board_submission.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.board_submission'`.

- [ ] **Step 3: Write the implementation**

```python
# tools/board_submission.py
"""Schema + validator for aether-board-submission/1 — the A<->B contract.
Hand-rolled (no jsonschema dep); mirrors tools/validate_keymap.py. Never raises."""
import re
import time

SCHEMA_ID = "aether-board-submission/1"
_SIZES = {"60", "65", "75", "tkl"}
_HEX = re.compile(r"^[0-9a-fA-F]*$")


def new_submission_skeleton(app_version):
    return {
        "schema": SCHEMA_ID,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "app_version": str(app_version),
        "device": {"vid": "", "pid": "", "manufacturer": "", "product": "",
                   "usage_page": "", "hid_descriptor_b64": "", "interfaces": []},
        "meta": {"brand": "", "model": "", "switch_type": "", "form_factor": "", "size": ""},
        "size_template": "",
        "input_capture": {"duration_ms": 0, "report_len": 0, "reports": [], "keys_seen": 0},
        "output_pcap": {"attached": False, "filename": None},
        "notes": "",
    }


def validate_submission(obj):
    """Return a list of human-readable error strings. [] == valid. Never raises."""
    e = []
    try:
        if not isinstance(obj, dict):
            return ["top-level value must be a JSON object"]
        if obj.get("schema") != SCHEMA_ID:
            e.append(f'schema must be "{SCHEMA_ID}"')
        dev = obj.get("device")
        if not isinstance(dev, dict):
            e.append('"device" must be an object')
        else:
            for f in ("vid", "pid"):
                if not isinstance(dev.get(f), str) or not dev.get(f):
                    e.append(f'device.{f} is required (non-empty string)')
        meta = obj.get("meta")
        if not isinstance(meta, dict):
            e.append('"meta" must be an object')
        else:
            for f in ("brand", "model"):
                if not isinstance(meta.get(f), str) or not meta.get(f):
                    e.append(f'meta.{f} is required')
            if meta.get("size") not in _SIZES:
                e.append(f'meta.size must be one of {sorted(_SIZES)}')
        cap = obj.get("input_capture")
        if not isinstance(cap, dict):
            e.append('"input_capture" must be an object')
        else:
            reps = cap.get("reports")
            if not isinstance(reps, list):
                e.append('input_capture.reports must be an array')
            else:
                for i, r in enumerate(reps):
                    if not isinstance(r, dict) or not _HEX.match(str(r.get("hex", "x"))):
                        e.append(f'input_capture.reports[{i}].hex must be hex')
                        break
    except Exception as ex:  # never raise
        return [f"validator error: {ex}"]
    return e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_board_submission.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/board_submission.py tests/test_board_submission.py
git commit -m "feat(submit): board-submission schema + validator (A<->B contract)"
```

---

### Task 2: Api.list_hid_devices

**Files:**
- Modify: `app_web.py` (add method to the `Api` class)
- Test: `tests/test_api_submission.py`

**Interfaces:**
- Produces: `Api.list_hid_devices() -> {"ok": True, "devices": [ {"path": str, "vid": "0x..", "pid": "0x..", "manufacturer": str, "product": str, "usage_page": "0x..", "interface_number": int} ]}`. Consumed by Task 3 (`open_capture(path)`) and the frontend picker.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_submission.py
import types, app_web

def _api():
    # Construct Api without opening hardware: bypass __init__ side effects.
    a = app_web.Api.__new__(app_web.Api)
    return a

def test_list_hid_devices_shape(monkeypatch):
    fake = [{"path": b"\\?\\hid#1", "vendor_id": 0x2E3C, "product_id": 0xC365,
             "manufacturer_string": "Aula", "product_string": "Win60 HE",
             "usage_page": 0xFF1B, "interface_number": 2}]
    monkeypatch.setattr(app_web.hid, "enumerate", lambda *a, **k: fake)
    out = _api().list_hid_devices()
    assert out["ok"] is True
    d = out["devices"][0]
    assert d["vid"] == "0x2e3c" and d["pid"] == "0xc365"
    assert d["usage_page"] == "0xff1b" and d["interface_number"] == 2
    assert isinstance(d["path"], str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_submission.py::test_list_hid_devices_shape -q`
Expected: FAIL — `AttributeError: 'Api' object has no attribute 'list_hid_devices'` (and/or `app_web.hid` missing).

- [ ] **Step 3: Implement**

At the top of `app_web.py`, ensure `import hid` is present (add if missing, next to the other imports).
Add to the `Api` class:

```python
    # ---- board submission (in-app) ----
    def list_hid_devices(self):
        """All HID devices for the submit-a-board picker. Read-only enumeration."""
        try:
            out = []
            for d in hid.enumerate():
                path = d.get("path")
                out.append({
                    "path": path.decode("utf-8", "replace") if isinstance(path, bytes) else str(path),
                    "vid": f"0x{d.get('vendor_id', 0):04x}",
                    "pid": f"0x{d.get('product_id', 0):04x}",
                    "manufacturer": d.get("manufacturer_string") or "",
                    "product": d.get("product_string") or "",
                    "usage_page": f"0x{d.get('usage_page', 0):04x}",
                    "interface_number": d.get("interface_number", -1),
                })
            return {"ok": True, "devices": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_submission.py::test_list_hid_devices_shape -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app_web.py tests/test_api_submission.py
git commit -m "feat(submit): Api.list_hid_devices for the board picker"
```

---

### Task 3: Api read-only capture (open/read/stop)

**Files:**
- Modify: `app_web.py`
- Test: `tests/test_api_submission.py`

**Interfaces:**
- Consumes: `list_hid_devices()` device `path`.
- Produces: `open_capture(path) -> {"ok": bool}` (opens a SEPARATE read-only handle); `read_capture() -> {"ok": True, "reports": [{"t": int_ms, "hex": str}], "count": int}` (drains buffer since last call); `stop_capture() -> {"ok": True}`. A background thread calls only `.read()` — never any write.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_api_submission.py
def test_capture_is_read_only(monkeypatch):
    reads = {"n": 0}
    class FakeDev:
        def open_path(self, p): pass
        def set_nonblocking(self, v): pass
        def read(self, n, timeout_ms=0):
            reads["n"] += 1
            return [1, 0xab] if reads["n"] == 1 else []
        def close(self): pass
        # NOTE: intentionally no write / send_feature_report — a write would AttributeError
    monkeypatch.setattr(app_web.hid, "device", lambda: FakeDev())
    a = _api()
    assert a.open_capture("\\?\\hid#1")["ok"] is True
    import time; time.sleep(0.05)
    out = a.read_capture()
    assert out["ok"] is True
    assert any(r["hex"] for r in out["reports"])   # got the 01ab report
    assert a.stop_capture()["ok"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_submission.py::test_capture_is_read_only -q`
Expected: FAIL — `AttributeError: ... 'open_capture'`.

- [ ] **Step 3: Implement**

Add to the `Api` class (and ensure `import threading, time` at top — both already imported):

```python
    def open_capture(self, path):
        """Open an arbitrary HID device READ-ONLY and stream input reports.
        Never writes to the device — this is the safety guarantee for unknown boards."""
        try:
            self._cap_stop = getattr(self, "_cap_stop", None)
            self.stop_capture()  # idempotent: close any prior capture
            dev = hid.device()
            dev.open_path(path.encode() if isinstance(path, str) else path)
            dev.set_nonblocking(True)
            self._cap_dev = dev
            self._cap_buf = []
            self._cap_t0 = time.time()
            self._cap_lock = threading.Lock()
            self._cap_stop = threading.Event()

            def loop():
                while not self._cap_stop.is_set():
                    try:
                        r = dev.read(64, timeout_ms=50)
                    except Exception:
                        break
                    if r:
                        rec = {"t": int((time.time() - self._cap_t0) * 1000),
                               "hex": bytes(r).hex()}
                        with self._cap_lock:
                            self._cap_buf.append(rec)
                    else:
                        time.sleep(0.005)

            self._cap_thread = threading.Thread(target=loop, daemon=True)
            self._cap_thread.start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def read_capture(self):
        """Drain and return input reports buffered since the last call."""
        try:
            buf = getattr(self, "_cap_buf", None)
            if buf is None:
                return {"ok": True, "reports": [], "count": 0}
            with self._cap_lock:
                out = self._cap_buf
                self._cap_buf = []
            return {"ok": True, "reports": out, "count": len(out)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stop_capture(self):
        try:
            ev = getattr(self, "_cap_stop", None)
            if ev:
                ev.set()
            th = getattr(self, "_cap_thread", None)
            if th:
                th.join(timeout=0.3)
            dev = getattr(self, "_cap_dev", None)
            if dev:
                dev.close()
            self._cap_dev = None
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_submission.py::test_capture_is_read_only -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app_web.py tests/test_api_submission.py
git commit -m "feat(submit): read-only HID capture Api (open/read/stop) — never writes"
```

---

### Task 4: Api.save_submission + open_submission_url + submissions dir

**Files:**
- Modify: `app_web.py`
- Test: `tests/test_api_submission.py`

**Interfaces:**
- Consumes: `tools.board_submission.validate_submission`.
- Produces: `save_submission(obj) -> {"ok": True, "path": str}` or `{"ok": False, "errors": [...]}`; `open_submission_url(url) -> {"ok": True}` (opens the pre-filled issue in the default browser); `_submissions_dir() -> str`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_api_submission.py
import json, os

def test_save_submission_validates_and_writes(monkeypatch, tmp_path):
    a = _api()
    monkeypatch.setattr(a, "_submissions_dir", lambda: str(tmp_path))
    good = {"schema": "aether-board-submission/1",
            "device": {"vid": "0x1", "pid": "0x2"},
            "meta": {"brand": "X", "model": "Y", "size": "60"},
            "input_capture": {"reports": []}}
    r = a.save_submission(good)
    assert r["ok"] is True and os.path.exists(r["path"])
    assert json.load(open(r["path"]))["meta"]["brand"] == "X"

def test_save_submission_rejects_invalid(monkeypatch, tmp_path):
    a = _api()
    monkeypatch.setattr(a, "_submissions_dir", lambda: str(tmp_path))
    r = a.save_submission({"schema": "wrong"})
    assert r["ok"] is False and r["errors"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_submission.py -k save_submission -q`
Expected: FAIL — `AttributeError: ... 'save_submission'`.

- [ ] **Step 3: Implement**

Add near the top of `app_web.py`: `from tools import board_submission`.
Add to the `Api` class:

```python
    def _submissions_dir(self):
        base = os.path.dirname(self._settings_path())   # <root>/AetherHE
        d = os.path.join(base, "submissions")
        os.makedirs(d, exist_ok=True)
        return d

    def save_submission(self, obj):
        """Validate against aether-board-submission/1 and write to the submissions dir."""
        errors = board_submission.validate_submission(obj)
        if errors:
            return {"ok": False, "errors": errors}
        try:
            slug = "".join(c for c in (obj.get("meta", {}).get("model", "board")).lower()
                           if c.isalnum() or c == "-") or "board"
            fn = f"board-{slug}-{time.strftime('%Y%m%d-%H%M%S')}.json"
            path = os.path.join(self._submissions_dir(), fn)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "errors": [str(e)]}

    def open_submission_url(self, url):
        """Open the pre-filled GitHub issue in the default browser."""
        try:
            import webbrowser
            webbrowser.open(str(url))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
```

Ensure `import json` is present at the top of `app_web.py` (add if missing).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_submission.py -q`
Expected: PASS (all submission Api tests).

- [ ] **Step 5: Commit**

```bash
git add app_web.py tests/test_api_submission.py
git commit -m "feat(submit): save_submission (schema-validated) + open_submission_url"
```

---

### Task 5: Frontend BoardSubmit flow

**Files:**
- Create: `ui/runtime_src/src/board-submit.jsx`
- Modify: `ui/runtime_src/build_runtime.py` (add to compile list)

**Interfaces:**
- Consumes (via `window.pywebview.api` / the app's `apiCall`): `list_hid_devices`, `open_capture`, `read_capture`, `stop_capture`, `save_submission`, `open_submission_url`.
- Produces: `window.AetherBoardSubmit = { BoardSubmit }` where `BoardSubmit({ open, onClose })` renders a glass modal.

- [ ] **Step 1: Write the component**

Create `ui/runtime_src/src/board-submit.jsx` (vanilla React off the global, like the other src files):

```jsx
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
```

- [ ] **Step 2: Add to the build compile list**

In `ui/runtime_src/build_runtime.py`, in the `jobs` list, add `("src/board-submit.jsx", "board-submit.js")` immediately before `("src/wizard.jsx", "wizard.js")`.

- [ ] **Step 3: Build**

Run: `python ui/runtime_src/build_runtime.py`
Expected: compiles all modules incl. `board-submit.jsx`; writes `ui/index_runtime.html`; offline assertion passes.

- [ ] **Step 4: Commit**

```bash
git add ui/runtime_src/src/board-submit.jsx ui/runtime_src/build_runtime.py ui/runtime_src/build/ ui/index_runtime.html
git commit -m "feat(submit): in-app BoardSubmit flow (detect/meta/capture/submit)"
```

---

### Task 6: Wire entry points + mount

**Files:**
- Modify: `ui/runtime_src/src/app.jsx` (mount `<BoardSubmit>`, add `ctx.setSubmitOpen`)
- Modify: `ui/runtime_src/src/wizard.jsx` (board step: "My board isn't listed → Submit it")
- Modify: `ui/runtime_src/workspaces/settings.jsx` (a "Submit a board" button)

**Interfaces:**
- Consumes: `window.AetherBoardSubmit.BoardSubmit`, `ctx.setSubmitOpen` (added here).

- [ ] **Step 1: Mount in app.jsx**

Near the wizard mount, add state + mount:

```jsx
const BoardSubmit = window.AetherBoardSubmit && window.AetherBoardSubmit.BoardSubmit;
// ...inside App():
const [submitOpen, setSubmitOpen] = useState(false);
// ...add setSubmitOpen to the ctx object (next to setWizardOpen):
//    setWizardOpen, setSubmitOpen,
// ...in the return, next to <SetupWizard ...>:
{BoardSubmit && <BoardSubmit open={submitOpen} onClose={() => setSubmitOpen(false)} />}
```

- [ ] **Step 2: Wizard entry point**

In `wizard.jsx`'s board-selection step, add a button under the board list:

```jsx
<button className="btn" onClick={() => { onClose(); ctx.setSubmitOpen && ctx.setSubmitOpen(true); }}>
  My board isn’t listed → Submit it
</button>
```

- [ ] **Step 3: Settings entry point**

In `settings.jsx`'s About/Update (or Profiles) widget, add:

```jsx
<button className="btn" onClick={() => ctx.setSubmitOpen && ctx.setSubmitOpen(true)}>Submit a board</button>
```

- [ ] **Step 4: Build + launch verify**

Run: `python ui/runtime_src/build_runtime.py` then `python app_web.py` (or the venv python).
Expected: launches, `errors: []`; opening the wizard's "Submit it" or Settings "Submit a board" shows the BoardSubmit modal; the device list populates.

- [ ] **Step 5: Commit**

```bash
git add ui/runtime_src/src/app.jsx ui/runtime_src/src/wizard.jsx ui/runtime_src/workspaces/settings.jsx ui/runtime_src/build/ ui/index_runtime.html
git commit -m "feat(submit): wire BoardSubmit into wizard + settings"
```

---

### Task 7: Integration verify + docs

**Files:**
- Modify: `README.md` (one line: "Submit your board from inside the app (Settings → Submit a board)")
- Test: manual + full suite

- [ ] **Step 1: Full test suite**

Run: `python -m pytest tests/ -q`
Expected: all pass (existing 23 + new submission tests).

- [ ] **Step 2: Dry-run capture on the known Aula board**

Run `python app_web.py`, open Submit-a-board, pick the Aula device, run a short capture (press keys), submit. Confirm:
- a file appears in `<LOCALAPPDATA>/AetherHE/submissions/board-*.json`,
- it validates: `python -c "import json,tools.board_submission as b; import glob; f=sorted(glob.glob('$LOCALAPPDATA/AetherHE/submissions/*.json'))[-1]; print(b.validate_submission(json.load(open(f))))"` → `[]`,
- the pre-filled GitHub issue opened in the browser with brand/model/VID:PID populated.

- [ ] **Step 3: Read-only proof**

Confirm the capture path issues no writes: `grep -n "write\|send_feature\|send_report" app_web.py` shows none inside `open_capture`/the capture loop. (Existing device-control writes are unrelated methods.)

- [ ] **Step 4: Offline + build assertion**

Run: `python ui/runtime_src/build_runtime.py`; `grep -c "googleapis\|gstatic" ui/index_runtime.html` → `0`. Confirm no MiniMax/API-key string anywhere: `grep -rin "minimax\|api[_-]key\|secret" ui/runtime_src/src app_web.py tools/board_submission.py` → nothing (proves A carries no key).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs(submit): note in-app board submission; integration verified"
```

---

## Self-Review Notes

- **Spec coverage:** transport/pre-filled issue (Task 5 `buildIssueUrl` + Task 4 `open_submission_url`); capture scope identity+descriptor+input+size (Tasks 2/3/5); output pcap optional (Task 5 step-3 copy + schema `output_pcap`); submission contract (Task 1 schema); new backend surface (Tasks 2-4); read-only safety (Task 3 + Task 7 step 3); consent copy (Task 5 step-2 text); non-goals size-template-only (Task 5 meta.size); key-security (Task 7 step 4 grep proof). All spec sections mapped.
- **Key security:** enforced structurally — no MiniMax code in this plan at all; Task 7 step 4 greps to prove no key/secret strings ship.
- **Type consistency:** `save_submission`/`validate_submission`/`SCHEMA_ID`/`open_capture(path)`/`read_capture().reports[].hex` names consistent across tasks.
- **Backend note:** this plan adds backend deliberately (approved); it is NOT a violation of the earlier UI-overhaul freeze (that shipped in v0.2.0).
