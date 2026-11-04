"""Key statistics (roadmap Phase 1): per-key, per-day aggregates built from
the live travel stream.

PRIVACY ANTI-GOAL: Aether must never become a keylogger. This module keeps
per-key COUNTERS only (presses, bottom-outs, a 34-bin peak-depth histogram,
shallow attempts, barely-over presses, summed time-to-peak). It never stores
or transmits key sequences, text, or per-keystroke timestamps; the only times
it looks at are the two ends of one press, and only their difference survives.

Press segmentation (integer hundredths of a millimetre, ``raw = round(mm*100)``):
  * A run starts at the first sample >= NOISE_RAW (0.05 mm) for a key with no
    open run and ends at a sample < NOISE_RAW. LiveReader reports its
    release-silence clear as a sample of 0.0, so that is the same rule.
  * Re-press split: when the depth has fallen >= REPRESS_RAW below the run's
    peak and then rises >= REPRESS_RAW above that trough, the run is closed at
    its peak and a new one starts (rapid re-press without a full release).
  * Runs peaking <= ATTEMPT_MIN_RAW (0.15 mm) are touch/noise and dropped.
  * Every other run goes into hist[min(33, raw // 10)]. With the key's
    actuation known: peak < act -> ``shallow`` only; otherwise ``presses``
    (+ ``barely`` when peak <= act + BARELY_RAW). With it unknown: ``presses``
    and ``unrated``. Every press adds its (capped) time-to-peak to ``ttp_ms``.
    Any run (press or shallow) peaking at BOTTOM_RAW or more also counts
    ``bottom``.
  Invariant: sum(hist) == presses + shallow.

Actuation buckets (Phase 4): a run is filed under the actuation its key had
when the run ended, so one key's counters for one day are split per
actuation value. Day-file keys are ``"<idx>"`` for runs with the actuation
unknown (the "unrated" ones) and ``"<idx>@<act>"`` (act in 0.01 mm) for the
rest; in memory a bucket is ``idx`` or ``(idx, act)``. ``load_day`` and
``aggregate`` merge a key's buckets (the Phase 1 view); ``load_day_buckets``
and ``recent_buckets`` keep them apart so auto-tune can use only the presses
recorded at a key's CURRENT actuation. Files written before the split hold
only ``"<idx>"`` keys and load as the unknown-actuation bucket.
"""
import datetime
import json
import logging
import os
import re
import threading

log = logging.getLogger(__name__)

NOISE_RAW = 5
ATTEMPT_MIN_RAW = 15
BOTTOM_RAW = 330
BARELY_RAW = 10
REPRESS_RAW = 30
TTP_CAP_MS = 1000
HIST_BINS = 34
FIELDS = ("presses", "shallow", "barely", "bottom", "unrated", "ttp_ms")
FILE_VERSION = 1
KEEP_DAYS = 90
FLUSH_INTERVAL_S = 60.0


def empty_agg():
    d = {f: 0 for f in FIELDS}
    d["hist"] = [0] * HIST_BINS
    return d


def merge_agg(dst, src):
    """Add ``src`` into ``dst`` in place and return ``dst``."""
    for f in FIELDS:
        dst[f] += int(src.get(f, 0))
    h = src.get("hist")
    if h:
        for i in range(HIST_BINS):
            dst["hist"][i] += int(h[i])
    return dst


def _is_empty(agg):
    return not any(agg[f] for f in FIELDS) and not any(agg["hist"])


def peak_percentile(hist, q):
    """q-quantile (0..1) of the peak depth in mm, by linear interpolation
    inside the 0.1 mm bin; None when the histogram is empty."""
    total = sum(hist)
    if total <= 0:
        return None
    target = q * total
    cb = 0
    for i, c in enumerate(hist):
        if c > 0 and cb + c >= target:
            return round((i + (target - cb) / c) * 0.1, 2)
        cb += c
    return None


_KEY_RE = re.compile(r"^(\d{1,3})(?:@(\d{1,3}))?$")
_DAY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
_CLEAR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json(\.tmp)?$")


def bucket_idx(bucket):
    """Device index of an aggregate bucket (``idx`` or ``(idx, act)``)."""
    return bucket[0] if isinstance(bucket, tuple) else bucket


