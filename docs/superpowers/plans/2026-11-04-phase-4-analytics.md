# Phase 4: Typing Analytics + Actuation Auto-tune Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Phase 1 key statistics into an "Analytics" tab (per-key press heatmap on the on-screen board, presses per day for 14 days, bottom-out %, average peak depth, shallow attempts and barely-over presses per key) and an actuation auto-tune that only SUGGESTS changes, each applied by an explicit click through the normal Actuation Apply path with read-back.

**Architecture:** `telemetry.py` files every press under the actuation its key had (new day-file key `"<idx>@<act>"`), so auto-tune can use exactly the presses recorded at a key's current actuation. A new pure module `analytics.py` turns day buckets into view summaries and suggestions (no disk, HID or clock). `Api.get_analytics(days)` and `Api.get_tune_suggestions()` are thin read-only bridges over it. A new workspace `ui/runtime_src/workspaces/analytics.jsx` renders four widgets and exports reusable pieces on `window.AetherAnalytics` for the Phase 5 dashboard. `app.jsx` factors its Apply into `writeActuation(codes, travel, mode, rtP, rtR)` (set_trigger_codes, then verify_actuation) and adds `applyTuneSuggestion(s)` on top of it.

**Tech Stack:** Python 3 stdlib only, pytest, the existing React/Tailwind UI (precompiled by `ui/runtime_src/build_runtime.py`, needs `node`).

**Spec:** `docs/superpowers/specs/2026-11-04-win60-roadmap-design.md` ("Phase 4"). Read it, `docs/superpowers/roadmap-status.md` and `docs/superpowers/plans/2026-11-04-phase-1-telemetry.md` (data model) before starting.

**Prototype:** every code block in this plan was run against the real tree on 2026-11-04 (full suite 984 passed, 13 skipped; built UI smoke-tested in a browser with a fake bridge: all four widgets render, key selection works, no console errors) and then reverted. Copy the code verbatim.

## Global Constraints

- Windows is the shipping target; nothing may break Linux (guard Windows-only code by `sys.platform`, degrade to "unavailable" elsewhere). Phase 4 is platform-neutral pure Python + JSX; add no platform code.
- **NEVER write to the keyboard, open HID, or run the app against it. Fakes only** (patterns: `tests/test_stats_api.py` `_api`/`FakeDriver`, `tests/test_travel_release.py`). Apply-suggestion tests use the fake driver. Hardware checks are listed at the end of this plan for the orchestrator.
- No push, merge into other branches, tag, release, or install. No network during development or tests.
- Python: `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe` (written `<py>` below). Full suite: `<py> -m pytest -q -p no:cacheprovider` (919 passed, 13 skipped at the start of this phase); must stay green at every commit.
- JSX changes need `<py> ui\runtime_src\build_runtime.py`; commit the regenerated `ui/index_runtime.html` + only the `ui/runtime_src/build/*.js` files with real (non-line-ending) diffs. Check with `git diff --ignore-cr-at-eol --stat`; `git checkout -- <file>` every build file that shows only in plain `git diff --stat`. New build files (`ws_analytics.js`) are committed. Run `node --check` on every touched build file.
- UI: edit `ui/runtime_src/src/*.jsx` / `ui/runtime_src/workspaces/*.jsx`, never `vendor/`. No raw-HTML sinks (`dangerouslySetInnerHTML`, `innerHTML`). Match the existing look (Tailwind classes, CSS vars `--text`, `--accent`, `--line`, `--ink`). Every `/*` must close (`tests/test_ui_sources.py`).
- New Python dependencies: **none**.
- **Privacy anti-goal:** Aether must never become a keylogger. Never store or transmit key sequences, text, or per-keystroke timestamps. Phase 4 reads per-key counters only; the one new stored fact is the actuation value a counter was recorded at (a setting, not a keystroke).
- Bridge methods return `{"ok": bool, ...}` and never raise to JS (follow `Api._fail`).
- Do NOT touch `service/server.py`, `updater.py`, `Api.open_submission_url`, `.github/workflows/board-bot.yml`, or the Pillow pin.
- `git add` only the files you changed (other agents leave untracked files in this worktree). Never use `git stash`.
- Every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Working-tree sources may be CRLF (core.autocrlf). If the Edit tool cannot match a multi-line `old_string`, do the same replacement with a short Python snippet (`open(p, encoding="utf-8", newline="")`, replace on `\n`-normalised text, convert back to `\r\n` if the file had them, write with `newline=""`).
- The user is asleep: "If it doesn't require my intervention write the code save items that require me for later." Do not stop to ask; queue user items in the status file.
- Context limit: if your context approaches ~400k tokens, stop: commit only what is green, append a status entry to `docs/superpowers/roadmap-status.md` saying exactly where you stopped, and return.

## Design decisions (resolved; do not re-decide)

1. **Where analytics lives.** New `analytics.py`: pure functions over telemetry aggregates (testable without disk, HID or clock). `Api` only loads day buckets (`Telemetry.recent_buckets`) and the read-back state and hands them in. `telemetry.py` gains actuation buckets (decision 2) and two readers; its Phase 1 per-key view (`load_day`, `aggregate`, `get_stats`) is unchanged.
2. **"Presses recorded at that actuation" = actuation buckets, over the whole window.** Phase 1 aggregates mixed every actuation a key had in a day, so a changed actuation made `shallow`/`barely` meaningless. Telemetry now files each finished run under `(idx, act)` (act = the read-back value in 0.01 mm the key had when the run ended), or `idx` when the actuation was unknown (the "unrated" presses). Day-file keys: `"46"` and `"46@80"` (`_KEY_RE = ^(\d{1,3})(?:@(\d{1,3}))?$`; file version stays 1). Auto-tune uses ONLY the buckets whose `act` equals the key's CURRENT read-back actuation, summed over the last `TUNE_WINDOW_DAYS = 14` days. Consequences: after any change (Apply, the Actuation tab, a Phase 3 game-profile switch) the key starts counting from zero at the new value and its suggestion disappears; switching back (e.g. a game ends and the profile reverts to 0.80) brings the old 0.80 presses back. Presses between a write and its read-back are unrated and never count. Rejected: "today since the last change" (needs a timestamped ledger and throws away 0.80 history on every game session) and "the raw window" (mixes actuations). Files written before this phase hold only `"<idx>"` keys and load as the unknown bucket (Phase 1 shipped tonight, so no real history is lost). Downgrade caveat: an older Aether drops `"idx@act"` keys on its next flush.
3. **Groups (design codes, `analytics.GROUPS`, disjoint):** `wasd` "WASD / Fn arrows" = W A S D; `letters` = the other 22 letters (Q E R T Y U I O P F G H J K L Z X C V B N M); `mods` = LShift RShift LCtrl RCtrl LAlt RAlt LWin Menu Fn; `space` = Space. The WIN60 has **no dedicated arrow keys**: its arrows are Fn+W/A/S/D on the same physical keys and the travel stream cannot tell layers apart, so "arrows" IS the WASD group. Every other key (number row, punctuation, Esc, Tab, Caps, Enter, Backspace) is judged per key only.
4. **Group vs per-key.** A group is judged on its SUMMED counters when every member is "ready" (decision 8) and all members share one actuation and one trigger setting (fixed mode compares as `(0, None, None)`, the stored RT pair is irrelevant there; RT modes compare `(mode, press, release)`). A group suggestion covers all its members. Then every key NOT covered is judged on its own counters. So a key never gets two suggestions, never opposite ones, and a group-level suggestion wins over a member's own. Non-uniform group -> members judged per key. `MIN_PRESSES = 200` registered presses at the current actuation, per key or summed per group.
5. **Rules.** `rated = presses - unrated` (registered presses at a known actuation), `attempts = rated + shallow`. Shallow rule: `shallow / attempts > 0.05` (strictly). Barely rule: `barely / rated > 0.15` (strictly), only for the `letters` group and individual letter keys **excluding WASD** (gaming keys: light, quick taps are intended there). Both rules at once -> NO suggestion, a "mixed" note (moving either way makes one of them worse).
6. **Amounts.** Shallower: `target = min(p10 - 0.10, current - 0.05)`, rounded DOWN to the 0.05 mm grid, then clamped to `[0.30, 3.40]` (spec 0.08..3.40 and never below 0.30). The `current - 0.05` term guarantees "toward p10 - 0.1" is at least one step when p10 - 0.1 is not below the current point. If the clamped target is not below the current point -> a "floor" note instead. With the user's 0.80 mm, one suggestion can therefore go at most to 0.30 mm, and only as far as `p10 - 0.10`. Deeper: `+0.10 mm`, or `+0.20 mm` when barely > 25 %, clamped to `[0.30, 3.40]`; none at 3.40. All arithmetic is in integer hundredths (`*_RAW` constants) so there is no float drift.
7. **What "p10 peak" means.** `telemetry.peak_percentile(hist, 0.10)` over the summed histogram of the key/group at its current actuation (presses AND shallow attempts; runs peaking <= 0.15 mm never reach the histogram). Bin `i` holds peaks with `raw // 10 == i`, i.e. `[i*0.1, (i+1)*0.1)` mm; bin 33 also holds >= 3.40. Linear interpolation inside the bin: with `N` total and `C` the count below bin `i` (the first bin where the running count reaches `0.1*N`), `p10 = (i + (0.1*N - C) / n_i) * 0.1`, rounded to 0.01 mm. Example: 30 of 300 attempts in bin 5 -> p10 = 0.60 -> suggestion 0.50 mm.
8. **Readiness = a fresh read-back.** A key gets a suggestion only when telemetry holds its read-back actuation (`Telemetry.actuation()`, forgotten on every write until the next `verify_actuation`) AND `Api._trig_mode` holds its read-back trigger mode (cleared on connect, refilled by `verify_actuation`). Offline / before the first read-back -> no suggestions and `read_back: False` (the UI says why). Each suggestion carries `mode`, `rt_press_mm`, `rt_release_mm` from the read-back so Apply keeps a rapid-trigger key in rapid trigger.
9. **Apply.** No new write bridge. `app.jsx` factors the existing `applyActuation` body into `writeActuation(codes, travel, mode, rtP, rtR)`: `set_trigger_codes(codes, travel, mode ? rtP : 0, mode ? rtR : 0, mode)`, then `verify_actuation(codes)`, update `perKeyActuation`/`perKeyTrigger`, notice on mismatch (unchanged behaviour for the Actuation button, which now calls `writeActuation(selected, actuation, rtEnabled ? 13 : 0, rtPress, rtRelease)`). `applyTuneSuggestion(s)` = `writeActuation(s.codes, s.suggested_mm, s.mode || 0, s.rt_press_mm || 0, s.rt_release_mm || 0)`; both are on `ctx`. After Apply the read-back moves the key to a new (empty) bucket, so the suggestion disappears on the next refresh. The widget offers **Undo** for the last apply: the same path with `suggested_mm = current_mm`.
10. **Views (`get_analytics(days)`, days clamped 1..90 like `get_stats`, UI ranges Today / 7 / 14 / 30 days).** Per design code over the window: presses, shallow, barely, bottom, unrated, attempts, `bottom_pct = bottom / attempts`, `shallow_pct = shallow / (rated + shallow)`, `barely_pct = barely / rated` (percentages over rated presses only; `None` when the denominator is 0), `avg_peak_mm` = histogram mean at bin midpoints (`(i + 0.5) * 0.1`, includes missed presses), `avg_ttp_ms`, and `heat = presses / busiest key's presses` (0..1, three decimals). Board `totals` with the same fields. `daily` = always the last 14 days, oldest first, `{date, presses, shallow, bottom}`, zero rows included. Buckets of one key are merged for every view.
11. **UI home.** New tab "Analytics" (icon `IActivity`) right after Actuation in `desktop.jsx` `SECTION_DEFS`, gated in `app.jsx` by `SECTION_CAPS.analytics = "keyStats"` (win60 only; fail-open without board data, like `macros`). `workspaces/analytics.jsx` widgets: **Key Heatmap** (range chips + `KeyboardPanel mode="lighting"` with heat colours as `ledMap`, legend on the right, click/ctrl-click selects keys), **Overview** (tiles for the whole board or the selected keys summed), **Presses per Day** (14 bars, plain divs), **Auto-tune** (suggestion cards with Apply, Undo bar, notes). Widgets share a module store; while any widget is mounted it refreshes both bridges every 5 s (`load_day_buckets` merges pending presses, so no flush is needed; about 30 small JSON reads per refresh, only while the tab is open). When statistics are off or the board has no travel stream, the widgets say so instead of showing zeros.
12. **Phase 5 reuse.** `window.AetherAnalytics = { store, useAnalytics, refreshAnalytics, refreshTune, setDays, heatColor, heatLedMap, topSuggestions, HeatmapBoard, DailyBars, SuggestionCard, SuggestionList, applySuggestion }`. Dashboard "today's heatmap": `useAnalytics(ctx.apiCall)` (store `days` defaults to 1 = today) + `<HeatmapBoard keys={store.analytics && store.analytics.keys}/>` (or `heatLedMap(keys)` as the `ledMap` of its own hero `KeyboardPanel`). "Top-3 suggestions with Apply": `<SuggestionList ctx={ctx} limit={3}/>` (Apply goes through `ctx.applyTuneSuggestion`). Suggestions arrive sorted by `score` = presses affected (shallow count for "earlier", barely count for "later"), so `topSuggestions(tune, 3)` is the top 3.
13. **Copy (plain words, exact strings in `analytics.py`).** Earlier: title `"<label>: actuate earlier, 0.80 → 0.50 mm"`, detail `"10.0% of your presses on these keys stopped before 0.80 mm and did not type. 9 in 10 of your presses reach 0.60 mm or deeper, so 0.50 mm should catch most of the missed ones."` Later: `"<label>: actuate later, 0.80 → 0.90 mm"`, `"20.0% of the presses that typed on this key went less than 0.10 mm past 0.80 mm. Presses that light are often a resting or brushing finger, so 0.90 mm leaves a little more room before a key types."` Notes: "data" (`"Space: 120 of 200 presses recorded at the current actuation. Suggestions start at 200."`, groups only), "floor", "mixed". Widget header: "Suggestions only: nothing is written until you click Apply. ..."
14. **Interaction with Phase 3.** A game-profile switch writes ONE actuation to all keys (`set_trigger_all`), which replaces applied per-key tunes; the revert writes the profile's slider value back. Not changed here; queued for the user (veto/accept).

