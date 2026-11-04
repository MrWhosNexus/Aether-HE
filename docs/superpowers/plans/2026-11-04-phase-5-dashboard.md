# Phase 5: Central Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new "Dashboard" tab, first in the nav and the landing tab, that shows the board on one composed page: a hero keyboard (today's heatmap / live depth / actuation map) beside a status rail (connection + poll rate, profile + detected game, actuation read-back summary), over a band with today's typing numbers, the top-3 auto-tune suggestions with Apply, the lighting effect with a quick switch, and a "Status on keys" tile that appears only once Phase 6 ships its bridge.

**Architecture:** UI only, no new Python bridge. `workspaces/dashboard.jsx` exports a page component (`window.AetherWorkspaces.DASHBOARD_PAGE`) that `app.jsx` renders inside the zoomed `.workspace` canvas instead of the draggable widget desktop, plus pure helpers on `window.AetherDashboard`. All data comes from what already exists: `window.AetherAnalytics` (store, `useAnalytics`, `heatLedMap`, `DailyBars`, `SuggestionList`), ctx state and actions, a games view filled by the existing 2 s `games_status` poll, and the existing Travel Test stream held through a new `ctx.setLiveView`. The only bridges the page calls itself are Phase 6's `get_overlays` / `set_overlay`.

**Tech Stack:** React 18 + Tailwind (precompiled by `ui/runtime_src/build_runtime.py`, needs `node`), pytest source checks, node for the pure-helper tests (skipped without node).

**Spec:** `docs/superpowers/specs/2026-11-04-win60-roadmap-design.md` ("Phase 5" and "Global constraints"). Read it, `docs/superpowers/roadmap-status.md`, and decision 12 of `docs/superpowers/plans/2026-11-04-phase-4-analytics.md` (the `window.AetherAnalytics` exports) before starting.

**Prototype:** every code block below was run against the real tree on 2026-11-04 (full suite **1009 passed, 14 skipped**; the built page was loaded in a browser from a local static server with a fake `window.pywebview.api` at 1160 x 800 and 1700 x 1000: no console errors, nothing scrolls at 1160 x 800, the top bar fits, live depth opens/closes the stream, Apply runs `set_trigger_codes` then `verify_actuation`, the overlay tile appears only with the fake Phase 6 bridge, a non-WIN60 board hides Heatmap and the Analytics links) and then reverted. Copy the code verbatim.

## Global Constraints

- Windows is the shipping target; nothing may break Linux. Phase 5 is JSX/CSS only; it adds no platform code (games already report `available: false` off Windows and the tile says so).
- **NEVER write to the keyboard, open HID, or run the app against it. Fakes only.** Optional browser checks use `file://` or a local static server with a fake bridge, never the real app or keyboard.
- No push, merge into other branches, tag, release, or install. No network during development or tests.
- Python: `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe` (written `<py>` below). Full suite: `<py> -m pytest -q -p no:cacheprovider` (**985 passed, 13 skipped** at the start of this phase); green at every commit.
- JSX/CSS changes need `<py> ui\runtime_src\build_runtime.py`; commit `ui/index_runtime.html` + only the `ui/runtime_src/build/*.js` files with real diffs (`git diff --ignore-cr-at-eol --stat`; `git checkout -- <file>` every build file that shows only in plain `git diff --stat`). New build file `ws_dashboard.js` is committed. `node --check` every touched build file.
- UI: edit `ui/runtime_src/src/*.jsx`, `ui/runtime_src/workspaces/*.jsx` and `ui/runtime_src/head_inner.html`; never `vendor/`. No raw-HTML sinks. Every `/*` must close (`tests/test_ui_sources.py`, which also parametrises over the new `dashboard.jsx`). Match the existing look (`.glass`, `.widget-dot`, `font-title`, Tailwind, CSS vars `--text`, `--text-dim`, `--text-faint`, `--accent`, `--line`, `--ink`).
- Source files may be CRLF (core.autocrlf). If the Edit tool cannot match a multi-line `old_string`, apply the same replacement with a short Python snippet (`open(p, encoding="utf-8", newline="")`, replace on `\n`-normalised text, convert back to `\r\n` if the file had them, write with `newline=""`).
- No new Python dependencies.
- Privacy anti-goal: never store or transmit key sequences, text, or per-keystroke timestamps. The dashboard only shows per-key counters that Phase 1/4 already produce; the one new stored item is the hero mode in `localStorage` (`aether-dash-hero`).
- Bridge methods return `{"ok": bool, ...}` and never raise to JS (`Api._fail`). Phase 5 adds none; Phase 6 must follow this for `get_overlays` / `set_overlay`.
- Do NOT touch `service/server.py`, `updater.py`, `Api.open_submission_url`, `.github/workflows/board-bot.yml`, or the Pillow pin.
- Implementer: `git add` only the files you changed (other agents leave untracked files here), never `git stash`, end every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The user is asleep: "If it doesn't require my intervention write the code save items that require me for later." Do not stop to ask; queue user items in the status file.
- Context limit: if your context approaches ~400k tokens, stop: commit only what is green, append a status entry to `docs/superpowers/roadmap-status.md` saying exactly where you stopped, and return.

## Design decisions (resolved; do not re-decide)

1. **One page, not widgets.** The other tabs are draggable `WidgetFrame`s on a 1480 px canvas. The dashboard is a single fixed composition on that same canvas, rendered by `app.jsx` inside `<div className="workspace" data-section="dashboard" style={{ paddingBottom: 0 }}>`, so it inherits the window-fit zoom (`--ws-zoom` = min(window width / 1480, (window height - 64) / 900) x user zoom) but has no title bars to drag. Panels reuse the widget grammar (`glass` surface, `widget-dot`, Impact uppercase title, mono meta on the right of the header, `border-[var(--line)]` hairline) so it reads as the same app, aligned on one grid with one gutter (`gap-3.5` = 14 px) and one inner padding (`px-4 py-3`).
2. **Layout (design px on the 1480 x 900 canvas; at the 1160 x 800 minimum the zoom is 0.784 and the visible canvas is 1480 x 939, so the 900 px page never scrolls; larger windows scale it up).**

```
x=24                                                                      x=1456
y=20  DASHBOARD  Default · Wed, 4 Nov                     key statistics on · counters only   (h-9)
y=68  ┌ ● KEYBOARD ─────────────── today · 1,336 presses ┐ ┌ CONNECTION ─────────────────┐
      │ [HEATMAP ]  ┌────── 60% board, ~730 px ──────┐ more │ │ ● AULA WIN60 HE   [DISCONNECT]│
      │ [LIVE    ]  │  heat colours / travel fill /  │  ▮   │ │ Linked · poll 8 kHz (0.125 ms)│
      │ [ACTUAT. ]  │  per-key actuation + RT        │ fewer│ ├ PROFILE · GAME ─────────────┤
      │             └────────────────────────────────┘      │ │ [DEFAULT] [FPS] [TYPING]      │
      │  W · 312 presses today · 12.0% bottom-out · actuates │ │ VALORANT  playing · profile FPS│
      │  at 0.80 mm                      (caption, h-5)     │ ├ ACTUATION · READ BACK ───────┤
      │                                                     │ │ 0.45–0.80 mm  2 values · 61   │
      │   hero: col 1fr, h 420                              │ │ 1 key in rapid trigger        │
      └─────────────────────────────────────────────────────┘ │ EDIT IN ACTUATION →   (392 px)│
                                                              └──────────────────────────────┘
y=502 ┌ ● TODAY ── 2026-11-04 ┐ ┌ ● AUTO-TUNE ───────── top 3 ┐ ┌ ● LIGHTING ── on the keyboard ┐
      │ PRESSES BOTTOM SHALLOW│ │ Suggestions only: nothing … │ │ ◒ RADAR                ‹  › │
      │ 1,336   8.8%   20     │ │ [EARLIER] Letters … [APPLY] │ │ [WAVE][NEON][RADAR][CROSS]  │
      │ LAST 14 DAYS ▂▅▇▃▁▂▅▆ │ │ [LATER]   Q: …      [APPLY] │ │ … 4-col chips, scrolls      │
      │                       │ │ [EARLIER] 1: …      [APPLY] │ ├ ● STATUS ON KEYS (Phase 6) ─┤
      │ OPEN ANALYTICS →      │ │ status line · ALL SUGG… →   │ │ [CPU LOAD 23%] [RAM] …      │
      └ 340 px ───────────────┘ └ 1fr ────────────────────────┘ └ 392 px ─────────────────────┘
y=880
```

   Exact classes: page `px-6 pt-5 pb-5 h-[900px] flex flex-col gap-3`; masthead `flex items-end gap-4 h-9 shrink-0` (title `font-title uppercase text-[30px]`); row 1 `grid grid-cols-[minmax(0,1fr)_392px] gap-3.5 h-[420px] shrink-0`; row 2 `grid grid-cols-[340px_minmax(0,1fr)_392px] gap-3.5 flex-1 min-h-0`; right column of row 2 `flex flex-col gap-3.5 min-h-0` (Lighting `flex-1`, Status on keys below it when present). Hierarchy: the keyboard is the only element with a halo (blurred `--accent-gradient` ellipse at 16 % opacity) and the largest area; the rail answers "is it connected / which profile / what is it set to"; the band answers "how did I type today / what should I change / how does it look".
