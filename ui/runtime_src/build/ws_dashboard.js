(() => {
  /* ============================================================
     Dashboard workspace (roadmap Phase 5): the landing page. ONE composed
     page on the fixed 1480 x 900 design canvas (app.jsx zooms it to the
     window, so it fits the 1160 x 800 minimum without scrolling):
  
       masthead   DASHBOARD · profile · date                 statistics pill
       row 1      hero keyboard (heatmap | live depth | actuation)  | rail:
                                                                     connection,
                                                                     profile + game,
                                                                     actuation
       row 2      today | auto-tune top 3 | lighting (+ status on keys)
  
     Exports window.AetherWorkspaces.DASHBOARD_PAGE (a component taking ctx as
     props; app.jsx renders it instead of a widget desktop) and
     window.AetherDashboard (pure helpers, unit-tested through node).
  
     Data: everything comes from ctx and the shared stores, so no second
     polling loop exists. Analytics = window.AetherAnalytics.useAnalytics
     (5 s, only while mounted); games = ctx.games (app.jsx's 2 s
     games_status poll); live depth = ctx.setLiveView(true) holds app.jsx's
     Travel Test stream (one "analog" reader owner) and is released when the
     hero leaves "live" or the page unmounts; actuation = ctx.perKeyActuation
     / ctx.perKeyTrigger (firmware read-back); lighting = ctx.pattern /
     ctx.setPattern (the same path as the tray panel).
     The only bridges called here are Phase 6's get_overlays / set_overlay,
     through ctx.apiCall; with no such bridge the tile is not rendered.
  
     Privacy: counters only (see analytics.jsx); nothing here stores keys.
     ============================================================ */
  const {
    useState,
    useEffect,
    useMemo
  } = React;
  const KB = window.AetherKeyboard || {};
  const KeyboardPanel = KB.KeyboardPanel;
  const KB_ROWS = KB.KB_ROWS || [];
  const ALL_CODES = KB_ROWS.flat().map(r => r[2]);
  const LABEL_OF_CODE = {};
  KB_ROWS.flat().forEach(([label, _u, code]) => {
    LABEL_OF_CODE[code] = label;
  });

  // analytics.jsx loads before this file, lighting.jsx after it (build order is
  // alphabetical), so both are read when used, never at module load.
  const AN = () => window.AetherAnalytics || null;
  const LB = () => window.AetherWorkspaces && window.AetherWorkspaces.LIGHTING_BOARD || null;
  const useAnalyticsStore = window.AetherAnalytics && window.AetherAnalytics.useAnalytics || (() => null);
  const HERO_KEY = "aether-dash-hero";
  const OVERLAY_POLL_MS = 2000;
  const HERO_MODES = [{
    id: "heatmap",
    label: "Heatmap"
  }, {
    id: "live",
    label: "Live depth"
  }, {
    id: "actuation",
    label: "Actuation"
  }];
  const HEAT_GRADIENT = "linear-gradient(to top, #16324a, #1f9fb4, #f2b84b, #ff4d5e)";
  const ACT_GRADIENT = "linear-gradient(to top, hsl(180 80% 55%), hsl(99 80% 55%), hsl(27 80% 55%))";

  /* ===== pure helpers (window.AetherDashboard) ===== */
  // isSupported = ctx.board.isSupported (fail-open without board data).
  const heroModesFor = isSupported => HERO_MODES.filter(m => m.id === "heatmap" ? isSupported("keyStats") : isSupported("actuation")).map(m => m.id);
  const pickHeroMode = (available, remembered) => available.includes(remembered) ? remembered : available[0] || null;

  // Firmware read-back -> KeyboardPanel perKeyOverride (as the Actuation tab).
  const perKeyOverrideOf = (act, trig) => {
    const out = {};
    const a = act || {},
      t = trig || {};
    new Set([...Object.keys(a), ...Object.keys(t)]).forEach(c => {
      const k = t[c];
      const rt = !!(k && k.mode && k.mode !== 0);
      out[c] = {
        actuation: a[c] != null ? a[c] : k ? k.travel_mm : undefined,
        rtPress: rt ? k.rt_press_mm : 0,
        rtRelease: rt ? k.rt_release_mm : 0
      };
    });
    return out;
  };

  // Read-back summary: null when nothing was read. groups = up to 3 most
  // common values (0.01 mm), most keys first.
  const actuationSummary = (act, trig, total) => {
    const vals = Object.values(act || {}).filter(v => typeof v === "number" && isFinite(v));
    if (!vals.length) return null;
    const counts = {};
    vals.forEach(v => {
      const k = v.toFixed(2);
      counts[k] = (counts[k] || 0) + 1;
    });
    const groups = Object.entries(counts).map(([mm, n]) => ({
      mm: +mm,
      n
    })).sort((x, y) => y.n - x.n || x.mm - y.mm);
    const sorted = vals.slice().sort((x, y) => x - y);
    const rt = Object.values(trig || {}).filter(k => k && k.mode && k.mode !== 0).length;
    return {
      keys: vals.length,
      total: total || vals.length,
      min: sorted[0],
      max: sorted[sorted.length - 1],
      uniform: groups.length === 1,
      distinct: groups.length,
      groups: groups.slice(0, 3),
      rt
    };
  };

  // get_analytics().daily always ends with today's row.
  const todayFrom = analytics => {
    const rows = analytics && Array.isArray(analytics.daily) ? analytics.daily : [];
    const d = rows.length ? rows[rows.length - 1] : null;
    if (!d) return null;
    const presses = d.presses || 0,
      shallow = d.shallow || 0,
      bottom = d.bottom || 0;
    const attempts = presses + shallow;
    return {
      date: d.date,
      presses,
      shallow,
      bottom,
      bottom_pct: attempts ? Math.round(1000 * bottom / attempts) / 10 : null
    };
  };

  // ctx.games (games_status view) -> {tone, text, sub}. Names are text only.
  const gameLine = (games, profiles) => {
    if (!games) return {
      tone: "dim",
      text: "Checking for games…",
      sub: ""
    };
    if (!games.available) return {
      tone: "dim",
      text: "Game detection unavailable",
      sub: "Windows only"
    };
    const pname = id => ((profiles || []).find(p => p.id === id) || {}).name;
    if (games.active) return {
      tone: "accent",
      text: games.active.name,
      sub: `playing · profile ${pname(games.active.profileId) || "of the game"}`
    };
    const det = Array.isArray(games.detected) ? games.detected : [];
    if (det.length) {
      const g = det.find(x => x.id === games.foreground) || det[0];
      return {
        tone: "text",
        text: g.name,
        sub: !g.mapped ? "running · not mapped to a profile" : games.autoSwitch ? "running · switching soon" : "running · auto-switch off"
      };
    }
    return {
      tone: "dim",
      text: "No game running",
      sub: games.autoSwitch ? "auto-switch on" : "auto-switch off"
    };
  };

  // get_overlays() result -> overlay list, or null = do not render the tile
  // (no bridge before Phase 6, an error, or supported:false).
  const overlayView = r => r && r.ok && r.supported !== false && Array.isArray(r.overlays) ? r.overlays.filter(o => o && typeof o.id === "string") : null;

  // Chip text: a running Pomodoro shows its phase and countdown, the sensors their load.
  const overlayText = o => {
    if (o.id === "pomodoro" && o.on && typeof o.remaining_s === "number") {
      const sec = Math.max(0, Math.floor(o.remaining_s));
      return `${o.phase === "break" ? "Break" : "Focus"} ${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
    }
    return `${o.label}${typeof o.value === "number" && o.id !== "pomodoro" ? ` ${Math.round(o.value * 100)}%` : ""}`;
  };
  const readHero = () => {
    try {
      return localStorage.getItem(HERO_KEY);
    } catch (e) {
      return null;
    }
  };
  const writeHero = m => {
    try {
      localStorage.setItem(HERO_KEY, m);
    } catch (e) {}
  };
  const fmtInt = v => v == null ? "–" : Number(v).toLocaleString();
  const fmtMm = v => v == null ? "–" : `${v.toFixed(2)} mm`;

  /* ===== shared bits (same grammar as the widget frames) ===== */
  const Panel = ({
    title,
    meta,
    children,
    className = "",
    bodyClass = "",
    id
  }) => /*#__PURE__*/React.createElement("section", {
    className: `glass flex flex-col min-h-0 overflow-hidden ${className}`,
    "data-dash-panel": id
  }, /*#__PURE__*/React.createElement("header", {
    className: "flex items-center gap-2 px-4 pt-3 pb-2.5 border-b border-[var(--line)] shrink-0"
  }, /*#__PURE__*/React.createElement("span", {
    className: "widget-dot",
    "aria-hidden": true
  }), /*#__PURE__*/React.createElement("span", {
    className: "font-title uppercase text-[16px] tracking-[0.04em] text-[var(--text)]"
  }, title), meta != null && meta !== "" && /*#__PURE__*/React.createElement("span", {
    className: "ml-auto font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)] truncate"
  }, meta)), /*#__PURE__*/React.createElement("div", {
    className: `flex-1 min-h-0 px-4 py-3 ${bodyClass}`
  }, children));
  const Label = ({
    children
  }) => /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[9.5px] uppercase tracking-[0.22em] text-[var(--text-faint)] mb-1"
  }, children);
  const Note = ({
    children,
    tone
  }) => /*#__PURE__*/React.createElement("div", {
    className: `text-[11px] leading-relaxed ${tone === "warn" ? "text-amber-300/90" : "text-[var(--text-dim)]"}`
  }, children);
  const LinkBtn = ({
    children,
    onClick
  }) => /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    className: "font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)] hover:text-[var(--accent)] transition-colors"
  }, children, " \u2192");
  const Chip = ({
    on,
    children,
    onClick,
    title,
    disabled
  }) => /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    title: title,
    disabled: disabled,
    className: `px-2.5 h-7 rounded-lg font-display text-[10.5px] uppercase tracking-[0.14em] truncate transition-all
                ${on ? "bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]" : "text-[var(--text-dim)] hover:text-[var(--text)] border border-[var(--line)] disabled:opacity-40"}`
  }, children);
  const Big = ({
    children,
    sub
  }) => /*#__PURE__*/React.createElement("div", {
    className: "flex items-baseline gap-2 min-w-0"
  }, /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[22px] leading-none text-[var(--text)] truncate"
  }, children), sub && /*#__PURE__*/React.createElement("span", {
    className: "text-[11px] text-[var(--text-dim)] truncate"
  }, sub));

  /* ===== hero: the keyboard ===== */
  const Legend = ({
    top,
    bottom,
    gradient
  }) => /*#__PURE__*/React.createElement("div", {
    className: "flex flex-col items-end gap-1"
  }, /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
  }, top), /*#__PURE__*/React.createElement("span", {
    className: "w-2 h-24 rounded-full",
    style: {
      background: gradient
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
  }, bottom));
  function Hero({
    ctx,
    store,
    modes,
    mode,
    setMode
  }) {
    const [focus, setFocus] = useState(() => new Set());
    const a = store && store.analytics;
    const keys = a && a.keys || {};
    const override = useMemo(() => perKeyOverrideOf(ctx.perKeyActuation, ctx.perKeyTrigger), [ctx.perKeyActuation, ctx.perKeyTrigger]);
    const depths = ctx.liveDepths || {};
    const deepest = Math.max(0, ...Object.values(depths).map(v => +v || 0));
    const An = AN();
    const today = todayFrom(a);
    const panelMode = mode === "heatmap" ? "lighting" : mode === "actuation" ? "actuation" : "keymap";
    const meta = mode === "heatmap" ? a && a.supported === false ? "" : today ? `today · ${fmtInt(today.presses)} presses` : "loading…" : mode === "live" ? ctx.connected ? `live · deepest ${(deepest < 0.05 ? 0 : deepest).toFixed(2)} mm` : "offline" : mode === "actuation" ? ctx.connected ? Object.keys(override).length ? `read back · ${Object.keys(override).length} keys` : "reading…" : "offline · not from the board" : "";
    const codes = Array.from(focus);
    const c = codes.length === 1 ? codes[0] : null;
    let caption;
    if (mode === "heatmap" && a && a.enabled === false) caption = /*#__PURE__*/React.createElement("span", {
      className: "text-amber-300/90"
    }, "Key statistics are off, so nothing new is counted. Turn them on in Settings.");else if (mode === "live" && !ctx.connected) caption = "Connect the keyboard to see how deep each key goes.";else if (c) {
      const k = keys[c];
      const o = override[c];
      const parts = [LABEL_OF_CODE[c] || c];
      if (k) parts.push(`${fmtInt(k.presses)} presses today`, `${k.bottom_pct == null ? "–" : k.bottom_pct.toFixed(1) + "%"} bottom-out`);
      if (o && o.actuation != null) parts.push(`actuates at ${o.actuation.toFixed(2)} mm${o.rtPress ? " · rapid trigger" : ""}`);
      if (mode === "live") parts.push(`now ${((depths[c] || 0) < 0.05 ? 0 : depths[c]).toFixed(2)} mm`);
      caption = parts.join(" · ");
    } else if (codes.length > 1) {
      const n = codes.reduce((s, x) => s + (keys[x] && keys[x].presses || 0), 0);
      caption = `${codes.length} keys · ${fmtInt(n)} presses today`;
    } else {
      caption = mode === "heatmap" ? "Colour = share of today's presses against the busiest key. Click a key for its numbers." : mode === "live" ? "Press any key: the fill is its travel, the glow means it went past its actuation point." : mode === "actuation" ? "Each key's actuation point and rapid-trigger pair as the keyboard stores them." : "This board reports no travel or actuation data.";
    }
    const switcher = /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-1.5",
      "data-hero-modes": true
    }, modes.map(id => /*#__PURE__*/React.createElement(Chip, {
      key: id,
      on: mode === id,
      onClick: () => setMode(id)
    }, (HERO_MODES.find(m => m.id === id) || {}).label)));
    const sum = mode === "actuation" ? actuationSummary(ctx.perKeyActuation, ctx.perKeyTrigger, ALL_CODES.length) : null;
    const legend = mode === "heatmap" ? /*#__PURE__*/React.createElement(Legend, {
      top: "more",
      bottom: "fewer",
      gradient: HEAT_GRADIENT
    }) : mode === "actuation" ? /*#__PURE__*/React.createElement(Legend, {
      top: sum ? `${sum.max.toFixed(2)} later` : "later",
      bottom: sum ? `${sum.min.toFixed(2)} earlier` : "earlier",
      gradient: ACT_GRADIENT
    }) : mode === "live" ? /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col items-end gap-0.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
    }, "deepest"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[16px] text-[var(--accent)]"
    }, (deepest < 0.05 ? 0 : deepest).toFixed(2)), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
    }, "mm")) : null;
    return /*#__PURE__*/React.createElement(Panel, {
      id: "hero",
      title: "Keyboard",
      meta: meta,
      className: "relative",
      bodyClass: "relative flex flex-col justify-center gap-3"
    }, /*#__PURE__*/React.createElement("div", {
      "aria-hidden": true,
      className: "absolute -top-24 left-1/2 -translate-x-1/2 w-[720px] h-[300px] rounded-[50%] opacity-[0.16] pointer-events-none blur-3xl",
      style: {
        background: "var(--accent-gradient, var(--accent))"
      }
    }), typeof KeyboardPanel === "function" ? /*#__PURE__*/React.createElement(KeyboardPanel, {
      mode: panelMode,
      layer: "default",
      showPill: false,
      showFooter: false,
      selectedKeys: focus,
      setSelectedKeys: setFocus,
      ledMap: mode === "heatmap" && An ? An.heatLedMap(keys) : null,
      actuationPoint: typeof ctx.actuation === "number" ? ctx.actuation : 1.70,
      rtPress: 0,
      rtRelease: 0,
      perKeyOverride: mode === "heatmap" ? null : override,
      liveDepths: mode === "live" ? ctx.liveDepths : null,
      leftSlot: modes.length > 1 ? switcher : null,
      rightSlot: legend
    }) : /*#__PURE__*/React.createElement(Note, {
      tone: "warn"
    }, "Keyboard view failed to load."), /*#__PURE__*/React.createElement("div", {
      className: "relative h-5 text-center text-[11.5px] text-[var(--text-dim)] truncate",
      "data-hero-caption": true
    }, caption));
  }

  /* ===== rail: connection / profile + game / actuation ===== */
  function Rail({
    ctx
  }) {
    const board = ctx.board || {};
    const name = board.board && board.board.name || "Keyboard";
    const isSup = board.isSupported || (() => true);
    const state = ctx.pollRestarting ? "Restarting keyboard…" : ctx.connecting ? "Connecting…" : ctx.connected ? "Linked" : "Offline";
    const g = gameLine(ctx.games, ctx.profiles);
    const sum = actuationSummary(ctx.perKeyActuation, ctx.perKeyTrigger, ALL_CODES.length);
    const block = "px-4 py-3";
    return /*#__PURE__*/React.createElement("section", {
      className: "glass flex flex-col min-h-0 overflow-hidden",
      "data-dash-panel": "rail"
    }, /*#__PURE__*/React.createElement("div", {
      className: block,
      "data-dash-block": "connection"
    }, /*#__PURE__*/React.createElement(Label, null, "Connection"), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: `relative inline-block w-2 h-2 rounded-full pulse-ring ${ctx.connected ? "bg-[var(--good)] text-[var(--good)]" : "bg-[var(--text-faint)] text-[var(--text-faint)]"}`
    }), /*#__PURE__*/React.createElement("div", {
      className: "min-w-0 flex-1"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-title uppercase text-[17px] tracking-[0.04em] text-[var(--text)] truncate"
    }, name), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10.5px] text-[var(--text-dim)]"
    }, state, ctx.connected && ctx.polling ? ` · poll ${ctx.polling} kHz (${(1 / ctx.polling).toFixed(3)} ms)` : "")), /*#__PURE__*/React.createElement(Chip, {
      on: !ctx.connected,
      onClick: ctx.togglePair,
      disabled: !!ctx.connecting || !!ctx.pollRestarting
    }, ctx.connected ? "Disconnect" : "Pair"))), /*#__PURE__*/React.createElement("div", {
      className: `${block} border-t border-[var(--line)]`,
      "data-dash-block": "profile"
    }, /*#__PURE__*/React.createElement(Label, null, "Profile \xB7 game"), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-wrap gap-1.5 max-h-[64px] overflow-y-auto"
    }, (ctx.profiles || []).map(p => /*#__PURE__*/React.createElement(Chip, {
      key: p.id,
      on: p.id === ctx.activeId,
      onClick: () => ctx.switchProfile && ctx.switchProfile(p.id),
      title: `Switch to ${p.name}`
    }, p.name))), /*#__PURE__*/React.createElement("div", {
      className: "mt-2 flex items-baseline gap-2 min-w-0",
      "data-games-line": true
    }, /*#__PURE__*/React.createElement("span", {
      className: `text-[12.5px] truncate ${g.tone === "accent" ? "text-[var(--accent)]" : g.tone === "text" ? "text-[var(--text)]" : "text-[var(--text-dim)]"}`
    }, g.text), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-[var(--text-faint)] truncate"
    }, g.sub))), /*#__PURE__*/React.createElement("div", {
      className: `${block} border-t border-[var(--line)] flex-1 flex flex-col`,
      "data-dash-block": "actuation"
    }, /*#__PURE__*/React.createElement(Label, null, "Actuation \xB7 read back from the keyboard"), !isSup("actuation") ? /*#__PURE__*/React.createElement(Note, null, "This board has no adjustable actuation.") : !sum ? /*#__PURE__*/React.createElement(Note, null, ctx.connected ? "Reading from the keyboard…" : "Connect the keyboard to read its actuation back.") : /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-1.5"
    }, /*#__PURE__*/React.createElement(Big, {
      sub: sum.uniform ? sum.keys < sum.total ? `on ${sum.keys} of ${sum.total} keys` : `on all ${sum.keys} keys` : `${sum.distinct} values · ${sum.keys} keys`
    }, sum.uniform ? fmtMm(sum.min) : `${sum.min.toFixed(2)}–${sum.max.toFixed(2)} mm`), !sum.uniform && /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10.5px] text-[var(--text-dim)] truncate"
    }, sum.groups.map(x => `${x.mm.toFixed(2)} × ${x.n}`).join(" · "), sum.distinct > 3 ? " · …" : ""), /*#__PURE__*/React.createElement("div", {
      className: "text-[11px] text-[var(--text-dim)]"
    }, sum.rt ? `${sum.rt} key${sum.rt === 1 ? "" : "s"} in rapid trigger` : "Fixed actuation, no rapid trigger")), /*#__PURE__*/React.createElement("div", {
      className: "mt-auto pt-2"
    }, /*#__PURE__*/React.createElement(LinkBtn, {
      onClick: () => ctx.setSection("actuation")
    }, "Edit in Actuation"))));
  }

  /* ===== row 2 ===== */
  function TodayPanel({
    ctx,
    store
  }) {
    const a = store && store.analytics;
    const t = todayFrom(a);
    const An = AN();
    const unsupported = a && a.supported === false;
    return /*#__PURE__*/React.createElement(Panel, {
      id: "today",
      title: "Today",
      meta: t ? t.date : "",
      bodyClass: "flex flex-col gap-3"
    }, unsupported ? /*#__PURE__*/React.createElement(Note, null, "Typing statistics need a board with a live travel stream (Aula Win60 HE).") : !a ? /*#__PURE__*/React.createElement(Note, null, "Loading\u2026") : /*#__PURE__*/React.createElement(React.Fragment, null, a.enabled === false && /*#__PURE__*/React.createElement(Note, {
      tone: "warn"
    }, "Key statistics are off: nothing new is counted."), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-2"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Label, null, "Presses"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[22px] leading-none text-[var(--text)]"
    }, fmtInt(t && t.presses))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Label, null, "Bottom-out"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[22px] leading-none text-[var(--text)]"
    }, t && t.bottom_pct != null ? `${t.bottom_pct.toFixed(1)}%` : "–")), /*#__PURE__*/React.createElement("div", {
      title: "Presses that moved the key but stopped before its actuation point, so nothing typed."
    }, /*#__PURE__*/React.createElement(Label, null, "Shallow"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[22px] leading-none text-[var(--text)]"
    }, fmtInt(t && t.shallow)))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Label, null, "Last 14 days"), An && An.DailyBars ? /*#__PURE__*/React.createElement(An.DailyBars, {
      daily: a.daily,
      height: 64
    }) : null)), !unsupported && /*#__PURE__*/React.createElement("div", {
      className: "mt-auto"
    }, /*#__PURE__*/React.createElement(LinkBtn, {
      onClick: () => ctx.setSection(a && a.enabled === false ? "settings" : "analytics")
    }, a && a.enabled === false ? "Turn on in Settings" : "Open Analytics")));
  }
  function TunePanel({
    ctx,
    store
  }) {
    const An = AN();
    const st = store && store.status;
    const t = store && store.tune;
    return /*#__PURE__*/React.createElement(Panel, {
      id: "tune",
      title: "Auto-tune",
      meta: "top 3",
      bodyClass: "flex flex-col gap-2.5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-[11px] text-[var(--text-dim)] truncate",
      title: "Apply writes the new actuation to those keys and reads it back, like Apply in the Actuation tab."
    }, "Suggestions only: nothing is written until you click Apply."), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 min-h-0 overflow-y-auto"
    }, An && An.SuggestionList ? /*#__PURE__*/React.createElement(An.SuggestionList, {
      ctx: ctx,
      limit: 3,
      compact: true
    }) : /*#__PURE__*/React.createElement(Note, null, "Analytics failed to load.")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-3 h-4"
    }, /*#__PURE__*/React.createElement("span", {
      className: `flex-1 truncate font-mono text-[10.5px] ${st && st.tone === "ok" ? "text-[var(--accent)]" : "text-rose-300/90"}`
    }, st ? st.msg : ""), !(t && t.supported === false) && /*#__PURE__*/React.createElement(LinkBtn, {
      onClick: () => ctx.setSection("analytics")
    }, "All suggestions, notes and Undo")));
  }
  function LightingPanel({
    ctx
  }) {
    const board = ctx.board || {};
    const isSup = board.isSupported || (() => true);
    const L = LB();
    const grid = L && L.modeGridFor ? L.modeGridFor(board.lighting || null) : [];
    const idx = grid.findIndex(m => m.id === ctx.pattern);
    const cur = grid[idx] || {
      id: ctx.pattern,
      label: ctx.pattern,
      icon: ""
    };
    const step = d => {
      if (grid.length) ctx.setPattern(grid[(Math.max(0, idx) + d + grid.length) % grid.length].id);
    };
    return /*#__PURE__*/React.createElement(Panel, {
      id: "lighting",
      title: "Lighting",
      meta: ctx.connected ? "on the keyboard" : "applies when connected",
      className: "flex-1",
      bodyClass: "flex flex-col gap-2.5"
    }, !isSup("lighting") ? /*#__PURE__*/React.createElement(Note, null, "This board's lighting is not supported yet.") : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-[18px] w-6 text-center text-[var(--accent)]"
    }, cur.icon), /*#__PURE__*/React.createElement("span", {
      className: "font-title uppercase text-[20px] tracking-[0.04em] text-[var(--text)] flex-1 truncate",
      "data-current-effect": true
    }, cur.label), !ctx.power && /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] uppercase tracking-[0.18em] text-amber-300/90"
    }, "lights off"), /*#__PURE__*/React.createElement(Chip, {
      onClick: () => step(-1),
      title: "Previous effect"
    }, "\u2039"), /*#__PURE__*/React.createElement(Chip, {
      onClick: () => step(1),
      title: "Next effect"
    }, "\u203A")), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-4 gap-1.5 overflow-y-auto min-h-0",
      "data-effect-grid": true
    }, grid.map(m => /*#__PURE__*/React.createElement(Chip, {
      key: m.id,
      on: m.id === ctx.pattern,
      onClick: () => ctx.setPattern(m.id),
      title: m.label
    }, m.label)))));
  }

  /* Phase 6 plugs in here: rendered only when get_overlays answers ok with
     supported !== false (contract in docs/superpowers/plans/2026-11-04-phase-5-dashboard.md). */
  function OverlaysPanel({
    ctx
  }) {
    const [list, setList] = useState(null);
    useEffect(() => {
      let alive = true,
        timer = null;
      const load = () => ctx.apiCall("get_overlays").then(r => {
        if (!alive) return null;
        const v = overlayView(r);
        setList(prev => JSON.stringify(prev) === JSON.stringify(v) ? prev : v);
        return v;
      });
      load().then(v => {
        if (alive && v) timer = setInterval(() => {
          if (!document.hidden) load();
        }, OVERLAY_POLL_MS);
      });
      return () => {
        alive = false;
        if (timer) clearInterval(timer);
      };
    }, [ctx.connected]);
    if (!list || !list.length) return null;
    const toggle = o => ctx.apiCall("set_overlay", o.id, !o.on).then(r => {
      if (r && r.ok) setList(l => (l || []).map(x => x.id === r.id ? {
        ...x,
        on: !!r.on
      } : x));
    });
    return /*#__PURE__*/React.createElement(Panel, {
      id: "overlays",
      title: "Status on keys",
      meta: "",
      bodyClass: "grid grid-cols-2 gap-1.5 content-start"
    }, list.map(o => /*#__PURE__*/React.createElement(Chip, {
      key: o.id,
      on: !!o.on,
      disabled: o.available === false,
      onClick: () => toggle(o),
      title: o.available === false ? o.reason || "unavailable" : `${o.label} on the ${o.row || "keys"}`
    }, overlayText(o))));
  }

  /* ===== the page ===== */
  function DashboardPage(ctx) {
    const store = useAnalyticsStore(ctx.apiCall);
    const isSup = ctx.board && ctx.board.isSupported || (() => true);
    const modes = heroModesFor(isSup);
    const [pref, setPref] = useState(() => readHero());
    const mode = pickHeroMode(modes, pref);
    const setMode = m => {
      setPref(m);
      writeHero(m);
    };

    // The dashboard is "today": the shared Analytics store goes back to 1 day.
    useEffect(() => {
      const An = AN();
      if (An && An.store && An.store.days !== 1) An.setDays(1);
    }, []);
    // Live depth holds app.jsx's Travel Test stream only while shown.
    useEffect(() => {
      if (mode !== "live" || !ctx.setLiveView) return undefined;
      ctx.setLiveView(true);
      return () => ctx.setLiveView(false);
    }, [mode]);
    const a = store && store.analytics;
    const date = new Date().toLocaleDateString(undefined, {
      weekday: "short",
      day: "numeric",
      month: "short"
    });
    return /*#__PURE__*/React.createElement("div", {
      className: "px-6 pt-5 pb-5 h-[900px] flex flex-col gap-3",
      "data-dashboard": true
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-end gap-4 h-9 shrink-0"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-title uppercase text-[30px] leading-none tracking-[0.04em] text-[var(--text)]"
    }, "Dashboard"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10.5px] uppercase tracking-[0.2em] text-[var(--text-faint)] pb-0.5"
    }, ctx.activeProfileName, " \xB7 ", date), a && a.supported !== false && /*#__PURE__*/React.createElement("span", {
      className: `ml-auto font-mono text-[10px] uppercase tracking-[0.18em] pb-0.5 ${a.enabled ? "text-[var(--text-faint)]" : "text-amber-300/90"}`,
      title: "Aether keeps per-key counters only: never what you typed, in what order, or when."
    }, a.enabled ? "key statistics on · counters only" : "key statistics off")), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-[minmax(0,1fr)_392px] gap-3.5 h-[420px] shrink-0"
    }, /*#__PURE__*/React.createElement(Hero, {
      ctx: ctx,
      store: store,
      modes: modes,
      mode: mode,
      setMode: setMode
    }), /*#__PURE__*/React.createElement(Rail, {
      ctx: ctx
    })), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-[340px_minmax(0,1fr)_392px] gap-3.5 flex-1 min-h-0"
    }, /*#__PURE__*/React.createElement(TodayPanel, {
      ctx: ctx,
      store: store
    }), /*#__PURE__*/React.createElement(TunePanel, {
      ctx: ctx,
      store: store
    }), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-3.5 min-h-0"
    }, /*#__PURE__*/React.createElement(LightingPanel, {
      ctx: ctx
    }), /*#__PURE__*/React.createElement(OverlaysPanel, {
      ctx: ctx
    }))));
  }
  window.AetherWorkspaces = window.AetherWorkspaces || {};
  window.AetherWorkspaces.DASHBOARD_PAGE = DashboardPage;
  window.AetherDashboard = {
    HERO_MODES,
    OVERLAY_POLL_MS,
    heroModesFor,
    pickHeroMode,
    perKeyOverrideOf,
    actuationSummary,
    todayFrom,
    gameLine,
    overlayView,
    overlayText
  };
})();