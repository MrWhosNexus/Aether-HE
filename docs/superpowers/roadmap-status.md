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
