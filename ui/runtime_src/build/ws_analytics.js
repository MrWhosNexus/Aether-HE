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
  const {
    useState,
    useEffect
  } = React;
  const KB = window.AetherKeyboard || {};
  const KeyboardPanel = KB.KeyboardPanel;
  const KB_ROWS = KB.KB_ROWS || [];
  const LABEL_OF_CODE = {};
  KB_ROWS.flat().forEach(([label, _u, code]) => {
    LABEL_OF_CODE[code] = label;
  });
  const RANGES = [{
    days: 1,
    label: "Today"
  }, {
    days: 7,
    label: "7 days"
  }, {
    days: 14,
    label: "14 days"
  }, {
    days: 30,
    label: "30 days"
  }];
  const POLL_MS = 5000;

  /* ===== shared store (widget frames are separate components) ===== */
  const store = {
    days: 1,
    analytics: null,
    // get_analytics result
    tune: null,
    // get_tune_suggestions result
    sel: new Set(),
    // selected design codes on the heatmap
    applying: null,
    // suggestion id being written
    lastApplied: null,
    // {s, codes, prev_mm} for Undo
    status: null,
    // {tone, msg}
    apiCall: null,
    users: 0,
    timer: null,
    inflight: false,
    again: false,
    // a refresh was asked for while one was in flight
    listeners: new Set()
  };
  const emit = () => store.listeners.forEach(fn => {
    try {
      fn();
    } catch (e) {}
  });
  const setStatus = (tone, msg) => {
    store.status = msg ? {
      tone,
      msg
    } : null;
    emit();
    if (msg) setTimeout(() => {
      if (store.status && store.status.msg === msg) {
        store.status = null;
        emit();
      }
    }, 6000);
  };
  const refreshAnalytics = async apiCall => {
    const call = apiCall || store.apiCall;
    if (!call) return;
    if (store.inflight) {
      store.again = true;
      return;
    }
    store.inflight = true;
    try {
      const [a, t] = await Promise.all([call("get_analytics", store.days), call("get_tune_suggestions")]);
      if (a && a.ok) store.analytics = a;
      if (t && t.ok) store.tune = t;
      emit();
    } finally {
      store.inflight = false;
      if (store.again) {
        store.again = false;
        refreshAnalytics(call);
      }
    }
  };
  const refreshTune = async apiCall => {
    const call = apiCall || store.apiCall;
    if (!call) return;
    const t = await call("get_tune_suggestions");
    if (t && t.ok) {
      store.tune = t;
      emit();
    }
  };
  const setDays = days => {
    store.days = days;
    emit();
    refreshAnalytics();
  };

  /* Subscribe a component to the store. While at least one subscriber is
     mounted the store refreshes every POLL_MS (day files are live: pending
     presses are merged in, so no flush is needed). */
  const useAnalytics = apiCall => {
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
        if (store.users <= 0) {
          store.users = 0;
          clearInterval(store.timer);
          store.timer = null;
        }
      };
    }, []);
    return store;
  };

  /* ===== heat colours: deep teal -> cyan -> amber -> red ===== */
  const HEAT_STOPS = [[0, [22, 50, 74]], [0.35, [31, 159, 180]], [0.7, [242, 184, 75]], [1, [255, 77, 94]]];
  const hex2 = v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0");
  const heatColor = t => {
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
  const heatLedMap = keys => {
    const out = {};
    Object.entries(keys || {}).forEach(([code, k]) => {
      const c = heatColor(k && k.heat);
      if (c) out[code] = c;
    });
    return out;
  };
  const topSuggestions = (tune, n) => (tune && Array.isArray(tune.suggestions) ? tune.suggestions : []).slice(0, n || 3);
  const fmtPct = v => v == null ? "–" : `${v.toFixed(1)}%`;
  const fmtMm = v => v == null ? "–" : `${v.toFixed(2)} mm`;
  const fmtInt = v => v == null ? "–" : Number(v).toLocaleString();

  /* ===== small shared bits ===== */
  const Label = ({
    children
  }) => /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--text-faint)] mb-1.5"
  }, children);
  const Note = ({
    children,
    tone
  }) => /*#__PURE__*/React.createElement("div", {
    className: `text-[11px] leading-relaxed ${tone === "warn" ? "text-amber-300/90" : tone === "bad" ? "text-rose-300/90" : "text-[var(--text-dim)]"}`
  }, children);
  const Btn = ({
    children,
    onClick,
    disabled,
    variant = "ghost",
    title
  }) => /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    disabled: disabled,
    title: title,
    className: `px-3 h-8 text-[10.5px] rounded-md border font-display uppercase tracking-[0.16em] transition-all
                ${disabled ? "border-[var(--line)] bg-white/[0.02] text-[var(--text-faint)] cursor-not-allowed" : variant === "primary" ? "border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25 shadow-[0_0_12px_var(--accent-glow)]" : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] hover:text-[var(--text)]"}`
  }, children);
  const Tile = ({
    label,
    value,
    hint
  }) => /*#__PURE__*/React.createElement("div", {
    className: "rounded-xl border border-[var(--line)] bg-white/[0.02] px-3 py-2 min-w-0",
    title: hint || ""
  }, /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[9px] uppercase tracking-[0.22em] text-[var(--text-faint)] truncate"
  }, label), /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[16px] text-[var(--text)] mt-0.5 truncate"
  }, value));
  const StatusLine = () => {
    const st = store.status;
    return /*#__PURE__*/React.createElement("div", {
      className: "h-4 text-[11px] font-mono tracking-[0.12em] truncate"
    }, st && /*#__PURE__*/React.createElement("span", {
      className: st.tone === "ok" ? "text-[var(--accent)]" : st.tone === "warn" ? "text-amber-300/90" : "text-rose-300/90"
    }, st.msg));
  };
  /* Collection off / board without a travel stream: say so instead of zeros. */
  const DataGate = ({
    children
  }) => {
    const a = store.analytics;
    if (a && a.supported === false) return /*#__PURE__*/React.createElement(Note, {
      tone: "warn"
    }, "Analytics need a board with a live travel stream (Aula Win60 HE).");
    if (a && a.enabled === false) return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-2"
    }, /*#__PURE__*/React.createElement(Note, {
      tone: "warn"
    }, "Key statistics are off, so nothing new is being counted. Turn on \"Collect key statistics\" in Settings to fill these views."), children);
    return children;
  };

  /* ===== Heatmap ===== */
  const HeatLegend = () => /*#__PURE__*/React.createElement("div", {
    className: "flex flex-col items-end gap-1"
  }, /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
  }, "more"), /*#__PURE__*/React.createElement("span", {
    className: "w-2 h-24 rounded-full",
    style: {
      background: "linear-gradient(to top, #16324a, #1f9fb4, #f2b84b, #ff4d5e)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
  }, "fewer"));
  /* Reusable board: colours each key by its share of presses. `keys` is
     get_analytics().keys. Selection is the Analytics store's unless given. */
  const HeatmapBoard = ({
    keys,
    selectedKeys,
    setSelectedKeys,
    leftSlot
  }) => {
    if (!KeyboardPanel) return /*#__PURE__*/React.createElement(Note, {
      tone: "bad"
    }, "Keyboard view failed to load.");
    const sel = selectedKeys || store.sel;
    const setSel = setSelectedKeys || (upd => {
      store.sel = typeof upd === "function" ? upd(store.sel) : upd;
      emit();
    });
    return /*#__PURE__*/React.createElement(KeyboardPanel, {
      mode: "lighting",
      layer: "default",
      showPill: false,
      selectedKeys: sel,
      setSelectedKeys: setSel,
      ledMap: heatLedMap(keys),
      leftSlot: leftSlot || null,
      rightSlot: /*#__PURE__*/React.createElement(HeatLegend, null)
    });
  };
  function HeatmapWidget(ctx) {
    const s = useAnalytics(ctx.apiCall);
    const a = s.analytics;
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-3 h-full"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 flex-wrap"
    }, RANGES.map(r => /*#__PURE__*/React.createElement("button", {
      key: r.days,
      onClick: () => setDays(r.days),
      className: `px-3 h-7 rounded-lg font-display text-[11px] uppercase tracking-[0.16em] transition-all
                        ${s.days === r.days ? "bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]" : "text-[var(--text-dim)] hover:text-[var(--text)] border border-[var(--line)]"}`
    }, r.label)), /*#__PURE__*/React.createElement("span", {
      className: "ml-auto font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
    }, a ? `${fmtInt(a.totals && a.totals.presses)} presses` : "loading…")), /*#__PURE__*/React.createElement(DataGate, null, /*#__PURE__*/React.createElement(HeatmapBoard, {
      keys: a && a.keys
    }), /*#__PURE__*/React.createElement(Note, null, "Click a key to see its numbers in Overview; Ctrl-click to add keys. Colour = share of presses against the busiest key.")));
  }

  /* ===== Overview: board totals, or the selected keys summed ===== */
  const sumKeys = (keys, codes) => {
    const t = {
      presses: 0,
      shallow: 0,
      barely: 0,
      bottom: 0,
      unrated: 0,
      attempts: 0,
      peakSum: 0,
      peakN: 0
    };
    codes.forEach(c => {
      const k = keys[c];
      if (!k) return;
      t.presses += k.presses;
      t.shallow += k.shallow;
      t.barely += k.barely;
      t.bottom += k.bottom;
      t.unrated += k.unrated;
      t.attempts += k.attempts;
      if (k.avg_peak_mm != null) {
        t.peakSum += k.avg_peak_mm * k.attempts;
        t.peakN += k.attempts;
      }
    });
    const rated = Math.max(0, t.presses - t.unrated);
    const pct = (n, d) => d > 0 ? 100 * n / d : null;
    return {
      presses: t.presses,
      shallow: t.shallow,
      barely: t.barely,
      bottom_pct: pct(t.bottom, t.attempts),
      shallow_pct: pct(t.shallow, rated + t.shallow),
      barely_pct: pct(t.barely, rated),
      avg_peak_mm: t.peakN ? t.peakSum / t.peakN : null
    };
  };
  function OverviewWidget(ctx) {
    const s = useAnalytics(ctx.apiCall);
    const a = s.analytics;
    const keys = a && a.keys || {};
    const codes = Array.from(s.sel);
    const view = codes.length ? sumKeys(keys, codes) : a && a.totals || null;
    const name = codes.length === 0 ? "Whole board" : codes.length === 1 ? LABEL_OF_CODE[codes[0]] || codes[0] : `${codes.length} keys`;
    const range = (RANGES.find(r => r.days === s.days) || RANGES[0]).label;
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-3 h-full"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline gap-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-title text-[18px] text-[var(--text)]"
    }, name), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
    }, range), codes.length > 0 && /*#__PURE__*/React.createElement("button", {
      onClick: () => {
        store.sel = new Set();
        emit();
      },
      className: "ml-auto font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)] hover:text-[var(--text)]"
    }, "clear")), /*#__PURE__*/React.createElement(DataGate, null, /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-2"
    }, /*#__PURE__*/React.createElement(Tile, {
      label: "Presses",
      value: fmtInt(view && view.presses),
      hint: "Presses that went past the actuation point and typed."
    }), /*#__PURE__*/React.createElement(Tile, {
      label: "Bottom-out",
      value: fmtPct(view && view.bottom_pct),
      hint: "Presses that reached 3.30 mm or deeper."
    }), /*#__PURE__*/React.createElement(Tile, {
      label: "Avg peak",
      value: fmtMm(view && view.avg_peak_mm),
      hint: "Average deepest point of a press, missed presses included."
    }), /*#__PURE__*/React.createElement(Tile, {
      label: "Shallow",
      value: view ? `${fmtInt(view.shallow)} · ${fmtPct(view.shallow_pct)}` : "–",
      hint: "Presses that stopped before the actuation point, so nothing typed."
    }), /*#__PURE__*/React.createElement(Tile, {
      label: "Barely over",
      value: view ? `${fmtInt(view.barely)} · ${fmtPct(view.barely_pct)}` : "–",
      hint: "Presses that typed but went less than 0.10 mm past the actuation point."
    })), /*#__PURE__*/React.createElement(Note, null, "Shallow = the key moved more than 0.15 mm but stopped before its actuation point, so nothing typed. Barely over = it typed, but by less than 0.10 mm. Percentages count only presses recorded while Aether knew the key's actuation.")));
  }

  /* ===== Presses per day (14 days) ===== */
  const DailyBars = ({
    daily,
    height = 120
  }) => {
    const rows = Array.isArray(daily) ? daily : [];
    const top = Math.max(1, ...rows.map(r => r.presses || 0));
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-1"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-end gap-1",
      style: {
        height
      }
    }, rows.map(r => /*#__PURE__*/React.createElement("div", {
      key: r.date,
      className: "flex-1 h-full flex flex-col justify-end",
      title: `${r.date}: ${r.presses} presses, ${r.shallow} shallow, ${r.bottom} bottom-outs`
    }, /*#__PURE__*/React.createElement("div", {
      className: "w-full rounded-t-sm bg-[var(--accent)]/70",
      style: {
        height: `${Math.max(r.presses ? 2 : 0, 100 * r.presses / top)}%`
      }
    })))), /*#__PURE__*/React.createElement("div", {
      className: "flex justify-between font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
    }, /*#__PURE__*/React.createElement("span", null, rows.length ? rows[0].date.slice(5) : ""), /*#__PURE__*/React.createElement("span", null, "today")));
  };
  function DailyWidget(ctx) {
    const s = useAnalytics(ctx.apiCall);
    const a = s.analytics;
    const daily = a && a.daily || [];
    const total = daily.reduce((n, r) => n + (r.presses || 0), 0);
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-3 h-full"
    }, /*#__PURE__*/React.createElement(Label, null, "Presses per day \xB7 last 14 days \xB7 ", fmtInt(total), " total"), /*#__PURE__*/React.createElement(DataGate, null, /*#__PURE__*/React.createElement(DailyBars, {
      daily: daily
    })));
  }

  /* ===== Auto-tune suggestions ===== */
  /* compact (the Phase 5 dashboard): the detail note becomes one truncated
     line with the full text as its tooltip, so three cards fit one panel. */
  const SuggestionCard = ({
    s,
    onApply,
    disabled,
    busy,
    compact
  }) => /*#__PURE__*/React.createElement("div", {
    className: `rounded-xl border border-[var(--line)] bg-white/[0.02] flex flex-col ${compact ? "px-3 py-2 gap-1" : "p-3 gap-1.5"}`,
    "data-tune-card": s.id
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-2"
  }, /*#__PURE__*/React.createElement("span", {
    className: `font-mono text-[9px] uppercase tracking-[0.2em] px-1.5 py-0.5 rounded border
                        ${s.direction === "shallower" ? "border-[var(--accent)]/40 text-[var(--accent)]" : "border-amber-400/40 text-amber-300"}`
  }, s.direction === "shallower" ? "earlier" : "later"), /*#__PURE__*/React.createElement("span", {
    className: "text-[12.5px] text-[var(--text)] flex-1 min-w-0 truncate",
    title: s.title
  }, s.title), onApply && /*#__PURE__*/React.createElement(Btn, {
    variant: "primary",
    onClick: () => onApply(s),
    disabled: disabled,
    title: `Write ${s.suggested_mm.toFixed(2)} mm to ${s.codes.length} key(s), then read it back`
  }, busy ? "Applying…" : "Apply")), compact ? /*#__PURE__*/React.createElement("div", {
    className: "text-[11px] text-[var(--text-dim)] truncate",
    title: s.detail
  }, s.detail) : /*#__PURE__*/React.createElement(Note, null, s.detail), !compact && /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[10px] text-[var(--text-faint)]"
  }, `${fmtInt(s.presses)} presses at ${s.current_mm.toFixed(2)} mm · ${s.codes.length} key${s.codes.length === 1 ? "" : "s"}`));

  /* Apply through the normal Actuation Apply path (ctx.applyTuneSuggestion =
     app.jsx writeActuation: set_trigger_codes, then verify_actuation). */
  const applySuggestion = async (ctx, s) => {
    if (!ctx || !ctx.applyTuneSuggestion || store.applying) return;
    store.applying = s.id;
    emit();
    try {
      const r = await ctx.applyTuneSuggestion(s);
      if (r && r.ok) {
        store.lastApplied = {
          s
        };
        setStatus("ok", `${s.label}: ${s.suggested_mm.toFixed(2)} mm written and read back`);
      } else {
        setStatus("bad", `Not applied: ${r && r.error || "no reply"}`);
      }
    } finally {
      store.applying = null;
      emit();
      refreshAnalytics(ctx.apiCall);
    }
  };
  const undoLast = async ctx => {
    const last = store.lastApplied;
    if (!last || !ctx || !ctx.applyTuneSuggestion || store.applying) return;
    const back = Object.assign({}, last.s, {
      id: last.s.id + ":undo",
      suggested_mm: last.s.current_mm
    });
    store.applying = back.id;
    emit();
    try {
      const r = await ctx.applyTuneSuggestion(back);
      if (r && r.ok) {
        store.lastApplied = null;
        setStatus("ok", `${last.s.label}: back to ${last.s.current_mm.toFixed(2)} mm`);
      } else {
        setStatus("bad", `Undo failed: ${r && r.error || "no reply"}`);
      }
    } finally {
      store.applying = null;
      emit();
      refreshAnalytics(ctx.apiCall);
    }
  };

  /* Reusable list: `limit` = 3 gives the Phase 5 dashboard's top-3. */
  const SuggestionList = ({
    ctx,
    limit,
    compact
  }) => {
    const s = useAnalytics(ctx && ctx.apiCall);
    const t = s.tune;
    const list = topSuggestions(t, limit || 99);
    const connected = !!(ctx && ctx.connected);
    if (!t) return /*#__PURE__*/React.createElement(Note, null, "Loading\u2026");
    if (t.supported === false) return /*#__PURE__*/React.createElement(Note, {
      tone: "warn"
    }, "Auto-tune needs a board with a live travel stream.");
    if (!list.length) return /*#__PURE__*/React.createElement(Note, null, !connected ? "Connect the keyboard: suggestions use the actuation read back from it." : !t.read_back ? "Waiting for the actuation read-back from the keyboard." : `No suggestions. Each key or group needs ${t.min_presses} presses at its current actuation in the last ${t.window_days} days.`);
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-2"
    }, list.map(x => /*#__PURE__*/React.createElement(SuggestionCard, {
      key: x.id,
      s: x,
      busy: s.applying === x.id,
      compact: !!compact,
      disabled: !connected || !!s.applying,
      onApply: sg => applySuggestion(ctx, sg)
    })));
  };
  function TuneWidget(ctx) {
    const s = useAnalytics(ctx.apiCall);
    const t = s.tune;
    const notes = t && Array.isArray(t.notes) ? t.notes : [];
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-3 h-full min-h-0"
    }, /*#__PURE__*/React.createElement(Note, null, "Suggestions only: nothing is written until you click Apply. Apply writes the new actuation to those keys and reads it back, like Apply in the Actuation tab. A game profile that switches in later sets every key to its own value."), s.lastApplied && /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 rounded-md border border-[var(--line)] bg-white/[0.02] px-2 py-1.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-[11px] text-[var(--text-dim)] flex-1 truncate"
    }, `Applied: ${s.lastApplied.s.label} ${s.lastApplied.s.suggested_mm.toFixed(2)} mm (was ${s.lastApplied.s.current_mm.toFixed(2)} mm)`), /*#__PURE__*/React.createElement(Btn, {
      onClick: () => undoLast(ctx),
      disabled: !ctx.connected || !!s.applying
    }, "Undo")), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 min-h-0 overflow-y-auto flex flex-col gap-3"
    }, /*#__PURE__*/React.createElement(SuggestionList, {
      ctx: ctx
    }), notes.length > 0 && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Label, null, "Notes"), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-1"
    }, notes.map(n => /*#__PURE__*/React.createElement(Note, {
      key: n.id
    }, n.text))))), /*#__PURE__*/React.createElement(StatusLine, null));
  }
  const ANALYTICS_WIDGETS = [{
    id: "heatmap",
    title: "Key Heatmap",
    default: {
      x: 40,
      y: 32,
      w: 820,
      h: 400
    },
    min: {
      w: 560,
      h: 320
    },
    render: HeatmapWidget
  }, {
    id: "overview",
    title: "Overview",
    default: {
      x: 880,
      y: 32,
      w: 380,
      h: 400
    },
    min: {
      w: 300,
      h: 300
    },
    render: OverviewWidget
  }, {
    id: "daily",
    title: "Presses per Day",
    default: {
      x: 40,
      y: 456,
      w: 520,
      h: 240
    },
    min: {
      w: 340,
      h: 200
    },
    render: DailyWidget
  }, {
    id: "tune",
    title: "Auto-tune",
    default: {
      x: 580,
      y: 456,
      w: 680,
      h: 420
    },
    min: {
      w: 420,
      h: 300
    },
    render: TuneWidget
  }];
  window.AetherWorkspaces = window.AetherWorkspaces || {};
  window.AetherWorkspaces.ANALYTICS_WIDGETS = ANALYTICS_WIDGETS;
  window.AetherAnalytics = {
    store,
    useAnalytics,
    refreshAnalytics,
    refreshTune,
    setDays,
    heatColor,
    heatLedMap,
    topSuggestions,
    HeatmapBoard,
    DailyBars,
    SuggestionCard,
    SuggestionList,
    applySuggestion
  };
})();