## Review Focus

- **Actuation changed mid-window:** suggestions must use only presses recorded at the current read-back value. Tests: Task 4 `test_presses_at_an_old_actuation_do_not_count`, `test_presses_between_a_write_and_its_read_back_are_ignored`; Task 1 `test_a_changed_actuation_starts_a_new_bucket`.
- **A key in two suggestions, or shallower AND deeper:** impossible. Tests: Task 3 `test_no_key_gets_two_suggestions`, `test_shallow_and_barely_together_is_mixed`, `test_notes_explain_waiting_floor_and_mixed`.
- **Limits:** never below 0.30 or above 3.40, at the floor nothing shallower. Tests: Task 3 `test_shallower_never_goes_below_0_30`, `test_at_the_floor_there_is_nothing_shallower`, `test_deeper_is_clamped_to_3_40`, `test_suggested_values_respect_the_hard_limits`.
- **Suggestions never write; Apply is the normal write + read-back and keeps the trigger mode.** Tests: Task 4 `test_get_tune_suggestions_never_writes`, `test_applying_a_suggestion_is_the_normal_write_plus_read_back`, `test_rapid_trigger_mode_and_pair_come_from_the_read_back`; Task 6 `test_apply_goes_through_the_normal_actuation_path`.
- **Phase 1 view unchanged / file format compatible:** Task 1 `test_load_day_and_aggregate_still_merge_per_key`, `test_pre_split_file_loads_as_the_unknown_actuation_bucket`, `test_malformed_bucket_keys_are_dropped`; all Phase 1 tests stay green (one assertion is widened in `test_day_file_holds_only_per_key_aggregates`).
- **Privacy:** outputs are counters only. Tests: Task 3 `test_output_is_aggregates_only`, Task 4 `test_get_analytics_output_is_aggregates_only`.

## File Structure

- Modify `telemetry.py`: actuation buckets (`_KEY_RE`, `bucket_idx`, `_bucket_str`, `_record`, `_read_day`, `flush`), `actuation()`, `load_day_buckets(date)`, `recent_buckets(days)`; `load_day` merges buckets.
- Create `analytics.py`: constants + `GROUPS`, `merge_days`, `rated_at`, `key_summary`, `summarize` (Task 2); `trig_norm`, `evaluate`, `suggest` (Task 3).
- Modify `app_web.py`: `import analytics`; `Api.get_analytics`, `Api.get_tune_suggestions`.
- Modify `flatpak/io.github.mrwhosnexus.AetherHE.yml`: `analytics.py` in the `cp` list (`tests/test_packaging.py` requires every module `app_web` imports).
- Create `ui/runtime_src/workspaces/analytics.jsx`; modify `ui/runtime_src/src/app.jsx`, `ui/runtime_src/src/desktop.jsx`. Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/ws_analytics.js` (new), `app.js`, `desktop.js`.
- Modify `CLAUDE.md`.
- Tests: create `tests/test_telemetry_buckets.py` (11), `tests/test_analytics_views.py` (7), `tests/test_analytics_tune.py` (25), `tests/test_analytics_api.py` (14), `tests/test_analytics_ui_sources.py` (8); widen one assertion in `tests/test_telemetry_store.py`. 65 new tests: expect **984 passed, 13 skipped** (without `node` on PATH: 983 passed, 14 skipped).

---

### Task 1: Telemetry actuation buckets

**Files:**
- Modify: `telemetry.py`, `tests/test_telemetry_store.py`
- Test: `tests/test_telemetry_buckets.py` (create)

**Interfaces:**
- Produces: `telemetry.bucket_idx(bucket) -> int`; `Telemetry.actuation() -> dict[int, int]` (idx -> 0.01 mm, a copy); `Telemetry.load_day_buckets(date) -> dict[int | tuple[int, int], agg]`; `Telemetry.recent_buckets(days) -> list[tuple[str, dict]]` (newest first, at least one day). Unchanged: `load_day`, `aggregate`, the agg shape, `FILE_VERSION = 1`.

- [ ] **Step 1: Write the failing tests** — `tests/test_telemetry_buckets.py`:

```python
"""Phase 4: telemetry files every press under the actuation its key had, so
auto-tune can use only presses recorded at the CURRENT actuation. The
Phase 1 per-key view (load_day / aggregate / get_stats) is unchanged.
No HID: Telemetry.feed is driven directly."""
import json

from telemetry import Telemetry, bucket_idx, HIST_BINS
from test_telemetry import _tel, _press, W, TODAY

SLUG = "aula-win60-he"


def _doc(tmp_path, date=TODAY):
    p = tmp_path / "stats" / f"{date}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_rated_and_unrated_presses_land_in_separate_buckets(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [2.0])                       # actuation unknown
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [2.0], t0=t)
    _press(tel, W, [0.50], t0=t)                    # shallow at 0.80
    b = tel.load_day_buckets(TODAY)
    assert set(b) == {W, (W, 80)}
    assert b[W]["presses"] == 1 and b[W]["unrated"] == 1
    assert b[(W, 80)]["presses"] == 1 and b[(W, 80)]["shallow"] == 1
    assert b[(W, 80)]["unrated"] == 0


def test_load_day_and_aggregate_still_merge_per_key(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [2.0])
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [2.0], t0=t)
    tel.set_actuation({W: 0.50})
    _press(tel, W, [0.30], t0=t)
    day = tel.load_day(TODAY)
    assert set(day) == {W}
    assert day[W]["presses"] == 2 and day[W]["shallow"] == 1
    assert sum(day[W]["hist"]) == 3
    assert tel.aggregate(1)[W] == day[W]


def test_a_changed_actuation_starts_a_new_bucket(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [2.0])
    tel.set_actuation({W: 0.55})
    _press(tel, W, [2.0], t0=t)
    b = tel.load_day_buckets(TODAY)
    assert b[(W, 80)]["presses"] == 1 and b[(W, 55)]["presses"] == 1


def test_forgotten_actuation_files_presses_as_unrated(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    tel.forget_actuation([W])
    _press(tel, W, [2.0])
    assert set(tel.load_day_buckets(TODAY)) == {W}


def test_bucket_keys_round_trip_through_the_day_file(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [2.0])
    tel.set_actuation({W: 0.80})
    _press(tel, W, [2.0], t0=t)
    tel.flush()
    assert set(_doc(tmp_path)["boards"][SLUG]) == {"46", "46@80"}
    again = _tel(tmp_path)
    b = again.load_day_buckets(TODAY)
    assert b[W]["presses"] == 1 and b[(W, 80)]["presses"] == 1


def test_pending_and_file_counts_of_one_bucket_add_up(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [2.0])
    tel.flush()
    _press(tel, W, [2.0], t0=t)
    assert tel.load_day_buckets(TODAY)[(W, 80)]["presses"] == 2
    tel.flush()
    assert _doc(tmp_path)["boards"][SLUG]["46@80"]["presses"] == 2


def test_malformed_bucket_keys_are_dropped(tmp_path):
    (tmp_path / "stats").mkdir()
    rec = {"presses": 1, "hist": [0] * HIST_BINS}
    doc = {"version": 1, "date": TODAY, "boards": {SLUG: {
        "46@80": rec, "46@": rec, "46@1234": rec, "@80": rec, "a@b": rec,
        "46@80@1": rec, "1234": rec}}}
    (tmp_path / "stats" / f"{TODAY}.json").write_text(json.dumps(doc), encoding="utf-8")
    tel = _tel(tmp_path)
    assert set(tel.load_day_buckets(TODAY)) == {(W, 80)}
    tel.set_actuation({W: 0.80})
    _press(tel, W, [2.0])
    tel.flush()
    assert set(_doc(tmp_path)["boards"][SLUG]) == {"46@80"}


def test_pre_split_file_loads_as_the_unknown_actuation_bucket(tmp_path):
    (tmp_path / "stats").mkdir()
    rec = {"presses": 5, "shallow": 2, "barely": 1, "hist": [0] * HIST_BINS}
    doc = {"version": 1, "date": TODAY, "boards": {SLUG: {"46": rec}}}
    (tmp_path / "stats" / f"{TODAY}.json").write_text(json.dumps(doc), encoding="utf-8")
    b = _tel(tmp_path).load_day_buckets(TODAY)
    assert set(b) == {W} and b[W]["shallow"] == 2


def test_actuation_returns_a_copy_in_hundredths(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80, 47: 1.234})
    act = tel.actuation()
    assert act == {W: 80, 47: 123}
    act[W] = 1
    assert tel.actuation()[W] == 80


def test_recent_buckets_lists_days_newest_first(tmp_path):
    old = _tel(tmp_path, today=lambda: "2026-11-02")
    old.set_actuation({W: 0.80})
    _press(old, W, [2.0])
    old.flush()
    tel = _tel(tmp_path)
    days = tel.recent_buckets(3)
    assert [d for d, _ in days] == ["2026-11-04", "2026-11-03", "2026-11-02"]
    assert days[0][1] == {} and days[1][1] == {}
    assert days[2][1][(W, 80)]["presses"] == 1
    assert [d for d, _ in tel.recent_buckets(0)] == [TODAY]


def test_bucket_idx():
    assert bucket_idx(46) == 46 and bucket_idx((46, 80)) == 46
```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_telemetry_buckets.py`
Expected: ImportError (`cannot import name 'bucket_idx' from 'telemetry'`), i.e. collection error.

- [ ] **Step 3: Implement in `telemetry.py`** (exact replacements)

(a) Module docstring: after the line `  Invariant: sum(hist) == presses + shallow.` and before the closing `"""`, insert:

```text

Actuation buckets (Phase 4): a run is filed under the actuation its key had
when the run ended, so one key's counters for one day are split per
actuation value. Day-file keys are ``"<idx>"`` for runs with the actuation
unknown (the "unrated" ones) and ``"<idx>@<act>"`` (act in 0.01 mm) for the
rest; in memory a bucket is ``idx`` or ``(idx, act)``. ``load_day`` and
``aggregate`` merge a key's buckets (the Phase 1 view); ``load_day_buckets``
and ``recent_buckets`` keep them apart so auto-tune can use only the presses
recorded at a key's CURRENT actuation. Files written before the split hold
only ``"<idx>"`` keys and load as the unknown-actuation bucket.
```

(b) Replace `_KEY_RE = re.compile(r"^\d{1,3}$")` with:

```python
_KEY_RE = re.compile(r"^(\d{1,3})(?:@(\d{1,3}))?$")
```

(c) Insert before `def _default_today():`:

```python
def bucket_idx(bucket):
    """Device index of an aggregate bucket (``idx`` or ``(idx, act)``)."""
    return bucket[0] if isinstance(bucket, tuple) else bucket


def _bucket_str(bucket):
    return (f"{bucket[0]}@{bucket[1]}" if isinstance(bucket, tuple)
            else str(bucket))


```

(d) In `__init__`, change the comment `# (date, board) -> {idx: agg}` to `# (date, board) -> {bucket: agg}`.

(e) Insert before `    def forget_actuation(self, idxs):`:

```python
    def actuation(self):
        """Copy of the read-back actuation map ({device index: 0.01 mm})."""
        with self._lock:
            return dict(self._act)

```

(f) In `_record`, replace

```python
        if peak <= ATTEMPT_MIN_RAW:
            return
        agg = self._pending.setdefault((self._today(), self._board), {}) \
            .setdefault(idx, empty_agg())
        agg["hist"][min(HIST_BINS - 1, peak // 10)] += 1
        if peak >= BOTTOM_RAW:
            agg["bottom"] += 1
        act = self._act.get(idx)
        if act is not None and peak < act:
```

with

```python
        if peak <= ATTEMPT_MIN_RAW:
            return
        act = self._act.get(idx)
        bucket = idx if act is None else (idx, act)
        agg = self._pending.setdefault((self._today(), self._board), {}) \
            .setdefault(bucket, empty_agg())
        agg["hist"][min(HIST_BINS - 1, peak // 10)] += 1
        if peak >= BOTTOM_RAW:
            agg["bottom"] += 1
        if act is not None and peak < act:
```

(g) `_read_day`: docstring `"""board -> {idx: agg} ...` becomes `"""board -> {bucket: agg} from the day file; {} when missing/corrupt."""`, and replace

```python
            for k, rec in keys.items():
                if isinstance(k, str) and _KEY_RE.match(k):
                    part[int(k)] = self._sanitise(rec)
        return out
```

with

```python
            for k, rec in keys.items():
                m = _KEY_RE.match(k) if isinstance(k, str) else None
                if not m:
                    continue
                idx = int(m.group(1))
                bucket = idx if m.group(2) is None else (idx, int(m.group(2)))
                part[bucket] = self._sanitise(rec)
        return out
```

(h) Replace the whole `load_day` method with:

```python
    def load_day_buckets(self, date):
        """bucket -> aggregate for one day (file + pending) on the current
        board. A bucket is ``idx`` (actuation unknown) or ``(idx, act)``."""
        with self._io_lock:
            out = dict(self._read_day(date).get(self._board, {}))
            with self._lock:
                for b, a in self._pending.get((date, self._board), {}).items():
                    merge_agg(out.setdefault(b, empty_agg()), a)
            return out

    def load_day(self, date):
        """idx -> aggregate for one day (file + pending) on the current
        board, with every actuation bucket of a key merged."""
        out = {}
        for b, a in self.load_day_buckets(date).items():
            merge_agg(out.setdefault(bucket_idx(b), empty_agg()), a)
        return out
```

(i) In `flush`, replace

```python
                        for idx, a in keys.items():
                            merge_agg(part.setdefault(idx, empty_agg()), a)
                    doc = {"version": FILE_VERSION, "date": date,
                           "boards": {slug: {str(i): a for i, a in keys.items()}
                                      for slug, keys in cur.items()}}
```

