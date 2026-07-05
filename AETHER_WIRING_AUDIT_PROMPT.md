# AETHER WIRING AUDIT — Swarm Orchestration Prompt

You are deploying a multi-agent verification swarm on the **Aether** codebase (Aula WIN60 HE
controller, pywebview + Python HID). The UI was recently reworked (Abyssal Lagoon theme sweep
across `app.jsx` / `sections.jsx` / shell) and the repo moved to Windows. The mission: prove the
UI is sound and the codebase is **fully wired end-to-end** — every UI control reaches a real
Python API method, every API method builds correct HID packets, the Windows port is clean, and
the theme sweep is complete. Confirmed breaks get fixed, and every fix is independently
re-verified before it counts.

---

## 1. Organization & chain of command

| Role | Model / effort | Responsibility |
|---|---|---|
| **Chairman** | Miracle (human) | Final authority. Approves risky fixes, runs live hardware tests, receives the executive report. |
| **Liaison** | Sonnet 4.5 / standard | Sole channel to the Chairman. Translates swarm status into concise updates, relays Chairman decisions and live-test results downward. Never editorializes findings. |
| **CEO** | Opus / medium effort | Reports to Chairman via Liaison. Owns go/no-go on each workstream, resolves disputes between teams, signs the final report. Does not write code. |
| **Product Owner / Driver** | Fable / low effort | Drives the swarm day-to-day. Decomposes workstreams into tasks, assigns teams, tracks the findings ledger, enforces the fix+verify loop, escalates to CEO. |
| **Audit Team A** | 2× Sonnet / high effort | Workstreams W1 (UI→API bridge) and W4 (theme consistency). |
| **Audit Team B** | 2× Sonnet / high effort | Workstreams W2 (API→HID protocol) and W3 (Windows port readiness). |
| **Verify agents** | Sonnet / high effort, spawned per-fix | Fresh agents that re-verify fixes. **Never the agent that wrote the fix.** |

Scale-out rule: the PO may spawn additional Sonnet-high agents whenever a workstream stalls or
a finding needs deep tracing. There is no fixed cap — success matters more than headcount.

Communication rules: findings flow Team → PO → CEO → Liaison → Chairman. Nothing reaches the
Chairman except from the Liaison. Chairman decisions flow back down the same chain. Teams never
message each other directly; the PO brokers cross-team questions (e.g., Team A finds a call site
whose packet semantics Team B must judge).

> **Flattened-environment note:** if the runtime cannot nest agents or let subagents address the
> human directly (e.g., a Cowork session), the top-level agent plays Liaison + PO simultaneously,
> spawns Opus as CEO-synthesizer and Sonnet teams as subagents, and relays verbatim. Preserve the
> role separation in prompts even when one agent wears two hats — and never let a fixer verify
> its own fix.

---

## 2. Ground truth (read before auditing)

- Read `CLAUDE.md` at repo root and `docs/context/` — protocol and effect notes verified on hardware.
- **The app is `app_web.py`.** `main.py` is legacy CustomTkinter — ignore it entirely.
- **Bridge pattern:** the UI does NOT call `window.pywebview.api.x()` directly in most places. It
  uses a wrapper: `const apiCall = (name, ...args) => …` at `ui/runtime_src/src/app.jsx:20`.
  Enumerate call sites with `grep -nE 'apiCall\("[a-z_]+"' ui/runtime_src/src/*.jsx` **plus** the
  handful of direct `pywebview.api.*` calls (settings/autostart/update paths). Both patterns must
  be swept.
- **API surface:** the `Api` class in `app_web.py` (~45 public methods: `connect`, `set_light`,
  `set_color`, `set_trigger_all`, `set_trigger_codes`, `set_custom_colors`, `set_deadband_codes`,
  `set_switch_codes`, `set_remap`, `reset_remap`, `set_socd`, `calibrate`, `read_calibrated`,
  `open_analog`, `open_analog_codes`, `close_analog`, `read_live`, `set_poll`, `verify_actuation`,
  `start_multicolor`, `start_zones`, `stop_multicolor`, `stop_effect`, `get_light_frame`,
  `gamepad_mode`, `set_gamepad_capture`, `set_gamepad_map`, `gamepad_status`, `install_vigembus`,
  `load_settings`, `save_settings`, `settings_info`, `get_autostart`, `set_autostart`,
  `app_version`, `check_update`, `apply_update`, `reveal_settings`, `send_raw`, `status`,
  `disconnect`, `get_board`, …). Enumerate fresh — don't trust this list.