3. **Hero modes.** `heatmap` = `KeyboardPanel mode="lighting"` with `ledMap = AetherAnalytics.heatLedMap(store.analytics.keys)` (store days forced to 1, see 7); `live` = `mode="keymap"` with `liveDepths` and the read-back `perKeyOverride` (travel fill + accent glow once past the key's own actuation point; no per-key numbers); `actuation` = `mode="actuation"` with the read-back `perKeyOverride` (numbers, hue bar, RT pair, tick), no live depth. Availability: `heatmap` needs `board.isSupported("keyStats")`, `live` and `actuation` need `isSupported("actuation")` (fail-open without board data, like every gate); none available -> a plain keymap board with "This board reports no travel or actuation data." The switcher sits in `KeyboardPanel`'s `leftSlot` (vertical chips, like the Actuation tab's toolbar), the legend in `rightSlot`. Mode persists per viewer in `localStorage["aether-dash-hero"]` (try/catch); a remembered mode the board lacks falls back to the first available. Clicking keys selects them locally (not the shared `ctx.selectedKeys`, so a dashboard click never arms an Actuation write) and the caption shows that key's numbers. `KeyboardPanel` gains `showFooter` (default `true`) so the hero can drop the dead refresh button.
4. **Live depth without fighting reader owners.** No new loop and no direct `open_analog_codes`. `app.jsx` gets `const [liveView, setLiveView] = useState(false)` and the Travel Test effect keys on `liveWanted = travelTest || liveView` (deps `[connected, liveWanted]`): one 33 ms `read_live` loop (skips while `document.hidden`), one `"analog"` reader owner. The dashboard sets `ctx.setLiveView(true)` in an effect while the hero is in `live` and returns `() => ctx.setLiveView(false)`, so switching mode, switching tab or unmounting releases it; `close_analog` then runs unless the Actuation tab's Travel Test still wants the stream (that toggle is untouched). Phase 1's `"telemetry"` owner is unaffected (open_analog_codes already widens to all keys when others share the reader).
5. **Data flow, one source each.** Analytics: `window.AetherAnalytics.useAnalytics(ctx.apiCall)` (its single 5 s timer runs only while a subscriber is mounted; `SuggestionList` subscribes to the same store). Top 3: `<An.SuggestionList ctx={ctx} limit={3} compact/>` (Apply = `applySuggestion` -> `ctx.applyTuneSuggestion` -> `writeActuation`; the Analytics tab's Undo bar reads the same `store.lastApplied`). `SuggestionCard`/`SuggestionList` gain `compact` (detail on one truncated line with the full text as tooltip, no meta line) so three cards fit. Today: the last row of `get_analytics().daily` (`{presses, shallow, bottom}`, bottom-out % = bottom / (presses + shallow), one decimal). Games: the existing 2 s `games_status` tick in `app.jsx` also stores `{available, autoSwitch, active, foreground, detected}` in `gamesInfo` (deduped with `sameJson`) and exposes it as `ctx.games`; game names render as text only. Actuation summary: `ctx.perKeyActuation` / `ctx.perKeyTrigger` (firmware read-back on connect and after every write): uniform value, or min–max + the three most common values, + count of keys whose trigger mode != 0. Connection: `ctx.connected`, `ctx.connecting`, `ctx.pollRestarting`, `ctx.polling` (kHz code 1/2/4/8, shown as "poll 8 kHz (0.125 ms)" while linked), `ctx.togglePair`. Profile: chips over `ctx.profiles`, click = `ctx.switchProfile` (the profile menu's own path, so Phase 3's `games_sync` sees a manual switch). Lighting: `LIGHTING_BOARD.modeGridFor(board.lighting)` (the tray panel's list) and `ctx.setPattern` (the tray panel's path; `app.jsx`'s lighting effect sends it and `tray_sync` follows). `lighting.jsx` loads after `dashboard.jsx` (alphabetical build order), so `LIGHTING_BOARD` is read at render time.
6. **Graceful states.** Offline: rail says Offline + Pair; actuation says "Connect the keyboard to read its actuation back."; live caption says "Connect the keyboard to see how deep each key goes."; lighting meta "applies when connected" (chips still set the pattern, sent on connect, like the tray). Stats off: amber notes in the hero caption, Today and the masthead pill, link "Turn on in Settings". No travel stream (`get_analytics().supported === false`, e.g. MINI 60 HE PRO): Heatmap hidden, Today says "Typing statistics need a board with a live travel stream (Aula Win60 HE).", Auto-tune shows `SuggestionList`'s own unsupported note, Analytics links hidden (that tab is gated off). Board without lighting/actuation support: those blocks say so. Games unavailable (Linux): "Game detection unavailable · Windows only".
7. **Analytics range.** The dashboard is "today": on mount it calls `AetherAnalytics.setDays(1)` when `store.days !== 1`. The Analytics tab therefore shows "Today" after a dashboard visit (accepted; the store is per session anyway).
8. **Landing tab + remembered tab.** `SECTION_DEFS` gains `{ id: "dashboard", label: "Dashboard", icon: IGrid }` first; `section` starts as `"dashboard"`. Hydration restores `globals.section` only when `globals.dashboardIntro` is set, and every save writes `globals: { autoConnect, section, dashboardIntro: true }` (both the debounced save and the unload flush). So: fresh install -> Dashboard; first launch after the update -> Dashboard once; from then on the remembered tab wins (including Dashboard itself). A tab that becomes unavailable falls back to `"dashboard"` (ungated) instead of `"keymap"`. The tray mini panel is untouched (it drives `pattern`/`speed` through `window.__aetherTraySet` and never reads `section`); no test assumes the first tab (checked: none references `SECTION_DEFS` order or the landing tab).
9. **Top bar at the minimum width.** Measured in the prototype: the eight existing labelled tabs plus the connect cluster already needed ~1480 px, so at the default 1340 px window the Pair / zoom / gear buttons were pushed off screen before this phase; a ninth tab makes it worse. Fix in `head_inner.html`: `.topbar-tab` padding 14 -> 11 px (labelled bar then needs ~1560 px, under the bar's 1600 px cap) and `@media (max-width: 1580px) { .topbar-tab:not(.on) > span { display: none; } }` (icon-only inactive tabs, the active tab keeps its label); `desktop.jsx` tabs get `title={s.label} aria-label={s.label}`. Verified: 1160 px -> bar width 1160, 1581/1700 px -> all labels, no overflow. Queued for the user as a veto item.
10. **Phase 6 contract (status on keys).** The tile renders ONLY when the bridge answers. On mount (and when `ctx.connected` changes) the page calls `ctx.apiCall("get_overlays")`; without the method `apiCall` returns `{ok: false, error: "no bridge"}` and nothing renders. If the answer passes `overlayView` (ok, `supported !== false`, `overlays` array) the tile shows one chip per overlay and re-polls every `OVERLAY_POLL_MS = 2000` while the page is mounted and the window visible; a click calls `ctx.apiCall("set_overlay", id, !on)` and applies `{id, on}` from the reply. Phase 6 must add to `Api`:
    - `get_overlays()` -> `{"ok": True, "supported": bool, "overlays": [{"id": "cpu"|"ram"|"gpu"|"pomodoro", "label": str, "row": str, "on": bool, "available": bool, "reason": str|None, "value": float|None}], "pomodoro": {"phase": "work"|"break"|None, "remaining_s": int|None}}`. Order cpu, ram, gpu, pomodoro. `label` e.g. "CPU load"; `row` e.g. "number row" (tooltip "CPU load on the number row"); `value` 0..1 shown as a percentage (CPU/RAM/GPU load, Pomodoro progress) or None; `available: False` + `reason` (e.g. "nvidia-smi not found") renders a disabled chip; `supported: False` (e.g. non-Windows) hides the tile. `on` reflects the ACTIVE profile (spec: persisted per profile; the active profile id already reaches Python through `games_sync`).
    - `set_overlay(overlay_id: str, on: bool)` -> `{"ok": True, "id": overlay_id, "on": bool}` (persisted for the active profile, effective immediately) or `{"ok": False, "error": str}`; unknown id -> `ok: False`. Both never raise (`Api._fail`), never touch HID from the poll path except through the effect engine's existing stream.
    - `tests/test_dashboard_ui_sources.py::test_phase6_overlay_bridge_matches_the_dashboard_contract` is skipped until `Api.get_overlays` exists, then requires `set_overlay` too. Phase 6 must keep `window.AetherDashboard.overlayView` semantics if it changes the tile.
11. **Tests.** No JS test runner exists, so: source checks in a new `tests/test_dashboard_ui_sources.py` (repo style of `test_analytics_ui_sources.py`), `node --check` of the built file, and the pure helpers executed in node through a small `.cjs` harness that loads the BUILT `ws_dashboard.js` with stub `window`/`React`/`localStorage` globals (skipped without node). No Python bridge is added, so there are no new Api tests.

## Review Focus

- **Live stream left open, or closed under the Actuation tab:** leaving the dashboard (mode switch, tab switch, unmount) must close the analog reader unless Travel Test is on, and must not close it when it is. Pinned by Task 2 `test_live_view_holds_the_one_travel_test_stream` (one loop, `liveWanted` gate) and Task 3 `test_dashboard_reuses_the_shared_stores_and_ctx_actions` (`ctx.setLiveView(true)` + cleanup `setLiveView(false)`); hardware check 4.
- **Remembered tab lost, or Dashboard never seen by upgraders:** Task 4 `test_remembered_tab_wins_after_the_one_time_intro`, `test_dashboard_is_the_first_tab_and_the_landing_tab`; hardware check 1.
- **Zeros or wrong modes on boards without the data (non-WIN60, stats off, offline, Linux games):** Task 3 node tests `test_hero_modes_follow_the_board_capabilities`, `test_game_line_states`, `test_today_is_the_last_daily_row`, `test_actuation_summary_reads_the_firmware_values`; hardware checks 2, 9.
- **A dashboard action writing something unexpected:** the page calls only `get_overlays` / `set_overlay` itself; Apply, profile, lighting and live all go through existing ctx paths. Task 3 `test_dashboard_calls_only_the_phase6_bridges`; Phase 4's `test_apply_goes_through_the_normal_actuation_path` stays green.
- **Overflow at the 1160 x 800 minimum (page or top bar):** Task 3 `test_layout_fits_the_fixed_design_canvas`, Task 4 `test_top_bar_stays_on_screen_at_the_minimum_width`; hardware check 1 (and the optional browser check in Task 4).

## File Structure

- Modify `ui/runtime_src/src/keyboard.jsx`: `KeyboardPanel` prop `showFooter = true`.
- Modify `ui/runtime_src/workspaces/analytics.jsx`: `compact` on `SuggestionCard` / `SuggestionList`.
- Modify `ui/runtime_src/src/app.jsx`: `liveView` hold, `gamesInfo` -> `ctx.games`, landing tab + one-time intro, fallback, page render.
- Modify `ui/runtime_src/src/desktop.jsx`: Dashboard first in `SECTION_DEFS` (`IGrid`), tab tooltips.
- Modify `ui/runtime_src/head_inner.html`: compact top bar below 1580 px.
- Create `ui/runtime_src/workspaces/dashboard.jsx` (page + helpers). Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/ws_dashboard.js` (new), `keyboard.js`, `ws_analytics.js`, `app.js`, `desktop.js`.
- Create `tests/test_dashboard_ui_sources.py` (23 tests + 1 skipped Phase 6 contract test); `tests/test_ui_sources.py` gains one parametrised case for `dashboard.jsx` automatically.
- Modify `CLAUDE.md`.
- Expected end state: **1009 passed, 14 skipped** (without `node` on PATH: 1003 passed, 20 skipped).

---

### Task 1: Shared pieces the dashboard reuses (`showFooter`, compact suggestions)

**Files:**
- Modify: `ui/runtime_src/src/keyboard.jsx`, `ui/runtime_src/workspaces/analytics.jsx`
- Test: `tests/test_dashboard_ui_sources.py` (create; later tasks append)
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/keyboard.js`, `ui/runtime_src/build/ws_analytics.js`

**Interfaces:**
- Produces: `KeyboardPanel({..., showFooter = true})`; `SuggestionCard({ s, onApply, disabled, busy, compact })` (adds `data-tune-card={s.id}` on the card root); `SuggestionList({ ctx, limit, compact })`. Existing callers are unchanged (defaults keep today's rendering).

- [ ] **Step 1: Write the failing tests** — create `tests/test_dashboard_ui_sources.py` with exactly:

```python
"""Phase 5 Dashboard (source checks; the UI has no JS test runner, so the
pure helpers run in node when it is installed). The Dashboard is the landing
tab, reuses the shared stores and ctx actions (no second polling loop), holds
the live-depth stream only while shown, and talks to the bridge directly only
for Phase 6's get_overlays / set_overlay."""
import json
import os
import re
import shutil
import subprocess

import pytest

import app_web

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")
NODE = shutil.which("node")


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


def _code(text):
    """Source without block and whole-line // comments (they may name things)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


# ---- Task 1: shared pieces the dashboard reuses ---------------------------
KB = _read("src", "keyboard.jsx")
AN = _read("workspaces", "analytics.jsx")


def test_keyboard_panel_footer_is_optional():
    assert "  showFooter = true,\n}) => {" in KB
    assert "{showFooter && (" in KB


def test_suggestion_list_has_a_compact_variant():
    assert "const SuggestionList = ({ ctx, limit, compact }) =>" in AN
    assert "compact={!!compact}" in AN
    assert "title={s.detail}" in AN
    assert "{!compact && (" in AN
```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_dashboard_ui_sources.py`
Expected: `2 failed` (assertion errors on `showFooter = true` and the compact signature).

- [ ] **Step 3: Edit `ui/runtime_src/src/keyboard.jsx`** (exact replacements)

(a) Replace

```jsx
  liveDepths = null, calibrating = false, calibratedCodes = null,
}) => {
```

with

```jsx
  liveDepths = null, calibrating = false, calibratedCodes = null,
  showFooter = true,
}) => {
```

(b) Replace

```jsx
      {/* Below-keyboard refresh */}
      <div className="flex flex-col items-center mt-3 gap-1">
```

with

```jsx
      {/* Below-keyboard refresh. showFooter={false} (the Dashboard hero) drops
          it: the hero has its own caption line under the board. */}
      {showFooter && (
      <div className="flex flex-col items-center mt-3 gap-1">
```

(c) Replace the end of `KeyboardPanel`

```jsx
          </span>
        )}
      </div>
    </div>
  );
};
```

with

```jsx
          </span>
        )}
      </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Edit `ui/runtime_src/workspaces/analytics.jsx`** (exact replacements)