with

```python
                        for b, a in keys.items():
                            merge_agg(part.setdefault(b, empty_agg()), a)
                    doc = {"version": FILE_VERSION, "date": date,
                           "boards": {slug: {_bucket_str(b): a
                                             for b, a in keys.items()}
                                      for slug, keys in cur.items()}}
```

and further down (the failed-write re-merge) replace

```python
                            for idx, a in keys.items():
                                merge_agg(dst.setdefault(idx, empty_agg()), a)
```

with

```python
                            for b, a in keys.items():
                                merge_agg(dst.setdefault(b, empty_agg()), a)
```

(j) Directly under `    # ---- reading ----...` (before `def aggregate`), insert:

```python

    def recent_buckets(self, days):
        """[(date, load_day_buckets(date)), ...] for the last `days` days
        (at least 1), newest first, today included."""
        today = datetime.date.fromisoformat(self._today())
        out = []
        for k in range(max(1, int(days))):
            d = (today - datetime.timedelta(days=k)).isoformat()
            out.append((d, self.load_day_buckets(d)))
        return out
```

(k) `tests/test_telemetry_store.py`: add `import re` after `import json`, and in `test_day_file_holds_only_per_key_aggregates` replace

```python
    t = _press(tel, W, [0.4, 1.2, 3.35])
    _press(tel, 47, [0.3, 0.9], t0=t)
```

with

```python
    t = _press(tel, W, [0.4, 1.2, 3.35])
    tel.set_actuation({47: 0.80})                  # Phase 4 bucket "47@80"
    _press(tel, 47, [0.3, 0.9], t0=t)
```

and

```python
    for keys in doc["boards"].values():
        for k, rec in keys.items():
            assert k.isdigit()
```

with

```python
    for keys in doc["boards"].values():
        assert set(keys) == {"46", "47@80"}
        for k, rec in keys.items():
            assert re.fullmatch(r"\d{1,3}(@\d{1,3})?", k)
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_telemetry_buckets.py tests/test_telemetry.py tests/test_telemetry_store.py tests/test_stats_api.py`
Expected: `59 passed`.

- [ ] **Step 5: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `930 passed, 13 skipped`.

```bash
git add telemetry.py tests/test_telemetry_buckets.py tests/test_telemetry_store.py
git commit -m "feat(telemetry): file presses per actuation so auto-tune can use only the current one" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `analytics.py` views (groups, bucket merging, summaries)

**Files:**
- Create: `analytics.py` (this task writes everything up to and including `summarize`)
- Test: `tests/test_analytics_views.py` (create)

**Interfaces:**
- Produces: constants `DAILY_DAYS, TUNE_WINDOW_DAYS, MIN_PRESSES, SHALLOW_RATE, BARELY_RATE, BARELY_STRONG_RATE, P_QUANTILE, MARGIN_RAW, STEP_RAW, FLOOR_RAW, MIN_RAW, MAX_RAW, DEEPER_RAW, DEEPER_STRONG_RAW, LETTERS, WASD, GROUPS, DEEPER_CODES, KEY_LABELS`; `key_label(code)`, `merge_days(days)`, `rated_at(days, act_by_idx)`, `avg_peak_mm(hist)`, `key_summary(agg)`, `summarize(day_buckets, code_of, days)`.

- [ ] **Step 1: Write the failing tests** — `tests/test_analytics_views.py`:

```python
"""Phase 4 analytics views: pure functions over telemetry aggregates
(groups, bucket merging, per-key summaries, the 14-day series).
No disk, no HID, no clock."""
import datetime

import pytest

import analytics
import device_state
import telemetry

KM = device_state.KeyMap()
IDX = KM.index_of_code


def _agg(presses=0, shallow=0, barely=0, bottom=0, unrated=0, ttp_ms=0,
         hist=None, press_bin=30, shallow_bin=5):
    a = telemetry.empty_agg()
    a.update(presses=presses, shallow=shallow, barely=barely, bottom=bottom,
             unrated=unrated, ttp_ms=ttp_ms)
    if hist is None:
        a["hist"][press_bin] += presses
        a["hist"][shallow_bin] += shallow
    else:
        for b, n in hist.items():
            a["hist"][b] += n
    return a


# ---------------------------------------------------------------- groups ----
def test_groups_are_disjoint_and_use_real_design_codes():
    seen = []
    for gid, label, codes, _ in analytics.GROUPS:
        assert codes and label
        for c in codes:
            assert c in device_state.DESIGN_CODES, c
        seen.extend(codes)
    assert len(seen) == len(set(seen))
    assert [g[0] for g in analytics.GROUPS] == ["wasd", "letters", "mods", "space"]
    assert len(analytics.GROUPS[1][2]) == 22
    assert analytics.DEEPER_CODES == frozenset(analytics.GROUPS[1][2])
    assert not analytics.DEEPER_CODES & set(analytics.WASD)


# --------------------------------------------------------------- buckets ----
def test_merge_days_merges_every_bucket_per_key():
    d1 = {46: _agg(presses=2, unrated=2), (46, 80): _agg(presses=3)}
    d2 = {(46, 55): _agg(presses=1), (47, 80): _agg(presses=4)}
    m = analytics.merge_days([d1, d2])
    assert m[46]["presses"] == 6 and m[47]["presses"] == 4


def test_rated_at_keeps_only_the_current_actuation():
    d1 = {46: _agg(presses=2, unrated=2), (46, 80): _agg(presses=3),
          (46, 55): _agg(presses=9)}
    d2 = {(46, 80): _agg(presses=1, shallow=1), (47, 80): _agg(presses=4)}
    r = analytics.rated_at([d1, d2], {46: 80})
    assert set(r) == {46}
    assert r[46]["presses"] == 4 and r[46]["shallow"] == 1


# --------------------------------------------------------------- summary ----
def _days(n, today=datetime.date(2026, 11, 4)):
    """[(date, {})] for the last n days, newest first."""
    return [((today - datetime.timedelta(days=k)).isoformat(), {})
            for k in range(n)]


def test_key_summary_percentages_and_averages():
    a = _agg(presses=8, shallow=2, barely=2, bottom=5, unrated=4, ttp_ms=400,
             hist={2: 2, 7: 4, 33: 4})
    s = analytics.key_summary(a)
    assert s["attempts"] == 10
    assert s["bottom_pct"] == 50.0
    assert s["shallow_pct"] == pytest.approx(33.3)          # 2 / (4 rated + 2)
    assert s["barely_pct"] == 50.0                           # 2 / 4 rated
    assert s["avg_peak_mm"] == pytest.approx((2.5 * 2 + 7.5 * 4 + 33.5 * 4) * 0.1 / 10, abs=0.01)
    assert s["avg_ttp_ms"] == 50


def test_key_summary_of_nothing_has_no_divisions_by_zero():
    s = analytics.key_summary(telemetry.empty_agg())
    assert s["bottom_pct"] is None and s["shallow_pct"] is None
    assert s["barely_pct"] is None and s["avg_peak_mm"] is None
    assert s["avg_ttp_ms"] is None and s["presses"] == 0


def test_summarize_window_heat_and_daily_series():
    W, Q = IDX["W"], IDX["Q"]
    days = _days(14)
    days[0] = ("2026-11-04", {(W, 80): _agg(presses=10)})
    days[1] = ("2026-11-03", {Q: _agg(presses=5, unrated=5)})
    days[2] = ("2026-11-02", {(W, 80): _agg(presses=100)})
    out = analytics.summarize(days, KM.code_of, 2)
    assert set(out["keys"]) == {"W", "Q"}
    assert out["keys"]["W"]["presses"] == 10 and out["keys"]["W"]["heat"] == 1.0
    assert out["keys"]["Q"]["heat"] == 0.5
    assert out["totals"]["presses"] == 15
    assert len(out["daily"]) == analytics.DAILY_DAYS
    assert out["daily"][0]["date"] == "2026-10-22"
    assert out["daily"][-1] == {"date": "2026-11-04", "presses": 10,
                                "shallow": 0, "bottom": 0}
    assert out["daily"][-3]["presses"] == 100


def test_summarize_of_no_data():
    out = analytics.summarize(_days(14), KM.code_of, 1)
    assert out["keys"] == {} and out["totals"]["presses"] == 0
    assert all(r["presses"] == 0 for r in out["daily"])
```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_views.py`
Expected: collection error `ModuleNotFoundError: No module named 'analytics'`.

- [ ] **Step 3: Create `analytics.py`** with exactly:

```python
"""Typing analytics + actuation auto-tune (roadmap Phase 4).

Pure functions over telemetry aggregates: nothing here touches the disk, the
HID device or a clock. ``Api.get_analytics`` / ``Api.get_tune_suggestions``
load the day buckets (``telemetry.Telemetry.recent_buckets``) and pass them in.

PRIVACY: inputs and outputs are per-key counters only (see telemetry.py);
no key sequences, text or per-keystroke timestamps exist anywhere here.

Auto-tune makes SUGGESTIONS ONLY. Applying one is a separate, explicit user
click that goes through the normal Actuation Apply path in the UI
(``set_trigger_codes`` followed by the ``verify_actuation`` read-back).

Rules (spec Phase 4, decisions in docs/superpowers/plans/2026-11-04-phase-4-analytics.md):
  * Only presses recorded at the key's CURRENT read-back actuation count
    (telemetry bucket ``(idx, act)``), over the last TUNE_WINDOW_DAYS days.
  * At least MIN_PRESSES registered presses (per key, or summed per group).
  * shallow / (presses + shallow) > 5 %  -> shallower: the 10th-percentile
    peak minus 0.10 mm, and at least one 0.05 mm step below the current
    point, rounded DOWN to 0.05 mm, never below 0.30 mm.
  * barely / presses > 15 % on letter keys (not WASD) -> deeper by 0.10 mm,
    or 0.20 mm when above 25 %, never above 3.40 mm (nor below 0.30 mm).
  * Both at once -> no suggestion (a "mixed" note): moving either way makes
    one of the two worse.
"""
import telemetry

DAILY_DAYS = 14
TUNE_WINDOW_DAYS = 14
MIN_PRESSES = 200
SHALLOW_RATE = 0.05
BARELY_RATE = 0.15
BARELY_STRONG_RATE = 0.25
P_QUANTILE = 0.10
MARGIN_RAW = 10          # "p10 minus 0.1 mm"
STEP_RAW = 5             # shallower suggestions sit on a 0.05 mm grid
FLOOR_RAW = 30           # never suggest anything below 0.30 mm
MIN_RAW, MAX_RAW = 8, 340
DEEPER_RAW = 10
DEEPER_STRONG_RAW = 20

LETTERS = tuple("QWERTYUIOPASDFGHJKLZXCVBNM")
WASD = ("W", "A", "S", "D")
# (group id, label, design codes, deeper rule allowed). Order = precedence
# for reporting only; the groups are disjoint. The WIN60 has no arrow keys:
# its arrows are Fn+W/A/S/D on the same physical keys, which is all the
# travel stream can see, so "arrows" is the WASD group.
GROUPS = (
    ("wasd", "WASD / Fn arrows", WASD, False),
    ("letters", "Letters", tuple(c for c in LETTERS if c not in WASD), True),
    ("mods", "Modifiers", ("LShift", "RShift", "LCtrl", "RCtrl", "LAlt",
                           "RAlt", "LWin", "Menu", "Fn"), False),
    ("space", "Space", ("Space",), False),
)
DEEPER_CODES = frozenset(GROUPS[1][2])

KEY_LABELS = {
    "Escape": "Esc", "Minus": "-", "Equal": "=", "Lbr": "[", "Rbr": "]",
    "Bsl": "\\", "Caps": "Caps Lock", "Semi": ";", "Quot": "'",
    "Comma": ",", "Dot": ".", "Slash": "/", "LShift": "Left Shift",
    "RShift": "Right Shift", "LCtrl": "Left Ctrl", "RCtrl": "Right Ctrl",
    "LAlt": "Left Alt", "RAlt": "Right Alt", "LWin": "Win",
}


def key_label(code):
    return KEY_LABELS.get(code, code)


def _empty(agg):
    return (not any(agg[f] for f in telemetry.FIELDS)
            and not any(agg["hist"]))


def merge_days(days):
    """[{bucket: agg}, ...] -> {idx: agg}, every bucket of a key merged."""
    out = {}
    for day in days:
        for b, a in day.items():
            telemetry.merge_agg(
                out.setdefault(telemetry.bucket_idx(b), telemetry.empty_agg()), a)
    return out


def rated_at(days, act_by_idx):
    """[{bucket: agg}, ...] -> {idx: agg} of ONLY the buckets recorded at the
    key's current actuation (``act_by_idx``: idx -> 0.01 mm)."""
    out = {}
    for day in days:
        for b, a in day.items():
            if isinstance(b, tuple) and act_by_idx.get(b[0]) == b[1]:
                telemetry.merge_agg(out.setdefault(b[0], telemetry.empty_agg()), a)
    return out


def _pct(n, d):
    return round(100.0 * n / d, 1) if d > 0 else None


def avg_peak_mm(hist):
    """Mean peak depth from the 0.1 mm histogram (bin midpoints)."""
    n = sum(hist)
    if n <= 0:
        return None
    return round(sum((i + 0.5) * c for i, c in enumerate(hist)) * 0.1 / n, 2)


def key_summary(agg):
    """One aggregate -> the numbers the Analytics views show."""
    presses, shallow = agg["presses"], agg["shallow"]
    rated = max(0, presses - agg["unrated"])
    attempts = presses + shallow
    return {
        "presses": presses, "shallow": shallow, "barely": agg["barely"],
        "bottom": agg["bottom"], "unrated": agg["unrated"],
        "attempts": attempts,
        "bottom_pct": _pct(agg["bottom"], attempts),
        "shallow_pct": _pct(shallow, rated + shallow),
        "barely_pct": _pct(agg["barely"], rated),
        "avg_peak_mm": avg_peak_mm(agg["hist"]),
        "avg_ttp_ms": round(agg["ttp_ms"] / presses) if presses else None,
    }


def summarize(day_buckets, code_of, days):
    """``day_buckets``: [(date, {bucket: agg})] newest first, at least
    max(days, DAILY_DAYS) long. Returns {"keys", "totals", "daily"}:
    per design code summaries (+ ``heat`` 0..1 = presses / busiest key's)
    over the first `days` days, and DAILY_DAYS {date, presses, shallow,
    bottom} rows, oldest first."""
    window = merge_days(d for _, d in day_buckets[:days])
    keys, total = {}, telemetry.empty_agg()
    for idx in sorted(window):
        a = window[idx]
        if _empty(a):
            continue
        keys[code_of(idx) or f"idx{idx}"] = key_summary(a)
        telemetry.merge_agg(total, a)
    top = max((k["presses"] for k in keys.values()), default=0)
    for k in keys.values():
        k["heat"] = round(k["presses"] / top, 3) if top else 0.0
    daily = []
    for date, d in reversed(day_buckets[:DAILY_DAYS]):
        m = merge_days([d]).values()
        daily.append({"date": date,
                      "presses": sum(a["presses"] for a in m),
                      "shallow": sum(a["shallow"] for a in m),
                      "bottom": sum(a["bottom"] for a in m)})
    return {"keys": keys, "totals": key_summary(total), "daily": daily}
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_views.py`
Expected: `7 passed`.

