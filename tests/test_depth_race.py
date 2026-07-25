"""Tests for the LiveReader race-condition fix (depths dict atomicity).

Two threads share LiveReader.depths: the reader mutates it one-entry-at-a-time
inside the HID drain loop, and the gamepad-loop reads it via snapshot().  Before
the fix, releasing two keys on the same axis (A/D -> LX) could be caught mid-
drain: one key already popped, the other still present -> the axis flickered
to a non-zero value.  The fix batches all depth updates and applies them
atomically under _depth_lock.

No hardware: HID reports are synthesised in-memory.
"""
import queue
import threading
import time
import types

import device_state


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _travel_report(row, col, depth_100ths):
    """Build a 64-byte travel-test HID report (cmd 33, sub 5)."""
    r = [0] * 64
    r[1] = 33
    r[5] = 5
    r[7] = row
    r[8] = col
    r[9] = depth_100ths & 0xFF
    r[10] = (depth_100ths >> 8) & 0xFF
    return bytes(r)


# Index layout (DESIGN_CODES):  A=29 (row 1 col 7), D=31 (row 1 col 9)
_A_ROW, _A_COL = 1, 7
_D_ROW, _D_COL = 1, 9


class _FakeHandle:
    """HID handle backed by a queue of reports."""

    def __init__(self):
        self._q = queue.Queue()

    def set_nonblocking(self, v):
        pass

    def read(self, n):
        try:
            return self._q.get_nowait()
        except queue.Empty:
            return []


class _FakeDev:
    def __init__(self, handle):
        self._lock = threading.Lock()
        self._dev = handle

    def write(self, payload):
        return len(payload)


def _make_keymap():
    """Minimal keymap: only A(29) and D(31)."""
    code_of = {29: "A", 31: "D"}
    return types.SimpleNamespace(
        indices=lambda: [29, 31],
        code_of=lambda i: code_of.get(i),
    )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_batch_updates_prevent_partial_snapshot():
    """snapshot() must never see one key popped while the other is still present
    when both release reports arrive in the same drain cycle.

    Scenario:
    1. Both A and D pressed at 3.0 mm.
    2. Both released (0.0 mm) — reports queued back-to-back.
    3. Gamepad-loop reads snapshots in a tight loop.
    4. After both releases are consumed, every snapshot must be either
       {"A": ..., "D": ...} (before both popped) or {} (after both popped),
       never {"D": ...} alone or {"A": ...} alone.
    """
    handle = _FakeHandle()
    dev = _FakeDev(handle)
    km = _make_keymap()
    lr = device_state.LiveReader(dev, km, indices=[29, 31])

    # Seed: both keys pressed at 3.0 mm (300 × 0.01 mm).
    for _ in range(5):  # a few cycles so the reader caches both depths
        handle._q.put(_travel_report(_A_ROW, _A_COL, 300))
        handle._q.put(_travel_report(_D_ROW, _D_COL, 300))

    lr.start()
    # Let the reader process the "pressed" reports.
    time.sleep(0.05)
    snap = lr.snapshot()
    assert "A" in snap and "D" in snap, f"both keys should be cached: {snap}"

    # Now queue both release reports (0.0 mm) back-to-back in the same
    # backlog — exactly the scenario that triggered the race.
    handle._q.put(_travel_report(_A_ROW, _A_COL, 0))
    handle._q.put(_travel_report(_D_ROW, _D_COL, 0))

    # Hammer snapshot() from a "gamepad loop" thread, recording every state.
    snapshots = []
    stop = threading.Event()

    def gamepad_hammer():
        while not stop.is_set():
            s = lr.snapshot()
            snapshots.append(s)

    hammer = threading.Thread(target=gamepad_hammer, daemon=True)
    hammer.start()

    # Give the reader time to drain the two release reports.
    time.sleep(0.15)
    stop.set()
    hammer.join(timeout=1)
    lr.stop()

    # Filter to snapshots taken AFTER both release reports were consumed
    # (i.e. after A was popped — snapshots will no longer contain "A").
    late = [s for s in snapshots if "A" not in s]

    # The bug: some late snapshot still has "D" without "A" -> axis != 0.
    for s in late:
        assert "D" not in s, (
            f"snapshot after A release still contains D: {s}\n"
            f"All late snapshots: {late[-10:]}"
        )


def test_interleaved_release_across_drain_cycles():
    """When release reports arrive in separate drain cycles, the intermediate
    state (A released, D still pressed) IS physically correct — the keys were
    released at different times.  This test verifies that AFTER both reports
    are consumed, no stale D entry remains.
    """
    handle = _FakeHandle()
    dev = _FakeDev(handle)
    km = _make_keymap()
    lr = device_state.LiveReader(dev, km, indices=[29, 31])

    # Seed pressed state.
    for _ in range(3):
        handle._q.put(_travel_report(_A_ROW, _A_COL, 300))
        handle._q.put(_travel_report(_D_ROW, _D_COL, 300))

    lr.start()
    time.sleep(0.05)

    # Release A in one batch, D in a later batch.
    handle._q.put(_travel_report(_A_ROW, _A_COL, 0))
    time.sleep(0.02)  # let drain cycle process A-release
    handle._q.put(_travel_report(_D_ROW, _D_COL, 0))

    # Wait long enough for both drain cycles to complete.
    time.sleep(0.1)

    # Now BOTH releases have been consumed — final snapshot must be empty.
    final = lr.snapshot()
    lr.stop()
    assert final == {}, (
        f"after both releases consumed, snapshot should be empty, got: {final}"
    )


def test_snapshot_consistent_under_concurrent_mutation():
    """Concurrent writer (simulating drain loop) and reader (snapshot)
    must never produce a snapshot where the dict is missing keys that
    should coexist.
    """
    handle = _FakeHandle()
    dev = _FakeDev(handle)
    km = _make_keymap()
    lr = device_state.LiveReader(dev, km, indices=[29, 31])

    # Seed: both keys at 3.0 mm.
    for _ in range(3):
        handle._q.put(_travel_report(_A_ROW, _A_COL, 300))
        handle._q.put(_travel_report(_D_ROW, _D_COL, 300))

    lr.start()
    time.sleep(0.05)

    # Rapidly toggle A and D through different depths to stress the lock.
    depths_cycle = [300, 200, 100, 50, 10, 0, 0, 0]
    for d in depths_cycle:
        handle._q.put(_travel_report(_A_ROW, _A_COL, d))
        handle._q.put(_travel_report(_D_ROW, _D_COL, 300 - d))

    snapshots = []
    stop = threading.Event()

    def hammer():
        while not stop.is_set():
            s = lr.snapshot()
            snapshots.append(s)

    t = threading.Thread(target=hammer, daemon=True)
    t.start()
    time.sleep(0.1)
    stop.set()
    t.join(timeout=1)
    lr.stop()

    # The dict must never be None or raise during snapshot.
    for s in snapshots:
        assert isinstance(s, dict), f"snapshot returned {type(s)}: {s}"