(a) Replace

```jsx
const SuggestionCard = ({ s, onApply, disabled, busy }) => (
  <div className="rounded-xl border border-[var(--line)] bg-white/[0.02] p-3 flex flex-col gap-1.5">
```

with

```jsx
/* compact (the Phase 5 dashboard): the detail note becomes one truncated
   line with the full text as its tooltip, so three cards fit one panel. */
const SuggestionCard = ({ s, onApply, disabled, busy, compact }) => (
  <div className={`rounded-xl border border-[var(--line)] bg-white/[0.02] flex flex-col ${compact ? "px-3 py-2 gap-1" : "p-3 gap-1.5"}`}
       data-tune-card={s.id}>
```

(b) Replace

```jsx
    <Note>{s.detail}</Note>
    <div className="font-mono text-[10px] text-[var(--text-faint)]">
      {`${fmtInt(s.presses)} presses at ${s.current_mm.toFixed(2)} mm · ${s.codes.length} key${s.codes.length === 1 ? "" : "s"}`}
    </div>
```

with

```jsx
    {compact
      ? <div className="text-[11px] text-[var(--text-dim)] truncate" title={s.detail}>{s.detail}</div>
      : <Note>{s.detail}</Note>}
    {!compact && (
      <div className="font-mono text-[10px] text-[var(--text-faint)]">
        {`${fmtInt(s.presses)} presses at ${s.current_mm.toFixed(2)} mm · ${s.codes.length} key${s.codes.length === 1 ? "" : "s"}`}
      </div>
    )}
```

(c) Replace `const SuggestionList = ({ ctx, limit }) => {` with `const SuggestionList = ({ ctx, limit, compact }) => {`.

(d) Replace `        <SuggestionCard key={x.id} s={x} busy={s.applying === x.id}` with `        <SuggestionCard key={x.id} s={x} busy={s.applying === x.id} compact={!!compact}`.

- [ ] **Step 5: Build and check**

Run: `<py> ui\runtime_src\build_runtime.py`, then `node --check ui/runtime_src/build/keyboard.js` and `node --check ui/runtime_src/build/ws_analytics.js` (both silent).
Run: `git diff --ignore-cr-at-eol --stat` -> exactly the two sources, `ui/index_runtime.html`, `build/keyboard.js`, `build/ws_analytics.js`. `git checkout --` every other build file `git status` shows.
Run: `<py> -m pytest -q -p no:cacheprovider tests/test_dashboard_ui_sources.py tests/test_analytics_ui_sources.py tests/test_ui_sources.py` -> all pass.

- [ ] **Step 6: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `987 passed, 13 skipped`.

```bash
git add ui/runtime_src/src/keyboard.jsx ui/runtime_src/workspaces/analytics.jsx ui/runtime_src/build/keyboard.js ui/runtime_src/build/ws_analytics.js ui/index_runtime.html tests/test_dashboard_ui_sources.py
git commit -m "feat(ui): optional keyboard footer and compact auto-tune cards for the dashboard" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `app.jsx` plumbing (live-depth hold, games view)

**Files:**
- Modify: `ui/runtime_src/src/app.jsx`, `tests/test_dashboard_ui_sources.py` (append)
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/app.js`

**Interfaces:**
- Produces (ctx): `liveView: bool`, `setLiveView(bool)` (holds the Travel Test stream; release by setting false), `games: null | {available, autoSwitch, active: {id, name, profileId}|null, foreground, detected: [{id, name, mapped, profileId}]}`.

- [ ] **Step 1: Append the failing tests** to `tests/test_dashboard_ui_sources.py`:

```python
# ---- Task 2: app.jsx plumbing ----------------------------------------------
APP = _read("src", "app.jsx")


def test_live_view_holds_the_one_travel_test_stream():
    assert "const liveWanted = travelTest || liveView;" in APP
    assert "if (!connected || !liveWanted) {" in APP
    assert "}, [connected, liveWanted]);" in APP
    assert APP.count('apiCall("open_analog_codes"') == 1     # one loop, one owner
    assert APP.count('apiCall("read_live")') == 1
    assert "liveView, setLiveView," in APP


def test_games_view_comes_from_the_existing_poll():
    assert APP.count('apiCall("games_status")') == 1
    assert "setGamesInfo(prev => sameJson(prev, view) ? prev : view);" in APP
    assert "games: gamesInfo," in APP
```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_dashboard_ui_sources.py`
Expected: the 2 new tests fail.

- [ ] **Step 3: Edit `ui/runtime_src/src/app.jsx`** (exact replacements)

(a) Replace

```jsx
  const [actReadNonce, setActReadNonce] = useState(0);   // bump = re-read actuation
```

with

```jsx
  const [actReadNonce, setActReadNonce] = useState(0);   // bump = re-read actuation
  // The latest games_status() for the Dashboard (same 2 s poll, no second
  // loop). Only the fields it shows; deduped so an unchanged poll costs no render.
  const [gamesInfo, setGamesInfo] = useState(null);
```

(b) Replace

```jsx
        const s = await apiCall("games_status");
        const sw = s && s.ok ? s.switch : null;
```

with

```jsx
        const s = await apiCall("games_status");
        if (alive && s && s.ok) {
          const view = { available: !!s.available, autoSwitch: !!s.autoSwitch,
                         active: s.active || null, foreground: s.foreground || null,
                         detected: Array.isArray(s.detected) ? s.detected : [] };
          setGamesInfo(prev => sameJson(prev, view) ? prev : view);
        }
        const sw = s && s.ok ? s.switch : null;
```

(c) Replace

```jsx
  // Travel Test: stream live analog depth for ALL keys (so any keypress shows,
  // not just the selected ones) and mirror it onto the on-screen board.
  useEffect(() => {
    if (!connected || !travelTest) {
```

with

```jsx
  // Travel Test: stream live analog depth for ALL keys (so any keypress shows,
  // not just the selected ones) and mirror it onto the on-screen board.
  // The Dashboard's "Live depth" hero holds the same stream through liveView
  // (one loop, one "analog" reader owner); it drops the hold when it leaves
  // that mode or unmounts, and the reader closes once nobody wants it.
  const [liveView, setLiveView] = useState(false);
  const liveWanted = travelTest || liveView;
  useEffect(() => {
    if (!connected || !liveWanted) {
```

(d) In the same effect replace `  }, [connected, travelTest]);` with `  }, [connected, liveWanted]);` (it directly follows the `}, 33);   // ~30fps ...` interval line).

(e) In `const ctx = {` replace `    travelTest, setTravelTest, liveDepths, liveMax,` with `    travelTest, setTravelTest, liveDepths, liveMax, liveView, setLiveView,`, and replace

```jsx
    gamepadError, handleInstallVigem,
```

with

```jsx
    gamepadError, handleInstallVigem,
    // games (Dashboard tile): latest games_status() view, null until polled
    games: gamesInfo,
```

- [ ] **Step 4: Build and check**

Run: `<py> ui\runtime_src\build_runtime.py`, `node --check ui/runtime_src/build/app.js`.
Run: `git diff --ignore-cr-at-eol --stat` -> `app.jsx`, `build/app.js`, `ui/index_runtime.html` (+ the test file). `git checkout --` other build files.
Run: `<py> -m pytest -q -p no:cacheprovider tests/test_dashboard_ui_sources.py tests/test_games_ui_sources.py tests/test_analytics_ui_sources.py` -> all pass.

- [ ] **Step 5: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `989 passed, 13 skipped`.

```bash
git add ui/runtime_src/src/app.jsx ui/runtime_src/build/app.js ui/index_runtime.html tests/test_dashboard_ui_sources.py
git commit -m "feat(ui): ctx.setLiveView holds the travel stream; ctx.games from the existing games poll" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The Dashboard page (`workspaces/dashboard.jsx`)

**Files:**
- Create: `ui/runtime_src/workspaces/dashboard.jsx` (auto-discovered by `build_runtime.py`, compiled to `build/ws_dashboard.js` before `ws_lighting.js` and `app.js`)
- Modify: `tests/test_dashboard_ui_sources.py` (append)
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/ws_dashboard.js` (new)

