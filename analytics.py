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