- [ ] **Step 5: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `937 passed, 13 skipped`.

```bash
git add analytics.py tests/test_analytics_views.py
git commit -m "feat(analytics): per-key typing summaries, heat and 14-day series from telemetry buckets" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Auto-tune rules (`evaluate`, `suggest`)

**Files:**
- Modify: `analytics.py` (append)
- Test: `tests/test_analytics_tune.py` (create)

**Interfaces:**
- Produces: `trig_norm(t) -> tuple | None`; `evaluate(agg, act_raw, deeper_ok) -> dict | None` (`kind` in shallower/deeper/floor/mixed; `target_raw` for the first two); `suggest(rated, act_by_idx, trig_by_idx, index_of_code) -> {"suggestions": [...], "notes": [...]}`. Suggestion keys: `id, scope, group, label, codes, direction, current_mm, suggested_mm, mode, rt_press_mm, rt_release_mm, presses, attempts, shallow, barely, shallow_pct, barely_pct, p10_mm, score, title, detail`. Note keys: `id, kind, group, label, text`.

- [ ] **Step 1: Write the failing tests** — `tests/test_analytics_tune.py`:

```python
"""Phase 4 actuation auto-tune: suggestions only, from presses recorded at
each key's current actuation. Pure functions; no disk, no HID, no clock."""
import pytest

import analytics
from test_analytics_views import _agg, IDX


# -------------------------------------------------------------- evaluate ----
def test_too_few_presses_suggest_nothing():
    assert analytics.evaluate(_agg(presses=199, shallow=100), 80, True) is None


def test_shallow_attempts_suggest_p10_minus_0_1_rounded_down():
    # 30 of 300 attempts peak in 0.50-0.60 -> p10 = 0.60 -> 0.50 mm
    v = analytics.evaluate(_agg(presses=270, shallow=30), 80, False)
    assert v["kind"] == "shallower" and v["target_raw"] == 50
    assert v["p10_mm"] == pytest.approx(0.60)
    assert v["shallow_pct"] == 10.0 and v["presses"] == 270


def test_exactly_5_percent_shallow_is_not_enough():
    assert analytics.evaluate(_agg(presses=380, shallow=20), 80, False) is None


def test_shallower_is_at_least_one_step_below_the_current_point():
    # p10 lands deep (0.9 mm bin), so p10 - 0.1 >= current: one 0.05 step.
    v = analytics.evaluate(_agg(presses=280, shallow=20,
                                hist={7: 20, 9: 280}), 80, False)
    assert v["kind"] == "shallower" and v["target_raw"] == 75


def test_shallower_never_goes_below_0_30():
    v = analytics.evaluate(_agg(presses=250, shallow=50, shallow_bin=2), 80, False)
    assert v["kind"] == "shallower" and v["target_raw"] == 30


def test_at_the_floor_there_is_nothing_shallower():
    v = analytics.evaluate(_agg(presses=250, shallow=50, shallow_bin=2), 30, False)
    assert v["kind"] == "floor"
    v = analytics.evaluate(_agg(presses=250, shallow=50, shallow_bin=2), 25, False)
    assert v["kind"] == "floor"


def test_barely_over_suggests_deeper_on_letters_only():
    a = _agg(presses=300, barely=60)                  # 20 %
    assert analytics.evaluate(a, 80, False) is None
    v = analytics.evaluate(a, 80, True)
    assert v["kind"] == "deeper" and v["target_raw"] == 90


def test_lots_of_barely_over_suggests_0_2_deeper():
    v = analytics.evaluate(_agg(presses=300, barely=90), 80, True)   # 30 %
    assert v["kind"] == "deeper" and v["target_raw"] == 100


def test_exactly_15_percent_barely_is_not_enough():
    assert analytics.evaluate(_agg(presses=300, barely=45), 80, True) is None


def test_deeper_is_clamped_to_3_40():
    v = analytics.evaluate(_agg(presses=300, barely=90), 335, True)
    assert v["kind"] == "deeper" and v["target_raw"] == 340
    assert analytics.evaluate(_agg(presses=300, barely=90), 340, True) is None


def test_shallow_and_barely_together_is_mixed():
    v = analytics.evaluate(_agg(presses=300, shallow=30, barely=60), 80, True)
    assert v["kind"] == "mixed"


def test_unrated_presses_do_not_count_toward_the_minimum():
    assert analytics.evaluate(_agg(presses=300, shallow=30, unrated=150), 80, False) is None


# --------------------------------------------------------------- suggest ----
ALL = list(IDX.values())


def _ready(act=80, mode=(0, 0.3, 0.3)):
    return {i: act for i in ALL}, {i: mode for i in ALL}


def _spread(codes, **kw):
    """Spread one aggregate's counts evenly over `codes` (integer parts)."""
    n = len(codes)
    out = {}
    for c in codes:
        out[IDX[c]] = _agg(**{k: v // n for k, v in kw.items()})
    return out


def test_group_suggestion_from_summed_counts_covers_its_members():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 12, shallow=22 * 2)   # 12 each: < 200
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    [s] = out["suggestions"]
    assert s["id"] == "group:letters" and s["scope"] == "group"
    assert s["group"] == "letters" and s["direction"] == "shallower"
    assert sorted(s["codes"]) == sorted(letters)
    assert s["current_mm"] == 0.80 and s["suggested_mm"] == 0.45   # p10 0.57
    assert s["mode"] == 0 and s["rt_press_mm"] is None and s["rt_release_mm"] is None
    assert s["presses"] == 264 and s["shallow"] == 44
    assert "did not type" in s["detail"] and "0.80 → 0.45" in s["title"]


def test_per_key_suggestion_when_the_group_is_fine():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 300)
    rated[IDX["Q"]] = _agg(presses=300, barely=60)
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    [s] = out["suggestions"]
    assert s["id"] == "key:Q" and s["scope"] == "key" and s["group"] is None
    assert s["codes"] == ["Q"] and s["direction"] == "deeper"
    assert s["suggested_mm"] == 0.90


def test_no_key_gets_two_suggestions():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 300, shallow=22 * 30)
    rated[IDX["Q"]] = _agg(presses=300, barely=200)       # alone: deeper
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    codes = [c for s in out["suggestions"] for c in s["codes"]]
    assert len(codes) == len(set(codes))
    assert [s["id"] for s in out["suggestions"]] == ["group:letters"]


def test_wasd_never_gets_a_deeper_suggestion():
    rated = _spread(analytics.WASD, presses=4 * 300, barely=4 * 150)
    act, trig = _ready()
    assert analytics.suggest(rated, act, trig, IDX)["suggestions"] == []


def test_mixed_group_actuation_falls_back_to_per_key():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 12, shallow=22 * 2)
    rated[IDX["E"]] = _agg(presses=300, shallow=30)
    act, trig = _ready()
    act[IDX["Q"]] = 120                                    # group not uniform
    out = analytics.suggest(rated, act, trig, IDX)
    assert [s["id"] for s in out["suggestions"]] == ["key:E"]


def test_different_trigger_modes_split_the_group():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 12, shallow=22 * 2)
    act, trig = _ready()
    trig[IDX["Q"]] = (13, 0.3, 0.3)
    assert analytics.suggest(rated, act, trig, IDX)["suggestions"] == []


def test_fixed_mode_ignores_the_stored_rt_pair_when_grouping():
    letters = analytics.GROUPS[1][2]
    rated = _spread(letters, presses=22 * 12, shallow=22 * 2)
    act, trig = _ready()
    trig[IDX["Q"]] = (0, 0.1, 0.9)
    [s] = analytics.suggest(rated, act, trig, IDX)["suggestions"]
    assert s["id"] == "group:letters"


def test_rapid_trigger_keys_keep_their_mode_and_pair():
    rated = {IDX["Space"]: _agg(presses=300, shallow=30)}
    act, trig = _ready(mode=(13, 0.15, 0.2))
    [s] = analytics.suggest(rated, act, trig, IDX)["suggestions"]
    assert s["id"] == "group:space"
    assert (s["mode"], s["rt_press_mm"], s["rt_release_mm"]) == (13, 0.15, 0.2)


def test_keys_without_a_read_back_get_nothing():
    rated = {IDX["Space"]: _agg(presses=300, shallow=30)}
    act, trig = _ready()
    del trig[IDX["Space"]]
    assert analytics.suggest(rated, act, trig, IDX)["suggestions"] == []
    act, trig = _ready()
    del act[IDX["Space"]]
    assert analytics.suggest(rated, act, trig, IDX)["suggestions"] == []


def test_other_keys_are_judged_per_key_and_sorted_by_affected_presses():
    rated = {IDX["Enter"]: _agg(presses=300, shallow=20),
             IDX["1"]: _agg(presses=300, shallow=40)}
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    assert [s["id"] for s in out["suggestions"]] == ["key:1", "key:Enter"]
    assert out["suggestions"][0]["label"] == "1"


def test_notes_explain_waiting_floor_and_mixed():
    act, trig = _ready()
    rated = {IDX["Space"]: _agg(presses=120)}
    notes = {n["id"]: n for n in analytics.suggest(rated, act, trig, IDX)["notes"]}
    assert notes["note:space"]["kind"] == "data"
    assert "120 of 200" in notes["note:space"]["text"]
    assert notes["note:letters"]["kind"] == "data"

    act, trig = _ready(act=30)
    rated = {IDX["Space"]: _agg(presses=250, shallow=50, shallow_bin=2)}
    notes = {n["id"]: n for n in analytics.suggest(rated, act, trig, IDX)["notes"]}
    assert notes["note:space"]["kind"] == "floor" and "0.30 mm" in notes["note:space"]["text"]

    act, trig = _ready()
    rated = _spread(analytics.GROUPS[1][2], presses=22 * 300, shallow=22 * 30,
                    barely=22 * 60)
    out = analytics.suggest(rated, act, trig, IDX)
    assert out["suggestions"] == []
    notes = {n["id"]: n for n in out["notes"]}
    assert notes["note:letters"]["kind"] == "mixed"


def test_suggested_values_respect_the_hard_limits():
    act, trig = _ready()
    for a in (8, 30, 80, 200, 335, 340):
        for agg in (_agg(presses=300, shallow=90, shallow_bin=1),
                    _agg(presses=300, barely=100)):
            v = analytics.evaluate(agg, a, True)
            if v and "target_raw" in v:
                assert analytics.MIN_RAW <= v["target_raw"] <= analytics.MAX_RAW
                assert v["target_raw"] >= analytics.FLOOR_RAW


def test_output_is_aggregates_only():
    rated = {IDX["Space"]: _agg(presses=300, shallow=30)}
    act, trig = _ready()
    out = analytics.suggest(rated, act, trig, IDX)
    allowed = {"id", "scope", "group", "label", "codes", "direction",
               "current_mm", "suggested_mm", "mode", "rt_press_mm",
               "rt_release_mm", "presses", "attempts", "shallow", "barely",
               "shallow_pct", "barely_pct", "p10_mm", "score", "title", "detail"}
    for s in out["suggestions"]:
        assert set(s) == allowed
```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_tune.py`
Expected: `25 failed` (`AttributeError: module 'analytics' has no attribute 'evaluate'` / `'suggest'`).

- [ ] **Step 3: Append to `analytics.py`** (after `summarize`, separated by two blank lines):

