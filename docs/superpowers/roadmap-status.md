# Roadmap status — shared notes for the agent team

Spec: `docs/superpowers/specs/2026-11-04-win60-roadmap-design.md`. Read the spec and
this file before starting. Append one entry when you finish (newest at the bottom).

Entry format:
```
## <date> <phase/task> — <role> (<model>)
- Landed: <commit hashes + one line each>
- Decisions: <calls later phases must respect>
- For next phase: <interfaces, gotchas>
- For the user (morning): <hardware checks, open questions>
- Stopped early? <where, why>
```

## 2026-11-04 Phase 0 — planner (Opus, session that wrote the spec)
- The overnight branch is cut from `claude/missing-broken-audit-cda685` at the commit that adds this file (Travel Test release fix 839a076, build CRLF fix dcc46d2, security plan 3ef647c).
- Security fixes are NOT done on the overnight branch: a scheduled run implements them on `claude/missing-broken-audit-cda685` at 10:00 on 2026-11-04. Leave their targets alone (listed in the spec's Global constraints).
- Baseline: 683 tests passing.

## 2026-11-04 Phase 1 plan — planner (Opus)
- Landed: ca2f3c5 docs/superpowers/plans/2026-11-04-phase-1-telemetry.md (7 TDD tasks, 51 new tests; expect 734 passing).
- Decisions: press = run of samples >= 0.05 mm ended by a < 0.05 sample or LiveReader's release clear (reported as 0.0); split on a >= 0.30 mm fall then >= 0.30 mm rise; runs peaking <= 0.15 mm dropped.
- Decisions: per key per day {presses, shallow, barely, bottom, unrated, ttp_ms, hist[34] (0.1 mm)}; sum(hist) = presses + shallow; p10 via telemetry.peak_percentile(hist, q).
- Decisions: actuation per key comes from the firmware read-back the UI already does (verify_actuation on connect/Apply); actuation writes forget it (presses "unrated" until the next read-back). No new HID traffic.
- Decisions: LiveReader.on_sample hook; Api._make_live_reader is the only reader builder; owner "telemetry"; calibration now parks the shared reader; registry cap keyStats (win60 only).
- Decisions: files stats/YYYY-MM-DD.json (boards -> idx -> agg, sort_keys), flusher 60 s + disconnect, prune >= 90 days; collectKeyStats default ON on Windows only (Linux unchanged unless opted in).
- For next phase: Phase 4 reads Telemetry.load_day/aggregate; Phase 2 can reuse Api._make_live_reader.
- For the user (morning): 11 hardware checks at the end of the plan (typing feel/CPU with the always-on reader, calibration with stats on, shallow counting).
- Stopped early? No.

## 2026-11-04 Research — DKS decode — researcher (Opus)
- Landed: 8d329b6 — `docs/context/aula-win60-advanced-keys-decode.md`, `docs/context/aula-win60-advanced-keys-capture-checklist.md`, `protocol_win60_advkeys_wip.py` (pure, no imports, not wired), `tests/test_win60_advkeys_wip.py` (16 pass, SOURCE-ONLY goldens; read request and empty 40-slot pass pinned to webhid-capture-win60.json).
- Decisions:
  - WIN60 advanced keys are a separate 40-slot table on cmd 0x22. Write `22 <slot> 00 00 32 <type> …`; read `22 80` → 40 replies `22 80 00 <slot> 28 …`; types DKS1 MT2 TGL3 RS4 RKRT5.
  - A key binds to a slot with keymap (cmd 0x18) entry `[0x17, slot, slot, 0]`.
  - Delete = full 40-slot rewrite with that slot zeroed, plus the key's default entry restored.
  - DKS/MT/TGL are NOT gated by isRS/isRKRT (those only remove the RS/RKRT radios, wmIndex L428/L461). The Advanced tab is gated only by `isMech` (absent for WIN60) and PID 0xC345.
- For next phase:
  - MT puts the HOLD record before the TAP record on the wire. Duration is in 10 ms units (UI 15..100).
  - DKS travel points are 0.1 mm (not 0.01). Per action, 4 step codes 0..3, one per trigger point.
  - Do not reuse the MINI60 builders: different layout, and 0x22 means SET_KEY there.
  - `compose_base_keymap` already preserves vendor 0x17 bindings.
  - Wiring must sit behind `"advancedKeys": "wip"` in data/board_registry.json (not added).
- For the user (morning): run the capture checklist (D1/D2/M1/M2/T1/R1/X1, about 20 min in hed.aulacn.com; the WebHID console snippet never sees keystrokes).
  - Open questions: does the firmware honour DKS/MT/TGL; what do step codes 2/3 do; are single-slot writes accepted; is the MT 10 ms unit real.
- Stopped early? No.

## 2026-11-04 Orchestrator note
- User instruction relayed overnight: "If it doesn't require my intervention write the code save items that require me for later." Don't stop to ask; queue anything needing the user below.
- No network during dev/tests (Discord detectable list = fixture only; the shipped app may fetch at runtime).
- Agents: insert your status entry ABOVE "## Waiting on the user" and add your user items as one-line bullets INSIDE that section.

## 2026-11-04 Phase 1 — implementer (Sonnet)
- Landed: 53b3e4a telemetry.py press segmentation + aggregates; ed7ce1a day files/prune/clear/flusher; f50d86c LiveReader.on_sample hook; c6e2063 registry `keyStats` + Api reader plumbing (owner "telemetry", calibration parks the shared reader); 1677eee get_stats/clear_stats/set_stats_enabled + actuation from verify_actuation; 023d588 Settings "Key statistics" widget (+ rebuilt ws_settings.js/index_runtime.html); docs commit (CLAUDE.md + this entry).
- Suite: 766 passing, 12 skipped; green at every commit. Review fixes: dc5ca8d restored the lost */ that swallowed BackupWidget (+ tests/test_ui_sources.py), 85d5795 bottom-outs now counted independently of shallow (+ docstring fix).
- Decisions: executed the plan as written. Data model, `peak_percentile(hist, q)`, `Telemetry.load_day(date)`/`aggregate(days)` are ready for Phase 4; no new HID traffic; collectKeyStats defaults ON on Windows only.
- Deviation: added `telemetry.py` to the Flatpak `cp` list (flatpak/io.github.mrwhosnexus.AetherHE.yml); tests/test_packaging.py::test_flatpak_packages_entire_import_closure requires every module app_web imports.
- For next phase: build readers only via `Api._make_live_reader`; `_restore_shared_reader` is a no-op while `_calibrating`; stats are keyed per board slug then device index.
- For the user (morning): 11 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-1-telemetry.md (typing feel/CPU with the always-on reader, calibration with stats on, shallow counting, Clear, reconnect).
- Stopped early? No.

## 2026-11-04 Phase 2 plan — planner (Opus)
- Landed: 35e635b docs/superpowers/plans/2026-11-04-phase-2-pressure.md (5 TDD tasks, 42 new tests; expect 808 passing, 12 skipped). The plan's test code and implementation were prototyped against the real tree (all 42 green, full suite 808) and then reverted; the worktree holds only the plan.
- Decisions: `pressure` joins `effects.PRESS_REACTIVE`; level = 0 released / 0.5 at the key's actuation / 1.0 at 3.40 mm, linear each side; colour = 65-entry LUT of lerp(bg, non-looping palette gradient, level); instant attack, fall <= dt/0.12 s (frame-rate independent).
- Decisions: per-key actuation source = `Api._act_mm` (device index -> mm) filled by `verify_actuation` read-back and SUCCESSFUL `set_trigger_codes`/`set_trigger_all`, cleared by `select_board`; engine pulls `fx.get_actuation()` every 0.5 s; unknown key -> median of known, none known -> 1.70 mm.
- Decisions: LiveReader timing is untouched (worst case release->dark about 0.27 s = 0.15 s release window + 0.12 s fade). UI lists: lighting.jsx LIGHT_MODES/ZONE_MODES/HOST_FX_IDS/HOST_FX_FAST/previewKindFor + legacy sections.jsx; tray grid derives from LIGHT_MODES (no tray change); registry modes and FW_MODES not needed.
- Decisions: tester marker = 2 px line (`data-act-tick`) at `actuationPoint / TRAVEL_SCALE_MM (4)` of the key height, same scale as the travel fill, data from the existing `perKeyActuation` -> `override.actuation` (no new bridge).
- For next phase: `Api._actuation_snapshot()` is a reusable per-key actuation source (Phase 4/5 could use it); `tests/test_pressure_ui_sources.py` pins HOST_FX_IDS == engine generators and HOST_FX_FAST == PRESS_REACTIVE, so Phase 7's `music` effect must update both lists.
- For the user (morning): 9 hardware checks at the end of the plan (pressure feel, 120 ms fade, no stuck keys, actuation lines on the tester).
- Stopped early? No.

## 2026-11-04 Phase 2 — implementer (Sonnet)
- Landed: f9f15dd effects.py `pressure` generator + `pressure_level` (+25 tests); daed4c5 `Api._act_mm`/`_note_actuation`/`_actuation_snapshot`, `fx.get_actuation` (+9); 5174b5f Pressure in the Lighting/Zones/tray lists (+4); 1d0c0ac `data-act-tick` actuation line on the Travel Test board (+4); 731b120 CLAUDE.md. Suite: 808 passing, 12 skipped; green at every commit.
- Decisions later phases must respect: `pressure` is in `effects.PRESS_REACTIVE` (so `_ensure_reactive` owner "reactive" attaches the shared reader); `Api._actuation_snapshot()` is the per-key actuation source (read-back + successful writes, cleared by select_board) wired to the engine as `fx.get_actuation`; `Key` draws the tick at `TRAVEL_SCALE_MM = 4`, same scale as the travel fill.
- Deviation: `Api._act_mm` was kept as a SECOND cache next to Telemetry's `_act` on purpose, not merged. Both are fed from the same `verify_actuation` sweep, but Phase 1 telemetry deliberately FORGETS values on every write (presses read "unrated" until the next read-back) and is gated on stats enabled/supported; pressure wants the written value and must work with stats off. Merging would change Phase 1 semantics.
- Gotchas: tests/test_pressure_ui_sources.py pins HOST_FX_IDS == engine generators and HOST_FX_FAST == PRESS_REACTIVE (Phase 7's `music` effect must update both lists). Only keyboard.js, ws_lighting.js, ws_actuation.js, sections.js build files had real diffs; the rest was CRLF noise and was reverted.
- For the user (morning): 9 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-2-pressure.md (bullet already in the Waiting section).
- Stopped early? No.

## 2026-11-04 Phase 3 plan — planner (Opus)
- Landed: 676768d docs/superpowers/plans/2026-11-04-phase-3-games.md (10 TDD tasks, 108 new passing tests + 1 non-Windows skip; expect 916 passed, 13 skipped). Code and tests were prototyped against the real tree (full suite green), then reverted; the worktree holds only the plan.
- Decisions: stdlib-only `games.py`; matcher = dict of normalised trailing-segment patterns, looked up longest suffix first (<= 8 lookups/process) + a file-name prefilter so only candidate processes are ever opened; generic runtimes (javaw/python/browsers) ignored from Discord's list; user games override.
- Decisions: download = verified HTTPS, gzip requested, 5 MB cap on the wire while streaming, 32 MB decompressed cap; compact cache `<user_data_dir>/games/detectable.json` (atomic, re-validated), weekly refresh, 6 h retry; tests use tests/fixtures/discord_detectable_sample.json + injected fetchers only.
- Decisions: poll thread starts with the app (main(), Windows only, 3 s), not on connect; service is the PRIVATE `Api._games`. `GameSwitcher`: foreground mapped game wins, else sticky current, else newest; 5 s debounce; revert to the pre-session profile; a manual switch (after the UI acked the switch via `games_sync.handledSeq`) cancels revert/re-apply.
- Decisions: Python decides, app.jsx polls `games_status()` every 2 s, calls `switchProfile` (lighting follows) and `apply_profile_to_board(spec)` -> `set_trigger_all` (ALL keys) + `set_socd`; skipped when `_act_mm` + new `_trig_mode` / `_socd_last` show the board already holds it (cleared on every connect/select_board); deferred to `_connect` while offline. New `_SETTINGS_LOCK` serialises `save_settings`.
- For next phase: Phase 5 dashboard can read `games_status()["active"]`/`["detected"]`; `apply_profile_to_board` is the reusable "apply a profile's board settings" path. No new dependency or PyInstaller hidden import; Flatpak cp list gains games.py.
- For the user (morning): 12 hardware checks at the end of the plan; vetoable defaults queued below.
- Stopped early? No.

## 2026-11-04 Phase 3 — implementer (Sonnet)
- Landed: bc1e175 games.py list parser + trailing-segment matcher; 3ffc6d6 cached 5 MB capped TLS downloader; 68b5405 Toolhelp32 scan (candidate processes only); 6b5935f GameSwitcher (5 s debounce, manual override); f6594b1 GameService + 3 s poll thread; bff84ab games_* bridge + `_SETTINGS_LOCK` + Flatpak cp list; 3a21c69 `apply_profile_to_board` (+ `_trig_mode`/`_socd_last`/`_pending_board`); 574e100 tray tooltip + main() lifetime wiring; 5734c5b app.jsx game poll/switch + Settings Games widget (+ rebuilt app.js/ws_settings.js/index_runtime.html); 4f1616a CLAUDE.md.
- Suite: 916 passed, 13 skipped (the plan's expected count); green at every commit. `node --check` ok on the rebuilt app.js and ws_settings.js.
- Decisions later phases must respect: `Api._games` is PRIVATE (pywebview walks public attributes); `games_status()` shape incl. `active {id,name,profileId}` is the source for Phase 5's dashboard tile; `apply_profile_to_board` + `_trig_mode` is the reusable "apply a profile's board settings" path; `save_settings` is serialised by `_SETTINGS_LOCK`.
- Deviations: none in behaviour. Code/tests were copied verbatim from the plan; working-tree sources are CRLF (core.autocrlf) so app_web.py/tray.py/JSX edits were applied through a CRLF-preserving script, not the Edit tool. Only app.js and ws_settings.js build files had real diffs; the other 13 were line-ending noise and were reverted.
- Gotchas: tests never touch the network, the HID, or persist/print process names (the one Windows smoke test only reads this process's own pid).
- For the user (morning): the 12 hardware checks and the veto/limitation items are already in "Waiting on the user" below (nothing new added).
- Review fixes: 547d6d9 an all-keys apply now updates `_trigger_state` (later single-key edits no longer resend stale groups); 680cc27 `_board_has_actuation` checks every `km.indices()` key, missing cache entry = mismatch (suite 919 passed, 13 skipped).
- Stopped early? No.

## 2026-11-04 Phase 4 plan — planner (Opus)
- Landed: b8b445d docs/superpowers/plans/2026-11-04-phase-4-analytics.md (7 tasks, 65 new tests; expect 984 passed, 13 skipped). All code was prototyped against the real tree (suite green, built UI smoke-tested with a fake bridge in a browser), then reverted; the worktree holds only the plan.
- Decisions: telemetry files each press under the key's actuation (day-file key "idx@act", "idx" = unknown); load_day/aggregate still merge per key. Auto-tune uses ONLY buckets at the key's current read-back actuation over 14 days, so a change starts from zero and switching back restores the old count.
- Decisions: new pure `analytics.py`; groups by design code wasd ("WASD / Fn arrows": the WIN60 has no arrow keys) / letters (22) / mods / space, others per key. Group judged on summed counters only when all members share actuation + trigger mode; a group suggestion covers its members, so no key gets two or opposite suggestions.
- Decisions: shallow > 5 % -> min(p10 - 0.10, current - 0.05) rounded down to 0.05, floor 0.30; barely > 15 % on letters (not WASD) -> +0.10 (+0.20 above 25 %); both -> "mixed" note, no suggestion. Readiness = read-back actuation AND trigger mode; Apply keeps the key's mode/RT pair.
- Decisions: Apply = app.jsx `writeActuation` (set_trigger_codes + verify_actuation, shared with the Actuation button) via `ctx.applyTuneSuggestion`; Undo writes current_mm back the same way. Analytics tab after Actuation, gated on `keyStats`.
- For next phase (5): `window.AetherAnalytics` = useAnalytics, HeatmapBoard, heatLedMap, DailyBars, SuggestionList (`limit={3}`), topSuggestions, SuggestionCard, applySuggestion, store (days=1 = today). Bridges get_analytics(days) / get_tune_suggestions() are read-only.
- For the user (morning): 10 hardware checks at the end of the plan; Phase 3 interaction queued below.
- Stopped early? No.

## 2026-11-04 Phase 4 — implementer (Sonnet)
- Landed: 8f9874a telemetry actuation buckets ("idx@act", load_day_buckets/recent_buckets/actuation()); b8f7cc2 analytics.py views (groups, summarize, 14-day series); c5f1869 auto-tune evaluate/suggest; 6a9a725 get_analytics/get_tune_suggestions bridges (+ Flatpak cp list); a6f7348 analytics.jsx workspace (+ ws_analytics.js); 5be0c6e Analytics tab gated on keyStats + app.jsx writeActuation/applyTuneSuggestion; f479521 CLAUDE.md.
- Suite: 985 passed, 13 skipped (plan said 984: tests/test_ui_sources.py parametrises over workspaces, so the new analytics.jsx adds one case). Green at every commit; `node --check` ok on ws_analytics.js, app.js, desktop.js.
- Decisions later phases must respect: suggestions come only from the current read-back bucket (a changed actuation restarts at zero); suggestions never write, Apply = `ctx.applyTuneSuggestion` -> `ctx.writeActuation` (set_trigger_codes + verify_actuation). Phase 5 reuses `window.AetherAnalytics`: `useAnalytics(ctx.apiCall)`, `HeatmapBoard`, `heatLedMap`, `SuggestionList limit={3}`, `topSuggestions`.
- Deviations: none in behaviour; code/tests copied from the plan. Working-tree sources are CRLF, so edits went through a CRLF-preserving script. Only app.js, desktop.js, ws_analytics.js (new) and index_runtime.html had real build diffs; the other 13 build files were line-ending noise and were reverted.
- Gotchas: tests never touch HID or the network; the Apply test uses the fake driver. The tab polls both bridges every 5 s only while a widget is mounted.
- For the user (morning): the 10 hardware checks and the veto/accept items for Phase 4 are already in "Waiting on the user" below (nothing new added).
- Stopped early? No.

## 2026-11-04 Phase 5 plan — planner (Opus)
- Landed: b972eb4 docs/superpowers/plans/2026-11-04-phase-5-dashboard.md (5 tasks, 24 new tests + 1 skipped Phase 6 contract test; expect 1009 passed, 14 skipped). Code prototyped against the real tree (suite green; built page checked in a browser with a fake bridge at 1160x800 and 1700x1000), then reverted.
- Decisions: Dashboard = ONE page (`workspaces/dashboard.jsx` -> `window.AetherWorkspaces.DASHBOARD_PAGE`, rendered by app.jsx in the zoomed 1480x900 canvas, no widget frames). Row 1: hero keyboard (Heatmap / Live depth / Actuation) + rail (connection + poll, profile + game, actuation read-back). Row 2: Today | Auto-tune top 3 (`SuggestionList compact`) | Lighting quick switch (+ Status on keys).
- Decisions: no new bridge and no second loop. Live depth = new `ctx.setLiveView` holding app.jsx's Travel Test stream (one "analog" owner, released on mode/tab change); games = `ctx.games` from the existing 2 s games_status poll; analytics = `useAnalytics` with days forced to 1; lighting = `ctx.setPattern` (tray path).
- Decisions: Dashboard first + landing; remembered tab wins after one intro launch (`globals.dashboardIntro`); unavailable tab falls back to dashboard. Top bar: tabs padding 11 px, inactive tabs icon-only below 1580 px (the bar already overflowed at <= ~1480 px before this phase).
- For Phase 6 (contract): `Api.get_overlays()` -> {ok, supported, overlays: [{id: cpu|ram|gpu|pomodoro, label, row, on, available, reason, value 0..1|None}], pomodoro: {phase, remaining_s}}; `Api.set_overlay(id, on)` -> {ok, id, on}; never raise; `on` = active profile's toggle. The tile appears only when get_overlays answers ok with supported != false (polled 2 s while shown); `test_phase6_overlay_bridge_matches_the_dashboard_contract` un-skips when get_overlays exists.
- For the user (morning): 10 hardware checks at the end of the plan; veto items queued below.
- Stopped early? No.

## Waiting on the user
- [DKS] Run the advanced-keys capture checklist (docs/context/aula-win60-advanced-keys-capture-checklist.md, ~20 min in hed.aulacn.com) to confirm the source-only decode.
- [DKS] Open: does WIN60 firmware act on DKS/MT/TGL; DKS step codes 2/3; single-slot writes accepted; MT 10 ms unit; per-profile table?
- [Phase 1] Veto check: key statistics collection defaults ON on Windows (OFF on Linux unless opted in); stored as per-key daily aggregates only, 90 days.
- [Phase 1] Run the 11 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-1-telemetry.md (typing feel + CPU with the always-on reader, calibration with stats on, shallow/bottom counting, Clear, reconnect).
- [Phase 2] Run the 9 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-2-pressure.md (pressure feel, 120 ms fade, no stuck keys, actuation lines on the Travel Test board).
- [Phase 3] Veto check: a game switch writes the game profile's actuation/RT slider value to ALL keys (per-key actuation layouts get flattened) plus its SOCD pairs (a switch or revert also writes the profile's SOCD pairs, default A/D and W/S, even if you never applied SOCD); auto-switch defaults ON once any game is mapped.
- [Phase 3] Discord list size: the cap is 5 MB on the wire (gzip requested, 32 MB after unpacking). If Settings > Games > Update reports "larger than 5 MB", decide whether to raise `games.MAX_DETECTABLE_BYTES`.
- [Phase 3] Known limitation to accept or schedule: the revert target is not persisted, so if Aether restarts mid-game the game's exit does not revert the profile.
- [Phase 3] Run the 12 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-3-games.md (switch/revert, debounce, offline apply, tooltip, anti-cheat/CPU).
- [Phase 4] Run the 10 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-4-analytics.md (heatmap, shallow/barely counts, Apply + read-back, Undo, RT keys keep RT).
- [Phase 4] Veto check: auto-tune thresholds are the spec's first guess (shallow > 5 % -> earlier, toward the 10th-percentile depth minus 0.1 mm, never below 0.30; barely-over > 15 % on letters -> 0.1-0.2 mm later; 200 presses minimum). WASD never gets "later" suggestions. Say if any feel wrong.
- [Phase 4] Accept or schedule: a game-profile switch (Phase 3) writes one actuation to every key, replacing applied per-key auto-tune values until the revert; the revert writes the profile slider value, not the tuned values.
- [Phase 5] Run the 10 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-5-dashboard.md (landing tab + remembered tab, heatmap/today numbers, live depth opens and closes the stream, Apply from the dashboard, game line, lighting quick switch, offline/other board).
- [Phase 5] Veto check: Aether now opens on the Dashboard (existing installs once after the update, then the remembered tab); below 1580 px window width inactive top-bar tabs show only their icon (tooltip has the name). Before this the top bar already pushed Pair / zoom / gear off screen below ~1480 px.
- [Phase 5] Accept: opening the Dashboard resets the Analytics tab's range to "Today".
