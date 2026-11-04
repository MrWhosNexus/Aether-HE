# Phase 1: Live-Depth Telemetry Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** While the board is connected, consume the live travel stream into per-key, per-day aggregates (presses, bottom-outs, peak-depth histogram, shallow attempts, barely-over presses, time-to-peak), persist them to `<user_data_dir>/stats/YYYY-MM-DD.json`, and expose them through `get_stats` / `clear_stats` / `set_stats_enabled` plus a Settings widget.

**Architecture:** A new pure-Python `telemetry.py` (`Telemetry`) segments presses from `(device index, mm, t)` samples and keeps aggregate counters in memory. The existing `device_state.LiveReader` calls an optional `on_sample` hook for every mapped travel report and for each release-clear; `Api` attaches `Telemetry.feed` to every reader it creates and keeps the shared reader alive under a new owner `"telemetry"`. A daemon flusher writes the counters at most once a minute; `disconnect()` (which the tray's Exit also runs) flushes too.

**Tech Stack:** Python 3 stdlib only (`threading`, `json`, `datetime`, `re`, `os`), pytest, the existing React/Tailwind UI (precompiled by `ui/runtime_src/build_runtime.py`).

**Spec:** `docs/superpowers/specs/2026-11-04-win60-roadmap-design.md` (section "Phase 1"). Read it and `docs/superpowers/roadmap-status.md` before starting.

## Global Constraints

- Windows is the shipping target; nothing may break Linux (guard Windows-only code by `sys.platform`, degrade to "unavailable" elsewhere).
- **No HID writes during development or tests. Never run the app against the keyboard.** Fakes only (patterns: `tests/test_travel_release.py`, `tests/test_socd_clear.py`). Hardware checks are listed at the end of this plan for the orchestrator.
- No push, merge into other branches, tag, release, or install.
- Python: `C:\Users\yygbu\Aether-HE\venv-web\Scripts\python.exe` (written `<py>` below). Full suite: `<py> -m pytest -q -p no:cacheprovider` (683 passing at branch start); must pass after the phase.
- JSX changes need `<py> ui\runtime_src\build_runtime.py`; commit the regenerated `ui/index_runtime.html` + `ui/runtime_src/build/*.js` only in the task that changed JSX, and never a line-ending-only diff.
- UI: edit `ui/runtime_src/src/*.jsx` / `ui/runtime_src/workspaces/*.jsx`, never `vendor/`. No raw-HTML sinks (`dangerouslySetInnerHTML`, `innerHTML`). Match the existing look (Tailwind classes, CSS vars `--text`, `--accent`, `--line`, `--ink`).
- New Python deps: **none** in Phase 1.
- Capability gating through `data/board_registry.json` (`keyStats`, enabled for `aula-win60-he`).
- **Privacy anti-goal:** Aether must never become a keylogger. No storing or transmitting key *sequences*, text, or per-keystroke timestamps. Aggregates only.
- Bridge methods return `{"ok": bool, ...}` and never raise to JS (follow `Api._fail`).
- Do NOT touch `service/server.py`, `updater.py`, `Api.open_submission_url`, `.github/workflows/board-bot.yml`, or the Pillow pin.
- `git add` only the files you changed (other agents have untracked files in this worktree, e.g. `protocol_win60_advkeys_wip.py`, `docs/context/*`). Never use `git stash`.
- Every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Context limit: if your context approaches ~400k tokens, stop: commit only what is green, append a status entry to `docs/superpowers/roadmap-status.md` saying exactly where you stopped, and return.

## Design decisions (resolved; do not re-decide)

1. **Press segmentation.** Work in integer hundredths (`raw = round(mm*100)`). A run starts at the first sample `raw >= 5` (0.05 mm, the LiveReader's `NOISE_MM`) for a key with no open run. It ends when a sample `raw < 5` arrives. The LiveReader reports its 839a076 release-silence clear as a sample of `0.0`, so "ends when LiveReader clears the key" is the same rule. **Re-press split:** if the depth has fallen ≥ 0.30 mm below the run's peak and then rises ≥ 0.30 mm above that trough, the run is closed at its peak and a new run starts at the current sample (rapid re-press / RT double tap without full release). Smaller wobbles never split.
2. **What a run counts as.** Runs with peak ≤ 0.15 mm are discarded (touch / noise). Every other run goes into `hist[min(33, raw // 10)]` (34 bins of 0.1 mm over 0–3.4 mm; 3.40 lands in bin 33). With the key's actuation `act` known: `peak < act` → `shallow` (the board did not register it) and nothing else; otherwise `presses += 1`, `barely += 1` if `peak <= act + 0.10`. With `act` unknown: `presses += 1`, `unrated += 1`, no shallow/barely. For every press: `bottom += 1` if `peak >= 3.30`, `ttp_ms += min(1000, round((t_peak - t_start) * 1000))`. Invariant: `sum(hist) == presses + shallow`. Mean time-to-peak = `ttp_ms / presses`.
3. **Per-key actuation source = the firmware read-back the UI already performs.** `app.jsx` calls `verify_actuation` on every connect and after every Actuation Apply; `Api.verify_actuation` now also hands the whole-board `{device index: mm}` result to `Telemetry.set_actuation`. Rejected alternatives: `settings.json` profiles (can disagree with flash, see the spec backlog's factory-reset mystery), a dedicated read-back (an extra HID round trip and a reader pause). Any actuation write (`set_trigger_codes`, `set_trigger_all`) first calls `Telemetry.forget_actuation(idxs)` so a stale value is never used; those keys count as `unrated` until the UI's follow-up read-back. **No new HID traffic.**
4. **Hook from the reader thread.** `LiveReader.on_sample` (default `None`) is hoisted into a local before the loop and called once per mapped travel report as `on_sample(idx, depth_mm, now)` and once per release-silence clear as `on_sample(idx, 0.0, t_now)`, inside `try/except Exception: pass`. `Telemetry.feed` does integer math and dict updates under one uncontended `threading.Lock`, returns immediately when disabled, and never does I/O. Time-to-peak granularity is the reader's drain cycle (all reports of one drain share `now`); that is accepted.
5. **Reader lifecycle.** `Api._make_live_reader(indices=None)` is the only place readers are built (replaces the four `self.driver.make_live_reader(...)` call sites). It calls `Telemetry.abort_open()` (a new reader means the old stream ended: in-flight presses are dropped, never stuck) and sets `r.on_sample = telemetry.feed` when the board supports stats. `_connect` claims owner `"telemetry"` via `_start_stats_reader()`. `disconnect()` flushes and `_stop_readers()` clears the owner as for every other owner. **Calibration** now parks the shared reader (owners kept) and restores it when calibration ends: `CalibrationReader` must be the sole drain, and with an always-on reader it no longer would be. `_restore_shared_reader` refuses to start a reader while `_calibrating`.
6. **Storage.** Day file `<user_data_dir>/stats/YYYY-MM-DD.json` (local date at the moment a run *ends*), content `{"version": 1, "date": "...", "boards": {"<slug>": {"<device index>": {"presses", "shallow", "barely", "bottom", "unrated", "ttp_ms", "hist"[34]}}}}`, dumped with `sort_keys=True, separators=(",", ":")` (deterministic: identical counts give identical bytes whatever the keystroke order). Boards are kept apart because device indices are per board. Memory holds only deltas since the last flush; a flush reads the day file (sanitised: unknown fields and malformed values dropped), adds the delta, writes `*.tmp` then `os.replace`. On failure the delta is merged back and kept. The flusher is a daemon thread started lazily on the first recorded run, waking every 60 s; `disconnect()` flushes (the tray's Exit and `main()`'s `finally` both reach `disconnect()`). Every `flush()` also prunes day files with `(today - date).days >= 90`; only names matching `^\d{4}-\d{2}-\d{2}\.json$` are ever touched.
7. **Linux unaffected.** `telemetry.py` is platform-neutral, but the default for `collectKeyStats` is ON only when `sys.platform.startswith("win")`; elsewhere it is OFF until the user turns it on, so on Linux the reader lifecycle is exactly today's. The calibration park/restore is a no-op when no reader runs.
8. **Gating.** `data/board_registry.json` gains `"keyStats": true` for `aula-win60-he` only. `Api._stats_supported()` = `board.cap("keyStats") is True and driver.supports("travel_stream")`. Unsupported boards never get the hook, so analog-tab sessions on other boards record nothing.
9. **Settings.** `settings.json` key `collectKeyStats` (bool), written by `set_stats_enabled` through the existing merging `save_settings`. Settings workspace gets a new widget "Key statistics": toggle "Collect key statistics", today's totals line, "Clear statistics" with a two-click confirm (no `window.confirm`).
10. **Phase 4 readiness.** `telemetry.peak_percentile(hist, q)` computes a per-key percentile (e.g. p10 peak) from the stored histogram by linear interpolation inside the bin, so Phase 4 needs no new collection. `Telemetry.load_day(date)` gives per-day data for the 14-day chart.

## Review Focus

- **Stats folder unwritable or locked** (antivirus/OneDrive lock on `os.replace`, a file named `stats`): counts stay in memory, `flush()` returns `False`, nothing raises into the reader thread or JS. Test: Task 2 `test_unwritable_stats_dir_keeps_counts_and_never_raises`.
- **Corrupt, hand-edited or foreign day file:** read as empty/sanitised; foreign fields are never written back. Tests: Task 2 `test_corrupt_day_file_is_ignored_then_rewritten`, `test_foreign_fields_are_dropped_and_never_rewritten`.
- **Calibration started while the always-on stats reader runs:** the reader is parked, owners kept, and restored afterwards. Test: Task 4 `test_calibration_parks_the_stats_reader_then_restores_it`.
- **Reader replaced or paused mid-press** (actuation read-back, analog tab, link loss): the in-flight press is dropped, never stuck open or merged with the next one. Tests: Task 1 `test_abort_open_drops_a_press_in_progress`, Task 4 `test_new_reader_drops_a_press_in_progress`.
- **Flush racing the reader thread:** no lost and no double-counted presses. Test: Task 2 `test_concurrent_feed_and_flush_lose_and_duplicate_nothing`.

## File Structure

- Create `telemetry.py`: press segmentation, aggregates, persistence, prune, flusher, `peak_percentile`.
- Modify `device_state.py`: `LiveReader.on_sample` hook (two call points in `_run`).
- Modify `app_web.py`: `import telemetry`, `STATS_SETTING`, `_stats_default_enabled`, `_clamp_stats_days`; `Api._make_telemetry`, `_stats_supported`, `_make_live_reader`, `_start_stats_reader`, `_stats_actuation`, `_stats_forget_actuation`; edits in `__init__`, `_connect`, `select_board`, `_park_readers`, `_restore_shared_reader`, `disconnect`, `set_trigger_all`, `open_analog_codes`, `set_trigger_codes`, `verify_actuation`, `calibrate`, `set_gamepad_capture`, `_ensure_reactive`; bridge `get_stats`, `clear_stats`, `set_stats_enabled`.
- Modify `data/board_registry.json` (+ `boards.py` docstring): `keyStats`.
- Modify `ui/runtime_src/workspaces/settings.jsx`: `StatsWidget` + widget entry.
- Modify `CLAUDE.md`: one Architecture bullet.
- Tests: create `tests/test_telemetry.py`, `tests/test_telemetry_store.py`, `tests/test_stats_api.py`; extend `tests/test_travel_release.py`.

---

### Task 1: `telemetry.py` press segmentation and in-memory aggregates

**Files:**
- Create: `telemetry.py`
- Test: `tests/test_telemetry.py`

**Interfaces:**
- Produces (module constants): `NOISE_RAW = 5`, `ATTEMPT_MIN_RAW = 15`, `BOTTOM_RAW = 330`, `BARELY_RAW = 10`, `REPRESS_RAW = 30`, `TTP_CAP_MS = 1000`, `HIST_BINS = 34`, `FIELDS = ("presses", "shallow", "barely", "bottom", "unrated", "ttp_ms")`, `FILE_VERSION = 1`, `KEEP_DAYS = 90`, `FLUSH_INTERVAL_S = 60.0`.
- Produces: `empty_agg() -> dict` (every FIELD 0 plus `"hist": [0]*34`), `merge_agg(dst: dict, src: dict) -> dict` (adds in place, returns dst), `peak_percentile(hist: list[int], q: float) -> float | None`.
- Produces: `class Telemetry(root: str, *, enabled: bool = True, board: str | None = None, today: Callable[[], str] | None = None, flush_interval_s: float | None = FLUSH_INTERVAL_S, keep_days: int = KEEP_DAYS)` with read-only properties `enabled`, `board` and methods `set_enabled(on: bool) -> None`, `set_board(slug: str | None) -> None`, `set_actuation(mm_by_idx: dict[int, float]) -> None` (merge), `forget_actuation(idxs) -> None`, `feed(idx: int, mm: float, t: float) -> None`, `abort_open() -> None`, `load_day(date: str) -> dict[int, dict]`, `aggregate(days: int = 1) -> dict[int, dict]`. `today` defaults to `lambda: datetime.date.today().isoformat()`. The constructor must not create directories or start threads.

- [ ] **Step 1: Write the failing tests** — `tests/test_telemetry.py`:

```python
"""Phase 1 key statistics: press segmentation and per-key aggregates.
No HID: Telemetry.feed is driven directly with (device index, mm, t), the
way LiveReader.on_sample calls it (0.0 = the reader cleared the key)."""
from telemetry import Telemetry, peak_percentile, HIST_BINS

W = 46
TODAY = "2026-11-04"


def _tel(tmp_path, **kw):
    kw.setdefault("board", "aula-win60-he")
    kw.setdefault("today", lambda: TODAY)
    kw.setdefault("flush_interval_s", None)
    return Telemetry(str(tmp_path / "stats"), **kw)


def _press(tel, idx, depths, t0=100.0, step=0.01):
    """One press as the reader reports it: the samples, then the clear."""
    t = t0
    for mm in depths:
        tel.feed(idx, mm, t)
        t += step
    tel.feed(idx, 0.0, t)
    return t + step


def test_one_press_records_peak_bin_and_time_to_peak(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [0.31, 1.02, 2.06, 3.25, 2.42, 2.11, 1.72, 1.18, 0.45])
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 1 and agg["unrated"] == 1
    assert len(agg["hist"]) == HIST_BINS
    assert agg["hist"][32] == 1 and sum(agg["hist"]) == 1
    assert agg["bottom"] == 0 and agg["shallow"] == 0 and agg["barely"] == 0
    assert agg["ttp_ms"] == 30


def test_bottom_out_counts_from_3_30_and_3_40_lands_in_the_last_bin(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [1.0, 3.30])
    t = _press(tel, W, [1.0, 3.29], t0=t)
    _press(tel, W, [1.0, 3.40], t0=t)
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 3 and agg["bottom"] == 2
    assert agg["hist"][33] == 2 and agg["hist"][32] == 1


def test_touch_at_or_below_0_15_is_not_counted(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [0.10, 0.15])
    assert tel.aggregate(1) == {}
    _press(tel, W, [0.10, 0.16])
    assert tel.aggregate(1)[W]["hist"][1] == 1


def test_shallow_attempt_below_actuation_is_not_a_press(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    _press(tel, W, [0.20, 0.50, 0.30])
    agg = tel.aggregate(1)[W]
    assert agg["shallow"] == 1 and agg["presses"] == 0
    assert agg["hist"][5] == 1 and agg["ttp_ms"] == 0 and agg["unrated"] == 0


def test_barely_over_is_within_0_10_above_actuation(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    t = _press(tel, W, [0.50, 0.80])
    t = _press(tel, W, [0.50, 0.90], t0=t)
    _press(tel, W, [0.50, 0.91], t0=t)
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 3 and agg["barely"] == 2
    assert agg["shallow"] == 0 and agg["unrated"] == 0


def test_forgotten_actuation_makes_presses_unrated(tmp_path):
    tel = _tel(tmp_path)
    tel.set_actuation({W: 0.80})
    tel.forget_actuation([W])
    _press(tel, W, [0.50])
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 1 and agg["unrated"] == 1 and agg["shallow"] == 0


def test_repress_without_release_splits_into_two_presses(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [0.50, 1.50, 2.00, 1.60, 2.10])
    agg = tel.aggregate(1)[W]
    assert agg["presses"] == 2
    assert agg["hist"][20] == 1 and agg["hist"][21] == 1
    assert agg["ttp_ms"] == 20


def test_small_wobble_does_not_split(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [1.00, 2.00, 1.85, 2.00])
    assert tel.aggregate(1)[W]["presses"] == 1


def test_sample_below_noise_floor_ends_the_press(tmp_path):
    tel = _tel(tmp_path)
    tel.feed(W, 1.0, 1.0)
    tel.feed(W, 2.0, 1.01)
    tel.feed(W, 0.04, 1.02)
    assert tel.aggregate(1)[W]["presses"] == 1


def test_time_to_peak_is_capped_at_one_second(tmp_path):
    tel = _tel(tmp_path)
    tel.feed(W, 0.5, 1.0)
    tel.feed(W, 2.0, 6.0)
    tel.feed(W, 0.0, 6.1)
    assert tel.aggregate(1)[W]["ttp_ms"] == 1000


def test_nothing_is_counted_while_disabled_or_without_a_board(tmp_path):
    off = _tel(tmp_path, enabled=False)
    _press(off, W, [2.0])
    assert off.aggregate(1) == {}
    off.set_enabled(True)
    _press(off, W, [2.0])
    assert off.aggregate(1)[W]["presses"] == 1
    nob = _tel(tmp_path, board=None)
    _press(nob, W, [2.0])
    assert nob.aggregate(1) == {}


def test_abort_open_drops_a_press_in_progress(tmp_path):
    tel = _tel(tmp_path)
    tel.feed(W, 2.0, 1.0)
    tel.abort_open()
    tel.feed(W, 0.0, 1.1)
    assert tel.aggregate(1) == {}


def test_peak_percentile_interpolates_inside_the_bin():
    hist = [0] * HIST_BINS
    hist[5], hist[20] = 10, 90
    assert peak_percentile(hist, 0.10) == 0.6
    assert peak_percentile(hist, 0.50) == 2.04
    assert peak_percentile([0] * HIST_BINS, 0.10) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_telemetry.py -q -p no:cacheprovider`
Expected: collection error `ModuleNotFoundError: No module named 'telemetry'`.

- [ ] **Step 3: Implement `telemetry.py`**

Module docstring states the privacy anti-goal (aggregates only; no sequences, text, or per-keystroke timestamps) and the segmentation rules from "Design decisions" 1–2. State lives under `self._lock = threading.Lock()`:
`self._open: dict[int, list]` (per key `[t_start, peak_raw, t_peak, trough_raw]`), `self._act: dict[int, int]` (actuation in hundredths), `self._pending: dict[tuple[str, str], dict[int, dict]]` keyed `(date, board)`. Also create (unused until Task 2) `self._io_lock = threading.Lock()`, `self._flusher = None`, `self._stop = threading.Event()`.

`feed` algorithm (the part the tests pin; write it exactly like this):

```python
def feed(self, idx, mm, t):
    if not self._enabled or self._board is None:
        return
    raw = int(round(mm * 100))
    with self._lock:
        run = self._open.get(idx)
        if raw < NOISE_RAW:
            if run is not None:
                del self._open[idx]
                self._record(idx, run)
            return
        if run is None:
            self._open[idx] = [t, raw, t, raw]
            return
        if run[3] <= run[1] - REPRESS_RAW and raw >= run[3] + REPRESS_RAW:
            self._record(idx, run)                 # re-press without release
            self._open[idx] = [t, raw, t, raw]
        elif raw > run[1]:
            run[1], run[2], run[3] = raw, t, raw
        elif raw < run[3]:
            run[3] = raw
```

`_record(idx, run)` (caller holds the lock) applies "Design decisions" 2 to `self._pending.setdefault((self._today(), self._board), {}).setdefault(idx, empty_agg())`, then calls `self._ensure_flusher()` (define it now as a no-op `pass`; Task 2 fills it in). `set_board` and `set_enabled(False)` clear `_open`; `set_board` also clears `_act`. `set_actuation` stores `int(round(mm*100))` per `int(idx)`, skipping values that are not finite numbers > 0. `load_day(date)` returns a deep copy (`merge_agg(empty_agg(), a)`) of `self._pending.get((date, self._board), {})`. `aggregate(days)` sums `load_day` over `[(today - timedelta(k)).isoformat() for k in range(max(1, int(days)))]` where `today = date.fromisoformat(self._today())`, omitting keys whose every FIELD and every `hist` bin is 0.

`peak_percentile`: `total = sum(hist)`; `None` if 0; `target = q * total`; walk bins with cumulative `cb`; at the first bin `i` with count `c > 0` and `cb + c >= target` return `round((i + (target - cb) / c) * 0.1, 2)`.

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_telemetry.py -q -p no:cacheprovider`
Expected: `13 passed`.

- [ ] **Step 5: Commit**

```bash
git add telemetry.py tests/test_telemetry.py
git commit -m "feat(telemetry): per-key press segmentation and aggregates" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Day-file persistence, prune, clear, flusher (+ privacy tests)

**Files:**
- Modify: `telemetry.py`
- Test: `tests/test_telemetry_store.py`

**Interfaces:**
- Consumes: Task 1's `Telemetry`, `empty_agg`, `merge_agg`, `FIELDS`, `HIST_BINS`, `KEEP_DAYS`.
- Produces: `Telemetry.flush() -> bool` (True = nothing pending or written; False = write failed, delta kept), `Telemetry.clear() -> int` (number of day files deleted), `Telemetry.close() -> None` (stop flusher, then flush). `load_day` / `aggregate` now include the day file. Day file path `os.path.join(root, f"{date}.json")`.

- [ ] **Step 1: Write the failing tests** — `tests/test_telemetry_store.py`:

```python
"""Phase 1 key statistics on disk: day files, merge, prune, clear, flusher,
and the privacy anti-goal (only per-key aggregates ever reach the file)."""
import json
import threading
import time

from telemetry import Telemetry, FIELDS, HIST_BINS
from test_telemetry import _tel, _press, W, TODAY

SLUG = "aula-win60-he"


def _day(tmp_path, date=TODAY):
    return tmp_path / "stats" / f"{date}.json"


def _doc(tmp_path, date=TODAY):
    return json.loads(_day(tmp_path, date).read_text(encoding="utf-8"))


def test_nothing_is_written_until_flush(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [2.0])
    assert not (tmp_path / "stats").exists()
    assert tel.flush() is True
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 1


def test_flushes_accumulate_without_double_counting(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [2.0]); tel.flush()
    _press(tel, W, [2.0]); tel.flush()
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 2
    assert tel.aggregate(1)[W]["presses"] == 2


def test_aggregate_merges_day_files_and_pending(tmp_path):
    old = _tel(tmp_path, today=lambda: "2026-11-03")
    _press(old, W, [2.0]); old.flush()
    tel = _tel(tmp_path)
    _press(tel, W, [2.0])                      # still pending
    assert tel.aggregate(1)[W]["presses"] == 1
    assert tel.aggregate(2)[W]["presses"] == 2
    assert tel.load_day("2026-11-03")[W]["presses"] == 1


def test_day_rollover_buckets_by_the_day_a_press_ends(tmp_path):
    day = [TODAY]
    tel = _tel(tmp_path, today=lambda: day[0])
    _press(tel, W, [2.0])
    day[0] = "2026-11-05"
    _press(tel, W, [2.0])
    tel.flush()
    assert _doc(tmp_path, TODAY)["boards"][SLUG]["46"]["presses"] == 1
    assert _doc(tmp_path, "2026-11-05")["boards"][SLUG]["46"]["presses"] == 1


def test_prune_deletes_files_90_days_old_and_keeps_newer(tmp_path):
    d = tmp_path / "stats"
    d.mkdir()
    for name in ("2026-08-06.json", "2026-08-07.json", "notes.json", "2026-13-99.json"):
        (d / name).write_text("{}", encoding="utf-8")
    _tel(tmp_path).flush()
    left = sorted(p.name for p in d.iterdir())
    assert left == ["2026-08-07.json", "2026-13-99.json", "notes.json"]


def test_corrupt_day_file_is_ignored_then_rewritten(tmp_path):
    (tmp_path / "stats").mkdir()
    _day(tmp_path).write_text("{not json", encoding="utf-8")
    tel = _tel(tmp_path)
    assert tel.aggregate(1) == {}
    _press(tel, W, [2.0])
    assert tel.flush() is True
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 1


def test_foreign_fields_are_dropped_and_never_rewritten(tmp_path):
    (tmp_path / "stats").mkdir()
    rec = {"presses": 3, "hist": [0] * HIST_BINS, "typed": "hello"}
    doc = {"version": 1, "date": TODAY, "log": ["h", "e"],
           "boards": {SLUG: {"46": rec, "abc": {"presses": 9}}}}
    _day(tmp_path).write_text(json.dumps(doc), encoding="utf-8")
    tel = _tel(tmp_path)
    agg = tel.aggregate(1)
    assert set(agg) == {W}
    assert set(agg[W]) == set(FIELDS) | {"hist"} and agg[W]["presses"] == 3
    _press(tel, W, [2.0]); tel.flush()
    text = _day(tmp_path).read_text(encoding="utf-8")
    assert "hello" not in text and "log" not in text and "abc" not in text
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 4


def test_clear_removes_day_files_and_pending_only(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [2.0]); tel.flush()
    (tmp_path / "stats" / "notes.txt").write_text("keep", encoding="utf-8")
    _press(tel, W, [2.0])
    assert tel.clear() == 1
    assert tel.aggregate(1) == {}
    assert (tmp_path / "stats" / "notes.txt").exists()


def test_boards_are_kept_apart(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [2.0])
    tel.set_board("aula-win68-he")
    t = _press(tel, W, [2.0], t0=t)
    _press(tel, W, [2.0], t0=t)
    tel.flush()
    boards = _doc(tmp_path)["boards"]
    assert boards[SLUG]["46"]["presses"] == 1
    assert boards["aula-win68-he"]["46"]["presses"] == 2
    assert tel.aggregate(1)[W]["presses"] == 2


def test_unwritable_stats_dir_keeps_counts_and_never_raises(tmp_path):
    (tmp_path / "stats").write_text("a file where the folder should be", encoding="utf-8")
    tel = _tel(tmp_path)
    _press(tel, W, [2.0])
    assert tel.flush() is False
    assert tel.aggregate(1)[W]["presses"] == 1
    assert tel.clear() == 0


def test_flusher_writes_on_its_interval(tmp_path):
    tel = _tel(tmp_path, flush_interval_s=0.05)
    try:
        _press(tel, W, [2.0])
        deadline = time.monotonic() + 2.0
        while not _day(tmp_path).exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert _day(tmp_path).exists()
    finally:
        tel.close()


def test_close_flushes_pending(tmp_path):
    tel = _tel(tmp_path)
    _press(tel, W, [2.0])
    tel.close()
    assert _doc(tmp_path)["boards"][SLUG]["46"]["presses"] == 1


def test_concurrent_feed_and_flush_lose_and_duplicate_nothing(tmp_path):
    tel = _tel(tmp_path)

    def typist():
        t = 0.0
        for n in range(400):
            t = _press(tel, (n % 4) + 20, [0.5, 2.0], t0=t)

    th = threading.Thread(target=typist)
    th.start()
    while th.is_alive():
        tel.flush()
    th.join()
    tel.flush()
    keys = _doc(tmp_path)["boards"][SLUG]
    assert sum(k["presses"] for k in keys.values()) == 400


# ---- privacy anti-goal: aggregates only ----------------------------------
def test_day_file_holds_only_per_key_aggregates(tmp_path):
    tel = _tel(tmp_path)
    t = _press(tel, W, [0.4, 1.2, 3.35])
    _press(tel, 47, [0.3, 0.9], t0=t)
    tel.flush()
    doc = _doc(tmp_path)
    assert set(doc) == {"version", "date", "boards"}
    assert doc["version"] == 1 and doc["date"] == TODAY
    for keys in doc["boards"].values():
        for k, rec in keys.items():
            assert k.isdigit()
            assert set(rec) == set(FIELDS) | {"hist"}
            assert all(type(rec[f]) is int for f in FIELDS)
            assert len(rec["hist"]) == HIST_BINS
            assert all(type(v) is int for v in rec["hist"])


def test_day_file_is_identical_whatever_the_order_and_time_of_keystrokes(tmp_path):
    shapes = {46: [0.4, 1.2, 2.0], 47: [0.3, 3.35], 23: [0.5, 0.9]}

    def type_(tel, order, t0):
        t = t0
        for idx in order:
            t = _press(tel, idx, shapes[idx], t0=t)
        tel.flush()

    type_(_tel(tmp_path / "a"), [46, 47, 46, 23, 47, 46], 100.0)
    type_(_tel(tmp_path / "b"), [23, 46, 46, 47, 46, 47], 98765.4321)
    a = (tmp_path / "a" / "stats" / f"{TODAY}.json").read_bytes()
    b = (tmp_path / "b" / "stats" / f"{TODAY}.json").read_bytes()
    assert a == b
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_telemetry_store.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: 'Telemetry' object has no attribute 'flush'` (several tests).

- [ ] **Step 3: Implement persistence in `telemetry.py`**

- `_read_day(date) -> dict[str, dict[int, dict]]` (board → idx → agg): missing file, `OSError`, `ValueError`, non-dict, or `version != FILE_VERSION` → `{}`. Sanitise: board keys must be `str`; key ids must match `^\d{1,3}$`; per record keep only FIELDS whose value is an `int` (not `bool`) ≥ 0 (else 0) and `hist` only when it is a list of exactly 34 non-negative ints (else zeros). Nothing else survives.
- `load_day(date)`: under `self._io_lock`, sanitised file part for the current board merged with the pending part (pending copied under `self._lock`).
- `flush()`: under `self._io_lock`: swap `self._pending` for `{}` under `self._lock`; group the snapshot by date; per date read the file, `merge_agg` the delta, write `json.dumps({"version": 1, "date": date, "boards": {slug: {str(idx): agg}}}, sort_keys=True, separators=(",", ":"))` to `<path>.tmp` with `encoding="utf-8"`, then `os.replace`. If the snapshot is non-empty, `os.makedirs(root, exist_ok=True)` first; an empty snapshot writes nothing and goes straight to the prune. On any `OSError`/`ValueError`: merge the snapshot back into `self._pending` under `self._lock`, `log.warning(...)`, return `False`. Then `_prune()` (its own `OSError`s are swallowed) and return `True`. `log = logging.getLogger(__name__)`.
- `_prune()`: if `root` is not a directory return; for names matching `^(\d{4}-\d{2}-\d{2})\.json$` whose date parses and `(today - date).days >= self._keep_days`, `os.remove` (ignore `OSError`).
- `clear()`: under `self._io_lock`, then under `self._lock` empty `_pending` and `_open`; delete names matching `^\d{4}-\d{2}-\d{2}\.json(\.tmp)?$`; return the number of `.json` day files removed (0 if `root` is not a directory).
- `_ensure_flusher()` (lock held by caller): if `flush_interval_s` is truthy and no live flusher, start a daemon `threading.Thread(name="aether-stats-flush")` running `while not stop.wait(interval): self.flush()` with a per-start `threading.Event` (the `LiveReader` per-run-flag pattern).
- `close()`: set the stop event, join the flusher (`timeout=1.0`), then `flush()`.

- [ ] **Step 4: Run Task 1 and Task 2 tests**

Run: `<py> -m pytest tests/test_telemetry.py tests/test_telemetry_store.py -q -p no:cacheprovider`
Expected: `28 passed`.

- [ ] **Step 5: Commit**

```bash
git add telemetry.py tests/test_telemetry_store.py
git commit -m "feat(telemetry): daily aggregate files with prune, clear and flusher" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `LiveReader.on_sample` hook

**Files:**
- Modify: `device_state.py` (`LiveReader.__init__` and `_run`, around lines 97–247)
- Test: `tests/test_travel_release.py` (append)

**Interfaces:**
- Produces: `LiveReader.on_sample: Callable[[int, float, float], None] | None`, called as `(device index, depth_mm, monotonic t)` for every mapped travel report and as `(device index, 0.0, t)` when the release-silence rule clears a key. Must be set before `start()`.
- Consumes: Task 1's `Telemetry.feed` (same signature) in the end-to-end test.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_travel_release.py`:

```python
def _run_hooked(reports, wait_s, hook):
    lr = device_state.LiveReader(_FakeDev(reports), _KM, indices=[46])
    lr.on_sample = hook
    lr.start()
    try:
        time.sleep(wait_s)
        return lr.snapshot()
    finally:
        lr.stop()


def test_on_sample_sees_every_report_then_the_release_clear():
    seen = []
    frames = [_travel_report(46, mm) for mm in _PRESS + _RELEASE_TAIL]
    assert _run_hooked(frames, 0.6, lambda i, mm, t: seen.append((i, mm))) == {}
    assert seen == [(46, mm) for mm in _PRESS + _RELEASE_TAIL] + [(46, 0.0)]


def test_a_held_key_gets_no_clear():
    seen = []
    frames = [_travel_report(46, mm) for mm in (2.56, 3.40)]
    _run_hooked(frames, 0.6, lambda i, mm, t: seen.append(mm))
    assert seen == [2.56, 3.40]


def test_a_failing_hook_does_not_stop_the_reader():
    def boom(i, mm, t):
        raise RuntimeError("hook bug")
    frames = [_travel_report(46, mm) for mm in _PRESS + _RELEASE_TAIL]
    assert _run_hooked(frames, 0.6, boom) == {}


def test_reader_feeds_telemetry_one_press(tmp_path):
    import telemetry
    tel = telemetry.Telemetry(str(tmp_path), board="aula-win60-he",
                              today=lambda: "2026-11-04", flush_interval_s=None)
    tel.set_actuation({46: 0.80})
    frames = [_travel_report(46, mm) for mm in _PRESS + _RELEASE_TAIL]
    _run_hooked(frames, 0.6, tel.feed)
    agg = tel.aggregate(1)[46]
    assert agg["presses"] == 1 and agg["hist"][32] == 1 and agg["unrated"] == 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_travel_release.py -q -p no:cacheprovider`
Expected: the 4 new tests FAIL (`seen == []`, telemetry aggregate `KeyError: 46`); the 4 existing tests pass.

- [ ] **Step 3: Implement the hook in `device_state.py`**

In `__init__`, after `self.RELEASE_SILENCE_S = 0.15`:

```python
        # Optional per-sample consumer (Api attaches telemetry.Telemetry.feed):
        # called (device index, mm, t) for every mapped travel report and
        # (device index, 0.0, t) when the release-silence rule clears a key.
        # Set it before start(); it runs on this thread, so it must be cheap.
        self.on_sample = None
```

In `_run`, hoist `on_sample = self.on_sample` next to `release_silence = ...`. Inside `if code:` after the existing `if depth < noise: ... else: ...` block (still inside `if code:`):

```python
                                if on_sample is not None:
                                    try:
                                        on_sample(idx, depth, now)
                                    except Exception:
                                        pass
```

In the release-silence loop, after `del lifting[idx]`:

```python
                        if on_sample is not None:
                            try:
                                on_sample(idx, 0.0, t_now)
                            except Exception:
                                pass
```

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_travel_release.py -q -p no:cacheprovider`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add device_state.py tests/test_travel_release.py
git commit -m "feat(travel): LiveReader on_sample hook for telemetry" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Registry gate and Api reader plumbing (owner `"telemetry"`, calibration park)

**Files:**
- Modify: `data/board_registry.json` (aula-win60-he `capabilities`), `boards.py` (module docstring capability list)
- Modify: `app_web.py`
- Test: `tests/test_stats_api.py` (create)

**Interfaces:**
- Consumes: `telemetry.Telemetry` (Tasks 1–2), `LiveReader.on_sample` (Task 3).
- Produces (module level in `app_web.py`): `STATS_SETTING = "collectKeyStats"`; `_stats_default_enabled(settings: dict | None, platform: str | None = None) -> bool` (a bool `settings[STATS_SETTING]` wins; otherwise `(platform or sys.platform).startswith("win")`).
- Produces (Api): `self.telemetry: telemetry.Telemetry | None` (set in `__init__` via `_make_telemetry()`); `_make_telemetry() -> Telemetry | None`; `_stats_supported() -> bool`; `_make_live_reader(indices=None) -> reader`; `_start_stats_reader() -> bool`; `_park_readers(attrs=("reader", "calib_reader")) -> None`. Every use of `self.telemetry` elsewhere goes through `getattr(self, "telemetry", None)`: many tests build `Api.__new__` objects without it.

- [ ] **Step 1: Write the failing tests** — `tests/test_stats_api.py`:

```python
"""Phase 1 key statistics through the Api: the shared reader gets owner
"telemetry", every reader the Api builds feeds Telemetry, calibration parks
it, disconnect flushes. Fakes only: no HID, no keyboard."""
import json
import threading

import pytest

import app_web
import boards
import device_state
import drivers
import telemetry
from test_drivers import StubDevice
from test_telemetry import _press

TODAY = "2026-11-04"


class FakeReader:
    def __init__(self, km=None, indices=None):
        self.indices = indices
        self.on_sample = None
        self.started = self.stopped = False

    def start(self): self.started = True
    def stop(self): self.stopped = True
    def alive(self): return self.started and not self.stopped
    def snapshot(self): return {}
    def snapshot_by_index(self): return {}


class FakeDriver:
    FEATURES = frozenset({"travel_stream"})

    def __init__(self):
        self.readers, self.calibration, self.detail = [], [], {}

    def supports(self, f): return f in self.FEATURES
    def connect(self): return {"interface_number": 2}
    def read_keymap_layer(self, fn_layer=False, timeout_s=None): return None
    def make_live_reader(self, km, indices=None):
        r = FakeReader(km, indices)
        self.readers.append(r)
        return r
    def make_calibration_reader(self, km): return FakeReader(km)
    def set_calibration(self, start, any_key=False): self.calibration.append(bool(start))
    def read_trigger_detail(self, km): return self.detail
    def set_actuation(self, *a, **k): pass
    def end_host_stream(self): pass


class FakeDev:
    dead_events = 0
    def __init__(self): self.open = True
    def is_open(self): return self.open
    def close(self): self.open = False


def _api(tmp_path, enabled=True, slug="aula-win60-he"):
    a = app_web.Api.__new__(app_web.Api)
    a._lock = threading.RLock()
    a.board = boards.load_registry().by_slug(slug)
    a.km = device_state.KeyMap()
    a.dev = FakeDev()
    a.driver = FakeDriver()
    a.fx = None
    a.pad = None
    a._pad_thread = None
    a._pad_stop = threading.Event()
    a.reader = None
    a.calib_reader = None
    a._reader_users = set()
    a._calibrating = False
    a._trigger_state = {}
    a._settings_path = lambda: str(tmp_path / "settings.json")
    a.telemetry = telemetry.Telemetry(str(tmp_path / "stats"), enabled=enabled,
                                      board=slug, today=lambda: TODAY,
                                      flush_interval_s=None)
    return a


def test_win60_declares_key_stats_and_every_declaring_board_streams_travel():
    reg = boards.load_registry()
    assert reg.by_slug("aula-win60-he").cap("keyStats") is True
    for p in reg.profiles:
        if p.cap("keyStats") is True:
            d = drivers.get_driver(p, StubDevice(), threading.RLock())
            assert d.supports("travel_stream"), p.slug


def test_stats_default_is_on_for_windows_only():
    f = app_web._stats_default_enabled
    assert f(None, "win32") is True
    assert f(None, "linux") is False
    assert f({"collectKeyStats": False}, "win32") is False
    assert f({"collectKeyStats": True}, "linux") is True
    assert f({"collectKeyStats": "yes"}, "win32") is True


def test_make_telemetry_reads_the_setting_and_touches_no_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(app_web, "user_data_dir", lambda: str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({"collectKeyStats": False}))
    a = _api(tmp_path)
    tel = a._make_telemetry()
    assert tel.enabled is False and tel.board == "aula-win60-he"
    assert not (tmp_path / "stats").exists()


def test_api_made_readers_feed_telemetry(tmp_path):
    a = _api(tmp_path)
    r = a._make_live_reader()
    assert r.on_sample == a.telemetry.feed


def test_new_reader_drops_a_press_in_progress(tmp_path):
    a = _api(tmp_path)
    a.telemetry.feed(46, 2.0, 1.0)
    a._make_live_reader()
    a.telemetry.feed(46, 0.0, 1.1)
    assert a.telemetry.aggregate(1) == {}


def test_unsupported_board_is_not_hooked_and_gets_no_owner(tmp_path):
    a = _api(tmp_path, slug="aula-mini60he-pro")
    assert a._make_live_reader().on_sample is None
    assert a._start_stats_reader() is False
    assert "telemetry" not in a._reader_users


def test_connect_starts_the_stats_reader(tmp_path):
    a = _api(tmp_path)
    assert a.connect()["ok"] is True
    assert "telemetry" in a._reader_users
    assert a.reader is a.driver.readers[-1] and a.reader.started


def test_connect_with_stats_disabled_starts_no_reader(tmp_path):
    a = _api(tmp_path, enabled=False)
    assert a.connect()["ok"] is True
    assert a.reader is None and "telemetry" not in a._reader_users


def test_closing_the_analog_tab_keeps_the_stats_stream(tmp_path):
    a = _api(tmp_path)
    a._start_stats_reader()
    assert a.open_analog_codes(["W"])["ok"]
    assert a.reader.indices == a.km.indices()       # whole board: others own it
    assert a.reader.on_sample == a.telemetry.feed
    a.close_analog()
    assert a.reader is not None and "telemetry" in a._reader_users


def test_reader_paused_restores_a_hooked_reader(tmp_path):
    a = _api(tmp_path)
    a._start_stats_reader()
    first = a.reader
    with a._reader_paused():
        assert a.reader is None
    assert first.stopped and a.reader is not first
    assert a.reader.on_sample == a.telemetry.feed


def test_calibration_parks_the_stats_reader_then_restores_it(tmp_path):
    a = _api(tmp_path)
    a._start_stats_reader()
    first = a.reader
    assert a.calibrate(True)["ok"]
    assert a.reader is None and first.stopped
    assert "telemetry" in a._reader_users
    a._restore_shared_reader()                       # e.g. a read-back ends
    assert a.reader is None                          # calibration owns the stream
    assert a.calibrate(False)["ok"]
    assert a.reader is not None and a.reader.started


def test_disconnect_flushes_and_drops_the_owner(tmp_path):
    a = _api(tmp_path)
    a._start_stats_reader()
    first = a.reader
    _press(a.telemetry, 46, [2.0])
    assert a.disconnect()["ok"]
    assert (tmp_path / "stats" / f"{TODAY}.json").exists()
    assert a._reader_users == set() and first.stopped
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_stats_api.py -q -p no:cacheprovider`
Expected: FAIL — `assert False is True` on `cap("keyStats")`, `AttributeError: module 'app_web' has no attribute '_stats_default_enabled'`, `AttributeError: ... '_make_live_reader'`, etc.

- [ ] **Step 3: Registry**

In `data/board_registry.json`, add `"keyStats": true` after `"macros": true` in the `aula-win60-he` `capabilities` block only (keep the file's 2-space style; add the comma on the `macros` line). In `boards.py`'s module docstring, extend the finer-grained flag list to `(rapidTrigger, socd, macros, calibration, gamepad, deadzone, keyStats)` and add one line: `keyStats = host-side key statistics from the live travel stream (telemetry.py).`

- [ ] **Step 4: Api plumbing in `app_web.py`**

- `import telemetry` beside the other local imports; module-level `STATS_SETTING` and `_stats_default_enabled` per Interfaces (non-bool stored values fall back to the platform default).
- `_make_telemetry()`: read `self.load_settings()` (its `"settings"` may be `None`), return `telemetry.Telemetry(os.path.join(user_data_dir(), "stats"), enabled=_stats_default_enabled(s), board=self.board.slug if self.board else None)`; on any exception log a warning and return `None`. Call it at the end of `__init__`: `self.telemetry = self._make_telemetry()`.
- `_stats_supported()`: `True` only when `getattr(self, "board", None)` has `cap("keyStats") is True` and `getattr(self, "driver", None)` has `supports("travel_stream")` true; tolerate either being absent.
- `_make_live_reader(self, indices=None)`: `r = self.driver.make_live_reader(self.km)` when `indices is None`, else `self.driver.make_live_reader(self.km, indices)` (keeps one-argument test fakes working). If telemetry exists and `_stats_supported()`: `tel.abort_open()` then `r.on_sample = tel.feed` (wrap the assignment in `try/except Exception`). Return `r`.
- Replace the four builders: `_restore_shared_reader` → `self.reader = self._make_live_reader()`; `open_analog_codes` → `self.reader = self._make_live_reader(idxs)`; `set_gamepad_capture` → `self._acquire_reader("gamepad", self._make_live_reader)`; `_ensure_reactive` → `self._acquire_reader("reactive", self._make_live_reader)`.
- `_start_stats_reader()` (never raises): return `False` unless telemetry exists, `tel.enabled`, `_stats_supported()`, `self.km`, and `self.dev.is_open()`. If `self._calibrating`: just add `"telemetry"` to `_reader_users` under `self._lock` and return `True` (the calibrate-off restore starts it). Else `self._acquire_reader("telemetry", self._make_live_reader)` and return `True`; on exception log a warning, `self._release_reader("telemetry")`, return `False`.
- `_connect`: after `if resume: self._resume_session()`, call `self._start_stats_reader()`.
- `_park_readers(self, attrs=("reader", "calib_reader"))`: same body, iterating `attrs`.
- `_restore_shared_reader`: first line inside its `try`: `if getattr(self, "_calibrating", False): return`.
- `calibrate(start=True)`: before `set_calibration(True, ...)` call `self._park_readers(("reader",))`; if `set_calibration` raises, call `self._restore_shared_reader()` and re-raise (the outer `except` returns `_fail`). `calibrate(start=False)`: after `self._calibrating = False` call `self._restore_shared_reader()`.
- `disconnect`: just before `self._stop_readers()`: if telemetry exists, `tel.abort_open(); tel.flush()` in `try/except Exception` (log a warning).
- `select_board`: right after `self._registry = reg`, if telemetry exists `tel.set_board(p.slug)`.

- [ ] **Step 5: Run the new tests and the suites the plumbing touches**

Run: `<py> -m pytest tests/test_stats_api.py tests/test_link_recovery.py tests/test_drivers.py tests/test_actuation_readback.py tests/test_effects_stream.py tests/test_boards.py tests/test_wiring_matrix.py -q -p no:cacheprovider`
Expected: all pass (`12` in `test_stats_api.py`).

- [ ] **Step 6: Commit**

```bash
git add data/board_registry.json boards.py app_web.py tests/test_stats_api.py
git commit -m "feat(stats): keep the live reader on for key statistics (owner telemetry)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Actuation source and bridge methods

**Files:**
- Modify: `app_web.py` (`verify_actuation`, `set_trigger_codes`, `set_trigger_all`; new bridge methods)
- Test: `tests/test_stats_api.py` (append)

**Interfaces:**
- Consumes: Task 4's `_api` test helper, `_stats_supported`, `self.telemetry`; Task 1's `set_actuation`, `forget_actuation`, `aggregate`; Task 2's `clear`, `flush`.
- Produces: `Api._stats_actuation(mm_by_idx: dict) -> None`, `Api._stats_forget_actuation(idxs) -> None`, module `_clamp_stats_days(days) -> int` (non-int → 1; clamped to `1..telemetry.KEEP_DAYS`).
- Produces (bridge, never raise):
  - `get_stats(days=1)` → `{"ok": True, "enabled": bool, "supported": bool, "board": str|None, "days": int, "keys": {design_code: agg}, "totals": {"presses", "shallow", "barely", "bottom"}}`; `agg` is exactly `FIELDS` + `"hist"`; a device index with no code becomes `"idx<N>"`.
  - `clear_stats()` → `{"ok": True, "deleted": int}`.
  - `set_stats_enabled(on)` → `{"ok": True, "enabled": bool}`.
  - With no telemetry: `{"ok": False, "error": "key statistics are unavailable"}`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_stats_api.py`:

```python
def test_actuation_read_back_classifies_shallow_presses(tmp_path):
    a = _api(tmp_path)
    w = a.km.index_of_code["W"]
    a.driver.detail = {a.km.by_index[w]["name"]: {"travel_mm": 0.80, "mode": 0}}
    assert a.verify_actuation([])["ok"]
    _press(a.telemetry, w, [0.20, 0.50])
    agg = a.telemetry.aggregate(1)[w]
    assert agg["shallow"] == 1 and agg["presses"] == 0


def test_writing_actuation_forgets_the_read_back(tmp_path):
    a = _api(tmp_path)
    w = a.km.index_of_code["W"]
    a.driver.detail = {a.km.by_index[w]["name"]: {"travel_mm": 0.80, "mode": 0}}
    a.verify_actuation([])
    assert a.set_trigger_codes(["W"], 1.2)["ok"]
    _press(a.telemetry, w, [0.50])
    agg = a.telemetry.aggregate(1)[w]
    assert agg["presses"] == 1 and agg["unrated"] == 1


def test_get_stats_returns_per_code_aggregates_and_totals(tmp_path):
    a = _api(tmp_path)
    _press(a.telemetry, a.km.index_of_code["W"], [1.0, 3.35])
    r = a.get_stats(1)
    assert r["ok"] and r["enabled"] and r["supported"] and r["days"] == 1
    assert r["board"] == "aula-win60-he"
    assert r["keys"]["W"]["presses"] == 1 and r["keys"]["W"]["bottom"] == 1
    assert r["totals"] == {"presses": 1, "shallow": 0, "barely": 0, "bottom": 1}
    for rec in r["keys"].values():                  # privacy: aggregates only
        assert set(rec) == set(telemetry.FIELDS) | {"hist"}


def test_get_stats_clamps_days(tmp_path):
    a = _api(tmp_path)
    assert a.get_stats(0)["days"] == 1
    assert a.get_stats(1000)["days"] == 90
    assert a.get_stats("x")["days"] == 1
    assert a.get_stats(None)["days"] == 1


def test_set_stats_enabled_persists_and_releases_the_reader(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"theme": "neon"}))
    a = _api(tmp_path)
    a._start_stats_reader()
    first = a.reader
    assert a.set_stats_enabled(False) == {"ok": True, "enabled": False}
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved == {"theme": "neon", "collectKeyStats": False}
    assert "telemetry" not in a._reader_users and first.stopped
    assert a.telemetry.enabled is False
    assert a.set_stats_enabled(True) == {"ok": True, "enabled": True}
    assert "telemetry" in a._reader_users and a.reader is not None


def test_clear_stats_deletes_everything(tmp_path):
    a = _api(tmp_path)
    w = a.km.index_of_code["W"]
    _press(a.telemetry, w, [2.0])
    a.telemetry.flush()
    _press(a.telemetry, w, [2.0])
    assert a.clear_stats() == {"ok": True, "deleted": 1}
    assert a.get_stats(1)["keys"] == {}


def test_bridge_methods_without_telemetry_fail_softly(tmp_path):
    a = _api(tmp_path)
    a.telemetry = None
    for r in (a.get_stats(1), a.clear_stats(), a.set_stats_enabled(True)):
        assert r["ok"] is False and r["error"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `<py> -m pytest tests/test_stats_api.py -q -p no:cacheprovider`
Expected: the 7 new tests FAIL (`AttributeError: 'Api' object has no attribute 'get_stats'`, shallow `0 == 1`).

- [ ] **Step 3: Implement in `app_web.py`**

- `_stats_actuation(mm_by_idx)`: if telemetry exists, `mm_by_idx` is non-empty and `_stats_supported()`, `tel.set_actuation(mm_by_idx)`. `_stats_forget_actuation(idxs)`: same guards, `tel.forget_actuation(idxs)`.
- `verify_actuation`: in the `for design_code, idx in self.km.index_of_code.items()` loop also fill `act_by_idx[idx] = mm` when `mm is not None`; after the loop call `self._stats_actuation(act_by_idx)`.
- `set_trigger_codes`: right after `for i in idxs: self._trigger_state[i] = cfg`, call `self._stats_forget_actuation(idxs)`. `set_trigger_all`: right after `idxs = ...`, call `self._stats_forget_actuation(idxs)`.
- `get_stats(days=1)`, `clear_stats()`, `set_stats_enabled(on)` per Interfaces, each wrapped in `try/except Exception as e: return self._fail(e)`. Code lookup via `self.km.code_of(idx)`. `set_stats_enabled`: `on = bool(on)`; persist first with `r = self.save_settings({STATS_SETTING: on})` and return `r` if `not r.get("ok")`; then `tel.set_enabled(on)`; on → `self._start_stats_reader()`; off → `self._release_reader("telemetry")` then `tel.flush()`.

- [ ] **Step 4: Run the tests**

Run: `<py> -m pytest tests/test_stats_api.py tests/test_actuation_readback.py tests/test_keyboard_review.py tests/test_win60_settings_fixes.py tests/test_settings_merge.py -q -p no:cacheprovider`
Expected: all pass (`19` in `test_stats_api.py`).

- [ ] **Step 5: Commit**

```bash
git add app_web.py tests/test_stats_api.py
git commit -m "feat(stats): get_stats/clear_stats/set_stats_enabled; actuation from read-back" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Settings widget "Key statistics"

**Files:**
- Modify: `ui/runtime_src/workspaces/settings.jsx`
- Regenerated: `ui/index_runtime.html`, `ui/runtime_src/build/ws_settings.js` (whatever the build actually changes)

**Interfaces:**
- Consumes: bridge `get_stats(1)`, `set_stats_enabled(bool)`, `clear_stats()` (Task 5); the file's existing `Toggle` component.

- [ ] **Step 1: Add `StatsWidget` after `SystemWidget`**

Behaviour (exact copy below is fixed; markup follows `SystemWidget`'s classes):
- State `{ loaded, supported, enabled, totals }`, `err`, `confirming`. `refresh()` calls `window.pywebview?.api?.get_stats(1)` (no-op until the bridge exists) and stores `supported/enabled/totals`, or `err = r.error`. Run it on mount and every 3000 ms; ignore results after unmount (a `useRef` alive flag; destructure `useRef` from `React` beside `useState, useEffect`).
- Heading (same classes as SystemWidget's "Launch"): `Privacy`.
- `<Toggle on={st.enabled} onClick={toggle} label="Collect key statistics" desc="Counts presses, bottom-outs and press depth per key, per day, on this PC. Never what you type or when. Kept for 90 days." />`. `toggle` flips optimistically, calls `set_stats_enabled(next)`, reverts and shows the error on failure (the `flip` pattern).
- When `st.loaded && !st.supported`: line (`font-mono text-[10px] text-[var(--text-faint)]`) `Statistics need a board with a live travel stream (Aula Win60 HE).`
- Today line (same faint mono style): `` `Today: ${t.presses} presses · ${t.bottom} bottom-outs · ${t.shallow} shallow` `` with `t = st.totals || { presses: 0, bottom: 0, shallow: 0 }`.
- Button `Clear statistics`; first click sets `confirming` (label becomes `Click again to delete all statistics`, rose accent: `border-rose-400/50 text-rose-300`), auto-reset after 4000 ms via a `useEffect` timeout; second click calls `clear_stats()` then `refresh()`. Idle button classes: `px-2.5 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:border-rose-400/40 hover:text-rose-300`.
- `err` shown like SystemWidget (`mt-2 font-mono text-[10px] text-rose-300/90`).
- Render text only through JSX children: no raw-HTML sinks.

- [ ] **Step 2: Register the widget**

Append to `SETTINGS_WIDGETS`:

```jsx
  { id: "stats",    title: "Key statistics", default: { x: 800, y: 352, w: 360, h: 260 }, min: { w: 300, h: 200 }, render: StatsWidget },
```

- [ ] **Step 3: Build the UI**

Run: `<py> ui\runtime_src\build_runtime.py`
Expected: ends with `Wrote ...index_runtime.html  (NNN KB)` and no Babel error.

- [ ] **Step 4: Keep only real build diffs and run the UI-adjacent tests**

Run: `git diff --ignore-cr-at-eol --stat` and `git diff --stat`. Any build file that appears in the second list but not in the first is a line-ending-only change: restore it with `git checkout -- <that file>`. Then:
Run: `<py> -m pytest tests/test_tray.py -q -p no:cacheprovider` and `git grep -n "dangerouslySetInnerHTML\|innerHTML" -- ui/runtime_src/workspaces/settings.jsx`
Expected: tests pass; the grep prints nothing.

- [ ] **Step 5: Commit**

```bash
git add ui/runtime_src/workspaces/settings.jsx ui/index_runtime.html ui/runtime_src/build/ws_settings.js
git commit -m "feat(ui): Key statistics settings widget (toggle + clear)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
(Add any other `ui/runtime_src/build/*.js` only if it has a real, non-line-ending diff.)

---

### Task 7: Docs, full suite, status

**Files:**
- Modify: `CLAUDE.md` (Architecture list), `docs/superpowers/roadmap-status.md` (append)

- [ ] **Step 1: CLAUDE.md**

Add after the `device_state.py` bullet: ``- `telemetry.py` — key statistics (roadmap Phase 1): per-key, per-day aggregates from the live travel stream (`LiveReader.on_sample`), owner `"telemetry"` keeps the shared reader on while connected; files `<user_data_dir>/stats/YYYY-MM-DD.json`, 90 days; aggregates only, never sequences or timestamps.`` Also append to the `device_state.py` bullet: `Calibration parks the shared reader (CalibrationReader must be the only drain).`

- [ ] **Step 2: Full suite**

Run: `<py> -m pytest -q -p no:cacheprovider`
Expected: `734 passed` (683 + 51 new: 13 + 15 + 4 + 12 + 7), zero failures, zero errors.

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: record telemetry.py in the architecture notes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Status entry**

Append to `docs/superpowers/roadmap-status.md` (≤15 lines, its entry format): commits landed; decisions for later phases (data model per Design decisions 2/6, `peak_percentile`, `load_day`, owner `"telemetry"`, actuation from `verify_actuation`, calibration park, default OFF off-Windows); the hardware checks below for the user. Commit it alone:

```bash
git add docs/superpowers/roadmap-status.md
git commit -m "docs(status): phase 1 telemetry done" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Hardware checks (for the orchestrator → `docs/HARDWARE_TEST_CHECKLIST.md` under `## Roadmap 2026-11-04`)

1. Stats on (Windows default), connected: type normally for 10 minutes — no missed, doubled or laggy keystrokes; AetherHE CPU in Task Manager stays low (note the figure; the reader now runs whenever connected).
2. After 1–2 minutes, `%LOCALAPPDATA%\AetherHE\stats\<today>.json` exists and holds only per-key counters and a 34-number histogram — no letters, no timestamps.
3. Press W fully 10 times: Settings → Key statistics "Today" grows by ~10 presses (and ~10 bottom-outs if bottoming out).
4. Press W gently, below 0.80 mm, 5 times: "shallow" grows by ~5, presses do not.
5. Calibration with stats on: keys turn green as calibrated and calibration completes; afterwards the Travel Test still shows depth.
6. Actuation Apply (read-back matches), remap, macros, dead band and switch selection all still work with stats on.
7. Toggle "Collect key statistics" off: with the Actuation tab closed and no press-reactive effect, the travel stream stops; the day file stops changing. Toggle on: counting resumes.
8. "Clear statistics" (two clicks): the stats folder's day files are gone and Today shows 0.
9. Poll-rate change and an unplug/replug: counting continues after the reconnect.
10. Tray → Exit right after some typing: the day file includes those presses on the next launch.
11. Press-reactive effects and the Actuation tab's Travel Test behave as before; closing the Actuation tab no longer stops the stream (expected while stats are on).