```python
def trig_norm(t):
    """Read-back trigger tuple (mode, rt press, rt release) -> the part an
    actuation write must keep; None when unknown. Fixed mode ignores RT."""
    if not t:
        return None
    mode = int(t[0])
    return (0, None, None) if mode == 0 else (mode, t[1], t[2])


def evaluate(agg, act_raw, deeper_ok):
    """Verdict for one aggregate recorded at ``act_raw`` (0.01 mm), or None
    when there is too little data or nothing to suggest. ``kind`` is
    "shallower" / "deeper" (with ``target_raw``), "floor" or "mixed"."""
    rated = agg["presses"] - agg["unrated"]
    if rated < MIN_PRESSES:
        return None
    attempts = rated + agg["shallow"]
    s_rate = agg["shallow"] / attempts
    b_rate = agg["barely"] / rated
    base = {"current_raw": act_raw, "presses": rated, "attempts": attempts,
            "shallow": agg["shallow"], "barely": agg["barely"],
            "shallow_pct": round(100 * s_rate, 1),
            "barely_pct": round(100 * b_rate, 1),
            "p10_mm": telemetry.peak_percentile(agg["hist"], P_QUANTILE)}
    want_shallow = s_rate > SHALLOW_RATE
    want_deeper = deeper_ok and b_rate > BARELY_RATE
    if want_shallow and want_deeper:
        return dict(base, kind="mixed")
    if want_shallow:
        cand = act_raw - STEP_RAW
        if base["p10_mm"] is not None:
            cand = min(cand, int(round(base["p10_mm"] * 100)) - MARGIN_RAW)
        cand = (cand // STEP_RAW) * STEP_RAW
        cand = max(FLOOR_RAW, MIN_RAW, min(MAX_RAW, cand))
        if cand >= act_raw:
            return dict(base, kind="floor")
        return dict(base, kind="shallower", target_raw=cand)
    if want_deeper:
        step = DEEPER_STRONG_RAW if b_rate > BARELY_STRONG_RATE else DEEPER_RAW
        cand = max(FLOOR_RAW, min(MAX_RAW, act_raw + step))
        if cand <= act_raw:
            return None
        return dict(base, kind="deeper", target_raw=cand)
    return None


def _mm(raw):
    return round(raw / 100.0, 2)


def _suggestion(scope, sid, label, codes, v, trig):
    cur, new = _mm(v["current_raw"]), _mm(v["target_raw"])
    these = "these keys" if len(codes) > 1 else "this key"
    if v["kind"] == "shallower":
        title = f"{label}: actuate earlier, {cur:.2f} → {new:.2f} mm"
        detail = (f"{v['shallow_pct']:.1f}% of your presses on {these} stopped "
                  f"before {cur:.2f} mm and did not type. 9 in 10 of your "
                  f"presses reach {v['p10_mm']:.2f} mm or deeper, so {new:.2f} mm "
                  f"should catch most of the missed ones.")
        score = v["shallow"]
    else:
        title = f"{label}: actuate later, {cur:.2f} → {new:.2f} mm"
        detail = (f"{v['barely_pct']:.1f}% of the presses that typed on {these} "
                  f"went less than 0.10 mm past {cur:.2f} mm. Presses that light "
                  f"are often a resting or brushing finger, so {new:.2f} mm "
                  f"leaves a little more room before a key types.")
        score = v["barely"]
    mode, rtp, rtr = trig
    return {"id": f"{scope}:{sid}", "scope": scope,
            "group": sid if scope == "group" else None, "label": label,
            "codes": list(codes), "direction": v["kind"],
            "current_mm": cur, "suggested_mm": new,
            "mode": mode, "rt_press_mm": rtp, "rt_release_mm": rtr,
            "presses": v["presses"], "attempts": v["attempts"],
            "shallow": v["shallow"], "barely": v["barely"],
            "shallow_pct": v["shallow_pct"], "barely_pct": v["barely_pct"],
            "p10_mm": v["p10_mm"], "score": score,
            "title": title, "detail": detail}


def _note(kind, gid, label, v=None, presses=0):
    if kind == "data":
        text = (f"{label}: {presses} of {MIN_PRESSES} presses recorded at the "
                f"current actuation. Suggestions start at {MIN_PRESSES}.")
    elif kind == "floor":
        text = (f"{label}: {v['shallow_pct']:.1f}% of presses stopped short, but "
                f"{_mm(v['current_raw']):.2f} mm is already at the 0.30 mm "
                f"minimum Aether suggests, so there is nothing shallower to offer.")
    else:
        text = (f"{label}: presses bunch up right at {_mm(v['current_raw']):.2f} mm "
                f"({v['shallow_pct']:.1f}% stopped short, {v['barely_pct']:.1f}% "
                f"only just typed). Moving the point either way would make one of "
                f"those worse, so no change is suggested.")
    return {"id": f"note:{gid}", "kind": kind, "group": gid, "label": label,
            "text": text}


def suggest(rated, act_by_idx, trig_by_idx, index_of_code):
    """Auto-tune suggestions.

    rated:        idx -> agg recorded at the key's current actuation (rated_at)
    act_by_idx:   idx -> current read-back actuation, 0.01 mm
    trig_by_idx:  idx -> read-back (mode, rt press mm, rt release mm)
    index_of_code: design code -> idx (KeyMap.index_of_code)

    A key is "ready" only with both a read-back actuation and trigger mode.
    A group is judged on its summed counters when every member is ready and
    they all share one actuation and one trigger setting; a group suggestion
    covers its members, so no key ever gets two (or opposite) suggestions.
    Every key not covered is then judged on its own counters. Returns
    {"suggestions": [...] most-affected-presses first, "notes": [...]}."""
    code_of = {i: c for c, i in index_of_code.items()}
    suggestions, notes, covered = [], [], set()

    def ready(i):
        return i in act_by_idx and trig_norm(trig_by_idx.get(i)) is not None

    for gid, label, codes, deeper_ok in GROUPS:
        members = [index_of_code[c] for c in codes if c in index_of_code]
        if not members or not all(ready(i) for i in members):
            continue
        acts = {act_by_idx[i] for i in members}
        trigs = {trig_norm(trig_by_idx[i]) for i in members}
        if len(acts) != 1 or len(trigs) != 1:
            continue
        agg = telemetry.empty_agg()
        for i in members:
            if i in rated:
                telemetry.merge_agg(agg, rated[i])
        v = evaluate(agg, acts.pop(), deeper_ok)
        if v is None:
            n = agg["presses"] - agg["unrated"]
            if n < MIN_PRESSES:
                notes.append(_note("data", gid, label, presses=n))
        elif v["kind"] in ("shallower", "deeper"):
            suggestions.append(_suggestion("group", gid, label,
                                           [code_of[i] for i in members],
                                           v, trigs.pop()))
            covered.update(members)
        else:
            notes.append(_note(v["kind"], gid, label, v))
    for idx in sorted(code_of):
        code = code_of[idx]
        if idx in covered or not ready(idx) or idx not in rated:
            continue
        v = evaluate(rated[idx], act_by_idx[idx], code in DEEPER_CODES)
        if v is not None and v["kind"] in ("shallower", "deeper"):
            suggestions.append(_suggestion("key", code, key_label(code), [code],
                                           v, trig_norm(trig_by_idx[idx])))
    suggestions.sort(key=lambda s: (-s["score"], s["id"]))
    return {"suggestions": suggestions, "notes": notes}
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_views.py tests/test_analytics_tune.py`
Expected: `32 passed`.

- [ ] **Step 5: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `962 passed, 13 skipped`.

```bash
git add analytics.py tests/test_analytics_tune.py
git commit -m "feat(analytics): actuation auto-tune suggestions (per key and group, never automatic)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Bridge `get_analytics` / `get_tune_suggestions`

**Files:**
- Modify: `app_web.py`, `flatpak/io.github.mrwhosnexus.AetherHE.yml`
- Test: `tests/test_analytics_api.py` (create)

**Interfaces:**
- Consumes: `Telemetry.recent_buckets`, `Telemetry.actuation`, `Api._trig_mode`, `Api.km.index_of_code`, `Api._stats_supported`, `_clamp_stats_days`, `Api._STATS_UNAVAILABLE`, `Api._fail`.
- Produces (bridge): `get_analytics(days=14) -> {ok, enabled, supported, board, days, keys{code: summary+heat}, totals, daily[14]}`; `get_tune_suggestions() -> {ok, enabled, supported, min_presses, window_days, read_back, suggestions[], notes[]}`. Both read-only.

- [ ] **Step 1: Write the failing tests** — `tests/test_analytics_api.py`:

```python
"""Phase 4 bridge: get_analytics / get_tune_suggestions over real Telemetry
day buckets, actuation + trigger mode from the (faked) read-back. Applying a
suggestion is the existing set_trigger_codes + verify_actuation path; the
fake driver only records calls. No HID, no keyboard."""
import json

import analytics
import telemetry
from test_stats_api import _api, TODAY
from test_telemetry import _press


def _read_back(a, mm=0.80, mode=0, codes=None, rt=(0.3, 0.3)):
    """Fake firmware read-back of every key (or `codes`) at `mm`."""
    names = {a.km.by_index[i]["name"]: i for i in a.km.indices()}
    want = set(a.km.indices_for_codes(codes)) if codes else set(names.values())
    a.driver.detail = {n: {"travel_mm": mm, "mode": mode,
                           "rt_press_mm": rt[0], "rt_release_mm": rt[1]}
                       for n, i in names.items() if i in want}
    assert a.verify_actuation([])["ok"]


def _type(a, code, n, depths, t0=0.0):
    t = t0
    for _ in range(n):
        t = _press(a.telemetry, a.km.index_of_code[code], depths, t0=t)
    return t


# ---------------------------------------------------------- get_analytics ----
def test_get_analytics_per_code_views_and_daily_series(tmp_path):
    a = _api(tmp_path)
    t = _type(a, "W", 3, [1.0, 3.35])
    _type(a, "Q", 1, [1.0, 2.0], t0=t)
    r = a.get_analytics(7)
    assert r["ok"] and r["enabled"] and r["supported"]
    assert r["days"] == 7 and r["board"] == "aula-win60-he"
    w = r["keys"]["W"]
    assert w["presses"] == 3 and w["bottom"] == 3 and w["bottom_pct"] == 100.0
    assert w["heat"] == 1.0 and r["keys"]["Q"]["heat"] == 0.333
    assert w["avg_peak_mm"] == 3.35
    assert r["totals"]["presses"] == 4
    assert len(r["daily"]) == 14 and r["daily"][-1]["date"] == TODAY
    assert r["daily"][-1]["presses"] == 4


def test_get_analytics_merges_actuation_buckets(tmp_path):
    a = _api(tmp_path)
    t = _type(a, "W", 2, [2.0])
    _read_back(a, 0.80)
    _type(a, "W", 3, [2.0], t0=t)
    assert a.get_analytics(1)["keys"]["W"]["presses"] == 5


def test_get_analytics_clamps_days_and_never_raises(tmp_path):
    a = _api(tmp_path)
    assert a.get_analytics(0)["days"] == 1
    assert a.get_analytics(5000)["days"] == 90
    assert a.get_analytics("x")["days"] == 1
    a.telemetry.recent_buckets = None                    # boom
    r = a.get_analytics(1)
    assert r["ok"] is False and r["error"]


def test_get_analytics_output_is_aggregates_only(tmp_path):
    a = _api(tmp_path)
    _type(a, "W", 2, [1.0, 2.0])
    r = a.get_analytics(1)
    assert set(r) == {"ok", "enabled", "supported", "board", "days", "keys",
                      "totals", "daily"}
    for rec in r["keys"].values():
        assert set(rec) == {"presses", "shallow", "barely", "bottom",
                            "unrated", "attempts", "bottom_pct", "shallow_pct",
                            "barely_pct", "avg_peak_mm", "avg_ttp_ms", "heat"}
    for row in r["daily"]:
        assert set(row) == {"date", "presses", "shallow", "bottom"}
    json.dumps(r)                                        # bridge-serialisable


# --------------------------------------------------- get_tune_suggestions ----
def test_no_read_back_means_no_suggestions(tmp_path):
    a = _api(tmp_path)
    _type(a, "Space", 300, [2.0])
    r = a.get_tune_suggestions()
    assert r["ok"] and r["suggestions"] == [] and r["read_back"] is False
    assert r["min_presses"] == 200 and r["window_days"] == 14


def test_shallow_space_presses_produce_a_suggestion(tmp_path):
    a = _api(tmp_path)
    _read_back(a, 0.80)
    t = _type(a, "Space", 270, [1.0, 3.0])
    _type(a, "Space", 30, [0.30, 0.55], t0=t)
    r = a.get_tune_suggestions()
    assert r["read_back"] is True
    [s] = r["suggestions"]
    assert s["id"] == "group:space" and s["codes"] == ["Space"]
    assert s["direction"] == "shallower"
    assert s["current_mm"] == 0.80 and s["suggested_mm"] == 0.50
    assert s["mode"] == 0
    json.dumps(r)


def test_presses_at_an_old_actuation_do_not_count(tmp_path):
    a = _api(tmp_path)
    _read_back(a, 1.20)
    t = _type(a, "Space", 270, [1.5, 3.0])
    t = _type(a, "Space", 30, [0.30, 0.55], t0=t)
    _read_back(a, 0.80)                                  # user changed it
    _type(a, "Space", 50, [1.5, 3.0], t0=t)
    r = a.get_tune_suggestions()
    assert r["suggestions"] == []
    [n] = [n for n in r["notes"] if n["id"] == "note:space"]
    assert n["kind"] == "data" and "50 of 200" in n["text"]


def test_presses_between_a_write_and_its_read_back_are_ignored(tmp_path):
    a = _api(tmp_path)
    _read_back(a, 0.80)
    assert a.set_trigger_codes(["Space"], 0.50)["ok"]   # fake driver: no HID
    _type(a, "Space", 300, [0.30, 0.45])                 # unrated
    _read_back(a, 0.50)
    assert a.get_tune_suggestions()["suggestions"] == []


def test_rapid_trigger_mode_and_pair_come_from_the_read_back(tmp_path):
    a = _api(tmp_path)
    _read_back(a, 0.80, mode=13, rt=(0.15, 0.25))
    t = _type(a, "Space", 270, [1.0, 3.0])
    _type(a, "Space", 30, [0.30, 0.55], t0=t)
    [s] = a.get_tune_suggestions()["suggestions"]
    assert (s["mode"], s["rt_press_mm"], s["rt_release_mm"]) == (13, 0.15, 0.25)


def test_applying_a_suggestion_is_the_normal_write_plus_read_back(tmp_path):
    a = _api(tmp_path)
    writes = []
    a.driver.set_actuation = lambda idxs, mode, travel, i1, i2: writes.append(
        (sorted(idxs), mode, round(travel, 2), i1, i2))
    _read_back(a, 0.80)
    t = _type(a, "Space", 270, [1.0, 3.0])
    _type(a, "Space", 30, [0.30, 0.55], t0=t)
    [s] = a.get_tune_suggestions()["suggestions"]
    # what the UI's writeActuation does: set_trigger_codes, then read back
    r = a.set_trigger_codes(s["codes"], s["suggested_mm"],
                            s["rt_press_mm"] or 0, s["rt_release_mm"] or 0,
                            s["mode"])
    assert r["ok"]
    assert writes == [([a.km.index_of_code["Space"]], 0, 0.50, None, None)]
    _read_back(a, 0.50)
    assert a.get_tune_suggestions()["suggestions"] == []   # new bucket: 0 presses


