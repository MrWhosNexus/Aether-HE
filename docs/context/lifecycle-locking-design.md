# Design note — thread / handle lifecycle & locking fix

Status: **proposal, pre-implementation.** Covers the 7 "lifecycle cluster" defects from the
2026-07-22 audit (rounds 2–3). No code changed yet. Branch: `lifecycle-fixes`.

## Why this is a design note and not a patch

The round-2 adversarial verifier flagged that the obvious fix for the read-modify-write race —
wrapping each RMW op in `with self._lock:` — **deadlocks**, because the per-frame writer re-acquires
that same lock. So the fix has to be designed against the real lock topology, not guessed.

## As-built model (line-anchored)

Two distinct **non-reentrant** `threading.Lock`s, always nested in one order:

| Lock | Created | Guards | Taken |
|---|---|---|---|
| **outer** — `Api._lock` **is** `driver._lock` (same object) | `app_web.py:365`, passed to driver `:371`/`:540` | write-frame interleaving | per *frame* in `base._write` (`base.py:90`) |
| **inner** — `AulaDevice._lock` | `aula_device.py:113` | the raw `_dev` hidraw handle + `_info` | per *I/O call* inside `AulaDevice.write/read` (`:168`,`:187`) |

Ordering is always **outer → inner**: `base._write` takes the outer lock, then `AulaDevice.write`
takes the inner lock inside it. Reader threads take **only the inner lock**. `_dev` is set/cleared
only in `AulaDevice.open()`/`close()` under the inner lock.

Three structural facts that cause the bugs:
1. **The outer lock is released between frames.** `base._write` locks one frame then releases; no
   path in `BoardDriver` holds it across a read→modify→write. The *only* span-locked path is
   `stream_frame` (`mini60.py:580`, `win60.py:143`), which deliberately holds the outer lock across
   all chunks of one host-stream frame.
2. **Reads take no outer lock at all**, and one read path (`device_state.read_actuation:264`) takes
   **no inner lock either** — it bangs `device._dev.read/set_nonblocking` directly.
3. **Reader threads only exit on `_stop`** and swallow every read error (`sleep(0.05); continue`),
   with no dead-handle detection. `disconnect()` (`app_web.py:575`) never stops them nor disarms
   calibration; `select_board()` (`:506`) does stop them (the template `disconnect` should follow).

## The 7 defects → 3 root causes

| # | Defect | Sev | Root cause |
|---|---|---|---|
| 1 | `mini60.py:687` RMW race — concurrent table ops clobber | HIGH | A: no span-lock across RMW |
| 2 | `device_state.py:279` `read_actuation` reads raw handle unlocked | HIGH | B: raw handle access bypasses the inner lock |
| 3 | `app_web.py:578` `disconnect()` abandons calibration | HIGH | C: teardown contract incomplete |
| 4 | `device_state.py:169` `LiveReader` spins on dead handle | MED | C: no dead-handle self-teardown |
| 5 | `device_state.py:231` `CalibrationReader` spins on dead handle | MED | C: same |
| 6 | `app_web.py:578` `disconnect()` orphans readers onto closed handle | MED | C: same teardown gap as #3 |
| 7 | `app_web.py:946` gamepad-off leaves `LiveReader` running | LOW | C: reader ownership not tracked |

## Proposed model

### Fix A — RMW atomicity via a reentrant outer lock + explicit transaction (defect 1)

1. Promote the **outer** lock to `threading.RLock()` (`app_web.py:365`, and the `base.py:70`
   standalone fallback). The inner `AulaDevice._lock` stays a plain `Lock` (it's only ever taken
   for a single leaf I/O, never re-entered).
2. Add `BoardDriver.transaction()` → `return self._lock` as a context manager (it already *is* the
   RLock; this just names the intent). RMW methods wrap their whole read→modify→write body in
   `with self.transaction():`. Because the lock is now reentrant, the nested per-frame `_write`/read
   calls re-acquire it harmlessly, and no other op can interleave.
3. Apply to every RMW site in the drivers: `_patch_key_records`, `set_key_remap`,
   `set_advanced_socd`/`set_socd`, `set_actuation`, `write_macro`, `set_advanced_dks`, `set_deadband`.
   `stream_frame` already span-locks and is unaffected.

**Why reentrant, not a second lock:** a separate "operation lock" adds a new lock-ordering edge and
new deadlock surface. Re-entering the *existing* outer lock preserves the single outer→inner order and
is the minimal change. Cost: an RMW op now holds the outer lock for its whole duration (tens–hundreds
of ms), briefly blocking the effect-stream thread. Acceptable — RMW ops are user-initiated config
writes on the cold path, not the 60fps hot path, and correctness beats a few ms of streaming jitter.

### Fix B — all raw-handle I/O through the inner lock + single-active-reader (defect 2)

