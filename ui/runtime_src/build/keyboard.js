(() => {
  /* WIN60 HE keyboard visualization with per-key live actuation. */
  const {
    useState,
    useEffect,
    useRef,
    useMemo
  } = React;

  /* 60% ANSI layout — each row totals 60 cols (each 0.25u = 1 col). */
  /* Each entry: [label, units, code, fn?] — `units` is in 0.25u increments. */
  const KB_ROWS = [[["Esc", 4, "Escape", "`~"], ["1!", 4, "1", "F1"], ["2@", 4, "2", "F2"], ["3#", 4, "3", "F3"], ["$4", 4, "4", "F4"], ["5%", 4, "5", "F5"], ["6^", 4, "6", "F6"], ["7&", 4, "7", "F7"], ["8*", 4, "8", "F8"], ["9(", 4, "9", "F9"], ["0)", 4, "0", "F10"], ["-_", 4, "Minus", "F11"], ["=+", 4, "Equal", "F12"], ["Back", 8, "Backspace", "Del"]], [["Tab", 6, "Tab"], ["Q", 4, "Q", "PrtSc"], ["W", 4, "W", "↑"], ["E", 4, "E", "End"], ["R", 4, "R", "PgUp"], ["T", 4, "T", "Home"], ["Y", 4, "Y", ""], ["U", 4, "U", ""], ["I", 4, "I", "Ins"], ["O", 4, "O", ""], ["P", 4, "P", "Pause"], ["{[", 4, "Lbr", "Prev"], ["}]", 4, "Rbr", "Next"], ["\\|", 6, "Bsl", "Play"]], [["Caps", 7, "Caps"], ["A", 4, "A", "←"], ["S", 4, "S", "↓"], ["D", 4, "D", "→"], ["F", 4, "F", ""], ["G", 4, "G", ""], ["H", 4, "H", ""], ["J", 4, "J", ""], ["K", 4, "K", "Vol−"], ["L", 4, "L", "Vol+"], [";:", 4, "Semi", "Mute"], ["'\"", 4, "Quot", ""], ["Enter", 9, "Enter", ""]], [["L-Shift", 9, "LShift"], ["Z", 4, "Z", ""], ["X", 4, "X", ""], ["C", 4, "C", "Calc"], ["V", 4, "V", ""], ["B", 4, "B", ""], ["N", 4, "N", ""], ["M", 4, "M", ""], [",<", 4, "Comma", "Brt−"], [".>", 4, "Dot", "Brt+"], ["/?", 4, "Slash", ""], ["R-Shift", 11, "RShift"]], [["L-Ctrl", 5, "LCtrl"], ["L-Win", 5, "LWin", "WinLk"], ["L-Alt", 5, "LAlt"], ["Space", 25, "Space"], ["R-Alt", 5, "RAlt"], ["Menu", 5, "Menu"], ["R-Ctrl", 5, "RCtrl"], ["Fn", 5, "Fn", "Fn"]]];

  /* Compute a fractional width string given units in 0.25u increments out of 60 cols. */
  const ufrac = u => `${u / 60 * 100}%`;
  const Key = ({
    label,
    units,
    code,
    fnLabel,
    layer = "default",
    // default | fn
    depth = 0,
    actuationPoint = 1.70,
    rtPress = 0.05,
    rtRelease = 0.05,
    selected = false,
    highlighted = false,
    mode = "keymap",
    calibrating = false,
    calibrated = false,
    ledColor = null,
    onClick = () => {},
    onMouseDown = () => {},
    onMouseEnter = () => {},
    onContextMenu = () => {}
  }) => {
    const actuated = depth >= actuationPoint && actuationPoint > 0;
    const progress = Math.min(1, depth / 4);

    // Background depending on mode. In lighting mode each key shows its real
    // color (effect foreground, or the background color underneath) at FULL
    // strength — so a key lit with the effect color and a key showing only the
    // background read at the same brightness. Near-black (an "off"/background
    // color) falls back to the faint unlit surface instead of a black box.
    let bg = "rgba(255,255,255,0.025)";
    if (mode === "lighting" && ledColor) {
      const hx = String(ledColor).replace("#", "");
      const r = parseInt(hx.slice(0, 2), 16) || 0;
      const g = parseInt(hx.slice(2, 4), 16) || 0;
      const b = parseInt(hx.slice(4, 6), 16) || 0;
      const lum = 0.299 * r + 0.587 * g + 0.114 * b;
      bg = lum < 18 ? "rgba(255,255,255,0.025)" : `linear-gradient(180deg, ${ledColor}, ${ledColor}cc)`;
    }

    // Two-line labels (e.g. "1!" -> shifted/unshifted stack)
    const lines = label.length === 2 && !/^[a-zA-Z]+$/.test(label) && label !== "Fn" ? [label[0], label[1]] : null;
    const displayLabel = layer === "fn" && fnLabel ? fnLabel : label;
    const displayLines = layer === "fn" ? null : lines;
    return /*#__PURE__*/React.createElement("button", {
      onClick: onClick,
      onMouseDown: onMouseDown,
      onMouseEnter: onMouseEnter,
      onDragStart: e => e.preventDefault(),
      draggable: false,
      onContextMenu: e => {
        e.preventDefault();
        onContextMenu(e);
      },
      style: {
        gridColumn: `span ${units}`,
        background: calibrated ? "linear-gradient(180deg, #10b98133, #10b98119)" : bg
      },
      "data-code": code,
      className: `relative rounded-[5px] border text-left
                  px-1.5 pt-1 pb-0.5 h-[46px] overflow-hidden
                  transition-all duration-150
                  ${calibrated ? "border-emerald-400 shadow-[0_0_0_1px_#10b981,0_0_14px_rgba(16,185,129,0.6)]" : calibrating ? "border-amber-400/40 animate-pulse" : selected ? mode === "lighting" ? "border-white shadow-[0_0_0_2px_#ffffff,0_0_12px_rgba(255,255,255,0.75)]" : "border-[var(--accent)]/80 shadow-[0_0_0_1px_var(--accent),0_0_18px_var(--accent-glow)]" : actuated ? "border-[var(--accent)]/60 shadow-[0_0_14px_var(--accent-glow)]" : highlighted ? "border-white/15" : "border-white/[0.07] hover:border-white/20"}`
    }, mode !== "lighting" && depth > 0.02 && /*#__PURE__*/React.createElement("span", {
      "aria-hidden": true,
      className: "absolute inset-x-0 bottom-0 pointer-events-none",
      style: {
        height: progress * 100 + "%",
        background: actuated ? "linear-gradient(to top, var(--accent), transparent 90%)" : "linear-gradient(to top, rgba(148,163,184,0.18), transparent 90%)",
        opacity: actuated ? 0.45 : 0.55,
        transition: "height 120ms linear"
      }
    }), /*#__PURE__*/React.createElement("div", {
      className: "relative z-10 flex items-start justify-between"
    }, displayLines ? /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col leading-[1.0]"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-[10px] text-slate-200 font-medium"
    }, displayLines[1]), /*#__PURE__*/React.createElement("span", {
      className: "text-[10px] text-slate-400 font-medium"
    }, displayLines[0])) : /*#__PURE__*/React.createElement("span", {
      className: `text-[11px] font-medium tracking-wide
                            ${layer === "fn" && fnLabel ? "text-[var(--accent)]" : actuated ? "text-white" : "text-slate-200"}`
    }, displayLabel)), mode === "actuation" && /*#__PURE__*/React.createElement("div", {
      className: "absolute bottom-0.5 inset-x-1 z-10 flex items-end justify-between"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[8.5px] text-slate-300/90"
    }, actuationPoint.toFixed(2)), (rtPress > 0 || rtRelease > 0) && /*#__PURE__*/React.createElement("div", {
      className: "flex gap-1"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[8.5px] text-rose-300/90"
    }, rtPress.toFixed(2)), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[8.5px] text-emerald-300/90"
    }, rtRelease.toFixed(2)))), mode === "actuation" && /*#__PURE__*/React.createElement("span", {
      className: "absolute top-1 right-1 z-10 font-mono text-[8px] text-[var(--accent)]/90"
    }, (depth < 0.05 ? 0 : depth).toFixed(2)));
  };

  /* Top "WIN 60 HE" pill */
  const DevicePill = ({
    connected
  }) => /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-2 px-4 py-1.5 rounded-md bg-[var(--accent)]/15 border border-[var(--accent)]/40 text-[var(--accent)] shadow-[0_0_18px_var(--accent-glow)] whitespace-nowrap"
  }, /*#__PURE__*/React.createElement("span", {
    className: "relative inline-block w-1.5 h-1.5 rounded-full bg-[var(--accent)] pulse-ring text-[var(--accent)]"
  }), /*#__PURE__*/React.createElement("span", {
    className: "font-display font-semibold tracking-[0.18em] text-[12px]"
  }, "WIN 60 HE"), /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--accent)]/70 ml-1"
  }, connected ? "Linked" : "Offline"));

  /* The full keyboard panel — handles live actuation telemetry and selection */
  const KeyboardPanel = ({
    mode,
    layer = "default",
    selectedKeys,
    setSelectedKeys,
    actuationPoint,
    rtPress,
    rtRelease,
    perKeyOverride,
    ledMap,
    accent,
    leftSlot,
    rightSlot,
    showPill = true,
    compact = false,
    liveDepths = null,
    calibrating = false,
    calibratedCodes = null
  }) => {
    const calibSet = calibratedCodes || null;
    // Real per-key travel depth (mm), streamed from the board by the HID bridge
    // (App polls api.read_live() while Travel Test is on). When the bridge isn't
    // streaming, every key reads 0 — no simulated motion fighting the hardware.
    const depths = liveDepths || {};
    const _dv = Object.values(depths);
    const liveMax = _dv.length ? Math.max(0, ..._dv) : 0;
    const toggleSelect = (code, e) => {
      setSelectedKeys(prev => {
        const cur = new Set(prev);
        if (e.shiftKey || e.metaKey || e.ctrlKey) {
          cur.has(code) ? cur.delete(code) : cur.add(code);
        } else {
          if (cur.has(code) && cur.size === 1) cur.clear();else {
            cur.clear();
            cur.add(code);
          }
        }
        return cur;
      });
    };

    // Click-and-drag selection: press on a key to start (modifier = add to the
    // current selection, else start fresh), drag across keys to sweep-select.
    const dragging = useRef(false);
    const additive = useRef(false);
    const startDrag = (code, e) => {
      dragging.current = true;
      additive.current = e.shiftKey || e.metaKey || e.ctrlKey;
      setSelectedKeys(prev => {
        const cur = new Set(additive.current ? prev : []);
        if (additive.current && cur.has(code)) cur.delete(code); // ctrl-click toggles off
        else cur.add(code);
        return cur;
      });
    };
    const dragOver = code => {
      if (!dragging.current) return;
      setSelectedKeys(prev => {
        if (prev.has(code)) return prev;
        const cur = new Set(prev);
        cur.add(code);
        return cur;
      });
    };
    useEffect(() => {
      const up = () => {
        dragging.current = false;
      };
      window.addEventListener("mouseup", up);
      return () => window.removeEventListener("mouseup", up);
    }, []);
    return /*#__PURE__*/React.createElement("div", {
      className: "relative"
    }, showPill && /*#__PURE__*/React.createElement("div", {
      className: "flex justify-center mb-4"
    }, /*#__PURE__*/React.createElement(DevicePill, {
      connected: true
    })), /*#__PURE__*/React.createElement("div", {
      className: "flex items-start justify-center gap-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "shrink-0 w-[110px] pt-2 flex flex-col gap-1.5"
    }, leftSlot), /*#__PURE__*/React.createElement("div", {
      className: "relative w-full max-w-[720px] rounded-2xl border border-white/[0.06] bg-gradient-to-b from-white/[0.025] to-black/30 p-3.5 shadow-[0_24px_60px_-24px_rgba(0,0,0,0.8)]"
    }, /*#__PURE__*/React.createElement("span", {
      className: "pointer-events-none absolute -top-px left-12 right-12 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent"
    }), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-[3px]"
    }, KB_ROWS.map((row, ri) => /*#__PURE__*/React.createElement("div", {
      key: ri,
      className: "grid w-full gap-[3px]",
      style: {
        gridTemplateColumns: "repeat(60, minmax(0, 1fr))"
      }
    }, row.map(([label, units, code, fnLabel]) => {
      const override = perKeyOverride?.[code] || {};
      return /*#__PURE__*/React.createElement(Key, {
        key: code,
        label: label,
        units: units,
        code: code,
        fnLabel: fnLabel,
        layer: layer,
        depth: depths[code] || 0,
        actuationPoint: override.actuation ?? actuationPoint,
        rtPress: override.rtPress ?? rtPress,
        rtRelease: override.rtRelease ?? rtRelease,
        selected: selectedKeys.has(code),
        mode: mode,
        calibrating: calibrating,
        calibrated: !!(calibSet && calibSet.has(code)),
        ledColor: ledMap?.[code] || null,
        onMouseDown: e => startDrag(code, e),
        onMouseEnter: () => dragOver(code),
        onContextMenu: () => setSelectedKeys(prev => {
          if (!prev.has(code)) return prev;
          const cur = new Set(prev);
          cur.delete(code);
          return cur;
        })
      });
    }))))), /*#__PURE__*/React.createElement("div", {
      className: "shrink-0 w-[110px] pt-2 flex flex-col gap-1.5 items-end"
    }, mode === "actuation" && liveDepths && /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500 whitespace-nowrap"
    }, "Live \xB7 ", /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, (liveMax < 0.05 ? 0 : liveMax).toFixed(2), "mm")), rightSlot)), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col items-center mt-3 gap-1"
    }, /*#__PURE__*/React.createElement("button", {
      className: "grid place-items-center w-7 h-7 rounded-full border border-white/[0.06] bg-white/[0.02] text-slate-400 hover:text-slate-100 hover:border-white/20 transition-colors",
      title: "Refresh device state"
    }, /*#__PURE__*/React.createElement(window.AetherIcons.IRefresh, {
      size: 13
    })), mode === "socd" && /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-slate-500 uppercase tracking-[0.18em]"
    }, "Right-click to uncheck all keys")));
  };
  window.AetherKeyboard = {
    KeyboardPanel,
    KB_ROWS,
    DevicePill
  };
})();