def test_unsupported_board_gets_an_empty_ok_answer(tmp_path):
    a = _api(tmp_path, slug="aula-mini60he-pro")
    r = a.get_tune_suggestions()
    assert r["ok"] and r["supported"] is False and r["suggestions"] == []


def test_bridge_methods_without_telemetry_fail_softly(tmp_path):
    a = _api(tmp_path)
    a.telemetry = None
    for r in (a.get_analytics(1), a.get_tune_suggestions()):
        assert r["ok"] is False and r["error"]


def test_get_tune_suggestions_never_raises(tmp_path):
    a = _api(tmp_path)
    a.telemetry.actuation = None                         # boom
    r = a.get_tune_suggestions()
    assert r["ok"] is False and r["error"]


def test_get_tune_suggestions_never_writes(tmp_path):
    a = _api(tmp_path)
    calls = []
    a.driver.set_actuation = lambda *x, **k: calls.append(x)
    _read_back(a, 0.80)
    t = _type(a, "Space", 270, [1.0, 3.0])
    _type(a, "Space", 30, [0.30, 0.55], t0=t)
    assert a.get_tune_suggestions()["suggestions"]
    assert calls == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_api.py`
Expected: failures with `AttributeError: 'Api' object has no attribute 'get_analytics'` / `'get_tune_suggestions'`.

- [ ] **Step 3: Implement**

(a) `app_web.py` imports: after `import single_instance` add `import analytics`.

(b) In `class Api`, directly after the `set_stats_enabled` method and before `    # ---- connection ----`, insert:

```python
    # ---- typing analytics + auto-tune (Phase 4; aggregates only) ----
    def get_analytics(self, days=14):
        """Analytics views over the last `days` days (1..90): per design code
        presses / shallow / barely / bottom-out counts and percentages,
        average peak depth, heat 0..1; board totals; and presses per day for
        the last 14 days. Built from telemetry's per-key day aggregates only."""
        try:
            tel = getattr(self, "telemetry", None)
            if tel is None:
                return dict(self._STATS_UNAVAILABLE)
            days = _clamp_stats_days(days)
            km = getattr(self, "km", None)
            code_of = km.code_of if km else (lambda i: None)
            out = analytics.summarize(
                tel.recent_buckets(max(days, analytics.DAILY_DAYS)), code_of, days)
            out.update(ok=True, enabled=tel.enabled,
                       supported=self._stats_supported(), board=tel.board,
                       days=days)
            return out
        except Exception as e:
            return self._fail(e)

    def get_tune_suggestions(self):
        """Actuation auto-tune SUGGESTIONS (never writes anything). Uses only
        presses recorded at each key's current read-back actuation over the
        last analytics.TUNE_WINDOW_DAYS days. Applying one is the UI's normal
        Actuation Apply path (set_trigger_codes + verify_actuation)."""
        try:
            tel = getattr(self, "telemetry", None)
            km = getattr(self, "km", None)
            if tel is None or km is None:
                return dict(self._STATS_UNAVAILABLE)
            out = {"ok": True, "enabled": tel.enabled,
                   "supported": self._stats_supported(),
                   "min_presses": analytics.MIN_PRESSES,
                   "window_days": analytics.TUNE_WINDOW_DAYS,
                   "read_back": False, "suggestions": [], "notes": []}
            if not out["supported"]:
                return out
            act = tel.actuation()
            trig = dict(getattr(self, "_trig_mode", None) or {})
            out["read_back"] = bool(act) and bool(trig)
            days = [d for _, d in tel.recent_buckets(analytics.TUNE_WINDOW_DAYS)]
            out.update(analytics.suggest(analytics.rated_at(days, act), act,
                                         trig, km.index_of_code))
            return out
        except Exception as e:
            return self._fail(e)
```

(c) `flatpak/io.github.mrwhosnexus.AetherHE.yml`: in the `cp -r` list replace `telemetry.py games.py tools data ui` with `telemetry.py games.py analytics.py tools data ui`. (`AetherHE.spec` needs nothing: PyInstaller follows the import.)

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_api.py tests/test_packaging.py`
Expected: all pass (`14` in the new file).

- [ ] **Step 5: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `976 passed, 13 skipped`.

```bash
git add app_web.py flatpak/io.github.mrwhosnexus.AetherHE.yml tests/test_analytics_api.py
git commit -m "feat(api): get_analytics and get_tune_suggestions bridges (read-only)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Analytics workspace (`analytics.jsx`)

**Files:**
- Create: `ui/runtime_src/workspaces/analytics.jsx` (auto-discovered by `build_runtime.py`, compiled to `build/ws_analytics.js` before `app.js`)
- Test: `tests/test_analytics_ui_sources.py` (create; Task 6 appends to it)
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/ws_analytics.js`

**Interfaces:**
- Consumes (ctx): `apiCall`, `connected`, `applyTuneSuggestion` (Task 6; until then Apply simply does nothing because the tab is not reachable). `window.AetherKeyboard.{KeyboardPanel, KB_ROWS}`.
- Produces: `window.AetherWorkspaces.ANALYTICS_WIDGETS`; `window.AetherAnalytics` (decision 12).

- [ ] **Step 1: Write the failing tests** — `tests/test_analytics_ui_sources.py`:

```python
"""Phase 4 UI wiring (source checks; the UI has no JS test runner): the
Analytics workspace is registered and gated on keyStats, talks to the bridge
through ctx.apiCall only, applies suggestions through app.jsx's
writeActuation (set_trigger_codes + verify_actuation), and exports the
pieces the Phase 5 dashboard reuses."""
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


WS = _read("workspaces", "analytics.jsx")


def test_workspace_exports_widgets_and_reusable_pieces():
    assert "window.AetherWorkspaces.ANALYTICS_WIDGETS = ANALYTICS_WIDGETS" in WS
    for wid in ('id: "heatmap"', 'id: "overview"', 'id: "daily"', 'id: "tune"'):
        assert wid in WS
    m = re.search(r"window\.AetherAnalytics = \{(.*?)\};", WS, re.S)
    assert m, "window.AetherAnalytics export missing"
    names = {n.strip() for n in m.group(1).replace("\n", " ").split(",") if n.strip()}
    assert {"store", "useAnalytics", "refreshAnalytics", "refreshTune",
            "heatColor", "heatLedMap", "topSuggestions", "HeatmapBoard",
            "DailyBars", "SuggestionCard", "SuggestionList",
            "applySuggestion"} <= names


def test_workspace_uses_only_the_two_read_bridges():
    code = re.sub(r"/\*.*?\*/", "", WS, flags=re.S)    # comments may name them
    calls = set(re.findall(r'call\("([a-z_]+)"', code))
    assert calls == {"get_analytics", "get_tune_suggestions"}
    assert "pywebview" not in code                  # ctx.apiCall only
    assert "set_trigger_codes" not in code          # writes go through ctx


def test_no_raw_html_sinks_and_suggestions_only_copy():
    assert "dangerouslySetInnerHTML" not in WS and "innerHTML" not in WS
    assert "nothing is written until you click Apply" in WS


def test_built_workspace_is_current():
    built = os.path.join(SRC, "build", "ws_analytics.js")
    with open(built, encoding="utf-8") as fh:
        code = fh.read()
    assert "ANALYTICS_WIDGETS" in code and "AetherAnalytics" in code
    with open(os.path.join(HERE, "ui", "index_runtime.html"), encoding="utf-8") as fh:
        html = fh.read()
    assert "window.AetherAnalytics" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_built_workspace_parses():
    built = os.path.join(SRC, "build", "ws_analytics.js")
    subprocess.run(["node", "--check", built], check=True)

```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_ui_sources.py`
Expected: collection error (`FileNotFoundError` for `workspaces/analytics.jsx`).

- [ ] **Step 3: Create `ui/runtime_src/workspaces/analytics.jsx`** with exactly:

```jsx
(() => {
/* ============================================================
   Analytics workspace (roadmap Phase 4): typing analytics + actuation
   auto-tune, built from the per-key key-statistics aggregates (telemetry.py).
   Exports window.AetherWorkspaces.ANALYTICS_WIDGETS (widget descriptors
   { id, title, default:{x,y,w,h}, min:{w,h}, render:(ctx)=>JSX }) and
   window.AetherAnalytics (store, hooks and components the Phase 5 dashboard
   reuses: today's heatmap and the top-3 suggestions with Apply).

   Bridge (through ctx.apiCall only): get_analytics(days) and
   get_tune_suggestions(). Suggestions are NEVER written automatically: Apply
   is ctx.applyTuneSuggestion(s), which is app.jsx's writeActuation, the same
   set_trigger_codes + verify_actuation path as the Actuation Apply button.

   Privacy: everything shown here is a per-key counter. Aether never stores
   what was typed, in what order, or when.

   Capability gate: app.jsx hides the tab unless the board's registry flag
   keyStats is true (fail-open with no board data, like every gate).
   ============================================================ */
const { useState, useEffect } = React;
const KB = window.AetherKeyboard || {};
const KeyboardPanel = KB.KeyboardPanel;
const KB_ROWS = KB.KB_ROWS || [];

const LABEL_OF_CODE = {};
KB_ROWS.flat().forEach(([label, _u, code]) => { LABEL_OF_CODE[code] = label; });

const RANGES = [
  { days: 1, label: "Today" },
  { days: 7, label: "7 days" },
  { days: 14, label: "14 days" },
  { days: 30, label: "30 days" },
];
const POLL_MS = 5000;

/* ===== shared store (widget frames are separate components) ===== */
const store = {
  days: 1,
  analytics: null,     // get_analytics result
  tune: null,          // get_tune_suggestions result
  sel: new Set(),      // selected design codes on the heatmap
  applying: null,      // suggestion id being written
  lastApplied: null,   // {s, codes, prev_mm} for Undo
  status: null,        // {tone, msg}
  apiCall: null,
  users: 0,
  timer: null,
  inflight: false,
  again: false,        // a refresh was asked for while one was in flight
  listeners: new Set(),
};
const emit = () => store.listeners.forEach(fn => { try { fn(); } catch (e) {} });
const setStatus = (tone, msg) => {
  store.status = msg ? { tone, msg } : null;
  emit();
  if (msg) setTimeout(() => { if (store.status && store.status.msg === msg) { store.status = null; emit(); } }, 6000);
};

const refreshAnalytics = async (apiCall) => {
  const call = apiCall || store.apiCall;
  if (!call) return;
  if (store.inflight) { store.again = true; return; }
  store.inflight = true;
  try {
    const [a, t] = await Promise.all([call("get_analytics", store.days), call("get_tune_suggestions")]);
    if (a && a.ok) store.analytics = a;
    if (t && t.ok) store.tune = t;
    emit();
  } finally {
    store.inflight = false;
    if (store.again) { store.again = false; refreshAnalytics(call); }
  }
};
const refreshTune = async (apiCall) => {
  const call = apiCall || store.apiCall;
  if (!call) return;
  const t = await call("get_tune_suggestions");
  if (t && t.ok) { store.tune = t; emit(); }
};
const setDays = (days) => { store.days = days; emit(); refreshAnalytics(); };

/* Subscribe a component to the store. While at least one subscriber is
   mounted the store refreshes every POLL_MS (day files are live: pending
   presses are merged in, so no flush is needed). */
const useAnalytics = (apiCall) => {
  const [, force] = useState(0);
  useEffect(() => {
    const fn = () => force(n => n + 1);
    store.listeners.add(fn);
    if (apiCall) store.apiCall = apiCall;
    store.users += 1;
    if (store.users === 1) {
      refreshAnalytics(apiCall);
      store.timer = setInterval(() => refreshAnalytics(), POLL_MS);
    }
    return () => {
      store.listeners.delete(fn);
      store.users -= 1;
      if (store.users <= 0) { store.users = 0; clearInterval(store.timer); store.timer = null; }
    };
  }, []);
  return store;
};

/* ===== heat colours: deep teal -> cyan -> amber -> red ===== */
const HEAT_STOPS = [[0, [22, 50, 74]], [0.35, [31, 159, 180]], [0.7, [242, 184, 75]], [1, [255, 77, 94]]];
const hex2 = (v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0");
const heatColor = (t) => {
  if (!(t > 0)) return null;
  const x = Math.min(1, t);
  for (let i = 1; i < HEAT_STOPS.length; i++) {
    const [p1, c1] = HEAT_STOPS[i];
    const [p0, c0] = HEAT_STOPS[i - 1];
    if (x <= p1) {
      const f = (x - p0) / (p1 - p0);
      return "#" + [0, 1, 2].map(k => hex2(c0[k] + (c1[k] - c0[k]) * f)).join("");
    }
  }
  return "#ff4d5e";
};
/* get_analytics keys -> {code: "#rrggbb"} for KeyboardPanel's ledMap. */
const heatLedMap = (keys) => {
  const out = {};
  Object.entries(keys || {}).forEach(([code, k]) => {
    const c = heatColor(k && k.heat);
    if (c) out[code] = c;
  });
  return out;
};
const topSuggestions = (tune, n) => ((tune && Array.isArray(tune.suggestions)) ? tune.suggestions : []).slice(0, n || 3);

const fmtPct = (v) => (v == null ? "–" : `${v.toFixed(1)}%`);
const fmtMm = (v) => (v == null ? "–" : `${v.toFixed(2)} mm`);
const fmtInt = (v) => (v == null ? "–" : Number(v).toLocaleString());

/* ===== small shared bits ===== */
const Label = ({ children }) => (
  <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--text-faint)] mb-1.5">{children}</div>
);
const Note = ({ children, tone }) => (
  <div className={`text-[11px] leading-relaxed ${tone === "warn" ? "text-amber-300/90" : tone === "bad" ? "text-rose-300/90" : "text-[var(--text-dim)]"}`}>
    {children}
  </div>
);
const Btn = ({ children, onClick, disabled, variant = "ghost", title }) => (
  <button onClick={onClick} disabled={disabled} title={title}
    className={`px-3 h-8 text-[10.5px] rounded-md border font-display uppercase tracking-[0.16em] transition-all
                ${disabled
                  ? "border-[var(--line)] bg-white/[0.02] text-[var(--text-faint)] cursor-not-allowed"
                  : variant === "primary"
                    ? "border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25 shadow-[0_0_12px_var(--accent-glow)]"
                    : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] hover:text-[var(--text)]"}`}>
    {children}
  </button>
);
const Tile = ({ label, value, hint }) => (
  <div className="rounded-xl border border-[var(--line)] bg-white/[0.02] px-3 py-2 min-w-0" title={hint || ""}>
    <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-[var(--text-faint)] truncate">{label}</div>
    <div className="font-mono text-[16px] text-[var(--text)] mt-0.5 truncate">{value}</div>
  </div>
);
const StatusLine = () => {
  const st = store.status;
  return (
    <div className="h-4 text-[11px] font-mono tracking-[0.12em] truncate">
      {st && <span className={st.tone === "ok" ? "text-[var(--accent)]" : st.tone === "warn" ? "text-amber-300/90" : "text-rose-300/90"}>{st.msg}</span>}
    </div>
  );
};
/* Collection off / board without a travel stream: say so instead of zeros. */
const DataGate = ({ children }) => {
  const a = store.analytics;
  if (a && a.supported === false)
    return <Note tone="warn">Analytics need a board with a live travel stream (Aula Win60 HE).</Note>;
  if (a && a.enabled === false)
    return (
      <div className="flex flex-col gap-2">
        <Note tone="warn">Key statistics are off, so nothing new is being counted. Turn on "Collect key statistics" in Settings to fill these views.</Note>
        {children}
      </div>
    );
  return children;
};

