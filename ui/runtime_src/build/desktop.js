(() => {
  /* ============================================================
     Desktop-widget shell for AetherHE.
     Exposes window.AetherDesktop = { WidgetFrame, Workspace, Dock, TopBar }.
     Plain JSX, uses global React (no libs). Vanilla pointer events for
     drag + resize. Geometry persists per (workspace,widget) in localStorage
     under key `aether-wgt:{workspace}:{id}`.
     ============================================================ */
  const {
    useState,
    useEffect,
    useRef,
    useCallback
  } = React;
  const I = window.AetherIcons || {};
  const IKeyboard = I.IKeyboard,
    IBulb = I.IBulb,
    IGauge = I.IGauge,
    ICrosshair = I.ICrosshair,
    IZap = I.IZap,
    ISettings = I.ISettings,
    IPlug = I.IPlug,
    IPower = I.IPower,
    ICheck = I.ICheck,
    IMore = I.IMore;
  const GRID = 8;
  const snap = v => Math.max(0, Math.round(v / GRID) * GRID);

  /* ============================================================
     Active-board name for the top-bar status chip (additive).
     The chip used to be the hardcoded string "WIN 60 HE", which read wrong
     the moment Aether became multi-board. It now shows whichever board is
     actually selected.
  
     Resolved at module scope so the hook below is unconditional: if the
     board-context module isn't loaded (or nothing is selected) we fall back
     to a private context whose value is null, and the chip renders exactly
     the string it always did. The Win60 keeps its historical label verbatim
     via BOARD_CHIP_LABEL rather than a derived one, so its UI is unchanged.
     ============================================================ */
  const BOARD_CTX = window.AetherBoard && window.AetherBoard.BoardContext || React.createContext(null);
  const BOARD_CHIP_LABEL = {
    "aula-win60-he": "WIN 60 HE"
  };
  const boardChipName = board => {
    if (!board) return "WIN 60 HE"; // fail-open: today's string
    if (BOARD_CHIP_LABEL[board.slug]) return BOARD_CHIP_LABEL[board.slug];
    return String(board.name || "").replace(/^aula\s+/i, "") // vendor prefix is noise here
    .replace(/\s*\([^)]*\)\s*/g, " ") // drop "(wired)" / "(2.4GHz dongle)"
    .trim().toUpperCase() || "KEYBOARD";
  };

  /* ---- geometry persistence ---- */
  const geoKey = (workspace, id) => `aether-wgt:${workspace}:${id}`;
  const loadGeo = (workspace, id) => {
    try {
      const raw = localStorage.getItem(geoKey(workspace, id));
      if (!raw) return null;
      const g = JSON.parse(raw);
      if (!g || typeof g !== "object") return null;
      return g;
    } catch {
      return null;
    }
  };
  const saveGeo = (workspace, id, geo) => {
    try {
      localStorage.setItem(geoKey(workspace, id), JSON.stringify(geo));
    } catch {}
  };

  /* ============================================================
     WidgetFrame — a draggable + resizable window with an Impact title bar.
     Drag by the title bar, resize by the bottom-right handle, minimize button.
     ============================================================ */
  function WidgetFrame({
    id,
    workspace,
    title,
    defaultPos,
    defaultSize,
    minSize,
    onMinimize,
    z,
    onFocus,
    children
  }) {
    const min = minSize || {
      w: 220,
      h: 140
    };
    const init = loadGeo(workspace, id);
    const [pos, setPos] = useState(() => init && init.pos || defaultPos || {
      x: 40,
      y: 40
    });
    const [size, setSize] = useState(() => init && init.size || defaultSize || {
      w: 360,
      h: 300
    });
    const [minimized, setMinimized] = useState(() => !!(init && init.minimized));
    const [drag, setDrag] = useState(false);
    const [resizing, setResizing] = useState(false);
    const gesture = useRef(null);

    // Persist geometry whenever it settles.
    useEffect(() => {
      saveGeo(workspace, id, {
        pos,
        size,
        minimized
      });
    }, [workspace, id, pos, size, minimized]);

    // Report minimized transitions up so the Workspace can drive the dock.
    useEffect(() => {
      if (onMinimize) onMinimize(id, minimized);
    }, [minimized]);
    const onTitleDown = useCallback(e => {
      if (e.target.closest("button, input, textarea, select, a")) return;
      gesture.current = {
        kind: "drag",
        px: e.clientX,
        py: e.clientY,
        x: pos.x,
        y: pos.y
      };
      setDrag(true);
      e.currentTarget.setPointerCapture(e.pointerId);
    }, [pos.x, pos.y]);
    const onResizeDown = useCallback(e => {
      e.stopPropagation();
      gesture.current = {
        kind: "resize",
        px: e.clientX,
        py: e.clientY,
        w: size.w,
        h: size.h
      };
      setResizing(true);
      e.currentTarget.setPointerCapture(e.pointerId);
    }, [size.w, size.h]);
    const onMove = useCallback(e => {
      const g = gesture.current;
      if (!g) return;
      if (g.kind === "drag") {
        setPos({
          x: snap(g.x + (e.clientX - g.px)),
          y: snap(g.y + (e.clientY - g.py))
        });
      } else if (g.kind === "resize") {
        setSize({
          w: Math.max(min.w, snap(g.w + (e.clientX - g.px))),
          h: Math.max(min.h, snap(g.h + (e.clientY - g.py)))
        });
      }
    }, [min.w, min.h]);
    const endGesture = useCallback(() => {
      gesture.current = null;
      setDrag(false);
      setResizing(false);
    }, []);
    if (minimized) return null;
    return /*#__PURE__*/React.createElement("section", {
      className: `widget glass${drag ? " dragging" : ""}${resizing ? " resizing" : ""}`,
      style: {
        left: pos.x,
        top: pos.y,
        width: size.w,
        height: size.h,
        zIndex: z || 1
      },
      onPointerDownCapture: () => onFocus && onFocus(id)
    }, /*#__PURE__*/React.createElement("header", {
      className: "widget-head",
      onPointerDown: onTitleDown,
      onPointerMove: onMove,
      onPointerUp: endGesture,
      onPointerCancel: endGesture
    }, /*#__PURE__*/React.createElement("span", {
      className: "widget-dot",
      "aria-hidden": true
    }), /*#__PURE__*/React.createElement("span", {
      className: "widget-title font-title"
    }, title), /*#__PURE__*/React.createElement("button", {
      className: "widget-min",
      title: "Minimize",
      "aria-label": `Minimize ${title}`,
      onClick: e => {
        e.stopPropagation();
        setMinimized(true);
      }
    }, "\u2013")), /*#__PURE__*/React.createElement("div", {
      className: "widget-body"
    }, children), /*#__PURE__*/React.createElement("div", {
      className: "widget-resize",
      title: "Resize",
      onPointerDown: onResizeDown,
      onPointerMove: onMove,
      onPointerUp: endGesture,
      onPointerCancel: endGesture
    }));
  }

  /* ============================================================
     Dock — bottom-center pill of minimized-widget buttons.
     ============================================================ */
  function Dock({
    items,
    onRestore
  }) {
    if (!items || !items.length) return null;
    return /*#__PURE__*/React.createElement("nav", {
      className: "dock glass"
    }, items.map(w => /*#__PURE__*/React.createElement("button", {
      key: w.id,
      className: "font-title",
      title: `Restore ${w.title}`,
      onClick: () => onRestore(w.id)
    }, w.title)));
  }

  /* ============================================================
     Workspace — absolute-positioned desktop surface. Renders each widget in a
     WidgetFrame, plus a per-workspace Dock of minimized widgets to restore.
     widgets = [{ id, title, default:{x,y,w,h}, min:{w,h}, render:(ctx)=>JSX }]
     ============================================================ */
  function Workspace({
    section,
    widgets,
    ctx
  }) {
    const list = widgets || [];
    // Track which widgets are minimized (seeded from persisted geometry).
    const [minimized, setMinimized] = useState(() => {
      const s = {};
      list.forEach(w => {
        const g = loadGeo(section, w.id);
        if (g && g.minimized) s[w.id] = true;
      });
      return s;
    });
    // Reset when the workspace (section) changes.
    useEffect(() => {
      const s = {};
      list.forEach(w => {
        const g = loadGeo(section, w.id);
        if (g && g.minimized) s[w.id] = true;
      });
      setMinimized(s);
    }, [section]);
    const handleMinimize = useCallback((id, isMin) => {
      setMinimized(prev => prev[id] === isMin ? prev : {
        ...prev,
        [id]: isMin
      });
    }, []);
    const restore = useCallback(id => {
      // Flip persisted geometry and force a remount of that frame.
      const g = loadGeo(section, id) || {};
      saveGeo(section, id, {
        ...g,
        minimized: false
      });
      setMinimized(prev => ({
        ...prev,
        [id]: false
      }));
      setNonce(n => n + 1);
    }, [section]);
    const [nonce, setNonce] = useState(0);

    // Stacking order: clicking a widget raises it above the others and it stays
    // there until another is clicked. Seeded so array order is the initial stack.
    const zTop = useRef(10 + list.length);
    const [zmap, setZmap] = useState(() => {
      const m = {};
      list.forEach((w, i) => {
        m[w.id] = 10 + i;
      });
      return m;
    });
    useEffect(() => {
      const m = {};
      list.forEach((w, i) => {
        m[w.id] = 10 + i;
      });
      zTop.current = 10 + list.length;
      setZmap(m);
    }, [section]);
    const raise = useCallback(id => {
      setZmap(prev => prev[id] === zTop.current ? prev : {
        ...prev,
        [id]: ++zTop.current
      });
    }, []);
    const dockItems = list.filter(w => minimized[w.id]);
    return /*#__PURE__*/React.createElement("div", {
      className: "workspace",
      "data-section": section
    }, list.map(w => /*#__PURE__*/React.createElement(WidgetFrame, {
      key: `${section}:${w.id}:${nonce}`,
      id: w.id,
      workspace: section,
      title: w.title,
      defaultPos: {
        x: w.default.x,
        y: w.default.y
      },
      defaultSize: {
        w: w.default.w,
        h: w.default.h
      },
      minSize: w.min,
      onMinimize: handleMinimize,
      z: zmap[w.id],
      onFocus: raise
    }, React.createElement(w.render, ctx))), /*#__PURE__*/React.createElement(Dock, {
      items: dockItems,
      onRestore: restore
    }));
  }

  /* ============================================================
     TopBar — horizontal section tabs (Impact) + brand + connect cluster.
     Sections: keymap, lighting, actuation, socd, gamepad, settings.
     ============================================================ */
  const SECTION_DEFS = [{
    id: "keymap",
    label: "Keymap",
    icon: IKeyboard
  }, {
    id: "lighting",
    label: "Lighting",
    icon: IBulb
  }, {
    id: "actuation",
    label: "Actuation",
    icon: IGauge
  }, {
    id: "socd",
    label: "SOCD",
    icon: ICrosshair
  }, {
    id: "gamepad",
    label: "Gamepad",
    icon: IZap
  }, {
    id: "settings",
    label: "Settings",
    icon: ISettings
  }];
  function TopBar({
    sections,
    active,
    onSelect,
    connected,
    connecting,
    onTogglePair,
    autoConnect,
    setAutoConnect,
    onOpenSettings,
    zoom,
    setZoom
  }) {
    const defs = sections || SECTION_DEFS;
    const bctx = React.useContext(BOARD_CTX);
    const chipName = boardChipName(bctx && bctx.board);
    return /*#__PURE__*/React.createElement("header", {
      className: "topbar"
    }, /*#__PURE__*/React.createElement("div", {
      className: "topbar-inner"
    }, /*#__PURE__*/React.createElement("div", {
      className: "topbar-brand"
    }, /*#__PURE__*/React.createElement("img", {
      src: window.__resources && window.__resources.logo || "assets/logo.png",
      alt: "",
      className: "topbar-logo"
    }), /*#__PURE__*/React.createElement("span", {
      className: "topbar-name font-title"
    }, "AETHER")), /*#__PURE__*/React.createElement("nav", {
      className: "topbar-tabs"
    }, defs.map(s => {
      const Icon = s.icon;
      const on = active === s.id;
      return /*#__PURE__*/React.createElement("button", {
        key: s.id,
        onClick: () => onSelect(s.id),
        className: `topbar-tab font-title${on ? " on" : ""}`
      }, Icon && /*#__PURE__*/React.createElement(Icon, {
        size: 14
      }), /*#__PURE__*/React.createElement("span", null, s.label));
    })), /*#__PURE__*/React.createElement("div", {
      className: "topbar-right"
    }, /*#__PURE__*/React.createElement("div", {
      className: `topbar-status${connected ? " linked" : ""}`
    }, /*#__PURE__*/React.createElement("span", {
      className: "topbar-dot"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-title",
      title: bctx && bctx.board && bctx.board.vidPid || ""
    }, chipName), /*#__PURE__*/React.createElement("span", {
      className: "topbar-state"
    }, connected ? "Linked" : "Offline")), /*#__PURE__*/React.createElement("label", {
      className: "topbar-auto",
      title: "Connect automatically on launch"
    }, /*#__PURE__*/React.createElement("span", {
      onClick: () => setAutoConnect(!autoConnect),
      className: `topbar-check${autoConnect ? " on" : ""}`
    }, autoConnect && ICheck && /*#__PURE__*/React.createElement(ICheck, {
      size: 9
    })), /*#__PURE__*/React.createElement("span", {
      className: "font-title"
    }, "Auto")), /*#__PURE__*/React.createElement("button", {
      onClick: onTogglePair,
      disabled: connecting,
      className: `topbar-pair${connected ? " on" : ""}`
    }, connected ? IPower && /*#__PURE__*/React.createElement(IPower, {
      size: 13
    }) : IPlug && /*#__PURE__*/React.createElement(IPlug, {
      size: 13
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-title"
    }, connecting ? "…" : connected ? "Connected" : "Pair")), setZoom && /*#__PURE__*/React.createElement("div", {
      className: "topbar-zoom",
      title: "Zoom the workspace"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setZoom(z => Math.max(0.5, +(z - 0.1).toFixed(2))),
      "aria-label": "Zoom out"
    }, "\u2013"), /*#__PURE__*/React.createElement("span", {
      className: "font-title",
      onClick: () => setZoom(1),
      title: "Reset zoom"
    }, Math.round((zoom || 1) * 100), "%"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setZoom(z => Math.min(2, +(z + 0.1).toFixed(2))),
      "aria-label": "Zoom in"
    }, "+")), /*#__PURE__*/React.createElement("button", {
      title: "Settings",
      onClick: onOpenSettings,
      className: "topbar-gear"
    }, ISettings && /*#__PURE__*/React.createElement(ISettings, {
      size: 14
    })))));
  }
  window.AetherDesktop = {
    WidgetFrame,
    Workspace,
    Dock,
    TopBar,
    SECTION_DEFS
  };
})();