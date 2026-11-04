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