**Interfaces:**
- Consumes: ctx (`apiCall, connected, connecting, pollRestarting, togglePair, polling, profiles, activeId, activeProfileName, switchProfile, setSection, actuation, perKeyActuation, perKeyTrigger, liveDepths, setLiveView, games, pattern, setPattern, power, board`), `window.AetherKeyboard.{KeyboardPanel, KB_ROWS}`, `window.AetherAnalytics.{useAnalytics, store, setDays, heatLedMap, DailyBars, SuggestionList}`, `window.AetherWorkspaces.LIGHTING_BOARD.modeGridFor` (read at render time).
- Produces: `window.AetherWorkspaces.DASHBOARD_PAGE` (component, props = ctx); `window.AetherDashboard = { HERO_MODES, OVERLAY_POLL_MS, heroModesFor(isSupported) -> string[], pickHeroMode(available, remembered) -> string|null, perKeyOverrideOf(act, trig) -> {code: {actuation, rtPress, rtRelease}}, actuationSummary(act, trig, total) -> null|{keys, total, min, max, uniform, distinct, groups: [{mm, n}] (<= 3), rt}, todayFrom(analytics) -> null|{date, presses, shallow, bottom, bottom_pct}, gameLine(games, profiles) -> {tone, text, sub}, overlayView(r) -> null|overlay[] }`. Bridges called directly: `get_overlays`, `set_overlay` only (decision 10).

- [ ] **Step 1: Append the failing tests** to `tests/test_dashboard_ui_sources.py`:

```python
# ---- Task 3: workspaces/dashboard.jsx --------------------------------------
DASH = _read("workspaces", "dashboard.jsx")


def test_dashboard_exports_the_page_and_helpers():
    assert "window.AetherWorkspaces.DASHBOARD_PAGE = DashboardPage;" in DASH
    m = re.search(r"window\.AetherDashboard = \{(.*?)\};", DASH, re.S)
    assert m, "window.AetherDashboard export missing"
    names = {n.strip() for n in m.group(1).replace("\n", " ").split(",") if n.strip()}
    assert names == {"HERO_MODES", "OVERLAY_POLL_MS", "heroModesFor", "pickHeroMode",
                     "perKeyOverrideOf", "actuationSummary", "todayFrom", "gameLine",
                     "overlayView"}


def test_dashboard_calls_only_the_phase6_bridges():
    code = _code(DASH)
    assert set(re.findall(r'apiCall\("([a-z_]+)"', code)) == {"get_overlays", "set_overlay"}
    assert "pywebview" not in code
    for name in ("set_trigger_codes", "verify_actuation", "start_multicolor", "set_light",
                 "open_analog", "close_analog", "read_live", "games_status",
                 "get_analytics", "get_tune_suggestions"):
        assert name not in code, name


def test_dashboard_reuses_the_shared_stores_and_ctx_actions():
    code = _code(DASH)
    for needle in ("window.AetherAnalytics.useAnalytics",
                   "<An.SuggestionList ctx={ctx} limit={3} compact/>",
                   "An.heatLedMap(keys)", "<An.DailyBars daily={a.daily} height={64}/>",
                   "An.setDays(1)", "ctx.setLiveView(true);",
                   "return () => ctx.setLiveView(false);", "ctx.setPattern(",
                   "L.modeGridFor(", "ctx.switchProfile(p.id)", "ctx.togglePair",
                   "showFooter={false}"):
        assert needle in code, needle


def test_overlay_tile_polls_only_while_supported_and_cleans_up():
    body = DASH[DASH.index("function OverlaysPanel"):DASH.index("/* ===== the page")]
    assert "if (alive && v) timer = setInterval(" in body
    assert "return () => { alive = false; if (timer) clearInterval(timer); };" in body
    assert "if (!list || !list.length) return null;" in body


def test_no_raw_html_sinks_and_honest_copy():
    assert "dangerouslySetInnerHTML" not in DASH and "innerHTML" not in DASH
    assert "Suggestions only: nothing is written until you click Apply." in DASH
    assert "key statistics on · counters only" in DASH


def test_layout_fits_the_fixed_design_canvas():
    # app.jsx zooms a 1480 x 900 canvas to the window: 900 px tall = no
    # scrolling at the 1160 x 800 minimum (verified in a browser).
    for cls in ('"px-6 pt-5 pb-5 h-[900px] flex flex-col gap-3"',
                "grid-cols-[minmax(0,1fr)_392px] gap-3.5 h-[420px]",
                "grid-cols-[340px_minmax(0,1fr)_392px] gap-3.5 flex-1 min-h-0"):
        assert cls in DASH, cls


def test_built_dashboard_is_current():
    with open(os.path.join(SRC, "build", "ws_dashboard.js"), encoding="utf-8") as fh:
        built = fh.read()
    assert "DASHBOARD_PAGE" in built and "AetherDashboard" in built
    with open(os.path.join(HERE, "ui", "index_runtime.html"), encoding="utf-8") as fh:
        assert "window.AetherDashboard" in fh.read()


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_built_dashboard_parses():
    subprocess.run([NODE, "--check", os.path.join(SRC, "build", "ws_dashboard.js")], check=True)


HARNESS = r"""
const fs = require("fs");
global.window = { AetherKeyboard: { KB_ROWS: [[["Q", 4, "Q"], ["W", 4, "W"]]], KeyboardPanel() {} } };
global.React = { useState() {}, useEffect() {}, useMemo() {}, createElement() {} };
global.localStorage = { getItem() { return null; }, setItem() {} };
// Runs OUR built ws_dashboard.js (a repo file) with stub globals.
require("vm").runInThisContext(fs.readFileSync(process.argv[2], "utf8"), { filename: process.argv[2] });
const D = window.AetherDashboard;
const profiles = [{ id: "p1", name: "Default" }, { id: "p2", name: "FPS" }];
console.log(JSON.stringify({
  modesAll: D.heroModesFor(() => true),
  modesNoStats: D.heroModesFor(n => n !== "keyStats"),
  modesNone: D.heroModesFor(() => false),
  pick: [D.pickHeroMode(["heatmap", "live"], "live"), D.pickHeroMode(["live"], "heatmap"),
         D.pickHeroMode([], "live")],
  sum: D.actuationSummary({ Q: 0.8, W: 0.8, E: 0.45, R: 0.6, T: 0.3 },
                          { Q: { mode: 13 }, W: { mode: 0 } }, 61),
  uniform: D.actuationSummary({ Q: 0.8, W: 0.8 }, {}, 61),
  sumNone: D.actuationSummary({}, {}, 61),
  override: D.perKeyOverrideOf({ Q: 0.8 }, { Q: { mode: 13, travel_mm: 0.8, rt_press_mm: 0.15, rt_release_mm: 0.2 },
                                           W: { mode: 0, travel_mm: 1.2, rt_press_mm: 0.1, rt_release_mm: 0.1 } }),
  today: D.todayFrom({ daily: [{ date: "2026-11-03", presses: 9, shallow: 0, bottom: 0 },
                               { date: "2026-11-04", presses: 90, shallow: 10, bottom: 25 }] }),
  todayNone: D.todayFrom({ daily: [] }),
  games: [
    D.gameLine(null, profiles),
    D.gameLine({ available: false }, profiles),
    D.gameLine({ available: true, autoSwitch: true, active: { id: "g", name: "VALORANT", profileId: "p2" }, detected: [] }, profiles),
    D.gameLine({ available: true, autoSwitch: true, active: null, foreground: "g",
                 detected: [{ id: "g", name: "VALORANT", mapped: false }] }, profiles),
    D.gameLine({ available: true, autoSwitch: false, active: null, detected: [] }, profiles),
  ],
  overlays: [D.overlayView({ ok: false, error: "no bridge" }),
             D.overlayView({ ok: true, supported: false, overlays: [{ id: "cpu" }] }),
             D.overlayView({ ok: true, overlays: [{ id: "cpu", on: true }, null, { label: "x" }] })],
}));
"""


@pytest.fixture(scope="module")
def helpers(tmp_path_factory):
    if NODE is None:
        pytest.skip("node not installed")
    h = tmp_path_factory.mktemp("dash") / "harness.cjs"
    h.write_text(HARNESS, encoding="utf-8")
    out = subprocess.run([NODE, str(h), os.path.join(SRC, "build", "ws_dashboard.js")],
                         check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout)


def test_hero_modes_follow_the_board_capabilities(helpers):
    assert helpers["modesAll"] == ["heatmap", "live", "actuation"]
    assert helpers["modesNoStats"] == ["live", "actuation"]
    assert helpers["modesNone"] == []
    assert helpers["pick"] == ["live", "live", None]


def test_actuation_summary_reads_the_firmware_values(helpers):
    s = helpers["sum"]
    assert (s["keys"], s["total"], s["min"], s["max"]) == (5, 61, 0.3, 0.8)
    assert s["uniform"] is False and s["distinct"] == 4 and s["rt"] == 1
    assert s["groups"][0] == {"mm": 0.8, "n": 2} and len(s["groups"]) == 3
    assert helpers["uniform"]["uniform"] is True and helpers["uniform"]["keys"] == 2
    assert helpers["sumNone"] is None
    o = helpers["override"]
    assert o["Q"] == {"actuation": 0.8, "rtPress": 0.15, "rtRelease": 0.2}
    assert o["W"] == {"actuation": 1.2, "rtPress": 0, "rtRelease": 0}


def test_today_is_the_last_daily_row(helpers):
    assert helpers["today"] == {"date": "2026-11-04", "presses": 90, "shallow": 10,
                                "bottom": 25, "bottom_pct": 25}
    assert helpers["todayNone"] is None


def test_game_line_states(helpers):
    texts = [(g["tone"], g["text"]) for g in helpers["games"]]
    assert texts == [("dim", "Checking for games…"), ("dim", "Game detection unavailable"),
                     ("accent", "VALORANT"), ("text", "VALORANT"), ("dim", "No game running")]
    assert helpers["games"][2]["sub"] == "playing · profile FPS"
    assert helpers["games"][3]["sub"] == "running · not mapped to a profile"
    assert helpers["games"][4]["sub"] == "auto-switch off"


def test_overlay_tile_needs_a_supported_bridge(helpers):
    none, unsupported, ok = helpers["overlays"]
    assert none is None and unsupported is None
    assert ok == [{"id": "cpu", "on": True}]
```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_dashboard_ui_sources.py`
Expected: collection error (`FileNotFoundError` for `workspaces/dashboard.jsx`).

- [ ] **Step 3: Create `ui/runtime_src/workspaces/dashboard.jsx`** with exactly:

```jsx
(() => {
/* ============================================================
   Dashboard workspace (roadmap Phase 5): the landing page. ONE composed
   page on the fixed 1480 x 900 design canvas (app.jsx zooms it to the
   window, so it fits the 1160 x 800 minimum without scrolling):

     masthead   DASHBOARD · profile · date                 statistics pill
     row 1      hero keyboard (heatmap | live depth | actuation)  | rail:
                                                                   connection,
                                                                   profile + game,
                                                                   actuation
     row 2      today | auto-tune top 3 | lighting (+ status on keys)

   Exports window.AetherWorkspaces.DASHBOARD_PAGE (a component taking ctx as
   props; app.jsx renders it instead of a widget desktop) and
   window.AetherDashboard (pure helpers, unit-tested through node).

   Data: everything comes from ctx and the shared stores, so no second
   polling loop exists. Analytics = window.AetherAnalytics.useAnalytics
   (5 s, only while mounted); games = ctx.games (app.jsx's 2 s
   games_status poll); live depth = ctx.setLiveView(true) holds app.jsx's
   Travel Test stream (one "analog" reader owner) and is released when the
   hero leaves "live" or the page unmounts; actuation = ctx.perKeyActuation
   / ctx.perKeyTrigger (firmware read-back); lighting = ctx.pattern /
   ctx.setPattern (the same path as the tray panel).
   The only bridges called here are Phase 6's get_overlays / set_overlay,
   through ctx.apiCall; with no such bridge the tile is not rendered.

   Privacy: counters only (see analytics.jsx); nothing here stores keys.
   ============================================================ */
const { useState, useEffect, useMemo } = React;
const KB = window.AetherKeyboard || {};
const KeyboardPanel = KB.KeyboardPanel;
const KB_ROWS = KB.KB_ROWS || [];
const ALL_CODES = KB_ROWS.flat().map(r => r[2]);
const LABEL_OF_CODE = {};
KB_ROWS.flat().forEach(([label, _u, code]) => { LABEL_OF_CODE[code] = label; });

// analytics.jsx loads before this file, lighting.jsx after it (build order is
// alphabetical), so both are read when used, never at module load.
const AN = () => window.AetherAnalytics || null;
const LB = () => (window.AetherWorkspaces && window.AetherWorkspaces.LIGHTING_BOARD) || null;
const useAnalyticsStore = (window.AetherAnalytics && window.AetherAnalytics.useAnalytics)
  || (() => null);

const HERO_KEY = "aether-dash-hero";
const OVERLAY_POLL_MS = 2000;
const HERO_MODES = [
  { id: "heatmap",   label: "Heatmap" },
  { id: "live",      label: "Live depth" },
  { id: "actuation", label: "Actuation" },
];
const HEAT_GRADIENT = "linear-gradient(to top, #16324a, #1f9fb4, #f2b84b, #ff4d5e)";
const ACT_GRADIENT = "linear-gradient(to top, hsl(180 80% 55%), hsl(99 80% 55%), hsl(27 80% 55%))";

/* ===== pure helpers (window.AetherDashboard) ===== */
// isSupported = ctx.board.isSupported (fail-open without board data).
const heroModesFor = (isSupported) => HERO_MODES
  .filter(m => (m.id === "heatmap" ? isSupported("keyStats") : isSupported("actuation")))
  .map(m => m.id);
const pickHeroMode = (available, remembered) =>
  (available.includes(remembered) ? remembered : (available[0] || null));

// Firmware read-back -> KeyboardPanel perKeyOverride (as the Actuation tab).
const perKeyOverrideOf = (act, trig) => {
  const out = {};
  const a = act || {}, t = trig || {};
  new Set([...Object.keys(a), ...Object.keys(t)]).forEach(c => {
    const k = t[c];
    const rt = !!(k && k.mode && k.mode !== 0);
    out[c] = {
      actuation: a[c] != null ? a[c] : (k ? k.travel_mm : undefined),
      rtPress: rt ? k.rt_press_mm : 0,
      rtRelease: rt ? k.rt_release_mm : 0,
    };
  });
  return out;
};

// Read-back summary: null when nothing was read. groups = up to 3 most
// common values (0.01 mm), most keys first.
const actuationSummary = (act, trig, total) => {
  const vals = Object.values(act || {}).filter(v => typeof v === "number" && isFinite(v));
  if (!vals.length) return null;
  const counts = {};
  vals.forEach(v => { const k = v.toFixed(2); counts[k] = (counts[k] || 0) + 1; });
  const groups = Object.entries(counts).map(([mm, n]) => ({ mm: +mm, n }))
    .sort((x, y) => (y.n - x.n) || (x.mm - y.mm));
  const sorted = vals.slice().sort((x, y) => x - y);
  const rt = Object.values(trig || {}).filter(k => k && k.mode && k.mode !== 0).length;
  return {
    keys: vals.length, total: total || vals.length,
    min: sorted[0], max: sorted[sorted.length - 1],
    uniform: groups.length === 1, distinct: groups.length,
    groups: groups.slice(0, 3), rt,
  };
};

// get_analytics().daily always ends with today's row.
const todayFrom = (analytics) => {
  const rows = analytics && Array.isArray(analytics.daily) ? analytics.daily : [];
  const d = rows.length ? rows[rows.length - 1] : null;
  if (!d) return null;
  const presses = d.presses || 0, shallow = d.shallow || 0, bottom = d.bottom || 0;
  const attempts = presses + shallow;
  return { date: d.date, presses, shallow, bottom,
           bottom_pct: attempts ? Math.round((1000 * bottom) / attempts) / 10 : null };
};

// ctx.games (games_status view) -> {tone, text, sub}. Names are text only.
const gameLine = (games, profiles) => {
  if (!games) return { tone: "dim", text: "Checking for games…", sub: "" };
  if (!games.available) return { tone: "dim", text: "Game detection unavailable", sub: "Windows only" };
  const pname = (id) => ((profiles || []).find(p => p.id === id) || {}).name;
  if (games.active)
    return { tone: "accent", text: games.active.name,
             sub: `playing · profile ${pname(games.active.profileId) || "of the game"}` };
  const det = Array.isArray(games.detected) ? games.detected : [];
  if (det.length) {
    const g = det.find(x => x.id === games.foreground) || det[0];
    return { tone: "text", text: g.name,
             sub: !g.mapped ? "running · not mapped to a profile"
               : games.autoSwitch ? "running · switching soon" : "running · auto-switch off" };
  }
  return { tone: "dim", text: "No game running",
           sub: games.autoSwitch ? "auto-switch on" : "auto-switch off" };
};

// get_overlays() result -> overlay list, or null = do not render the tile
// (no bridge before Phase 6, an error, or supported:false).
const overlayView = (r) => ((r && r.ok && r.supported !== false && Array.isArray(r.overlays))
  ? r.overlays.filter(o => o && typeof o.id === "string") : null);

const readHero = () => { try { return localStorage.getItem(HERO_KEY); } catch (e) { return null; } };
const writeHero = (m) => { try { localStorage.setItem(HERO_KEY, m); } catch (e) {} };
const fmtInt = (v) => (v == null ? "–" : Number(v).toLocaleString());
const fmtMm = (v) => (v == null ? "–" : `${v.toFixed(2)} mm`);

/* ===== shared bits (same grammar as the widget frames) ===== */
const Panel = ({ title, meta, children, className = "", bodyClass = "", id }) => (
  <section className={`glass flex flex-col min-h-0 overflow-hidden ${className}`} data-dash-panel={id}>
    <header className="flex items-center gap-2 px-4 pt-3 pb-2.5 border-b border-[var(--line)] shrink-0">
      <span className="widget-dot" aria-hidden/>
      <span className="font-title uppercase text-[16px] tracking-[0.04em] text-[var(--text)]">{title}</span>
      {meta != null && meta !== "" && (
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)] truncate">{meta}</span>
      )}
    </header>
    <div className={`flex-1 min-h-0 px-4 py-3 ${bodyClass}`}>{children}</div>
  </section>
);
const Label = ({ children }) => (
  <div className="font-mono text-[9.5px] uppercase tracking-[0.22em] text-[var(--text-faint)] mb-1">{children}</div>
);
const Note = ({ children, tone }) => (
  <div className={`text-[11px] leading-relaxed ${tone === "warn" ? "text-amber-300/90" : "text-[var(--text-dim)]"}`}>{children}</div>
);
const LinkBtn = ({ children, onClick }) => (
  <button onClick={onClick}
    className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)] hover:text-[var(--accent)] transition-colors">
    {children} →
  </button>
);
const Chip = ({ on, children, onClick, title, disabled }) => (
  <button onClick={onClick} title={title} disabled={disabled}
    className={`px-2.5 h-7 rounded-lg font-display text-[10.5px] uppercase tracking-[0.14em] truncate transition-all
                ${on ? "bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]"
                     : "text-[var(--text-dim)] hover:text-[var(--text)] border border-[var(--line)] disabled:opacity-40"}`}>
    {children}
  </button>
);
const Big = ({ children, sub }) => (
  <div className="flex items-baseline gap-2 min-w-0">
    <span className="font-mono text-[22px] leading-none text-[var(--text)] truncate">{children}</span>
    {sub && <span className="text-[11px] text-[var(--text-dim)] truncate">{sub}</span>}
  </div>
);