/* ===== Heatmap ===== */
const HeatLegend = () => (
  <div className="flex flex-col items-end gap-1">
    <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]">more</span>
    <span className="w-2 h-24 rounded-full" style={{ background: "linear-gradient(to top, #16324a, #1f9fb4, #f2b84b, #ff4d5e)" }}/>
    <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]">fewer</span>
  </div>
);
/* Reusable board: colours each key by its share of presses. `keys` is
   get_analytics().keys. Selection is the Analytics store's unless given. */
const HeatmapBoard = ({ keys, selectedKeys, setSelectedKeys, leftSlot }) => {
  if (!KeyboardPanel) return <Note tone="bad">Keyboard view failed to load.</Note>;
  const sel = selectedKeys || store.sel;
  const setSel = setSelectedKeys || ((upd) => {
    store.sel = typeof upd === "function" ? upd(store.sel) : upd;
    emit();
  });
  return (
    <KeyboardPanel mode="lighting" layer="default" showPill={false}
      selectedKeys={sel} setSelectedKeys={setSel}
      ledMap={heatLedMap(keys)} leftSlot={leftSlot || null} rightSlot={<HeatLegend/>}/>
  );
};

function HeatmapWidget(ctx) {
  const s = useAnalytics(ctx.apiCall);
  const a = s.analytics;
  return (
    <div className="flex flex-col gap-3 h-full">
      <div className="flex items-center gap-2 flex-wrap">
        {RANGES.map(r => (
          <button key={r.days} onClick={() => setDays(r.days)}
            className={`px-3 h-7 rounded-lg font-display text-[11px] uppercase tracking-[0.16em] transition-all
                        ${s.days === r.days
                          ? "bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]"
                          : "text-[var(--text-dim)] hover:text-[var(--text)] border border-[var(--line)]"}`}>
            {r.label}
          </button>
        ))}
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)]">
          {a ? `${fmtInt(a.totals && a.totals.presses)} presses` : "loading…"}
        </span>
      </div>
      <DataGate>
        <HeatmapBoard keys={a && a.keys}/>
        <Note>Click a key to see its numbers in Overview; Ctrl-click to add keys. Colour = share of presses against the busiest key.</Note>
      </DataGate>
    </div>
  );
}

/* ===== Overview: board totals, or the selected keys summed ===== */
const sumKeys = (keys, codes) => {
  const t = { presses: 0, shallow: 0, barely: 0, bottom: 0, unrated: 0, attempts: 0, peakSum: 0, peakN: 0 };
  codes.forEach(c => {
    const k = keys[c];
    if (!k) return;
    t.presses += k.presses; t.shallow += k.shallow; t.barely += k.barely;
    t.bottom += k.bottom; t.unrated += k.unrated; t.attempts += k.attempts;
    if (k.avg_peak_mm != null) { t.peakSum += k.avg_peak_mm * k.attempts; t.peakN += k.attempts; }
  });
  const rated = Math.max(0, t.presses - t.unrated);
  const pct = (n, d) => (d > 0 ? (100 * n) / d : null);
  return {
    presses: t.presses, shallow: t.shallow, barely: t.barely,
    bottom_pct: pct(t.bottom, t.attempts),
    shallow_pct: pct(t.shallow, rated + t.shallow),
    barely_pct: pct(t.barely, rated),
    avg_peak_mm: t.peakN ? t.peakSum / t.peakN : null,
  };
};

function OverviewWidget(ctx) {
  const s = useAnalytics(ctx.apiCall);
  const a = s.analytics;
  const keys = (a && a.keys) || {};
  const codes = Array.from(s.sel);
  const view = codes.length ? sumKeys(keys, codes) : ((a && a.totals) || null);
  const name = codes.length === 0 ? "Whole board"
    : codes.length === 1 ? (LABEL_OF_CODE[codes[0]] || codes[0]) : `${codes.length} keys`;
  const range = (RANGES.find(r => r.days === s.days) || RANGES[0]).label;
  return (
    <div className="flex flex-col gap-3 h-full">
      <div className="flex items-baseline gap-2">
        <span className="font-title text-[18px] text-[var(--text)]">{name}</span>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)]">{range}</span>
        {codes.length > 0 && (
          <button onClick={() => { store.sel = new Set(); emit(); }}
            className="ml-auto font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)] hover:text-[var(--text)]">clear</button>
        )}
      </div>
      <DataGate>
        <div className="grid grid-cols-3 gap-2">
          <Tile label="Presses" value={fmtInt(view && view.presses)} hint="Presses that went past the actuation point and typed."/>
          <Tile label="Bottom-out" value={fmtPct(view && view.bottom_pct)} hint="Presses that reached 3.30 mm or deeper."/>
          <Tile label="Avg peak" value={fmtMm(view && view.avg_peak_mm)} hint="Average deepest point of a press, missed presses included."/>
          <Tile label="Shallow" value={view ? `${fmtInt(view.shallow)} · ${fmtPct(view.shallow_pct)}` : "–"} hint="Presses that stopped before the actuation point, so nothing typed."/>
          <Tile label="Barely over" value={view ? `${fmtInt(view.barely)} · ${fmtPct(view.barely_pct)}` : "–"} hint="Presses that typed but went less than 0.10 mm past the actuation point."/>
        </div>
        <Note>Shallow = the key moved more than 0.15 mm but stopped before its actuation point, so nothing typed. Barely over = it typed, but by less than 0.10 mm. Percentages count only presses recorded while Aether knew the key's actuation.</Note>
      </DataGate>
    </div>
  );
}

/* ===== Presses per day (14 days) ===== */
const DailyBars = ({ daily, height = 120 }) => {
  const rows = Array.isArray(daily) ? daily : [];
  const top = Math.max(1, ...rows.map(r => r.presses || 0));
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-end gap-1" style={{ height }}>
        {rows.map(r => (
          <div key={r.date} className="flex-1 h-full flex flex-col justify-end"
               title={`${r.date}: ${r.presses} presses, ${r.shallow} shallow, ${r.bottom} bottom-outs`}>
            <div className="w-full rounded-t-sm bg-[var(--accent)]/70"
                 style={{ height: `${Math.max(r.presses ? 2 : 0, (100 * r.presses) / top)}%` }}/>
          </div>
        ))}
      </div>
      <div className="flex justify-between font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]">
        <span>{rows.length ? rows[0].date.slice(5) : ""}</span>
        <span>today</span>
      </div>
    </div>
  );
};

function DailyWidget(ctx) {
  const s = useAnalytics(ctx.apiCall);
  const a = s.analytics;
  const daily = (a && a.daily) || [];
  const total = daily.reduce((n, r) => n + (r.presses || 0), 0);
  return (
    <div className="flex flex-col gap-3 h-full">
      <Label>Presses per day · last 14 days · {fmtInt(total)} total</Label>
      <DataGate>
        <DailyBars daily={daily}/>
      </DataGate>
    </div>
  );
}

/* ===== Auto-tune suggestions ===== */
const SuggestionCard = ({ s, onApply, disabled, busy }) => (
  <div className="rounded-xl border border-[var(--line)] bg-white/[0.02] p-3 flex flex-col gap-1.5">
    <div className="flex items-center gap-2">
      <span className={`font-mono text-[9px] uppercase tracking-[0.2em] px-1.5 py-0.5 rounded border
                        ${s.direction === "shallower" ? "border-[var(--accent)]/40 text-[var(--accent)]" : "border-amber-400/40 text-amber-300"}`}>
        {s.direction === "shallower" ? "earlier" : "later"}
      </span>
      <span className="text-[12.5px] text-[var(--text)] flex-1 min-w-0 truncate" title={s.title}>{s.title}</span>
      {onApply && (
        <Btn variant="primary" onClick={() => onApply(s)} disabled={disabled}
             title={`Write ${s.suggested_mm.toFixed(2)} mm to ${s.codes.length} key(s), then read it back`}>
          {busy ? "Applying…" : "Apply"}
        </Btn>
      )}
    </div>
    <Note>{s.detail}</Note>
    <div className="font-mono text-[10px] text-[var(--text-faint)]">
      {`${fmtInt(s.presses)} presses at ${s.current_mm.toFixed(2)} mm · ${s.codes.length} key${s.codes.length === 1 ? "" : "s"}`}
    </div>
  </div>
);

/* Apply through the normal Actuation Apply path (ctx.applyTuneSuggestion =
   app.jsx writeActuation: set_trigger_codes, then verify_actuation). */
const applySuggestion = async (ctx, s) => {
  if (!ctx || !ctx.applyTuneSuggestion || store.applying) return;
  store.applying = s.id; emit();
  try {
    const r = await ctx.applyTuneSuggestion(s);
    if (r && r.ok) {
      store.lastApplied = { s };
      setStatus("ok", `${s.label}: ${s.suggested_mm.toFixed(2)} mm written and read back`);
    } else {
      setStatus("bad", `Not applied: ${(r && r.error) || "no reply"}`);
    }
  } finally {
    store.applying = null;
    emit();
    refreshAnalytics(ctx.apiCall);
  }
};
const undoLast = async (ctx) => {
  const last = store.lastApplied;
  if (!last || !ctx || !ctx.applyTuneSuggestion || store.applying) return;
  const back = Object.assign({}, last.s, { id: last.s.id + ":undo", suggested_mm: last.s.current_mm });
  store.applying = back.id; emit();
  try {
    const r = await ctx.applyTuneSuggestion(back);
    if (r && r.ok) {
      store.lastApplied = null;
      setStatus("ok", `${last.s.label}: back to ${last.s.current_mm.toFixed(2)} mm`);
    } else {
      setStatus("bad", `Undo failed: ${(r && r.error) || "no reply"}`);
    }
  } finally {
    store.applying = null;
    emit();
    refreshAnalytics(ctx.apiCall);
  }
};

/* Reusable list: `limit` = 3 gives the Phase 5 dashboard's top-3. */
const SuggestionList = ({ ctx, limit }) => {
  const s = useAnalytics(ctx && ctx.apiCall);
  const t = s.tune;
  const list = topSuggestions(t, limit || 99);
  const connected = !!(ctx && ctx.connected);
  if (!t) return <Note>Loading…</Note>;
  if (t.supported === false) return <Note tone="warn">Auto-tune needs a board with a live travel stream.</Note>;
  if (!list.length)
    return (
      <Note>
        {!connected ? "Connect the keyboard: suggestions use the actuation read back from it."
          : !t.read_back ? "Waiting for the actuation read-back from the keyboard."
          : `No suggestions. Each key or group needs ${t.min_presses} presses at its current actuation in the last ${t.window_days} days.`}
      </Note>
    );
  return (
    <div className="flex flex-col gap-2">
      {list.map(x => (
        <SuggestionCard key={x.id} s={x} busy={s.applying === x.id}
          disabled={!connected || !!s.applying} onApply={(sg) => applySuggestion(ctx, sg)}/>
      ))}
    </div>
  );
};