- **Build step:** the UI runs from prebuilt `ui/index_runtime.html`. Any edit to
  `ui/runtime_src/src/*.jsx` is invisible until `venv-web/bin/python ui/runtime_src/build_runtime.py`
  (Win: `venv-web\Scripts\python`) regenerates it. **A stale runtime build is itself a wiring defect.**
- **`ui/runtime_src/vendor/` is unmodified third-party code** — do not audit or edit it.

### HID protocol reference (verified on hardware — treat as spec)
- **Cmd 7 lighting:** `[0]=7,[4]=14,[5]=mode,[6]=bri,[7]=speed,[8-10]=fg,[11-13]=bg,[14]=dir,[15]=fullColor,[16]=power`.
  Modes: static0 breath1 wave2 neon3 radar4 reactive6 cross7 ripple8 twinkle9 custom10
  fireworks11 speedres12 autorip14 striation15 aurora16. Directions: right0 left1 up2 down3 spread4 gather5.
- **Cmd 9 per-key RGB:** 396-byte table streamed in 54-byte pages (host effect engine, ~120fps).
- **Cmd 33 actuation:** mode **0 = fixed actuation**, 12 = RT single, 13 = RT separate
  press/release. Unit = **0.01 mm**, min 0.08, max 3.4 mm. Travel-test stream = cmd33 sub5
  (`r[1]==33, r[5]==5, idx=r[7]*22+r[8], depth=(r[9]|r[10]<<8)/100`).
- **Calibration:** cmd33 sub `r[6]∈{8,15}`; `r[7]==1` → bitmask `r[8:30]` (idx=bit*22+col); `r[7]==0` → complete.
- **Interface selection:** prefer usage_page `0xFF1B`; Linux falls back to highest
  interface_number. Windows usually reports the usage page correctly.
- Report ID 1, 64-byte reports. Ultimate reference: `driver_src/dec_agreement/deobfuscated.js`.

### Known trap: CRLF noise
The working tree shows ~87 modified files where insertions exactly equal deletions — Windows
line-ending churn, not real edits. Diff with `git diff --ignore-cr-at-eol` (or `-w`) and compare
against commit `70c93db` to find the *real* changes. Do not waste agent time reviewing CRLF diffs,
and do not let a fix commit smuggle in line-ending rewrites.

---

## 3. Workstreams

### W1 — UI → API bridge integrity (Team A)
Prove every interactive element is wired and every API method is reachable.
1. Enumerate all `apiCall("…")` + direct `pywebview.api.*` call sites in
   `ui/runtime_src/src/{app,sections,keyboard}.jsx`. For each: method exists on `Api`, arg count
   and types match the Python signature, return value is consumed correctly (promises awaited
   where the UI depends on the result).
2. Reverse sweep: every public `Api` method has at least one UI caller, or is documented as
   internal/CLI-only. Orphans are findings.
3. Every visible control (buttons, sliders, toggles, key-grid interactions, color pickers,
   SOCD pairing, calibration flow, gamepad mapping, updater, settings) has a handler that
   terminates in an `apiCall` or deliberate local state change. Dead controls are findings.
4. Confirm `ui/index_runtime.html` was rebuilt from the current `src/*.jsx` (rebuild and diff;
   a mismatch is a P1 finding).

### W2 — API → HID protocol correctness (Team B)
Prove `Api` methods produce packets matching the spec in §2.
1. Trace each `Api` method through `protocol.py` builders: byte offsets, mode/direction bytes,
   fg/bg ordering, report ID 1 / 64-byte framing.
2. Actuation paths: mm→unit conversion (×100), clamping to [0.08, 3.4], trigger mode bytes
   {0, 12, 13} — verify mode 0 is "fixed actuation", not a legacy value.
3. Effects engine (`effects.py`): cmd 9 table is 396 bytes in 54-byte pages; press-reactive
   effects (reactive, ripple, speedres, cross, fireworks) actually consume the live travel
   stream; spawners scale by `_SPAWN_NORM`.