/* ===== hero: the keyboard ===== */
const Legend = ({ top, bottom, gradient }) => (
  <div className="flex flex-col items-end gap-1">
    <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]">{top}</span>
    <span className="w-2 h-24 rounded-full" style={{ background: gradient }}/>
    <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]">{bottom}</span>
  </div>
);

function Hero({ ctx, store, modes, mode, setMode }) {
  const [focus, setFocus] = useState(() => new Set());
  const a = store && store.analytics;
  const keys = (a && a.keys) || {};
  const override = useMemo(() => perKeyOverrideOf(ctx.perKeyActuation, ctx.perKeyTrigger),
                           [ctx.perKeyActuation, ctx.perKeyTrigger]);
  const depths = ctx.liveDepths || {};
  const deepest = Math.max(0, ...Object.values(depths).map(v => +v || 0));
  const An = AN();
  const today = todayFrom(a);

  const panelMode = mode === "heatmap" ? "lighting" : mode === "actuation" ? "actuation" : "keymap";
  const meta = mode === "heatmap"
      ? (a && a.supported === false ? "" : today ? `today · ${fmtInt(today.presses)} presses` : "loading…")
    : mode === "live"
      ? (ctx.connected ? `live · deepest ${(deepest < 0.05 ? 0 : deepest).toFixed(2)} mm` : "offline")
    : mode === "actuation"
      ? (ctx.connected ? (Object.keys(override).length ? `read back · ${Object.keys(override).length} keys` : "reading…")
                       : "offline · not from the board")
    : "";

  const codes = Array.from(focus);
  const c = codes.length === 1 ? codes[0] : null;
  let caption;
  if (mode === "heatmap" && a && a.enabled === false)
    caption = <span className="text-amber-300/90">Key statistics are off, so nothing new is counted. Turn them on in Settings.</span>;
  else if (mode === "live" && !ctx.connected)
    caption = "Connect the keyboard to see how deep each key goes.";
  else if (c) {
    const k = keys[c];
    const o = override[c];
    const parts = [LABEL_OF_CODE[c] || c];
    if (k) parts.push(`${fmtInt(k.presses)} presses today`, `${k.bottom_pct == null ? "–" : k.bottom_pct.toFixed(1) + "%"} bottom-out`);
    if (o && o.actuation != null) parts.push(`actuates at ${o.actuation.toFixed(2)} mm${o.rtPress ? " · rapid trigger" : ""}`);
    if (mode === "live") parts.push(`now ${((depths[c] || 0) < 0.05 ? 0 : depths[c]).toFixed(2)} mm`);
    caption = parts.join(" · ");
  } else if (codes.length > 1) {
    const n = codes.reduce((s, x) => s + ((keys[x] && keys[x].presses) || 0), 0);
    caption = `${codes.length} keys · ${fmtInt(n)} presses today`;
  } else {
    caption = mode === "heatmap" ? "Colour = share of today's presses against the busiest key. Click a key for its numbers."
      : mode === "live" ? "Press any key: the fill is its travel, the glow means it went past its actuation point."
      : mode === "actuation" ? "Each key's actuation point and rapid-trigger pair as the keyboard stores them."
      : "This board reports no travel or actuation data.";
  }

  const switcher = (
    <div className="flex flex-col gap-1.5" data-hero-modes>
      {modes.map(id => (
        <Chip key={id} on={mode === id} onClick={() => setMode(id)}>
          {(HERO_MODES.find(m => m.id === id) || {}).label}
        </Chip>
      ))}
    </div>
  );
  const sum = mode === "actuation" ? actuationSummary(ctx.perKeyActuation, ctx.perKeyTrigger, ALL_CODES.length) : null;
  const legend = mode === "heatmap" ? <Legend top="more" bottom="fewer" gradient={HEAT_GRADIENT}/>
    : mode === "actuation" ? <Legend top={sum ? `${sum.max.toFixed(2)} later` : "later"}
                                     bottom={sum ? `${sum.min.toFixed(2)} earlier` : "earlier"} gradient={ACT_GRADIENT}/>
    : mode === "live" ? (
        <div className="flex flex-col items-end gap-0.5">
          <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]">deepest</span>
          <span className="font-mono text-[16px] text-[var(--accent)]">{(deepest < 0.05 ? 0 : deepest).toFixed(2)}</span>
          <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]">mm</span>
        </div>
      ) : null;

  return (
    <Panel id="hero" title="Keyboard" meta={meta} className="relative" bodyClass="relative flex flex-col justify-center gap-3">
      <div aria-hidden className="absolute -top-24 left-1/2 -translate-x-1/2 w-[720px] h-[300px] rounded-[50%] opacity-[0.16] pointer-events-none blur-3xl"
           style={{ background: "var(--accent-gradient, var(--accent))" }}/>
      {typeof KeyboardPanel === "function" ? (
        <KeyboardPanel
          mode={panelMode} layer="default" showPill={false} showFooter={false}
          selectedKeys={focus} setSelectedKeys={setFocus}
          ledMap={mode === "heatmap" && An ? An.heatLedMap(keys) : null}
          actuationPoint={typeof ctx.actuation === "number" ? ctx.actuation : 1.70}
          rtPress={0} rtRelease={0}
          perKeyOverride={mode === "heatmap" ? null : override}
          liveDepths={mode === "live" ? ctx.liveDepths : null}
          leftSlot={modes.length > 1 ? switcher : null} rightSlot={legend}/>
      ) : <Note tone="warn">Keyboard view failed to load.</Note>}
      <div className="relative h-5 text-center text-[11.5px] text-[var(--text-dim)] truncate" data-hero-caption>{caption}</div>
    </Panel>
  );
}