function TuneWidget(ctx) {
  const s = useAnalytics(ctx.apiCall);
  const t = s.tune;
  const notes = (t && Array.isArray(t.notes)) ? t.notes : [];
  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      <Note>Suggestions only: nothing is written until you click Apply. Apply writes the new actuation to those keys and reads it back, like Apply in the Actuation tab. A game profile that switches in later sets every key to its own value.</Note>
      {s.lastApplied && (
        <div className="flex items-center gap-2 rounded-md border border-[var(--line)] bg-white/[0.02] px-2 py-1.5">
          <span className="text-[11px] text-[var(--text-dim)] flex-1 truncate">
            {`Applied: ${s.lastApplied.s.label} ${s.lastApplied.s.suggested_mm.toFixed(2)} mm (was ${s.lastApplied.s.current_mm.toFixed(2)} mm)`}
          </span>
          <Btn onClick={() => undoLast(ctx)} disabled={!ctx.connected || !!s.applying}>Undo</Btn>
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-3">
        <SuggestionList ctx={ctx}/>
        {notes.length > 0 && (
          <div>
            <Label>Notes</Label>
            <div className="flex flex-col gap-1">
              {notes.map(n => <Note key={n.id}>{n.text}</Note>)}
            </div>
          </div>
        )}
      </div>
      <StatusLine/>
    </div>
  );
}

const ANALYTICS_WIDGETS = [
  { id: "heatmap",  title: "Key Heatmap",     default: { x: 40,  y: 32,  w: 820, h: 400 }, min: { w: 560, h: 320 }, render: HeatmapWidget },
  { id: "overview", title: "Overview",        default: { x: 880, y: 32,  w: 380, h: 400 }, min: { w: 300, h: 300 }, render: OverviewWidget },
  { id: "daily",    title: "Presses per Day", default: { x: 40,  y: 456, w: 520, h: 240 }, min: { w: 340, h: 200 }, render: DailyWidget },
  { id: "tune",     title: "Auto-tune",       default: { x: 580, y: 456, w: 680, h: 420 }, min: { w: 420, h: 300 }, render: TuneWidget },
];

window.AetherWorkspaces = window.AetherWorkspaces || {};
window.AetherWorkspaces.ANALYTICS_WIDGETS = ANALYTICS_WIDGETS;
window.AetherAnalytics = {
  store, useAnalytics, refreshAnalytics, refreshTune, setDays,
  heatColor, heatLedMap, topSuggestions,
  HeatmapBoard, DailyBars, SuggestionCard, SuggestionList, applySuggestion,
};
})();
```

- [ ] **Step 4: Build and check**

Run: `<py> ui\runtime_src\build_runtime.py`
Expected: ends with `Wrote ...\ui\index_runtime.html`.
Run: `node --check ui/runtime_src/build/ws_analytics.js` -> no output, exit 0.
Run: `git diff --ignore-cr-at-eol --stat` -> only `ui/index_runtime.html` changed among tracked build outputs; `git status --short` shows `?? ui/runtime_src/build/ws_analytics.js`. `git checkout --` every other `ui/runtime_src/build/*.js` that `git status` lists as modified (line endings only).
Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_ui_sources.py tests/test_ui_sources.py`
Expected: all pass (`5` in the new file; the node test skips only without node).

- [ ] **Step 5: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `981 passed, 13 skipped`.

```bash
git add ui/runtime_src/workspaces/analytics.jsx ui/runtime_src/build/ws_analytics.js ui/index_runtime.html tests/test_analytics_ui_sources.py
git commit -m "feat(ui): Analytics workspace (heatmap, overview, presses per day, auto-tune)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Wire the tab and the Apply path (`app.jsx`, `desktop.jsx`)

**Files:**
- Modify: `ui/runtime_src/src/app.jsx`, `ui/runtime_src/src/desktop.jsx`, `tests/test_analytics_ui_sources.py` (append)
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/app.js`, `ui/runtime_src/build/desktop.js`

**Interfaces:**
- Produces (ctx): `writeActuation(codes, travel, mode, rtP, rtR) -> Promise<{ok, readback?...}>`, `applyTuneSuggestion(s) -> Promise<...>`; section id `"analytics"` gated by `keyStats`.

- [ ] **Step 1: Append the failing tests** to `tests/test_analytics_ui_sources.py`:

```python
# ---- Task 6: app.jsx / desktop.jsx wiring --------------------------------
APP = _read("src", "app.jsx")
DESK = _read("src", "desktop.jsx")


def test_apply_goes_through_the_normal_actuation_path():
    assert "ctx.applyTuneSuggestion(" in WS
    body = APP[APP.index("const writeActuation"):APP.index("const applyDeadband")]
    assert 'apiCall("set_trigger_codes", codes, travel' in body
    assert 'apiCall("verify_actuation", codes)' in body
    assert "const applyActuation = () =>\n    writeActuation(" in body
    assert "writeActuation(s.codes, s.suggested_mm, s.mode || 0" in body
    assert "writeActuation, applyTuneSuggestion," in APP


def test_tab_is_registered_and_gated_on_key_stats():
    assert 'analytics: wsArr("ANALYTICS_WIDGETS", "Analytics")' in APP
    assert 'const SECTION_CAPS = { macros: "macros", analytics: "keyStats" };' in APP
    assert '{ id: "analytics", label: "Analytics", icon: IActivity }' in DESK
    assert "IActivity = I.IActivity" in DESK


def test_built_page_carries_the_gated_tab():
    with open(os.path.join(HERE, "ui", "index_runtime.html"), encoding="utf-8") as fh:
        html = fh.read()
    assert 'analytics: "keyStats"' in html
    assert "applyTuneSuggestion" in html
```

- [ ] **Step 2: Run them to see them fail**

Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_ui_sources.py`
Expected: the 3 new tests fail (`ValueError: substring not found` for `const writeActuation`, assertion errors).

- [ ] **Step 3: Edit `ui/runtime_src/src/app.jsx`** (exact replacements)

(a) In `const WIDGETS = {`, after the `macros:` line add:

```jsx
  analytics: wsArr("ANALYTICS_WIDGETS", "Analytics"),
```

(b) Replace

```jsx
// Macros section they cannot drive.
const SECTION_CAPS = { macros: "macros" };
```

with

```jsx
// Macros section they cannot drive. Analytics needs the host-side key
// statistics (keyStats: a board with a live travel stream).
const SECTION_CAPS = { macros: "macros", analytics: "keyStats" };
```

(c) Replace the head of `applyActuation`:

```jsx
  const applyActuation = async () => {
    if (!connected) return { ok: false, error: "not connected" };
    const codes = Array.from(selectedKeys);
    if (codes.length === 0) return { ok: false, error: "no keys selected" };
    const mode = rtEnabled ? 13 : 0;
    const r = await apiCall("set_trigger_codes", codes, actuation,
                            rtEnabled ? rtPress : 0, rtEnabled ? rtRelease : 0, mode);
```

with

```jsx
  //
  // writeActuation is that one path (write, then firmware read-back) for
  // every caller: the Actuation Apply button and Analytics' "Apply
  // suggestion" (roadmap Phase 4), which passes the key's own trigger mode
  // and RT pair so a rapid-trigger key stays rapid-trigger.
  const writeActuation = async (codes, travel, mode, rtP, rtR) => {
    if (!connected) return { ok: false, error: "not connected" };
    if (!codes || codes.length === 0) return { ok: false, error: "no keys selected" };
    const r = await apiCall("set_trigger_codes", codes, travel,
                            mode ? rtP : 0, mode ? rtR : 0, mode);
```

(d) In the same function body replace

```jsx
      const off = codes.filter(c => v.actuation_mm[c] != null && Math.abs(v.actuation_mm[c] - actuation) > 0.006);
```

with

```jsx
      const off = codes.filter(c => v.actuation_mm[c] != null && Math.abs(v.actuation_mm[c] - travel) > 0.006);
```

(e) Replace the end of that function

```jsx
    pushNotice("Actuation written, but the read-back failed: the board view may be stale", { label: "Check" });
    return { ...r, readback: null };
  };
```

with

```jsx
    pushNotice("Actuation written, but the read-back failed: the board view may be stale", { label: "Check" });
    return { ...r, readback: null };
  };
  const applyActuation = () =>
    writeActuation(Array.from(selectedKeys), actuation, rtEnabled ? 13 : 0, rtPress, rtRelease);
  // Analytics auto-tune: an explicit click only, never automatic.
  const applyTuneSuggestion = (s) => {
    if (!s || !Array.isArray(s.codes) || typeof s.suggested_mm !== "number")
      return Promise.resolve({ ok: false, error: "no suggestion" });
    return writeActuation(s.codes, s.suggested_mm, s.mode || 0,
                          s.rt_press_mm || 0, s.rt_release_mm || 0);
  };
```

(f) In `const ctx = {`, replace

```jsx
    applyActuation, applyDeadband, refreshPerKeyActuation, perKeyActuation, perKeyTrigger,
```

with

```jsx
    applyActuation, applyDeadband, refreshPerKeyActuation, perKeyActuation, perKeyTrigger,
    writeActuation, applyTuneSuggestion,
```

- [ ] **Step 4: Edit `ui/runtime_src/src/desktop.jsx`**

(a) Replace `      ILayers = I.ILayers;` with `      ILayers = I.ILayers, IActivity = I.IActivity;`.

(b) Replace the comment lines

```jsx
   Sections: keymap, macros, lighting, actuation, socd, gamepad, settings.
   (app.jsx filters this list per board — "macros" is capability-gated.)
```

with

```jsx
   Sections: keymap, macros, lighting, actuation, analytics, socd, gamepad,
   settings. (app.jsx filters this list per board — "macros" and
   "analytics" are capability-gated.)
```

(c) In `SECTION_DEFS`, after the `actuation` entry add:

```jsx
  { id: "analytics", label: "Analytics", icon: IActivity },
```

- [ ] **Step 5: Build and check**

Run: `<py> ui\runtime_src\build_runtime.py`, then `node --check ui/runtime_src/build/app.js` and `node --check ui/runtime_src/build/desktop.js` (both silent).
Run: `git diff --ignore-cr-at-eol --stat` -> exactly `ui/index_runtime.html`, `ui/runtime_src/build/app.js`, `ui/runtime_src/build/desktop.js`, `ui/runtime_src/src/app.jsx`, `ui/runtime_src/src/desktop.jsx` (+ the test file). `git checkout --` any other build file shown by `git status`.
Run: `<py> -m pytest -q -p no:cacheprovider tests/test_analytics_ui_sources.py tests/test_ui_sources.py tests/test_games_ui_sources.py tests/test_pressure_ui_sources.py`
Expected: all pass (`8` in the analytics file).

- [ ] **Step 6: Full suite and commit**

Run: `<py> -m pytest -q -p no:cacheprovider` -> `984 passed, 13 skipped`.

```bash
git add ui/runtime_src/src/app.jsx ui/runtime_src/src/desktop.jsx ui/runtime_src/build/app.js ui/runtime_src/build/desktop.js ui/index_runtime.html tests/test_analytics_ui_sources.py
git commit -m "feat(ui): Analytics tab gated on keyStats; Apply suggestion uses the Actuation write + read-back path" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Docs, full suite, status

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/roadmap-status.md` (append)

- [ ] **Step 1: CLAUDE.md**

(a) Append to the `telemetry.py` Architecture bullet: ` Each press is filed under the actuation its key had (day-file key "idx@act", "idx" = unknown); load_day/aggregate merge them, load_day_buckets/recent_buckets keep them apart.`

(b) Add an Architecture bullet right after it:

```text
- `analytics.py` — typing analytics + actuation auto-tune (roadmap Phase 4), pure functions over telemetry buckets. Bridge `get_analytics(days)` / `get_tune_suggestions()` (read-only). Suggestions use ONLY presses at each key's current read-back actuation (14 days, >= 200 presses per key or group; groups WASD / letters / mods / space by design code), shallow > 5 % -> p10 - 0.1 mm (>= 0.30), barely > 15 % on letters (not WASD) -> +0.1/0.2 mm. Never written automatically: the Analytics tab's Apply is app.jsx `writeActuation` (set_trigger_codes + verify_actuation). UI: `ui/runtime_src/workspaces/analytics.jsx` (tab gated on registry `keyStats`), reusable pieces on `window.AetherAnalytics`.
```

- [ ] **Step 2: Full suite**

Run: `<py> -m pytest -q -p no:cacheprovider`
Expected: `984 passed, 13 skipped` (919 + 11 + 7 + 25 + 14 + 5 + 3), zero failures.

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: record typing analytics and auto-tune in the architecture notes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Status entry**

Insert into `docs/superpowers/roadmap-status.md`, ABOVE `## Waiting on the user`, a dated implementer entry in the file's format (≤15 lines): commits landed; decisions later phases must respect (actuation buckets `"idx@act"`; `Telemetry.load_day_buckets` / `recent_buckets` / `actuation()`; suggestions only from the current read-back bucket; `ctx.writeActuation` / `ctx.applyTuneSuggestion`; `window.AetherAnalytics` exports for Phase 5: `useAnalytics`, `HeatmapBoard`, `heatLedMap`, `SuggestionList limit={3}`, `topSuggestions`); gotchas; the hardware checks below pointing at this plan. Inside `## Waiting on the user` add `- [Phase 4] Run the 10 hardware checks at the end of docs/superpowers/plans/2026-11-04-phase-4-analytics.md (heatmap matches typing, shallow/barely counts, Apply + read-back, Undo, RT keys keep RT).` Commit it alone:

```bash
git add docs/superpowers/roadmap-status.md
git commit -m "docs(status): phase 4 analytics + auto-tune done" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Hardware checks (for the orchestrator → `docs/HARDWARE_TEST_CHECKLIST.md` under `## Roadmap 2026-11-04`)

1. Connect the WIN60 with key statistics on. The **Analytics** tab appears right after Actuation (and is absent for boards without `keyStats`, e.g. pick the MINI 60 HE PRO in the board picker).
2. Type a paragraph. Within about 5 s the heatmap (Today) shows the keys you used, the busiest one red/amber, unused keys uncoloured; Overview totals match Settings > Key statistics "Today".
3. Click a key on the heatmap: Overview shows that key; Ctrl-click a second key: "2 keys" with summed numbers; "clear" returns to Whole board. Range chips (Today / 7 / 14 / 30 days) change the numbers; Presses per Day shows today's bar at the right.
4. With the 0.80 mm actuation: press one key gently ten times so it moves but does not type (about 0.3-0.6 mm). Overview for that key shows them under Shallow; ten light presses that just type (stop right after the click point) show under Barely over.
5. Auto-tune with little data shows "Space: N of 200 presses recorded at the current actuation..." style notes and no suggestion; disconnecting shows "Connect the keyboard..." instead of suggestions.
6. After enough typing (≥ 200 presses on a key or group) check whether a suggestion appears and whether its text matches your experience (missed keys -> "earlier"; accidental letters -> "later"). Report suggestions that feel wrong: the 5 % / 15 % thresholds are the spec's first guess.
7. Click **Apply** on a suggestion: a read-back runs (no "Read-back differs" notice), the Actuation tab's board shows the new value on exactly those keys, other keys unchanged, and the suggestion disappears.
8. Click **Undo**: those keys return to the previous value (check in the Actuation tab).
9. Set one key to rapid trigger (Actuation tab, RT on, Apply), produce a suggestion for it (or its group), Apply it: the key is still in rapid trigger with the same press/release sensitivities after the read-back.
10. Typing feel and CPU with the Analytics tab open for 5 minutes (it refreshes every 5 s): no missed or doubled keys, CPU similar to other tabs; closing the tab stops the refreshes.