def _bucket_str(bucket):
    return (f"{bucket[0]}@{bucket[1]}" if isinstance(bucket, tuple)
            else str(bucket))


def _default_today():
    return datetime.date.today().isoformat()


class Telemetry:
    def __init__(self, root, *, enabled=True, board=None, today=None,
                 flush_interval_s=FLUSH_INTERVAL_S, keep_days=KEEP_DAYS):
        self._root = root
        self._enabled = bool(enabled)
        self._board = board
        self._today = today or _default_today
        self._flush_interval_s = flush_interval_s
        self._keep_days = int(keep_days)
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._open = {}      # idx -> [t_start, peak_raw, t_peak, trough_raw]
        self._act = {}       # idx -> actuation in hundredths of a mm
        self._pending = {}   # (date, board) -> {bucket: agg}
        self._flusher = None
        self._stop = threading.Event()

    # ---- state ---------------------------------------------------------
    @property
    def enabled(self):
        return self._enabled

    @property
    def board(self):
        return self._board

    def set_enabled(self, on):
        with self._lock:
            self._enabled = bool(on)
            if not self._enabled:
                self._open.clear()

    def set_board(self, slug):
        with self._lock:
            self._board = slug
            self._open.clear()
            self._act.clear()

    def set_actuation(self, mm_by_idx):
        with self._lock:
            for idx, mm in (mm_by_idx or {}).items():
                try:
                    v = float(mm)
                    if v != v or v in (float("inf"), float("-inf")) or v <= 0:
                        continue
                    self._act[int(idx)] = int(round(v * 100))
                except (TypeError, ValueError):
                    continue

    def actuation(self):
        """Copy of the read-back actuation map ({device index: 0.01 mm})."""
        with self._lock:
            return dict(self._act)

    def forget_actuation(self, idxs):
        with self._lock:
            for i in idxs or ():
                self._act.pop(int(i), None)

    def abort_open(self):
        """Drop in-flight presses (reader replaced / paused): never stuck."""
        with self._lock:
            self._open.clear()

    # ---- sample intake -------------------------------------------------
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

    def _record(self, idx, run):
        """Fold one finished run into the pending aggregates (lock held)."""
        t_start, peak, t_peak, _ = run
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
            agg["shallow"] += 1
        else:
            agg["presses"] += 1
            if act is None:
                agg["unrated"] += 1
            elif peak <= act + BARELY_RAW:
                agg["barely"] += 1
            agg["ttp_ms"] += min(TTP_CAP_MS, int(round((t_peak - t_start) * 1000)))
        self._ensure_flusher()

    def _ensure_flusher(self):
        """Start the daemon flusher on the first recorded run (lock held)."""
        if not self._flush_interval_s:
            return
        if self._flusher is not None and self._flusher.is_alive():
            return
        stop = threading.Event()
        self._stop = stop
        interval = self._flush_interval_s

        def loop():
            while not stop.wait(interval):
                self.flush()

        self._flusher = threading.Thread(target=loop, name="aether-stats-flush",
                                         daemon=True)
        self._flusher.start()

    # ---- storage -------------------------------------------------------
    def _path(self, date):
        return os.path.join(self._root, f"{date}.json")

    @staticmethod
    def _sanitise(rec):
        """Keep only the known counters; anything else never survives."""
        agg = empty_agg()
        if not isinstance(rec, dict):
            return agg
        for f in FIELDS:
            v = rec.get(f)
            agg[f] = v if type(v) is int and v >= 0 else 0
        h = rec.get("hist")
        if (isinstance(h, list) and len(h) == HIST_BINS
                and all(type(v) is int and v >= 0 for v in h)):
            agg["hist"] = list(h)
        return agg

    def _read_day(self, date):
        """board -> {bucket: agg} from the day file; {} when missing/corrupt."""
        try:
            with open(self._path(date), "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            return {}
        if not isinstance(doc, dict) or doc.get("version") != FILE_VERSION:
            return {}
        boards = doc.get("boards")
        if not isinstance(boards, dict):
            return {}
        out = {}
        for slug, keys in boards.items():
            if not isinstance(slug, str) or not isinstance(keys, dict):
                continue
            part = out.setdefault(slug, {})
            for k, rec in keys.items():
                m = _KEY_RE.match(k) if isinstance(k, str) else None
                if not m:
                    continue
                idx = int(m.group(1))
                bucket = idx if m.group(2) is None else (idx, int(m.group(2)))
                part[bucket] = self._sanitise(rec)
        return out

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

    def flush(self):
        """Write the pending deltas into their day files. True = nothing is
        left unwritten; False = a write failed (that delta is kept)."""
        with self._io_lock:
            with self._lock:
                snap, self._pending = self._pending, {}
            by_date = {}
            for (date, slug), keys in snap.items():
                by_date.setdefault(date, {})[slug] = keys
            ok = True
            failed = []
            todo = by_date
            try:
                if by_date:
                    os.makedirs(self._root, exist_ok=True)
            except OSError as e:
                log.warning("key statistics: cannot create %s: %s", self._root, e)
                ok = False
                failed = list(by_date)
                todo = {}
            for date, boards in todo.items():
                try:
                    cur = self._read_day(date)
                    for slug, keys in boards.items():
                        part = cur.setdefault(slug, {})
                        for b, a in keys.items():
                            merge_agg(part.setdefault(b, empty_agg()), a)
                    doc = {"version": FILE_VERSION, "date": date,
                           "boards": {slug: {_bucket_str(b): a
                                             for b, a in keys.items()}
                                      for slug, keys in cur.items()}}
                    path = self._path(date)
                    tmp = path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as fh:
                        fh.write(json.dumps(doc, sort_keys=True,
                                            separators=(",", ":")))
                    os.replace(tmp, path)
                except (OSError, ValueError) as e:
                    log.warning("key statistics: write %s failed: %s", date, e)
                    ok = False
                    failed.append(date)
            if failed:
                with self._lock:
                    for date in failed:
                        for slug, keys in by_date[date].items():
                            dst = self._pending.setdefault((date, slug), {})
                            for b, a in keys.items():
                                merge_agg(dst.setdefault(b, empty_agg()), a)
            self._prune()
            return ok

    def _prune(self):
        try:
            if not os.path.isdir(self._root):
                return
            today = datetime.date.fromisoformat(self._today())
            for name in os.listdir(self._root):
                m = _DAY_RE.match(name)
                if not m:
                    continue
                try:
                    d = datetime.date.fromisoformat(m.group(1))
                except ValueError:
                    continue
                if (today - d).days >= self._keep_days:
                    try:
                        os.remove(os.path.join(self._root, name))
                    except OSError:
                        pass
        except OSError:
            pass

    def clear(self):
        """Delete every day file and the in-memory counters. Returns the
        number of day files removed."""
        with self._io_lock:
            with self._lock:
                self._pending = {}
                self._open.clear()
            if not os.path.isdir(self._root):
                return 0
            try:
                names = os.listdir(self._root)
            except OSError:
                return 0
            n = 0
            for name in names:
                if not _CLEAR_RE.match(name):
                    continue
                try:
                    os.remove(os.path.join(self._root, name))
                    if name.endswith(".json"):
                        n += 1
                except OSError:
                    pass
            return n

    def close(self):
        self._stop.set()
        t = self._flusher
        if t is not None and t is not threading.current_thread():
            t.join(timeout=1.0)
        self.flush()

    # ---- reading -------------------------------------------------------

    def recent_buckets(self, days):
        """[(date, load_day_buckets(date)), ...] for the last `days` days
        (at least 1), newest first, today included."""
        today = datetime.date.fromisoformat(self._today())
        out = []
        for k in range(max(1, int(days))):
            d = (today - datetime.timedelta(days=k)).isoformat()
            out.append((d, self.load_day_buckets(d)))
        return out

    def aggregate(self, days=1):
        today = datetime.date.fromisoformat(self._today())
        out = {}
        for k in range(max(1, int(days))):
            d = (today - datetime.timedelta(days=k)).isoformat()
            for idx, a in self.load_day(d).items():
                merge_agg(out.setdefault(idx, empty_agg()), a)
        return {idx: a for idx, a in out.items() if not _is_empty(a)}