/* ===== rail: connection / profile + game / actuation ===== */
function Rail({ ctx }) {
  const board = ctx.board || {};
  const name = (board.board && board.board.name) || "Keyboard";
  const isSup = board.isSupported || (() => true);
  const state = ctx.pollRestarting ? "Restarting keyboard…" : ctx.connecting ? "Connecting…"
    : ctx.connected ? "Linked" : "Offline";
  const g = gameLine(ctx.games, ctx.profiles);
  const sum = actuationSummary(ctx.perKeyActuation, ctx.perKeyTrigger, ALL_CODES.length);
  const block = "px-4 py-3";
  return (
    <section className="glass flex flex-col min-h-0 overflow-hidden" data-dash-panel="rail">
      <div className={block} data-dash-block="connection">
        <Label>Connection</Label>
        <div className="flex items-center gap-3">
          <span className={`relative inline-block w-2 h-2 rounded-full pulse-ring ${ctx.connected ? "bg-[var(--good)] text-[var(--good)]" : "bg-[var(--text-faint)] text-[var(--text-faint)]"}`}/>
          <div className="min-w-0 flex-1">
            <div className="font-title uppercase text-[17px] tracking-[0.04em] text-[var(--text)] truncate">{name}</div>
            <div className="font-mono text-[10.5px] text-[var(--text-dim)]">
              {state}{ctx.connected && ctx.polling ? ` · poll ${ctx.polling} kHz (${(1 / ctx.polling).toFixed(3)} ms)` : ""}
            </div>
          </div>
          <Chip on={!ctx.connected} onClick={ctx.togglePair} disabled={!!ctx.connecting || !!ctx.pollRestarting}>
            {ctx.connected ? "Disconnect" : "Pair"}
          </Chip>
        </div>
      </div>
      <div className={`${block} border-t border-[var(--line)]`} data-dash-block="profile">
        <Label>Profile · game</Label>
        <div className="flex flex-wrap gap-1.5 max-h-[64px] overflow-y-auto">
          {(ctx.profiles || []).map(p => (
            <Chip key={p.id} on={p.id === ctx.activeId} onClick={() => ctx.switchProfile && ctx.switchProfile(p.id)}
                  title={`Switch to ${p.name}`}>{p.name}</Chip>
          ))}
        </div>
        <div className="mt-2 flex items-baseline gap-2 min-w-0" data-games-line>
          <span className={`text-[12.5px] truncate ${g.tone === "accent" ? "text-[var(--accent)]" : g.tone === "text" ? "text-[var(--text)]" : "text-[var(--text-dim)]"}`}>{g.text}</span>
          <span className="font-mono text-[10px] text-[var(--text-faint)] truncate">{g.sub}</span>
        </div>
      </div>
      <div className={`${block} border-t border-[var(--line)] flex-1 flex flex-col`} data-dash-block="actuation">
        <Label>Actuation · read back from the keyboard</Label>
        {!isSup("actuation") ? <Note>This board has no adjustable actuation.</Note>
          : !sum ? <Note>{ctx.connected ? "Reading from the keyboard…" : "Connect the keyboard to read its actuation back."}</Note>
          : (
            <div className="flex flex-col gap-1.5">
              <Big sub={sum.uniform ? (sum.keys < sum.total ? `on ${sum.keys} of ${sum.total} keys` : `on all ${sum.keys} keys`)
                                    : `${sum.distinct} values · ${sum.keys} keys`}>
                {sum.uniform ? fmtMm(sum.min) : `${sum.min.toFixed(2)}–${sum.max.toFixed(2)} mm`}
              </Big>
              {!sum.uniform && (
                <div className="font-mono text-[10.5px] text-[var(--text-dim)] truncate">
                  {sum.groups.map(x => `${x.mm.toFixed(2)} × ${x.n}`).join(" · ")}{sum.distinct > 3 ? " · …" : ""}
                </div>
              )}
              <div className="text-[11px] text-[var(--text-dim)]">
                {sum.rt ? `${sum.rt} key${sum.rt === 1 ? "" : "s"} in rapid trigger` : "Fixed actuation, no rapid trigger"}
              </div>
            </div>
          )}
        <div className="mt-auto pt-2"><LinkBtn onClick={() => ctx.setSection("actuation")}>Edit in Actuation</LinkBtn></div>
      </div>
    </section>
  );
}

/* ===== row 2 ===== */
function TodayPanel({ ctx, store }) {
  const a = store && store.analytics;
  const t = todayFrom(a);
  const An = AN();
  const unsupported = a && a.supported === false;
  return (
    <Panel id="today" title="Today" meta={t ? t.date : ""} bodyClass="flex flex-col gap-3">
      {unsupported ? <Note>Typing statistics need a board with a live travel stream (Aula Win60 HE).</Note>
        : !a ? <Note>Loading…</Note> : (
        <>
          {a.enabled === false && <Note tone="warn">Key statistics are off: nothing new is counted.</Note>}
          <div className="grid grid-cols-3 gap-2">
            <div><Label>Presses</Label><div className="font-mono text-[22px] leading-none text-[var(--text)]">{fmtInt(t && t.presses)}</div></div>
            <div><Label>Bottom-out</Label><div className="font-mono text-[22px] leading-none text-[var(--text)]">{t && t.bottom_pct != null ? `${t.bottom_pct.toFixed(1)}%` : "–"}</div></div>
            <div title="Presses that moved the key but stopped before its actuation point, so nothing typed.">
              <Label>Shallow</Label><div className="font-mono text-[22px] leading-none text-[var(--text)]">{fmtInt(t && t.shallow)}</div>
            </div>
          </div>
          <div>
            <Label>Last 14 days</Label>
            {An && An.DailyBars ? <An.DailyBars daily={a.daily} height={64}/> : null}
          </div>
        </>
      )}
      {!unsupported && (
        <div className="mt-auto">
          <LinkBtn onClick={() => ctx.setSection(a && a.enabled === false ? "settings" : "analytics")}>
            {a && a.enabled === false ? "Turn on in Settings" : "Open Analytics"}
          </LinkBtn>
        </div>
      )}
    </Panel>
  );
}

function TunePanel({ ctx, store }) {
  const An = AN();
  const st = store && store.status;
  const t = store && store.tune;
  return (
    <Panel id="tune" title="Auto-tune" meta="top 3" bodyClass="flex flex-col gap-2.5">
      <div className="text-[11px] text-[var(--text-dim)] truncate"
           title="Apply writes the new actuation to those keys and reads it back, like Apply in the Actuation tab.">
        Suggestions only: nothing is written until you click Apply.
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        {An && An.SuggestionList ? <An.SuggestionList ctx={ctx} limit={3} compact/> : <Note>Analytics failed to load.</Note>}
      </div>
      <div className="flex items-center gap-3 h-4">
        <span className={`flex-1 truncate font-mono text-[10.5px] ${st && st.tone === "ok" ? "text-[var(--accent)]" : "text-rose-300/90"}`}>{st ? st.msg : ""}</span>
        {!(t && t.supported === false) && (
          <LinkBtn onClick={() => ctx.setSection("analytics")}>All suggestions, notes and Undo</LinkBtn>
        )}
      </div>
    </Panel>
  );
}

