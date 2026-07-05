# AetherHE Desktop-Widget UI Overhaul — Plan

> Backend FROZEN (goal constraint). No edits to app_web.py, protocol.py, effects.py,
> device_state.py, or any Api/packet code. UI layer only (ui/runtime_src/**), reusing
> the existing `apiCall(...)` bridge and app.jsx's existing state + handlers.

**Goal:** Replace AetherHE's fixed-panel UI with a Nexus-style **desktop-OS** shell:
a top bar of section tabs; each section is a **workspace** = a desktop of free-drag,
resizable, persistable **widget windows**. Plus a first-run **setup wizard**.

## Locked design decisions (from interview)
- **Widgets:** free-drag + resize windows; position+size saved per (workspace,widget) in localStorage; minimize to a per-workspace dock.
- **Type:** Impact (weight 400, never bold) for TITLES only (top bar, section names, widget title bars). Body = Schibsted Grotesk. Numeric readouts = Fragment Mono. (+ global antialiasing already added.)
- **Wizard:** first run when no settings file found; reopenable from Settings. Steps: (1) Board selection (registry + submit link), (2) Board layout preview, (3) Animation how-to, (4) JSON import (returning users).
- **Also:** auto-connect wired (UI effect → existing `connect`); aurora green blob already fixed.

## Widget contract (LOCKED — all agents build against this)
Foundation exposes, from `ui/runtime_src/src/desktop.jsx`:
```
// A draggable/resizable window. Persists geometry under key `aether-wgt:{workspace}:{id}`.
<WidgetFrame id="travel" workspace="actuation" title="Travel"
             defaultPos={{x,y}} defaultSize={{w,h}} minSize={{w,h}}>
   ...widget body (plain children)...
</WidgetFrame>

// Per-workspace desktop surface + dock. Renders the widgets registered for `section`.
<Workspace section="actuation" widgets={ACTUATION_WIDGETS} ctx={ctx} />

// Registry shape each section file exports:
//   export const ACTUATION_WIDGETS = [{ id, title, default:{x,y,w,h}, min:{w,h}, render:(ctx)=>JSX }, ...]
```
- `ctx` = a single object app.jsx passes down carrying ALL existing state + handlers
  (connected, actuation, setActuation, applyActuation, deadTop, applyDeadband,
  polling, handleSetPolling, calibrating, handleCalibrate, colors, setColors,
  pattern, brightness, speed, zones, gamepadMap, handleGamepadToggle, selectedKeys,
  handlePickSwitch, handleSocdApply, liveDepths, calibratedKeys, remap handlers, …).
  Foundation builds `ctx` in app.jsx from the already-existing state/handlers — NO new backend.
- Each section file is DISJOINT (own file), so section builds run in parallel.

## Files
- Create `ui/runtime_src/src/desktop.jsx` — WidgetFrame, Workspace, Dock, useWidgetLayout, TopBar shell. **(Opus)**
- Create `ui/runtime_src/src/workspaces/actuation.jsx` — reference workspace. **(Opus, in foundation)**
- Create `ui/runtime_src/src/workspaces/{keymap,lighting,gamepad}.jsx` — **(Sonnet/high)**
- Create `ui/runtime_src/src/workspaces/{socd,settings}.jsx` — **(Haiku/high)**
- Create `ui/runtime_src/src/wizard.jsx` — first-run setup wizard. **(Opus/high)**
- Modify `ui/runtime_src/src/app.jsx` — build `ctx`, render TopBar + current Workspace instead of the old section panels; wire auto-connect; mount wizard when no settings. **(Opus, integration)**
- Modify `ui/runtime_src/head_inner.html` — Impact @font-face-free (system font) + `.widget`/`.dock` window CSS ported from Nexus styles.css; title→Impact, body→Schibsted, mono→Fragment. **(Opus)**
- Modify `ui/runtime_src/build_runtime.py` — add the new jsx files to the compile list. **(Opus)**
- Reuse verbatim (move, don't rewrite): the existing control JSX from sections.jsx/keyboard.jsx becomes widget bodies. Keep device-color/telemetry code byte-identical.

## Model routing
| Wave | Task | Model |
|---|---|---|
| 1 | Foundation: desktop.jsx (frame/dock/persist/topbar) + Impact CSS + build wiring + ctx in app.jsx + Actuation reference workspace + auto-connect | **Opus/high** |
| 2a | Lighting workspace (mode/palette/preview/paint — complex, device colors) | Sonnet/high |
| 2b | Keymap workspace (key grid/remap/layers) | Sonnet/high |
| 2c | Gamepad workspace (enable/status/axis map/driver) | Sonnet/high |
| 2d | SOCD workspace (pair editor/hotkey/active pairs) | Haiku/high |
| 2e | Settings workspace (profiles/theme/backup/about+update+reopen wizard) | Haiku/high |
| 3 | Setup wizard (board select+registry, layout preview, animation how-to, JSON import) | **Opus/high** |
| 4 | Integration: mount all workspaces + wizard in shell, rebuild, smoke-launch verify | **Opus/high** |
| 5 | Final review (whole-branch, backend-untouched proof, device-color intact) | **Opus/high** |

Wave 2 (a–e) runs in PARALLEL (disjoint workspace files) AFTER Wave 1 lands the contract.
Wave 3 can run parallel with Wave 2.

## Verification per task
- `python ui/runtime_src/build_runtime.py` succeeds + offline assertion (0 network refs).
- Backend-frozen proof: `git diff --stat main -- '*.py' ':!ui/runtime_src/build_runtime.py'` shows NO changes to app_web.py/protocol.py/effects.py/device_state.py/aula_device.py/gamepad.py/boards.py.
- Smoke-launch from source (`venv-web/Scripts/python app_web.py`), confirm board detected, bridge live, target workspace's widgets drag + persist, device colors/telemetry unchanged.
- Device-color/telemetry JSX moved into widgets must stay byte-identical (no re-tokenizing lighting swatches, hsl bars, ledColor).