4. Calibration + travel-test parsing in `device_state.py` matches the formulas in §2 exactly.
5. UI→packet value integrity: a UI slider value survives jsx → apiCall → Api → packet without
   unit/scale drift (e.g., brightness ranges, speed ranges, 0.01mm units).

### W3 — Windows port readiness (Team B)
1. `aula_device.find_vendor_interface` selects the `0xFF1B` vendor collection on Windows — not
   the keyboard HID interface.
2. `gamepad.py`: on Windows either the vgamepad/ViGEmBus port works or the feature self-disables
   cleanly (no crash on import, UI reflects unavailability); `install_vigembus` path is sane.
3. No Linux-only code in the hot path: udev rules unused, evdev guarded by
   `sys_platform=="linux"`, paths use `os.path`/`pathlib` (no hardcoded `/`), autostart/settings/
   updater paths correct for Windows.
4. `requirements.txt` installs clean on Windows; `venv-web\Scripts\python app_web.py` launches.

### W4 — Theme / visual consistency (Team A)
1. Abyssal Lagoon token sweep is complete: no stray hardcoded colors from the old palette in
   `app.jsx` / `sections.jsx` / shell (grep hex literals; whitelist deliberate ones, e.g. the
   calibration-green in `keyboard.jsx`).
2. Aurora presets and mint default render from theme tokens; regenerated `theme.js` / `app.js`
   build artifacts match their sources.
3. All panels/sections/nav states (hover, active, disabled, connected/disconnected) use tokens —
   no unstyled or half-migrated components.

---

## 4. Findings ledger & fix + verify policy

Every finding enters a shared ledger the PO owns:

```
ID | Severity (P1 wiring break / P2 wrong behavior / P3 cosmetic) | File:line | Claim | Evidence | Status
```

Fix policy — **fix + verify, with one gate:**
1. Team fixes any confirmed finding in UI/jsx, wiring, theme, or Windows-guard code, then reruns
   `build_runtime.py` if jsx changed.
2. **Anything touching `protocol.py` packet layout, byte offsets, or HID framing requires
   Chairman approval (via Liaison) before the edit** — a wrong packet can misconfigure hardware.
3. Every fix is re-verified by a fresh Verify agent who did not write it: reproduce the original
   defect on pre-fix code (or reasoning), confirm the fix, sweep for regressions in the touched
   file. Only then does the PO mark it `verified`.
4. No CRLF rewrites in fix diffs (`git diff --ignore-cr-at-eol` must equal `git diff` for the fix).

---

## 5. Live hardware test protocol (Chairman-in-the-loop)

Static tracing is necessary but not sufficient — final sign-off requires live confirmation on the
Chairman's Windows machine with the Win60 HE attached.

1. After W1–W4 reach "statically clean," the PO compiles a **scripted manual test checklist**:
   one row per verified wiring path — *action → expected on-keyboard/on-screen result* (e.g.,
   "set actuation slider to 0.5 mm, press A lightly → registers at ~0.5 mm in travel test";
   "select Ripple, press a key → ripple radiates from that key"; "run calibration → keys turn
   green as firmware confirms"). Cover: connect/disconnect, ≥4 firmware lighting modes, ≥3 host
   effects incl. one press-reactive, per-key custom colors, actuation set/verify, RT modes 12/13,
   SOCD, calibration, travel test stream, gamepad enable (or clean self-disable), settings
   save/load, autostart toggle, update check.
2. Liaison delivers the checklist; Chairman runs `venv-web\Scripts\python app_web.py` and reports
   pass/fail per row (screenshots where useful).
3. Failures become P1/P2 findings and re-enter the fix+verify loop; the affected checklist rows
   rerun after the fix.

---

## 6. Exit criteria & final report

Ship when **all** hold:
- Every ledger item is `verified` or explicitly `accepted` by the Chairman.
- Bidirectional bridge sweep clean: no orphaned `apiCall` names, no unreachable `Api` methods
  (or documented as intentional).
- `ui/index_runtime.html` provably rebuilt from current sources.
- Live checklist: 100% pass or Chairman-accepted exceptions.

The CEO then signs an executive report (delivered by the Liaison): scope, method, findings table,
fixes with verification evidence, live-test results, residual risks. Concise — the Chairman reads
evidence, not narration.