function LightingPanel({ ctx }) {
  const board = ctx.board || {};
  const isSup = board.isSupported || (() => true);
  const L = LB();
  const grid = (L && L.modeGridFor) ? L.modeGridFor(board.lighting || null) : [];
  const idx = grid.findIndex(m => m.id === ctx.pattern);
  const cur = grid[idx] || { id: ctx.pattern, label: ctx.pattern, icon: "" };
  const step = (d) => { if (grid.length) ctx.setPattern(grid[(Math.max(0, idx) + d + grid.length) % grid.length].id); };
  return (
    <Panel id="lighting" title="Lighting" meta={ctx.connected ? "on the keyboard" : "applies when connected"}
           className="flex-1" bodyClass="flex flex-col gap-2.5">
      {!isSup("lighting") ? <Note>This board's lighting is not supported yet.</Note> : (
        <>
          <div className="flex items-center gap-2">
            <span className="text-[18px] w-6 text-center text-[var(--accent)]">{cur.icon}</span>
            <span className="font-title uppercase text-[20px] tracking-[0.04em] text-[var(--text)] flex-1 truncate" data-current-effect>{cur.label}</span>
            {!ctx.power && <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-amber-300/90">lights off</span>}
            <Chip onClick={() => step(-1)} title="Previous effect">‹</Chip>
            <Chip onClick={() => step(1)} title="Next effect">›</Chip>
          </div>
          <div className="grid grid-cols-4 gap-1.5 overflow-y-auto min-h-0" data-effect-grid>
            {grid.map(m => (
              <Chip key={m.id} on={m.id === ctx.pattern} onClick={() => ctx.setPattern(m.id)} title={m.label}>
                {m.label}
              </Chip>
            ))}
          </div>
        </>
      )}
    </Panel>
  );
}

/* Phase 6 plugs in here: rendered only when get_overlays answers ok with
   supported !== false (contract in docs/superpowers/plans/2026-11-04-phase-5-dashboard.md). */
function OverlaysPanel({ ctx }) {
  const [list, setList] = useState(null);
  useEffect(() => {
    let alive = true, timer = null;
    const load = () => ctx.apiCall("get_overlays").then(r => {
      if (!alive) return null;
      const v = overlayView(r);
      setList(prev => (JSON.stringify(prev) === JSON.stringify(v) ? prev : v));
      return v;
    });
    load().then(v => {
      if (alive && v) timer = setInterval(() => { if (!document.hidden) load(); }, OVERLAY_POLL_MS);
    });
    return () => { alive = false; if (timer) clearInterval(timer); };
  }, [ctx.connected]);
  if (!list || !list.length) return null;
  const toggle = (o) => ctx.apiCall("set_overlay", o.id, !o.on).then(r => {
    if (r && r.ok) setList(l => (l || []).map(x => (x.id === r.id ? { ...x, on: !!r.on } : x)));
  });
  return (
    <Panel id="overlays" title="Status on keys" meta="" bodyClass="grid grid-cols-2 gap-1.5 content-start">
      {list.map(o => (
        <Chip key={o.id} on={!!o.on} disabled={o.available === false} onClick={() => toggle(o)}
              title={o.available === false ? (o.reason || "unavailable") : `${o.label} on the ${o.row || "keys"}`}>
          {o.label}{typeof o.value === "number" ? ` ${Math.round(o.value * 100)}%` : ""}
        </Chip>
      ))}
    </Panel>
  );
}

/* ===== the page ===== */
function DashboardPage(ctx) {
  const store = useAnalyticsStore(ctx.apiCall);
  const isSup = (ctx.board && ctx.board.isSupported) || (() => true);
  const modes = heroModesFor(isSup);
  const [pref, setPref] = useState(() => readHero());
  const mode = pickHeroMode(modes, pref);
  const setMode = (m) => { setPref(m); writeHero(m); };

  // The dashboard is "today": the shared Analytics store goes back to 1 day.
  useEffect(() => { const An = AN(); if (An && An.store && An.store.days !== 1) An.setDays(1); }, []);
  // Live depth holds app.jsx's Travel Test stream only while shown.
  useEffect(() => {
    if (mode !== "live" || !ctx.setLiveView) return undefined;
    ctx.setLiveView(true);
    return () => ctx.setLiveView(false);
  }, [mode]);

  const a = store && store.analytics;
  const date = new Date().toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  return (
    <div className="px-6 pt-5 pb-5 h-[900px] flex flex-col gap-3" data-dashboard>
      <div className="flex items-end gap-4 h-9 shrink-0">
        <span className="font-title uppercase text-[30px] leading-none tracking-[0.04em] text-[var(--text)]">Dashboard</span>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-[var(--text-faint)] pb-0.5">
          {ctx.activeProfileName} · {date}
        </span>
        {a && a.supported !== false && (
          <span className={`ml-auto font-mono text-[10px] uppercase tracking-[0.18em] pb-0.5 ${a.enabled ? "text-[var(--text-faint)]" : "text-amber-300/90"}`}
                title="Aether keeps per-key counters only: never what you typed, in what order, or when.">
            {a.enabled ? "key statistics on · counters only" : "key statistics off"}
          </span>
        )}
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_392px] gap-3.5 h-[420px] shrink-0">
        <Hero ctx={ctx} store={store} modes={modes} mode={mode} setMode={setMode}/>
        <Rail ctx={ctx}/>
      </div>
      <div className="grid grid-cols-[340px_minmax(0,1fr)_392px] gap-3.5 flex-1 min-h-0">
        <TodayPanel ctx={ctx} store={store}/>
        <TunePanel ctx={ctx} store={store}/>
        <div className="flex flex-col gap-3.5 min-h-0">
          <LightingPanel ctx={ctx}/>
          <OverlaysPanel ctx={ctx}/>
        </div>
      </div>
    </div>
  );
}

window.AetherWorkspaces = window.AetherWorkspaces || {};
window.AetherWorkspaces.DASHBOARD_PAGE = DashboardPage;
window.AetherDashboard = {
  HERO_MODES, OVERLAY_POLL_MS, heroModesFor, pickHeroMode, perKeyOverrideOf,
  actuationSummary, todayFrom, gameLine, overlayView,
};
})();
```

- [ ] **Step 4: Build and check**

Run: `<py> ui\runtime_src\build_runtime.py`, then `node --check ui/runtime_src/build/ws_dashboard.js` (silent).
Run: `git status --short` -> new `ui/runtime_src/workspaces/dashboard.jsx`, `ui/runtime_src/build/ws_dashboard.js`; `git diff --ignore-cr-at-eol --stat` -> only `ui/index_runtime.html` (+ the test file). `git checkout --` other build files.
Run: `<py> -m pytest -q -p no:cacheprovider tests/test_dashboard_ui_sources.py tests/test_ui_sources.py` -> all pass (`17 passed` in the dashboard file).

- [ ] **Step 5: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `1003 passed, 13 skipped` (13 new dashboard tests + the new `test_ui_sources.py` case).

```bash
git add ui/runtime_src/workspaces/dashboard.jsx ui/runtime_src/build/ws_dashboard.js ui/index_runtime.html tests/test_dashboard_ui_sources.py
git commit -m "feat(ui): Dashboard page (hero keyboard, status rail, today, auto-tune, lighting, Phase 6 slot)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Make it the landing tab (`desktop.jsx`, `app.jsx`, top bar)

**Files:**
- Modify: `ui/runtime_src/src/desktop.jsx`, `ui/runtime_src/src/app.jsx`, `ui/runtime_src/head_inner.html`, `tests/test_dashboard_ui_sources.py` (append)
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/desktop.js`, `ui/runtime_src/build/app.js`

**Interfaces:**
- Consumes: `window.AetherWorkspaces.DASHBOARD_PAGE` (Task 3), ctx (Task 2).
- Produces: section id `"dashboard"` (ungated, first, default); settings `globals.dashboardIntro: true`.

- [ ] **Step 1: Append the failing tests** to `tests/test_dashboard_ui_sources.py`:

```python
# ---- Task 4: landing tab + wiring ------------------------------------------
DESK = _read("src", "desktop.jsx")
HEAD = _read("head_inner.html")


def test_dashboard_is_the_first_tab_and_the_landing_tab():
    first = DESK.index('{ id: "dashboard", label: "Dashboard", icon: IGrid },')
    assert first < DESK.index('{ id: "keymap",')
    assert "IGrid = I.IGrid" in DESK
    assert 'const [section, setSection] = useState("dashboard");' in APP


def test_remembered_tab_wins_after_the_one_time_intro():
    assert "if (migrated.globals?.section && migrated.globals?.dashboardIntro)" in APP
    assert APP.count("globals: { autoConnect, section, dashboardIntro: true }") == 2


def test_an_unavailable_tab_falls_back_to_the_dashboard():
    assert 'if (!sectionAllowed(section, board)) setSection("dashboard");' in APP
    assert 'setSection("keymap")' not in APP


def test_dashboard_page_replaces_the_widget_desktop():
    assert "const DashboardPage = window.AetherWorkspaces && window.AetherWorkspaces.DASHBOARD_PAGE;" in APP
    assert "<DashboardPage {...ctx}/>" in APP
    assert 'dashboard: comingSoon("Dashboard"),' in APP


def test_top_bar_stays_on_screen_at_the_minimum_width():
    assert "@media (max-width: 1580px)" in HEAD
    assert "height: 34px; padding: 0 11px; border-radius: 10px;" in HEAD
    assert ".topbar-tab:not(.on) > span { display: none; }" in HEAD
    assert "title={s.label} aria-label={s.label}" in DESK


def test_built_page_lands_on_the_dashboard():
    with open(os.path.join(HERE, "ui", "index_runtime.html"), encoding="utf-8") as fh:
        html = fh.read()
    assert 'useState("dashboard")' in html and "DASHBOARD_PAGE" in html
    assert "max-width: 1580px" in html


@pytest.mark.skipif(not hasattr(app_web.Api, "get_overlays"),
                    reason="Phase 6 (status on keys) not built yet")
def test_phase6_overlay_bridge_matches_the_dashboard_contract():
    assert callable(app_web.Api.get_overlays) and callable(app_web.Api.set_overlay)
```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_dashboard_ui_sources.py`
Expected: the 6 new tests fail, `test_phase6_overlay_bridge_matches_the_dashboard_contract` is skipped.

- [ ] **Step 3: Edit `ui/runtime_src/src/desktop.jsx`**

(a) Replace `      ILayers = I.ILayers, IActivity = I.IActivity;` with `      ILayers = I.ILayers, IActivity = I.IActivity, IGrid = I.IGrid;`.

(b) Replace

```jsx
   Sections: keymap, macros, lighting, actuation, analytics, socd, gamepad,
   settings. (app.jsx filters this list per board — "macros" and
   "analytics" are capability-gated.)
```

