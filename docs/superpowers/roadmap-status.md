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

## Waiting on the user
- [DKS] Run the advanced-keys capture checklist (docs/context/aula-win60-advanced-keys-capture-checklist.md, ~20 min in hed.aulacn.com) to confirm the source-only decode.
- [DKS] Open: does WIN60 firmware act on DKS/MT/TGL; DKS step codes 2/3; single-slot writes accepted; MT 10 ms unit; per-profile table?
- [Phase 1] Veto check: key statistics collection defaults ON on Windows (OFF on Linux unless opted in); stored as per-key daily aggregates only, 90 days.
- [Phase 1] Run the 11 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-1-telemetry.md (typing feel + CPU with the always-on reader, calibration with stats on, shallow/bottom counting, Clear, reconnect).