1. Add `AulaDevice.set_nonblocking(flag)` that locks and forwards to `_dev`. Route
   `device_state.read_actuation` through `device.read(...)` and `device.set_nonblocking(...)` — **no
   direct `device._dev` access anywhere.** After this, every raw-handle touch is inner-lock-guarded,
   so no torn/interleaved reports at the byte level.
2. Byte-safety isn't enough on its own: a verify sweep and a `LiveReader` both consuming reports from
   one handle still steal each other's frames. Enforce a **single active handle-reader** invariant
   (Fix C's ownership model): the verify sweep acquires the reader slot for its duration, so the live
   reader is paused, not competing. Lock-ordering stays safe — the sweep takes outer+inner (in order),
   the live reader takes inner only, and it never runs *during* the sweep.

### Fix C — one teardown contract (defects 3–7)

1. **Central `_stop_readers()`** on the Api: stop → join → `None` both `self.reader` and
   `self.calib_reader`. `disconnect()` and `select_board()` both call it (select_board already does
   the equivalent inline; factor it out).
2. **`disconnect()` order becomes:** stop effect engine → stop gamepad → **disarm calibration if
   armed** (`set_calibration(False)`, best-effort) → **`_stop_readers()`** → `dev.close()`. Readers and
   calibration are torn down *before* the handle closes, so threads exit cleanly and the firmware
   leaves calibration mode.
3. **Calibration re-arm guarantee.** Track `self._calibrating`. `calibrate(start=True)` sets it inside
   a `try`; any abort disarms: the exception path via `try/finally` in `calibrate`, the user-abort
   path via `disconnect()` checking `self._calibrating`. The board is never left wiped-and-armed.
4. **Reader dead-handle self-teardown.** Both readers' `_run()` loops gain a liveness check: if the
   handle is closed (`dev._dev is None`) or reads raise persistently (N consecutive failures), the
   loop **exits** instead of spinning. Defensive backstop so an unplug (or a missed teardown path)
   can't leave a thread burning ~20Hz forever. `CalibrationReader` exiting on a dead handle is
   correct — the session was aborted; `done` staying false is the honest outcome.
5. **Reader ownership set** (fixes #7 cleanly and prevents future leaks). `self._reader_users:set`.
   Consumers `_acquire_reader(who)` / `_release_reader(who)`; the reader starts on first acquire and
   `_stop_readers()`-style stops when the set empties. Owners: `"analog"` (Actuation tab),
   `"reactive"` (press-reactive effects), `"gamepad"` (capture). `set_gamepad_capture(False)` releases
   `"gamepad"`; the reader stops only if no other owner remains. `disconnect()` clears the set.

## Deadlock analysis

- Only two locks; single ordering **outer → inner**, never reversed. Reader threads take inner only,
  so they can never hold inner while waiting on outer.
- Making the outer lock reentrant removes the self-deadlock (RMW body holding outer, then `_write`
  re-taking outer) without adding any new lock or edge.
- The verify sweep holds outer across its span and takes inner per I/O (outer→inner) — same order as
  every frame write. Because the single-active-reader invariant means no `LiveReader` runs during the
  sweep, there is no inner-lock contention that could interact with a held outer lock.

## Implementation checklist (mapped to defects + tests)

- [ ] Outer lock → `RLock`; add `transaction()`; wrap RMW methods. **(1)** — test: two threads RMW the
      same key table concurrently, assert both edits survive (currently one is lost).
- [ ] `AulaDevice.set_nonblocking`; route `read_actuation` through locked methods. **(2)** — test: a
      `LiveReader` running while `read_actuation` sweeps → no exception, no torn report (stub handle
      asserting no concurrent `_dev` access).
- [ ] `_stop_readers()`; rewrite `disconnect()` to the contract order; `_calibrating` + disarm-on-abort.
      **(3,6)** — test: calibrate → disconnect asserts `set_calibration(False)` was sent and both
      readers stopped.
- [ ] Reader dead-handle self-teardown in both `_run()` loops. **(4,5)** — test: close the handle
      under a running reader → thread exits within a bounded time (not spinning).
- [ ] Reader ownership set. **(7)** — test: gamepad-off with no other owner stops the reader; with the
      analog tab open, it keeps running.

## Risk / tradeoffs

- **RLock hold time** on RMW ops briefly blocks the effect stream — measured in ms, cold path, fine.
- **Ownership set** is the one net-new mechanism; keep it tiny (a `set[str]` + two helpers) to avoid
  its own bugs. If it proves fiddly, the minimum viable fix for #7 is deferring to the central
  teardown (accept the LOW leak during a live session) — but the set is cheap and prevents recurrence.
- All changes are Win60-and-mini60 symmetric; verify both drivers' `stream_frame`/read paths still hold.
- Hardware smoke test required (the Aula is plugged into this machine): calibrate→disconnect, unplug
  mid-travel-test, concurrent remap+SOCD apply. Unit tests use the existing stub-handle harness.