with

```jsx
   Sections: dashboard (first = the landing tab), keymap, macros, lighting,
   actuation, analytics, socd, gamepad, settings. (app.jsx filters this list
   per board — "macros" and "analytics" are capability-gated.)
```

(c) Replace `const SECTION_DEFS = [` (and its newline) with

```jsx
const SECTION_DEFS = [
  { id: "dashboard", label: "Dashboard", icon: IGrid },
```

(d) Replace

```jsx
              <button key={s.id} onClick={() => onSelect(s.id)}
                className={`topbar-tab font-title${on ? " on" : ""}`}>
```

with

```jsx
              <button key={s.id} onClick={() => onSelect(s.id)} title={s.label} aria-label={s.label}
                className={`topbar-tab font-title${on ? " on" : ""}`}>
```

- [ ] **Step 4: Edit `ui/runtime_src/head_inner.html`**

(a) In `.topbar-tab` replace `    height: 34px; padding: 0 14px; border-radius: 10px;` with `    height: 34px; padding: 0 11px; border-radius: 10px;`.

(b) Directly after the line `  .topbar-tab:hover { color: var(--text); background: rgba(234,244,240,0.03); }` insert:

```css
  /* Nine labelled tabs + the connect cluster need ~1560 px (the bar is
     capped at 1600). Below that only the active tab keeps its label (the
     others show the icon, label in the tooltip), so the Pair / zoom / gear
     cluster stays on screen down to the 1160 px minimum window. */
  @media (max-width: 1580px) {
    .topbar-tab:not(.on) > span { display: none; }
  }
```

- [ ] **Step 5: Edit `ui/runtime_src/src/app.jsx`** (exact replacements)

(a) Replace

```jsx
const WIDGETS = {
  actuation: wsArr("ACTUATION_WIDGETS", "Actuation"),
```

with

```jsx
// The Dashboard (roadmap Phase 5) is ONE composed page, not a widget
// desktop: workspaces/dashboard.jsx exports a component as DASHBOARD_PAGE.
// If that file failed to load, the "coming soon" placeholder shows instead.
const DashboardPage = window.AetherWorkspaces && window.AetherWorkspaces.DASHBOARD_PAGE;
const WIDGETS = {
  dashboard: comingSoon("Dashboard"),
  actuation: wsArr("ACTUATION_WIDGETS", "Actuation"),
```

(b) Replace `  const [section, setSection] = useState("actuation");` with

```jsx
  // Dashboard is the landing tab. A remembered tab (globals.section) still
  // wins, except once: settings written before the Dashboard existed lack
  // globals.dashboardIntro, so the first launch after the update lands here.
  const [section, setSection] = useState("dashboard");
```

(c) Replace

```jsx
          if (migrated.globals?.section) setSection(migrated.globals.section === "other" ? "settings" : migrated.globals.section);
```

with

```jsx
          if (migrated.globals?.section && migrated.globals?.dashboardIntro)
            setSection(migrated.globals.section === "other" ? "settings" : migrated.globals.section);
```

(d) Replace BOTH occurrences of `globals: { autoConnect, section }` (the debounced save `... globals: { autoConnect, section } };` and the unload flush `... globals: { autoConnect, section } }); } catch {}`) with `globals: { autoConnect, section, dashboardIntro: true }`.

(e) Replace `  // fall back to the Keymap tab rather than showing an orphaned workspace.` with `  // fall back to the (ungated) Dashboard rather than an orphaned workspace.` and `    if (!sectionAllowed(section, board)) setSection("keymap");` with `    if (!sectionAllowed(section, board)) setSection("dashboard");`.

(f) Replace

```jsx
      <main id="desktop-main" className="desktop-main">
        <Workspace section={section} widgets={WIDGETS[section] || []} ctx={ctx}/>
      </main>
```

with

```jsx
      <main id="desktop-main" className="desktop-main">
        {section === "dashboard" && DashboardPage
          ? <div className="workspace" data-section="dashboard" style={{ paddingBottom: 0 }}>
              <DashboardPage {...ctx}/>
            </div>
          : <Workspace section={section} widgets={WIDGETS[section] || []} ctx={ctx}/>}
      </main>
```

- [ ] **Step 6: Build and check**

Run: `<py> ui\runtime_src\build_runtime.py`, then `node --check ui/runtime_src/build/app.js` and `node --check ui/runtime_src/build/desktop.js`.
Run: `git diff --ignore-cr-at-eol --stat` -> `app.jsx`, `desktop.jsx`, `head_inner.html`, `build/app.js`, `build/desktop.js`, `ui/index_runtime.html` (+ the test file). `git checkout --` other build files.
Run: `<py> -m pytest -q -p no:cacheprovider tests/test_dashboard_ui_sources.py tests/test_ui_sources.py tests/test_analytics_ui_sources.py tests/test_games_ui_sources.py tests/test_pressure_ui_sources.py tests/test_travel_tick_sources.py` -> all pass (dashboard file: `23 passed, 1 skipped`).

Optional (recommended) browser check, never the real app: copy `ui/index_runtime.html` into a scratch folder with a `<script src="fake.js">` inserted right after `<head>`, where `fake.js` sets `localStorage["aether-setup-done"] = "1"` and `window.pywebview = { api }` with a `Proxy` that answers `load_settings` (profiles, `globals: {section: "actuation"}` without `dashboardIntro`), `get_board` (`capabilities.keyStats: true`), `status`/`connect` ok, `verify_actuation`, `get_analytics` (keys + 14 `daily` rows), `get_tune_suggestions` (3 suggestions), `games_status`, `read_live`, `get_auto_update {autoUpdate: false}` and `{ok: true}` for anything else (return `undefined` for `get_overlays`/`set_overlay` unless testing the Phase 6 tile). Serve it with `<py> -m http.server 8731 --bind 127.0.0.1` from that folder, open it at 1160 x 800: the Dashboard is active, nothing scrolls, the top bar ends at 1160 px, `window.__aetherErrors` is empty; Live depth calls `open_analog_codes`/`read_live`, leaving it calls `close_analog`. Stop the server afterwards.

- [ ] **Step 7: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `1009 passed, 14 skipped`.

```bash
git add ui/runtime_src/src/app.jsx ui/runtime_src/src/desktop.jsx ui/runtime_src/head_inner.html ui/runtime_src/build/app.js ui/runtime_src/build/desktop.js ui/index_runtime.html tests/test_dashboard_ui_sources.py
git commit -m "feat(ui): Dashboard is the first and landing tab; compact top bar below 1580 px" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Docs, full suite, status

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/roadmap-status.md`

- [ ] **Step 1: CLAUDE.md** — add an Architecture bullet after the `analytics.py` bullet:

```text
- `ui/runtime_src/workspaces/dashboard.jsx` — the Dashboard (roadmap Phase 5), first and landing tab (a remembered tab wins after one intro launch: settings `globals.dashboardIntro`). ONE composed page on the 1480 x 900 canvas (app.jsx renders `DASHBOARD_PAGE` instead of the widget desktop): hero keyboard (Heatmap = today's AetherAnalytics heat / Live depth = `ctx.setLiveView` holding the Travel Test stream / Actuation = read-back), rail (connection + poll, profile + `ctx.games`, actuation summary), band (today, `SuggestionList limit={3} compact`, lighting quick switch via `ctx.setPattern`). No new bridge; it calls only Phase 6's `get_overlays` / `set_overlay` and hides "Status on keys" until they exist. Pure helpers on `window.AetherDashboard` are tested in node.
```

- [ ] **Step 2: Full suite**

Run: `<py> -m pytest -q -p no:cacheprovider`
Expected: `1009 passed, 14 skipped` (985 + 2 + 2 + 14 + 6; the extra skip is the Phase 6 contract test), zero failures.

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: record the Phase 5 dashboard in the architecture notes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Status entry**

Insert into `docs/superpowers/roadmap-status.md`, ABOVE `## Waiting on the user`, a dated implementer entry in the file's format (<= 15 lines): commits; decisions later phases must respect (`ctx.setLiveView`, `ctx.games`, `DASHBOARD_PAGE`, `window.AetherDashboard`, `SuggestionList compact`, `KeyboardPanel showFooter`, landing tab + `dashboardIntro`, compact top bar, the Phase 6 contract of decision 10 unchanged or say what changed); gotchas; pointer to the hardware checks below. Do not duplicate user bullets already queued by the planner. Commit it alone:

```bash
git add docs/superpowers/roadmap-status.md
git commit -m "docs(status): phase 5 dashboard done" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Hardware checks (for the orchestrator → `docs/HARDWARE_TEST_CHECKLIST.md` under `## Roadmap 2026-11-04`)

1. Launch the updated build at the minimum window (1160 x 800): it opens on **Dashboard**, nothing scrolls, the top bar shows Pair / zoom / gear (inactive tabs icon-only with tooltips). Switch to Lighting, quit, relaunch: it opens on Lighting (remembered). Maximise: all tab labels return.
2. With the WIN60 connected and statistics on: Heatmap matches what you typed today (busiest keys red/amber) and Today's presses / bottom-out % / shallow match the Analytics tab on "Today".
3. Click a key on the hero: the caption shows its presses today, bottom-out %, and its actuation (e.g. 0.80 mm). The Actuation tab's selection is unchanged.
4. Switch the hero to **Live depth** and press keys: fills track travel, a key glows once past its actuation point, "deepest" follows. Switch to Heatmap, then to another tab: typing feel and CPU return to normal (the analog stream closed). Turn Travel Test on in the Actuation tab, come back to Live depth, leave again: Travel Test in the Actuation tab still streams.
5. **Actuation** mode shows the same per-key values as the Actuation tab; the rail says e.g. "0.80 mm on all 61 keys" (or the range and the most common values) and counts rapid-trigger keys correctly.
6. Apply a suggestion from the Auto-tune panel: read-back succeeds (no "Read-back differs" notice), the rail's actuation summary updates, the suggestion disappears, and the Analytics tab offers Undo.
7. Start a mapped game: the rail shows it ("playing · profile …") within a few seconds and the profile chip switches; an unmapped game shows "not mapped to a profile"; close it: "No game running".
8. Pick effects from the Lighting panel (chips and ‹ ›): the keyboard changes like a Lighting-tab click and the tray mini panel shows the same effect.
9. Unplug the keyboard: rail says Offline with Pair, Live depth says to connect, Heatmap/Today still show today's counts. Select the MINI 60 HE PRO in the board picker (if available): Heatmap is not offered, Today says typing statistics need a live travel stream, no Analytics links.
10. Leave the app on the Dashboard for 5 minutes: CPU similar to the Analytics tab (one 5 s analytics refresh, the existing 2 s games poll, no live stream unless Live depth is shown).
