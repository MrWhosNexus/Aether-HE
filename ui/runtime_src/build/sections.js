(() => {
  /* Section panels: Keymap, Actuation, Lighting, SOCD, Other */
  const {
    useState,
    useEffect,
    useRef,
    useMemo
  } = React;
  const {
    IFolder,
    IKeyboard,
    IBulb,
    IGauge,
    ICrosshair,
    IGrid,
    IPlug,
    IPower,
    IChevron,
    IChevronD,
    ICheck,
    IEdit,
    IRefresh,
    IZap,
    ISave,
    ILink,
    IUnlink,
    IPalette,
    IActivity,
    IWaves,
    ISettings,
    ITrash,
    IPlus,
    ICpu,
    ILayers,
    IMore,
    IDownload
  } = window.AetherIcons;

  /* ===== Shared bits ===== */
  const SubTabs = ({
    tabs,
    active,
    onChange
  }) => /*#__PURE__*/React.createElement("nav", {
    className: "flex items-center gap-1 border-b border-white/[0.06] mb-4"
  }, tabs.map(t => {
    const isActive = active === t.id;
    return /*#__PURE__*/React.createElement("button", {
      key: t.id,
      onClick: () => onChange(t.id),
      className: `relative flex items-center gap-2 px-4 h-10 -mb-px font-display text-[12px] uppercase tracking-[0.16em] whitespace-nowrap
                      transition-colors
                      ${isActive ? "text-[var(--accent)]" : "text-slate-400 hover:text-slate-200"}`
    }, t.icon, t.label, isActive && /*#__PURE__*/React.createElement("span", {
      className: "absolute left-2 right-2 -bottom-px h-px bg-[var(--accent)] shadow-[0_0_8px_var(--accent-glow)]"
    }));
  }));
  const Slider = ({
    label,
    value,
    min,
    max,
    step,
    onChange,
    unit = "",
    color = "accent"
  }) => {
    const pct = (value - min) / (max - min) * 100;
    return /*#__PURE__*/React.createElement("div", null, label && /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[12px] uppercase tracking-[0.18em] text-slate-300"
    }, label), /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline gap-1.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[14px] text-[var(--accent)]"
    }, Number(value).toFixed(step < 1 ? 2 : 0)), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-slate-500 uppercase tracking-[0.18em]"
    }, unit))), /*#__PURE__*/React.createElement("input", {
      type: "range",
      className: "aether w-full",
      min: min,
      max: max,
      step: step,
      value: value,
      style: {
        "--pct": pct + "%"
      },
      onChange: e => onChange(parseFloat(e.target.value))
    }));
  };
  const ToolbarButton = ({
    children,
    onClick,
    variant = "ghost",
    active,
    glow
  }) => /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    className: `px-3 h-8 rounded-md font-display text-[11px] uppercase tracking-[0.16em] border transition-all
                ${variant === "primary" ? "bg-[var(--accent)]/15 border-[var(--accent)]/50 text-[var(--accent)] hover:bg-[var(--accent)]/25 shadow-[0_0_10px_var(--accent-glow)]" : active ? "border-white/15 bg-white/[0.04] text-slate-100" : "border-white/[0.06] bg-white/[0.015] text-slate-300 hover:border-white/15 hover:text-slate-100"}`
  }, children);
  const Chip = ({
    children,
    color = "slate"
  }) => {
    const tones = {
      slate: "border-white/[0.06] bg-white/[0.02] text-slate-300",
      accent: "border-[var(--accent)]/30 bg-[var(--accent)]/10 text-[var(--accent)]",
      danger: "border-rose-400/30 bg-rose-500/10 text-rose-300",
      ok: "border-emerald-400/30 bg-emerald-500/10 text-emerald-300"
    };
    return /*#__PURE__*/React.createElement("span", {
      className: `inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-[0.18em] border ${tones[color]}`
    }, children);
  };

  /* ===== Layer pill (Default Layer / Fn Layer) ===== */
  const LayerPicker = ({
    layer,
    setLayer
  }) => /*#__PURE__*/React.createElement("div", {
    className: "flex flex-col gap-2 mr-6"
  }, ["default", "fn"].map(l => /*#__PURE__*/React.createElement("button", {
    key: l,
    onClick: () => setLayer(l),
    className: `px-3.5 h-9 rounded-md font-display text-[11.5px] uppercase tracking-[0.14em] border transition-all
                    ${layer === l ? "bg-[var(--accent)] border-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_18px_var(--accent-glow)]" : "bg-white/[0.02] border-white/[0.06] text-slate-300 hover:border-white/20"}`
  }, l === "default" ? "Default Layer" : "Fn Layer")));

  /* ===== KEYMAP SECTION ===== */
  const BASIC_KEYS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "1!", "2@", "3#", "$4", "5%", "6^", "7&", "8*", "9(", "0)", "-_", "=+", "{[", "}]", "\\|", "<>", ";:", "'\"", "`~", ",<", ".>", "/?"];
  const EXTENDED_KEYS = ["Esc", "Tab", "Caps", "Back", "Enter", "Space", "L-Ctrl", "R-Ctrl", "L-Shift", "R-Shift", "L-Alt", "R-Alt", "L-Win", "R-Win", "Menu", "Left", "Up", "Right", "Down", "PrtSc", "ScrLk", "Pause", "Ins", "Home", "Del", "End", "PgUp", "PgDn", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"];
  const KeymapSection = ({
    selectedKey,
    selectedCount = 0,
    onRemap,
    onResetKey
  }) => {
    const [tab, setTab] = useState("remap");
    const [picked, setPicked] = useState(null);
    const [flash, setFlash] = useState(null); // "applied" | "reset" toast
    const showFlash = kind => {
      setFlash(kind);
      setTimeout(() => setFlash(null), 1400);
    };
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(SubTabs, {
      active: tab,
      onChange: setTab,
      tabs: [{
        id: "remap",
        label: "Remap Key",
        icon: /*#__PURE__*/React.createElement(IKeyboard, {
          size: 13
        })
      }, {
        id: "adv",
        label: "Advanced",
        icon: /*#__PURE__*/React.createElement(IZap, {
          size: 13
        })
      }]
    }), tab === "adv" && /*#__PURE__*/React.createElement(AdvancedKeyPanel, {
      selectedKey: selectedKey
    }), tab !== "adv" && /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("ol", {
      className: "text-[12px] text-slate-400 leading-relaxed space-y-2 mb-4 font-mono"
    }, /*#__PURE__*/React.createElement("li", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "01."), " Click a key on the keyboard above."), /*#__PURE__*/React.createElement("li", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "02."), " Pick the new mapping at right."), /*#__PURE__*/React.createElement("li", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "03."), " Or type it into the input below."), /*#__PURE__*/React.createElement("li", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "04."), " Hit ", /*#__PURE__*/React.createElement("span", {
      className: "text-slate-200"
    }, "Apply"), " to flash.")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-stretch gap-2 mb-3"
    }, /*#__PURE__*/React.createElement("div", {
      className: "grid place-items-center w-14 rounded-md border border-white/[0.06] bg-white/[0.02] font-mono text-[11px] text-slate-300"
    }, selectedKey || "None"), /*#__PURE__*/React.createElement("div", {
      className: "grid place-items-center text-slate-500"
    }, /*#__PURE__*/React.createElement(IChevron, {
      size: 14
    })), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 rounded-md border border-white/[0.06] bg-white/[0.02] px-3 grid place-items-start py-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[12px] text-slate-100"
    }, picked || "—"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9px] uppercase tracking-[0.18em] text-slate-500"
    }, "remap target"))), /*#__PURE__*/React.createElement("div", {
      className: "flex gap-2"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => {
        onResetKey && onResetKey();
        setPicked(null);
        showFlash("reset");
      },
      className: "flex-1 h-9 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 font-display text-[11px] uppercase tracking-[0.18em] hover:border-white/20"
    }, "Default"), /*#__PURE__*/React.createElement("button", {
      disabled: !picked || !selectedCount,
      onClick: () => {
        onRemap && onRemap(picked);
        showFlash("applied");
      },
      className: `flex-1 h-9 rounded-md border font-display text-[11px] uppercase tracking-[0.18em] transition-all
                          ${!picked || !selectedCount ? "border-white/[0.06] bg-white/[0.02] text-slate-600 cursor-not-allowed" : "border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25 shadow-[0_0_12px_var(--accent-glow)]"}`
    }, "Apply")), /*#__PURE__*/React.createElement("div", {
      className: "h-5 mt-2 text-[11px] font-mono tracking-[0.14em]"
    }, !selectedCount && /*#__PURE__*/React.createElement("span", {
      className: "text-amber-400/80"
    }, "Select a key on the board first."), flash === "applied" && /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "\u2713 Remapped ", selectedCount, " key", selectedCount > 1 ? "s" : "", " \u2192 ", picked), flash === "reset" && /*#__PURE__*/React.createElement("span", {
      className: "text-slate-400"
    }, "\u21A9 Restored default mapping"))), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-4"
    }, /*#__PURE__*/React.createElement(KeyGrid, {
      title: "Basic Keys",
      keys: BASIC_KEYS,
      picked: picked,
      onPick: setPicked
    }), /*#__PURE__*/React.createElement(KeyGrid, {
      title: "Extended Keys",
      keys: EXTENDED_KEYS,
      picked: picked,
      onPick: setPicked
    }))));
  };

  /* Advanced: DKS / MT / TGL */
  const AdvancedKeyPanel = ({
    selectedKey
  }) => {
    const [mode, setMode] = useState("dks");
    const [dksPoints, setDksPoints] = useState([1.5, 3.0, 3.0, 1.5]);
    const [tapKey, setTapKey] = useState("");
    const [holdKey, setHoldKey] = useState("");
    const [holdDuration, setHoldDuration] = useState(150);
    const [tglKey, setTglKey] = useState("");
    const [picked, setPicked] = useState(null);
    return /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6"
    }, /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 mb-5"
    }, [{
      id: "dks",
      label: "DKS"
    }, {
      id: "mt",
      label: "MT"
    }, {
      id: "tgl",
      label: "TGL"
    }].map(b => /*#__PURE__*/React.createElement("button", {
      key: b.id,
      onClick: () => setMode(b.id),
      className: `flex-1 max-w-[120px] h-9 rounded-md border font-display text-[11.5px] uppercase tracking-[0.18em] transition-all
                          ${mode === b.id ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"}`
    }, b.label))), mode === "dks" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[11.5px] text-slate-400 mb-4"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-slate-200"
    }, "DKS"), " \xB7 Dynamic Key Stroke. Bind up to 4 different actions to a single key at different actuation depths."), /*#__PURE__*/React.createElement(DKSDiagram, {
      points: dksPoints,
      setPoints: setDksPoints
    }), /*#__PURE__*/React.createElement("button", {
      className: "mt-4 px-4 h-9 rounded-md border border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] font-display text-[11.5px] uppercase tracking-[0.18em] shadow-[0_0_12px_var(--accent-glow)]"
    }, "Save DKS Layer")), mode === "mt" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[11.5px] text-slate-400 mb-5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-slate-200"
    }, "MT"), " \xB7 Mod-Tap. Send one keycode on a quick tap, another when held past the threshold."), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 gap-4 mb-5"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-1.5"
    }, "Tap"), /*#__PURE__*/React.createElement("div", {
      className: `h-10 rounded-md border grid place-items-center font-mono text-[14px]
                                 ${tapKey ? "border-[var(--accent)]/50 text-[var(--accent)] bg-[var(--accent)]/10" : "border-white/[0.06] text-slate-500 bg-white/[0.02]"}`
    }, tapKey || "—")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-1.5"
    }, "Hold"), /*#__PURE__*/React.createElement("div", {
      className: `h-10 rounded-md border grid place-items-center font-mono text-[14px]
                                 ${holdKey ? "border-[var(--accent)]/50 text-[var(--accent)] bg-[var(--accent)]/10" : "border-white/[0.06] text-slate-500 bg-white/[0.02]"}`
    }, holdKey || "—"))), /*#__PURE__*/React.createElement("div", {
      className: "mb-2"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-1"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11.5px] uppercase tracking-[0.18em] text-slate-300"
    }, "Hold Duration"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[12px] text-[var(--accent)]"
    }, holdDuration, "ms")), /*#__PURE__*/React.createElement("input", {
      type: "range",
      className: "aether w-full",
      min: 50,
      max: 800,
      step: 10,
      value: holdDuration,
      style: {
        "--pct": (holdDuration - 50) / 750 * 100 + "%"
      },
      onChange: e => setHoldDuration(parseInt(e.target.value))
    }))), mode === "tgl" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[11.5px] text-slate-400 mb-5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-slate-200"
    }, "TGL"), " \xB7 Toggle. One tap latches the key down until tapped again \u2014 perfect for auto-walk or capslock-style behavior."), /*#__PURE__*/React.createElement("div", {
      className: "max-w-[180px]"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-1.5"
    }, "Toggle key"), /*#__PURE__*/React.createElement("div", {
      className: `h-10 rounded-md border grid place-items-center font-mono text-[14px]
                               ${tglKey ? "border-[var(--accent)]/50 text-[var(--accent)] bg-[var(--accent)]/10" : "border-white/[0.06] text-slate-500 bg-white/[0.02]"}`
    }, tglKey || "—")))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(KeyGrid, {
      title: "Basic Keys",
      keys: BASIC_KEYS,
      picked: picked,
      onPick: k => {
        setPicked(k);
        if (mode === "mt") {
          if (!tapKey) setTapKey(k);else setHoldKey(k);
        } else if (mode === "tgl") {
          setTglKey(k);
        }
      }
    })));
  };
  const DKSDiagram = ({
    points,
    setPoints
  }) => {
    // 4 columns, 4 row tracks. Up/down arrow indicators with depth labels.
    return /*#__PURE__*/React.createElement("div", {
      className: "rounded-lg border border-white/[0.06] bg-black/30 p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-end gap-4 mb-3"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-2 w-10"
    }, [1, 2, 3, 4].map(i => /*#__PURE__*/React.createElement("div", {
      key: i,
      className: `h-7 rounded border text-center font-mono text-[10px] grid place-items-center
                                    ${i === 1 ? "border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent)]" : "border-white/[0.06] bg-white/[0.02] text-slate-500"}`
    }, "K", i))), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 grid grid-cols-4 gap-3"
    }, points.map((p, idx) => /*#__PURE__*/React.createElement("div", {
      key: idx,
      className: "flex flex-col items-center"
    }, /*#__PURE__*/React.createElement("span", {
      className: `font-mono text-[11px] mb-1 ${idx % 3 === 0 ? "text-amber-300" : "text-slate-200"}`
    }, p.toFixed(1), "mm"), /*#__PURE__*/React.createElement("span", {
      className: "text-slate-400 mb-1"
    }, idx < 2 ? "↓" : "↑"), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-2 w-full"
    }, [0, 1, 2, 3].map(row => {
      const filled = row === idx;
      return /*#__PURE__*/React.createElement("button", {
        key: row,
        className: `h-7 rounded-full border grid place-items-center transition-colors
                                  ${filled ? "border-[var(--accent)] bg-[var(--accent)]/20 text-[var(--accent)]" : "border-white/[0.06] bg-white/[0.02] text-slate-500 hover:border-white/20"}`
      }, /*#__PURE__*/React.createElement("span", {
        className: "text-[10px]"
      }, filled ? "●" : "+"));
    })))))), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between text-[10px] font-mono text-slate-500 mt-2"
    }, /*#__PURE__*/React.createElement("span", null, "Press \u2192"), /*#__PURE__*/React.createElement("span", null, "\u2190 Release")));
  };
  const KeyGrid = ({
    title,
    keys,
    picked,
    onPick
  }) => {
    const [open, setOpen] = useState(true);
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(o => !o),
      className: "flex items-center gap-2 mb-2 text-slate-300 hover:text-slate-100"
    }, /*#__PURE__*/React.createElement(IChevronD, {
      size: 12,
      className: open ? "" : "-rotate-90"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[12px] uppercase tracking-[0.18em]"
    }, title)), open && /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-[repeat(auto-fill,minmax(46px,1fr))] gap-1.5"
    }, keys.map(k => {
      const active = picked === k;
      return /*#__PURE__*/React.createElement("button", {
        key: k,
        onClick: () => onPick(k),
        className: `h-9 rounded-md border font-mono text-[11px] transition-all
                            ${active ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20 hover:text-slate-100"}`
      }, k);
    })));
  };

  /* ===== ACTUATION SECTION ===== */
  const ActuationSection = ({
    actuation,
    setActuation,
    rtPress,
    setRtPress,
    rtRelease,
    setRtRelease,
    rtEnabled,
    setRtEnabled,
    polling,
    setPolling,
    travelTest,
    setTravelTest,
    onSelectAll,
    onSelectInvert,
    onDeselectAll,
    onResetTrigger,
    calibrating,
    onCalibrate,
    deadTop,
    setDeadTop,
    deadBottom,
    setDeadBottom,
    switchId,
    onPickSwitch,
    liveDepth = 0,
    selectedCount = 0
  }) => {
    const scope = selectedCount > 0 ? `${selectedCount} selected key${selectedCount > 1 ? "s" : ""}` : "ALL keys";
    const [tab, setTab] = useState("travel");
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(SubTabs, {
      active: tab,
      onChange: setTab,
      tabs: [{
        id: "travel",
        label: "Travel",
        icon: /*#__PURE__*/React.createElement(IGauge, {
          size: 13
        })
      }, {
        id: "dead",
        label: "Dead Band",
        icon: /*#__PURE__*/React.createElement(IActivity, {
          size: 13
        })
      }, {
        id: "switch",
        label: "Switch",
        icon: /*#__PURE__*/React.createElement(ICpu, {
          size: 13
        })
      }, {
        id: "poll",
        label: "Polling Rate",
        icon: /*#__PURE__*/React.createElement(IActivity, {
          size: 13
        })
      }, {
        id: "calib",
        label: "Calibration",
        icon: /*#__PURE__*/React.createElement(ICrosshair, {
          size: 13
        })
      }]
    }), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6"
    }, /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between mb-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-slate-300"
    }, "Travel Test"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setTravelTest(!travelTest),
      className: `relative w-10 h-5 rounded-full border transition-colors
                          ${travelTest ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-white/[0.08]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                                ${travelTest ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`
    }))), /*#__PURE__*/React.createElement(SwitchRender, {
      depth: travelTest ? liveDepth : actuation,
      actuation: actuation
    })), /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-5"
    }, tab === "travel" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-slate-400 mb-3"
    }, "Adjust the actuation point below. Select keys on the board to scope it; with none selected it applies to every key."), /*#__PURE__*/React.createElement("div", {
      className: "mb-5 inline-flex items-center gap-2 px-3 h-7 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/[0.06]"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] uppercase tracking-[0.18em] text-slate-400"
    }, "Applying to"), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.16em] text-[var(--accent)]"
    }, scope)), /*#__PURE__*/React.createElement("div", {
      className: "mb-5"
    }, /*#__PURE__*/React.createElement(Slider, {
      label: "Key Trigger Travel",
      value: actuation,
      min: 0.1,
      max: 4.0,
      step: 0.05,
      unit: "mm",
      onChange: setActuation
    }), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 mt-2"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setActuation(Math.max(0.1, actuation - 0.05)),
      className: "w-7 h-7 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"
    }, "\u2212"), /*#__PURE__*/React.createElement("div", {
      className: "px-3 h-7 rounded-md border border-white/[0.06] bg-white/[0.02] grid place-items-center font-mono text-[12px] text-slate-100"
    }, actuation.toFixed(2), " mm"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setActuation(Math.min(4.0, actuation + 0.05)),
      className: "w-7 h-7 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"
    }, "+"))), /*#__PURE__*/React.createElement("label", {
      className: "flex items-center gap-2 cursor-pointer select-none mb-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: `w-4 h-4 rounded border grid place-items-center transition
                                  ${rtEnabled ? "border-[var(--accent)] bg-[var(--accent)]/20" : "border-white/15 bg-white/[0.02]"}`,
      onClick: () => setRtEnabled(!rtEnabled)
    }, rtEnabled && /*#__PURE__*/React.createElement(ICheck, {
      size: 10,
      className: "text-[var(--accent)]"
    })), /*#__PURE__*/React.createElement("input", {
      type: "checkbox",
      checked: rtEnabled,
      onChange: e => setRtEnabled(e.target.checked),
      className: "sr-only"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11.5px] uppercase tracking-[0.16em] text-slate-200"
    }, "Rapid Trigger"), /*#__PURE__*/React.createElement(Chip, {
      color: "accent"
    }, "RT")), /*#__PURE__*/React.createElement("p", {
      className: "text-[11.5px] text-slate-500 leading-relaxed mb-4"
    }, "Rapid Trigger dynamically actuates and resets your key based on your intent \u2014 perfect for counter-strafing and rebound presses."), rtEnabled && /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 gap-5 mt-4 p-4 rounded-lg border border-[var(--accent)]/20 bg-[var(--accent)]/[0.05]"
    }, /*#__PURE__*/React.createElement(Slider, {
      label: "Press Sensitivity",
      value: rtPress,
      min: 0.05,
      max: 2.0,
      step: 0.05,
      unit: "mm",
      onChange: setRtPress
    }), /*#__PURE__*/React.createElement(Slider, {
      label: "Release Sensitivity",
      value: rtRelease,
      min: 0.05,
      max: 2.0,
      step: 0.05,
      unit: "mm",
      onChange: setRtRelease
    }))), tab === "dead" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-slate-400 mb-5"
    }, "Configure the dead-band region near the keycap's rest and bottom-out positions \u2014 noise inside this band is ignored."), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 gap-6"
    }, /*#__PURE__*/React.createElement(Slider, {
      label: "Top Dead Band",
      value: deadTop ?? 0.04,
      min: 0,
      max: 0.5,
      step: 0.01,
      unit: "mm",
      onChange: setDeadTop
    }), /*#__PURE__*/React.createElement(Slider, {
      label: "Bottom Dead Band",
      value: deadBottom ?? 0.05,
      min: 0,
      max: 0.5,
      step: 0.01,
      unit: "mm",
      onChange: setDeadBottom
    }))), tab === "switch" && (() => {
      const SWITCHES = [{
        id: "hm1",
        name: "HM1",
        sub: "Magnetic Switch",
        dot: "#3b82f6",
        maker: "Gateron",
        travel: "4.0 mm",
        force: "30 gf",
        range: "0.1 – 4.0 mm",
        poles: "Single",
        life: "100 M"
      }, {
        id: "hh1",
        name: "HH1",
        sub: "Magnetic Switch",
        dot: "#a3a300",
        maker: "Gateron",
        travel: "3.5 mm",
        force: "40 gf",
        range: "0.1 – 3.5 mm",
        poles: "Single",
        life: "100 M"
      }, {
        id: "cy1",
        name: "CY1",
        sub: "Magnetic Switch",
        dot: "#cbd5e1",
        maker: "KZZI",
        travel: "3.4 mm",
        force: "35 gf",
        range: "0.1 – 3.4 mm",
        poles: "Single",
        life: "80 M"
      }, {
        id: "tc1",
        name: "TC1",
        sub: "TTC Kom",
        dot: "#c026d3",
        maker: "TTC",
        travel: "3.6 mm",
        force: "45 gf",
        range: "0.2 – 3.6 mm",
        poles: "Dual",
        life: "100 M"
      }];
      const cur = SWITCHES.find(s => s.id === (switchId || "hm1")) || SWITCHES[0];
      return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
        className: "text-[12px] text-slate-400 mb-5"
      }, "Select the magnetic switch profile installed in your board. Calibration curves load automatically."), /*#__PURE__*/React.createElement("div", {
        className: "grid grid-cols-2 gap-3 mb-5"
      }, SWITCHES.map(s => {
        const active = (switchId || "hm1") === s.id;
        return /*#__PURE__*/React.createElement("button", {
          key: s.id,
          onClick: () => onPickSwitch && onPickSwitch(s.id),
          className: `text-left rounded-lg border p-3 transition-all
                                ${active ? "border-[var(--accent)]/50 bg-[var(--accent)]/[0.06] shadow-[0_0_14px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] hover:border-white/20"}`
        }, /*#__PURE__*/React.createElement("div", {
          className: "flex items-center gap-2"
        }, /*#__PURE__*/React.createElement("div", {
          className: "font-display text-[14px] text-slate-100"
        }, s.name), /*#__PURE__*/React.createElement("span", {
          className: "w-2.5 h-2.5 rounded-full",
          style: {
            background: s.dot,
            boxShadow: `0 0 8px ${s.dot}`
          }
        })), /*#__PURE__*/React.createElement("div", {
          className: "font-mono text-[10px] text-slate-500 uppercase tracking-[0.18em] mt-0.5"
        }, s.sub));
      })), /*#__PURE__*/React.createElement("div", {
        className: "rounded-xl border border-white/[0.06] bg-black/30 p-4"
      }, /*#__PURE__*/React.createElement("div", {
        className: "flex items-center gap-2 mb-3"
      }, /*#__PURE__*/React.createElement("span", {
        className: "w-2.5 h-2.5 rounded-full",
        style: {
          background: cur.dot,
          boxShadow: `0 0 8px ${cur.dot}`
        }
      }), /*#__PURE__*/React.createElement("span", {
        className: "font-display text-[13px] text-slate-100"
      }, cur.name), /*#__PURE__*/React.createElement("span", {
        className: "font-mono text-[10px] text-slate-500 uppercase tracking-[0.18em]"
      }, cur.maker, " \xB7 ", cur.sub)), /*#__PURE__*/React.createElement("div", {
        className: "grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3 font-mono text-[11px]"
      }, [["Total Travel", cur.travel], ["Actuation Range", cur.range], ["Initial Force", cur.force], ["Sensing", cur.poles + " Hall"], ["Rated Life", cur.life + " presses"], ["Tech", "Magnetic / Analog"]].map(([k, v]) => /*#__PURE__*/React.createElement("div", {
        key: k
      }, /*#__PURE__*/React.createElement("div", {
        className: "text-slate-500 uppercase tracking-[0.14em] text-[9.5px]"
      }, k), /*#__PURE__*/React.createElement("div", {
        className: "text-slate-100 mt-0.5"
      }, v))))));
    })(), tab === "poll" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-slate-400 mb-5"
    }, "Switch the polling rate of the device. The keyboard will restart and disconnect briefly after switching."), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-wrap gap-2"
    }, [1, 2, 4, 8].map(p => /*#__PURE__*/React.createElement("button", {
      key: p,
      onClick: () => setPolling(p),
      className: `px-4 h-9 rounded-md border font-display text-[12px] uppercase tracking-[0.16em] transition-all
                                ${polling === p ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_18px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"}`
    }, p, "KHz"))), /*#__PURE__*/React.createElement("div", {
      className: "mt-6 p-4 rounded-lg border border-white/[0.06] bg-black/30 font-mono text-[11px] text-slate-400 leading-relaxed"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "text-slate-500"
    }, "current"), " \xB7 ", /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, polling, "000 Hz"), " \xB7 ", (1000 / polling).toFixed(2), "ms tick"), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "text-slate-500"
    }, "latency"), " \xB7 ~", (0.5 + 1 / polling).toFixed(2), "ms end-to-end"))), tab === "calib" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[12px] uppercase tracking-[0.18em] text-slate-200 mb-3"
    }, "Key Calibration"), /*#__PURE__*/React.createElement("button", {
      onClick: () => onCalibrate && onCalibrate(!calibrating),
      className: "px-5 h-10 rounded-md border border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] font-display text-[12px] uppercase tracking-[0.18em] shadow-[0_0_18px_var(--accent-glow)] mb-5"
    }, calibrating ? "Stop Calibration" : "Start Calibration"), /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-slate-300 mb-2"
    }, "Calibration steps:"), /*#__PURE__*/React.createElement("ol", {
      className: "space-y-2 text-[12px] text-slate-400 max-w-2xl"
    }, ["Click the Start Calibration button", "Press the required key (Hit bottom)", "Wait for the corresponding key to change color, and the key calibration is complete", "Click the Stop Calibration button"].map((step, i) => /*#__PURE__*/React.createElement("li", {
      key: i,
      className: "flex items-start gap-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: "shrink-0 grid place-items-center w-5 h-5 rounded border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent)] font-mono text-[10px]"
    }, i + 1), /*#__PURE__*/React.createElement("span", null, step))))))));
  };
  const SwitchRender = ({
    depth,
    actuation
  }) => {
    // Stylized magnetic switch: bottom housing, stem moves with depth
    const stemY = Math.min(40, depth / 4 * 40); // 0..40px push-down
    return /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "relative w-[110px] h-[150px] flex-shrink-0"
    }, /*#__PURE__*/React.createElement("div", {
      className: "absolute left-1/2 -translate-x-1/2 bottom-0 w-20 h-16 rounded-md bg-gradient-to-b from-emerald-200/20 to-emerald-300/10 border border-emerald-200/15"
    }), /*#__PURE__*/React.createElement("div", {
      className: "absolute left-1/2 -translate-x-1/2 bottom-2 w-14 h-4 rounded-sm bg-slate-900/60 border border-white/10"
    }), /*#__PURE__*/React.createElement("div", {
      className: "absolute left-1/2 -translate-x-1/2 w-8 rounded-t-sm bg-slate-100/95 border border-white/30 shadow-[0_2px_6px_rgba(0,0,0,0.4)]",
      style: {
        top: 18 + stemY,
        height: 60
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "absolute left-1/2 -translate-x-1/2 top-1 w-3 h-3 bg-slate-300 rounded-sm"
    }), /*#__PURE__*/React.createElement("div", {
      className: "absolute left-1/2 -translate-x-1/2 bottom-1 w-1 h-1 bg-rose-500 rounded-full"
    })), /*#__PURE__*/React.createElement("div", {
      className: "absolute left-1/2 -translate-x-1/2 bottom-6 w-12 h-12 rounded-full blur-2xl bg-[var(--accent)]/30 opacity-70"
    })), /*#__PURE__*/React.createElement("div", {
      className: "relative flex flex-col justify-between h-[150px] text-right pr-1"
    }, /*#__PURE__*/React.createElement("div", {
      className: "absolute -right-1 inset-y-0 w-px bg-white/10"
    }), [0, 1, 2, 3, 4].map(mm => /*#__PURE__*/React.createElement("div", {
      key: mm,
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-slate-400"
    }, mm, ".0mm"), /*#__PURE__*/React.createElement("span", {
      className: "w-2 h-px bg-white/30"
    }))), /*#__PURE__*/React.createElement("div", {
      className: "absolute right-0 w-3 h-px bg-[var(--accent)] shadow-[0_0_8px_var(--accent-glow)]",
      style: {
        top: `${depth / 4 * 100}%`
      }
    })));
  };

  /* Selection toolbar (visible above keyboard when in actuation mode) */
  const ActuationToolbar = ({
    onSelectAll,
    onSelectInvert,
    onDeselectAll,
    onResetTrigger
  }) => /*#__PURE__*/React.createElement("div", {
    className: "flex flex-col gap-1.5"
  }, [{
    label: "Select All",
    onClick: onSelectAll
  }, {
    label: "Select Invert",
    onClick: onSelectInvert
  }, {
    label: "Deselect All",
    onClick: onDeselectAll
  }, {
    label: "Reset Trigger",
    onClick: onResetTrigger,
    primary: true
  }].map(b => /*#__PURE__*/React.createElement("button", {
    key: b.label,
    onClick: b.onClick,
    className: `w-[110px] h-8 rounded-md border font-display text-[10.5px] uppercase tracking-[0.16em] transition-all
                    ${b.primary ? "border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25 shadow-[0_0_10px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"}`
  }, b.label)));

  /* ===== LIGHTING SECTION ===== */
  const PRESETS = [{
    id: "neon",
    name: "Neon Red",
    hex: "#ff1f5a"
  }, {
    id: "cyber",
    name: "Cyber Green",
    hex: "#39ff8a"
  }, {
    id: "elec",
    name: "Electric Blue",
    hex: "#00b8ff"
  }, {
    id: "violet",
    name: "Hyper Violet",
    hex: "#9d4edd"
  }, {
    id: "amber",
    name: "Solar Amber",
    hex: "#ffaa1f"
  }, {
    id: "ice",
    name: "Glacier Ice",
    hex: "#c7f3ff"
  }];
  const LIGHT_MODES = [{
    id: "wave",
    label: "Wave",
    icon: "〰"
  }, {
    id: "neon",
    label: "Neon",
    icon: "◎"
  }, {
    id: "radar",
    label: "Radar",
    icon: "◒"
  }, {
    id: "cross",
    label: "Cross",
    icon: "✚"
  }, {
    id: "breath",
    label: "Breath",
    icon: "○"
  }, {
    id: "static",
    label: "Static",
    icon: "■"
  }, {
    id: "aurora",
    label: "Aurora",
    icon: "◐"
  }, {
    id: "ripple",
    label: "Ripple",
    icon: "◎"
  }, {
    id: "twinkle",
    label: "Twinkle",
    icon: "✸"
  }, {
    id: "reactive",
    label: "Reactive",
    icon: "☼"
  }, {
    id: "striation",
    label: "Striation",
    icon: "⦹"
  }, {
    id: "fireworks",
    label: "Fireworks",
    icon: "✻"
  }, {
    id: "frenzy",
    label: "Frenzy",
    icon: "✺"
  }, {
    id: "autorip",
    label: "Auto Ripple",
    icon: "◈"
  }, {
    id: "speedres",
    label: "Speed Respond",
    icon: "⦿"
  }, {
    id: "rain",
    label: "Rain",
    icon: "☂"
  }, {
    id: "comet",
    label: "Comet",
    icon: "☄"
  }, {
    id: "tide",
    label: "Tide",
    icon: "≈"
  }, {
    id: "custom",
    label: "Custom",
    icon: "◇"
  }];

  // Per-mode capabilities (mirrors app.jsx FW_MODES, from the firmware driver).
  // bg: uses a background color · speed: has a speed control · full: Full-RGB applies
  // dir: "none" | "lr" | "ud" | "all" | "rotate" | "gather"
  const MODE_CAPS = {
    static: {
      bg: false,
      speed: false,
      dir: "none",
      full: false
    },
    breath: {
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    wave: {
      bg: true,
      speed: true,
      dir: "all",
      full: true
    },
    neon: {
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    radar: {
      bg: true,
      speed: true,
      dir: "rotate",
      full: true
    },
    reactive: {
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    cross: {
      bg: true,
      speed: true,
      dir: "gather",
      full: true
    },
    ripple: {
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    twinkle: {
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    custom: {
      bg: false,
      speed: false,
      dir: "none",
      full: false
    },
    fireworks: {
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    frenzy: {
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    speedres: {
      bg: true,
      speed: false,
      dir: "ud",
      full: true
    },
    autorip: {
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    striation: {
      bg: true,
      speed: true,
      dir: "lr",
      full: true
    },
    aurora: {
      bg: true,
      speed: true,
      dir: "none",
      full: true
    }
  };
  // Direction button sets per dir-type (value = firmware direction byte).
  const DIR_OPTS = {
    lr: [["→", 0], ["←", 1]],
    ud: [["↑", 2], ["↓", 3]],
    all: [["→", 0], ["←", 1], ["↑", 2], ["↓", 3], ["⊙", 5], ["⊕", 4]],
    rotate: [["↻", 0], ["↺", 1]],
    gather: [["⊙", 5], ["⊕", 4]]
  };
  const ZONE_MODES = [{
    id: "twinkle",
    label: "Twinkle"
  }, {
    id: "wave",
    label: "Wave"
  }, {
    id: "striation",
    label: "Striation"
  }, {
    id: "radar",
    label: "Radar"
  }, {
    id: "ripple",
    label: "Ripple"
  }, {
    id: "cross",
    label: "Cross"
  }, {
    id: "fireworks",
    label: "Fireworks"
  }, {
    id: "aurora",
    label: "Aurora"
  }, {
    id: "breath",
    label: "Breath"
  }, {
    id: "static",
    label: "Static"
  }, {
    id: "rain",
    label: "Rain"
  }, {
    id: "comet",
    label: "Comet"
  }, {
    id: "tide",
    label: "Tide"
  }];

  /* Effect zones: each = a group of keys running its own effect+colors. */
  const ZonesPanel = ({
    zones,
    selectedKeys,
    onAdd,
    onUpdate,
    onRemove
  }) => /*#__PURE__*/React.createElement("div", {
    className: "rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center justify-between mb-3"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "font-display text-[12px] uppercase tracking-[0.18em] text-slate-200"
  }, "Effect Zones"), /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[10px] text-slate-500 mt-0.5"
  }, "Select keys on the board, add a zone, give it its own effect")), /*#__PURE__*/React.createElement("button", {
    onClick: onAdd,
    disabled: !selectedKeys || selectedKeys.size === 0,
    className: "px-2.5 h-8 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] disabled:opacity-40 font-display text-[10.5px] uppercase tracking-[0.16em]"
  }, "+ Zone (", selectedKeys?.size ?? 0, ")")), (!zones || zones.length === 0) && /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[11px] text-slate-500"
  }, "No zones yet \u2014 select keys, then click \u201C+ Zone\u201D. Keys outside every zone stay off."), /*#__PURE__*/React.createElement("div", {
    className: "flex flex-col gap-2"
  }, (zones || []).map(z => /*#__PURE__*/React.createElement("div", {
    key: z.id,
    className: "rounded-lg border border-white/[0.06] bg-black/20 p-2.5"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-2 mb-2"
  }, /*#__PURE__*/React.createElement("select", {
    value: z.mode,
    onChange: e => onUpdate(z.id, {
      mode: e.target.value
    }),
    className: "flex-1 h-8 rounded-md bg-black/40 border border-white/[0.08] text-slate-100 font-display text-[11px] uppercase tracking-[0.12em] px-2 outline-none"
  }, ZONE_MODES.map(m => /*#__PURE__*/React.createElement("option", {
    key: m.id,
    value: m.id
  }, m.label))), /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[10px] text-slate-500 whitespace-nowrap"
  }, z.codes.length, " keys"), /*#__PURE__*/React.createElement("button", {
    onClick: () => onRemove(z.id),
    title: "Remove zone",
    className: "w-7 h-7 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-400 hover:text-rose-300 hover:border-rose-400/40"
  }, "\u2715")), /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-2"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-1.5"
  }, (z.colors || []).map((c, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "relative w-7 h-7"
  }, /*#__PURE__*/React.createElement("div", {
    className: "w-full h-full rounded-md ring-1 ring-white/10",
    style: {
      background: c
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "color",
    value: c,
    onChange: e => {
      const cs = [...z.colors];
      cs[i] = e.target.value;
      onUpdate(z.id, {
        colors: cs
      });
    },
    className: "absolute inset-0 opacity-0 cursor-pointer w-full h-full"
  })), z.colors.length > 1 && /*#__PURE__*/React.createElement("button", {
    onClick: () => onUpdate(z.id, {
      colors: z.colors.filter((_, j) => j !== i)
    }),
    className: "absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-slate-900 ring-1 ring-white/20 text-slate-300 hover:text-rose-300 grid place-items-center text-[9px]"
  }, "\u2715"))), (z.colors || []).length < 4 && /*#__PURE__*/React.createElement("button", {
    onClick: () => onUpdate(z.id, {
      colors: [...(z.colors || []), "#ffffff"]
    }),
    className: "w-7 h-7 rounded-md border-2 border-dashed border-white/15 text-slate-400 hover:border-white/30 grid place-items-center text-[12px]"
  }, "+")), /*#__PURE__*/React.createElement("div", {
    className: "flex-1 flex items-center gap-2"
  }, /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[9px] uppercase tracking-[0.18em] text-slate-500"
  }, "Spd"), /*#__PURE__*/React.createElement("input", {
    type: "range",
    className: "aether flex-1",
    min: 0,
    max: 100,
    step: 1,
    value: z.speed != null ? z.speed : 60,
    style: {
      "--pct": (z.speed != null ? z.speed : 60) + "%"
    },
    onChange: e => onUpdate(z.id, {
      speed: parseFloat(e.target.value)
    })
  })))))));
  const LightingSection = ({
    colors,
    setColors,
    bgColor,
    setBgColor,
    perKeyColors,
    setPerKeyColors,
    pattern,
    setPattern,
    brightness,
    setBrightness,
    speed,
    setSpeed,
    power,
    setPower,
    fullColor,
    setFullColor,
    direction,
    setDirection,
    striOrient,
    setStriOrient,
    bgBright,
    setBgBright,
    zones,
    onAddZone,
    onUpdateZone,
    onRemoveZone,
    selectedKeys,
    onSelectAll,
    onClearSelection
  }) => {
    const palette = colors || []; // may be empty — user builds their own palette
    // Full RGB (rainbow) isn't meaningful for Static or per-key Custom.
    const fullColorOk = pattern !== "static" && pattern !== "custom";
    const [activeSlot, setActiveSlot] = useState(0);
    const setSlot = (i, value) => {
      const p = [...palette];
      p[i] = value;
      setColors(p);
    };
    const addSlot = () => {
      if (palette.length >= 4) return;
      const seeds = ["#663390", "#009fa6", "#a62848", "#a66e14"]; // ~2 tones darker defaults
      const next = seeds[palette.length] || "#a6a6a6";
      setColors([...palette, next]);
      setActiveSlot(palette.length);
    };
    const removeSlot = i => {
      if (palette.length <= 0) return;
      const p = palette.filter((_, idx) => idx !== i);
      setColors(p);
      if (activeSlot >= p.length) setActiveSlot(p.length - 1);
    };

    // Apply currently-active palette slot to selected keys
    const assignToSelection = () => {
      if (!selectedKeys || selectedKeys.size === 0) return;
      const c = palette[activeSlot] || palette[0];
      const next = {
        ...(perKeyColors || {})
      };
      selectedKeys.forEach(code => {
        next[code] = c;
      });
      setPerKeyColors(next);
    };
    const clearPerKeyForSelection = () => {
      if (!selectedKeys || selectedKeys.size === 0) return;
      const next = {
        ...(perKeyColors || {})
      };
      selectedKeys.forEach(code => {
        delete next[code];
      });
      setPerKeyColors(next);
    };
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between mb-5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[15px] text-slate-100 tracking-[0.02em] font-semibold"
    }, "Lighting"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500"
    }, "RGB engine \xB7 per-key")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-4"
    }, fullColorOk && /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2",
      title: "Cycle the full RGB spectrum (rainbow) instead of the chosen colors"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-slate-300"
    }, "Full RGB"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setFullColor(!fullColor),
      className: `relative w-10 h-5 rounded-full border transition-colors
                            ${fullColor ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-white/[0.08]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                                  ${fullColor ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`
    }))), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-slate-300"
    }, "Power"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setPower(!power),
      className: `relative w-10 h-5 rounded-full border transition-colors
                          ${power ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-white/[0.08]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                                ${power ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`
    }))))), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 lg:grid-cols-[1.1fr_1fr] gap-6"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-5"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-slate-400 mb-2"
    }, "Light Mode"), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-1.5"
    }, LIGHT_MODES.map(m => {
      const active = pattern === m.id;
      return /*#__PURE__*/React.createElement("button", {
        key: m.id,
        onClick: () => setPattern(m.id),
        className: `h-9 rounded-lg border font-display text-[11px] tracking-[0.06em] flex items-center justify-center gap-1.5 transition-all
                                ${active ? "border-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"}`,
        style: active ? {
          background: "var(--accent-gradient, var(--accent))"
        } : {}
      }, /*#__PURE__*/React.createElement("span", {
        className: "text-[12px]"
      }, m.icon), " ", m.label);
    }))), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 gap-5"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-1.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-slate-400"
    }, "Brightness"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[12px] text-[var(--accent)]"
    }, Math.round(brightness), "%")), /*#__PURE__*/React.createElement("input", {
      type: "range",
      className: "aether w-full",
      min: 0,
      max: 100,
      step: 1,
      value: brightness,
      style: {
        "--pct": brightness + "%"
      },
      onChange: e => setBrightness(parseFloat(e.target.value))
    })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-1.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-slate-400"
    }, "Speed"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[12px] text-[var(--accent)]"
    }, Math.round(speed), "%")), /*#__PURE__*/React.createElement("input", {
      type: "range",
      className: "aether w-full",
      min: 0,
      max: 100,
      step: 1,
      value: speed,
      style: {
        "--pct": speed + "%"
      },
      onChange: e => setSpeed(parseFloat(e.target.value))
    }))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-slate-400 mb-2"
    }, "Direction"), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-4 gap-1.5 max-w-[220px]"
    }, [["→", 0], ["←", 1], ["↑", 2], ["↓", 3]].map(([arrow, val]) => {
      const active = direction === val;
      return /*#__PURE__*/React.createElement("button", {
        key: val,
        onClick: () => setDirection(val),
        className: `h-9 rounded-lg border text-[15px] transition-all
                                ${active ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"}`
      }, arrow);
    }))), pattern === "striation" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-slate-400 mb-2"
    }, "Stripe Orientation"), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-1.5 max-w-[260px]"
    }, [["Vertical", "v", "▥"], ["Horizontal", "h", "▤"], ["Both", "both", "▦"]].map(([lbl, val, ic]) => {
      const active = (striOrient || "v") === val;
      return /*#__PURE__*/React.createElement("button", {
        key: val,
        onClick: () => setStriOrient && setStriOrient(val),
        className: `h-9 rounded-lg border text-[11px] uppercase tracking-[0.12em] flex items-center justify-center gap-1.5 transition-all
                                  ${active ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"}`
      }, /*#__PURE__*/React.createElement("span", {
        className: "text-[14px]"
      }, ic), lbl);
    }))), /*#__PURE__*/React.createElement("div", {
      className: "rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-2.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-slate-300"
    }, "Background color"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-slate-500"
    }, "underlies the effect")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-3"
    }, /*#__PURE__*/React.createElement("div", {
      className: "relative w-14 h-12 rounded-xl overflow-hidden ring-1 ring-white/10",
      style: {
        background: bgColor,
        boxShadow: `0 0 18px ${bgColor}55`
      }
    }, /*#__PURE__*/React.createElement("input", {
      type: "color",
      value: bgColor,
      onChange: e => setBgColor(e.target.value),
      className: "absolute inset-0 opacity-0 cursor-pointer w-full h-full"
    })), /*#__PURE__*/React.createElement("input", {
      type: "text",
      value: bgColor.toUpperCase(),
      onChange: e => {
        const v = e.target.value;
        if (/^#[0-9a-fA-F]{6}$/.test(v)) setBgColor(v);else setBgColor(v);
      },
      className: "flex-1 h-10 px-3 rounded-lg bg-black/30 border border-white/[0.06] font-mono text-[12px] text-slate-100 outline-none focus:border-white/20"
    }), /*#__PURE__*/React.createElement("button", {
      onClick: () => setBgColor("#000000"),
      className: "px-2.5 h-10 rounded-lg border border-white/[0.06] bg-white/[0.02] text-slate-300 hover:text-white hover:border-white/20 font-display text-[10.5px] uppercase tracking-[0.16em]"
    }, "Off")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-1.5 mt-2.5"
    }, ["#000000", "#0b0f19", "#1a0833", "#001318", "#0a1f10", "#241400", "#2a0814", "#ffffff"].map(c => /*#__PURE__*/React.createElement("button", {
      key: c,
      onClick: () => setBgColor(c),
      className: `w-6 h-6 rounded-md ring-1 ${bgColor.toLowerCase() === c.toLowerCase() ? "ring-white scale-110" : "ring-white/15 hover:scale-105"} transition-transform`,
      style: {
        background: c
      },
      title: c
    }))))), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-4"
    }, pattern !== "custom" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-slate-300"
    }, "Effect colors \xB7 ", palette.length, "/4"), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-3"
    }, palette.length > 0 && /*#__PURE__*/React.createElement("button", {
      onClick: () => setColors([]),
      className: "font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400 hover:text-rose-300"
    }, "Clear all"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-slate-500"
    }, "click slot to recolor"))), /*#__PURE__*/React.createElement("div", {
      className: "flex items-stretch gap-2 mb-3"
    }, palette.map((c, i) => {
      const isActive = activeSlot === i;
      return /*#__PURE__*/React.createElement("div", {
        key: i,
        className: "relative flex-1 min-w-0 group"
      }, /*#__PURE__*/React.createElement("button", {
        onClick: () => setActiveSlot(i),
        className: `relative w-full h-16 rounded-2xl overflow-hidden ring-1 transition-all
                                  ${isActive ? "ring-2 ring-white/80 scale-[1.02]" : "ring-white/10 hover:scale-[1.01]"}`,
        style: {
          background: c,
          boxShadow: `0 0 24px ${c}55, inset 0 0 0 1px rgba(255,255,255,0.06)`
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "absolute bottom-1.5 left-2 text-[10px] font-mono text-white/85",
        style: {
          textShadow: "0 1px 4px rgba(0,0,0,0.6)"
        }
      }, c.toUpperCase()), /*#__PURE__*/React.createElement("input", {
        type: "color",
        value: c,
        onChange: e => setSlot(i, e.target.value),
        onClick: e => e.stopPropagation(),
        className: "absolute inset-0 opacity-0 cursor-pointer w-full h-full"
      })), palette.length > 0 && /*#__PURE__*/React.createElement("button", {
        onClick: e => {
          e.stopPropagation();
          removeSlot(i);
        },
        title: "Remove",
        className: "absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-slate-900 ring-1 ring-white/20 text-slate-300 hover:text-rose-300 grid place-items-center text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
      }, "\u2715"));
    }), palette.length < 4 && /*#__PURE__*/React.createElement("button", {
      onClick: addSlot,
      className: "flex-1 min-w-0 h-16 rounded-2xl border-2 border-dashed border-white/15 bg-white/[0.02] text-slate-400 hover:border-white/30 hover:bg-white/[0.04] hover:text-white grid place-items-center transition-all"
    }, /*#__PURE__*/React.createElement("span", {
      className: "flex items-center gap-1.5 font-display text-[11px] uppercase tracking-[0.18em]"
    }, /*#__PURE__*/React.createElement(IPlus, {
      size: 13
    }), " Add"))), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-4 gap-2"
    }, [["#9d4edd"], ["#00f5ff"], ["#ff3d6e"], ["#39ff8a"], ["#9d4edd", "#00f5ff"], ["#ff7a59", "#ffaa1f"], ["#ff3d6e", "#ffaa1f", "#39ff8a"], ["#ff3d6e", "#ffaa1f", "#39ff8a", "#3b82f6"]].map((p, i) => /*#__PURE__*/React.createElement("button", {
      key: i,
      onClick: () => {
        setColors([...p]);
        setActiveSlot(0);
      },
      className: "h-7 rounded-lg ring-1 ring-white/10 hover:scale-[1.02] transition-transform overflow-hidden",
      title: p.join(", ")
    }, /*#__PURE__*/React.createElement("div", {
      className: "w-full h-full flex"
    }, p.map((c, j) => /*#__PURE__*/React.createElement("span", {
      key: j,
      className: "flex-1",
      style: {
        background: c
      }
    }))))))), /*#__PURE__*/React.createElement("div", {
      className: "rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between mb-3"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[12px] uppercase tracking-[0.18em] text-slate-200"
    }, "Per-key colors"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] text-slate-500 mt-0.5"
    }, selectedKeys?.size ?? 0, " key", (selectedKeys?.size ?? 0) === 1 ? "" : "s", " selected \xB7 Ctrl/\u2318-click to toggle")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-1.5"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: onSelectAll,
      className: "px-2.5 h-8 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 hover:text-white hover:border-white/20 font-display text-[10.5px] uppercase tracking-[0.16em]"
    }, "Select all"), /*#__PURE__*/React.createElement("button", {
      onClick: onClearSelection,
      className: "px-2.5 h-8 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 hover:text-white hover:border-white/20 font-display text-[10.5px] uppercase tracking-[0.16em]"
    }, "Clear"))), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: assignToSelection,
      disabled: !selectedKeys || selectedKeys.size === 0,
      className: "flex-1 h-10 rounded-lg font-display text-[12px] uppercase tracking-[0.18em] text-[var(--accent-fg)] disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:brightness-110",
      style: {
        background: "var(--accent-gradient, var(--accent))",
        boxShadow: "0 8px 24px -8px var(--accent-glow)"
      }
    }, "Paint selected with slot ", activeSlot + 1), /*#__PURE__*/React.createElement("button", {
      onClick: clearPerKeyForSelection,
      disabled: !selectedKeys || selectedKeys.size === 0,
      className: "px-3 h-10 rounded-lg border border-white/[0.06] bg-white/[0.02] text-slate-300 hover:text-white hover:border-white/20 disabled:opacity-40 font-display text-[11.5px] uppercase tracking-[0.18em]"
    }, "Reset"))), pattern === "custom" && /*#__PURE__*/React.createElement(ZonesPanel, {
      zones: zones,
      selectedKeys: selectedKeys,
      onAdd: onAddZone,
      onUpdate: onUpdateZone,
      onRemove: onRemoveZone
    }))));
  };
  const LightingSection_unused = () => {
    return null;
  };
  const _Old_Lighting_remove = ({
    color,
    setColor,
    pattern,
    setPattern,
    brightness,
    setBrightness,
    speed,
    setSpeed
  }) => {
    const [tab, setTab] = useState("color");
    const [flash, setFlash] = useState(false);
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(SubTabs, {
      active: tab,
      onChange: setTab,
      tabs: [{
        id: "color",
        label: "Color",
        icon: /*#__PURE__*/React.createElement(IPalette, {
          size: 13
        })
      }, {
        id: "pattern",
        label: "Pattern",
        icon: /*#__PURE__*/React.createElement(IWaves, {
          size: 13
        })
      }, {
        id: "per-key",
        label: "Per Key",
        icon: /*#__PURE__*/React.createElement(IGrid, {
          size: 13
        })
      }]
    }), tab === "color" && /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 md:grid-cols-[220px_1fr] gap-6"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col items-center gap-3"
    }, /*#__PURE__*/React.createElement("div", {
      className: "relative"
    }, /*#__PURE__*/React.createElement("div", {
      className: "absolute inset-0 rounded-full blur-2xl opacity-70",
      style: {
        background: `radial-gradient(circle, ${color}, transparent 70%)`
      }
    }), /*#__PURE__*/React.createElement("div", {
      className: "relative w-[170px] h-[170px] rounded-full p-[3px]",
      style: {
        background: `conic-gradient(from 0deg, #ff1f5a, #ffaa1f, #39ff8a, #00f5ff, #5b8cff, #9d4edd, #ff1f5a)`
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "w-full h-full rounded-full bg-[var(--bg-1)] p-2 grid place-items-center"
    }, /*#__PURE__*/React.createElement("div", {
      className: "relative w-full h-full rounded-full overflow-hidden ring-1 ring-white/10",
      style: {
        background: color,
        boxShadow: `inset 0 0 30px rgba(0,0,0,0.4), 0 0 30px ${color}55`
      }
    }, /*#__PURE__*/React.createElement("input", {
      type: "color",
      value: color,
      onChange: e => setColor(e.target.value),
      className: "absolute inset-0 opacity-0 cursor-pointer w-full h-full"
    }))))), /*#__PURE__*/React.createElement("div", {
      className: "text-center"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500"
    }, "picked"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[13px] text-slate-100"
    }, color.toUpperCase()))), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-5"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-2"
    }, "Quick Presets"), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-6 gap-2"
    }, PRESETS.map(p => {
      const active = color.toLowerCase() === p.hex.toLowerCase();
      return /*#__PURE__*/React.createElement("button", {
        key: p.id,
        onClick: () => setColor(p.hex),
        title: p.name,
        className: `group relative aspect-square rounded-lg border transition-all overflow-hidden
                                  ${active ? "border-white/40 scale-[1.04]" : "border-white/[0.06] hover:border-white/20"}`,
        style: {
          background: p.hex,
          boxShadow: active ? `0 0 18px ${p.hex}80` : "none"
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.35),transparent_50%)]"
      }), active && /*#__PURE__*/React.createElement("span", {
        className: "absolute bottom-1 right-1 w-4 h-4 rounded-full bg-black/60 grid place-items-center text-white"
      }, /*#__PURE__*/React.createElement(ICheck, {
        size: 10,
        strokeWidth: 2.5
      })));
    }))), /*#__PURE__*/React.createElement(Slider, {
      label: "Brightness",
      value: brightness,
      min: 0,
      max: 100,
      step: 1,
      unit: "%",
      onChange: setBrightness
    }), /*#__PURE__*/React.createElement("button", {
      onClick: () => {
        setFlash(true);
        setTimeout(() => setFlash(false), 350);
      },
      className: `h-11 rounded-xl border font-display uppercase tracking-[0.18em] text-[12px] font-semibold transition-all
                          border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25
                          shadow-[0_0_18px_var(--accent-glow)] ${flash ? "flash-on-click" : ""}`
    }, /*#__PURE__*/React.createElement("span", {
      className: "flex items-center justify-center gap-2"
    }, /*#__PURE__*/React.createElement(IWaves, {
      size: 14
    }), " Apply Color")))), tab === "pattern" && /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 md:grid-cols-[1fr_280px] gap-6"
    }, /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 lg:grid-cols-3 gap-3"
    }, PATTERNS.map(p => {
      const active = pattern === p.id;
      return /*#__PURE__*/React.createElement("button", {
        key: p.id,
        onClick: () => setPattern(p.id),
        className: `text-left rounded-xl border p-4 transition-all
                              ${active ? "border-[var(--accent)]/60 bg-[var(--accent)]/[0.06] shadow-[0_0_18px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] hover:border-white/20"}`
      }, /*#__PURE__*/React.createElement("div", {
        className: "font-display text-[14px] text-slate-100 mb-1"
      }, p.label), /*#__PURE__*/React.createElement("div", {
        className: "text-[11px] text-slate-400"
      }, p.desc), /*#__PURE__*/React.createElement(PatternPreview, {
        kind: p.id,
        color: active ? "var(--accent)" : "#94a3b8"
      }));
    })), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-5 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4"
    }, /*#__PURE__*/React.createElement(Slider, {
      label: "Speed",
      value: speed,
      min: 0,
      max: 100,
      step: 1,
      unit: "%",
      onChange: setSpeed
    }), /*#__PURE__*/React.createElement(Slider, {
      label: "Brightness",
      value: brightness,
      min: 0,
      max: 100,
      step: 1,
      unit: "%",
      onChange: setBrightness
    }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-2"
    }, "Direction"), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-4 gap-1.5"
    }, ["←", "↑", "→", "↓"].map(d => /*#__PURE__*/React.createElement("button", {
      key: d,
      className: "h-8 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"
    }, d)))))), tab === "per-key" && /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-5"
    }, /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-slate-400 mb-3"
    }, "Click any key above to assign a color. Bulk-select with Shift-click."), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-8 gap-1.5"
    }, ["#ff1f5a", "#ffaa1f", "#39ff8a", "#00f5ff", "#5b8cff", "#9d4edd", "#c77dff", "#ffffff"].map(c => /*#__PURE__*/React.createElement("button", {
      key: c,
      onClick: () => setColor(c),
      className: "aspect-square rounded-md border border-white/10 hover:scale-105 transition-transform",
      style: {
        background: c,
        boxShadow: `0 0 12px ${c}50`
      }
    })))));
  };
  const PatternPreview = ({
    kind,
    color
  }) => /*#__PURE__*/React.createElement("svg", {
    viewBox: "0 0 100 30",
    className: "w-full h-8 mt-3",
    preserveAspectRatio: "none"
  }, kind === "static" && Array.from({
    length: 8
  }).map((_, i) => /*#__PURE__*/React.createElement("rect", {
    key: i,
    x: i * 13 + 2,
    y: 6,
    width: "10",
    height: "18",
    rx: "2",
    fill: color,
    opacity: "0.7"
  })), kind === "wave" && Array.from({
    length: 8
  }).map((_, i) => /*#__PURE__*/React.createElement("rect", {
    key: i,
    x: i * 13 + 2,
    y: 6,
    width: "10",
    height: "18",
    rx: "2",
    fill: color,
    opacity: 0.2 + (Math.sin(i) + 1) * 0.4
  })), kind === "react" && Array.from({
    length: 8
  }).map((_, i) => /*#__PURE__*/React.createElement("rect", {
    key: i,
    x: i * 13 + 2,
    y: 6,
    width: "10",
    height: "18",
    rx: "2",
    fill: color,
    opacity: i === 3 ? 1 : 0.15
  })), kind === "ripple" && [10, 18, 26].map((r, i) => /*#__PURE__*/React.createElement("circle", {
    key: i,
    cx: "50",
    cy: "15",
    r: r,
    fill: "none",
    stroke: color,
    strokeWidth: "0.8",
    opacity: 1 - i * 0.3
  })), kind === "breathe" && /*#__PURE__*/React.createElement("rect", {
    x: "2",
    y: "6",
    width: "96",
    height: "18",
    rx: "3",
    fill: color,
    opacity: "0.5"
  }), kind === "rain" && Array.from({
    length: 6
  }).map((_, i) => /*#__PURE__*/React.createElement("line", {
    key: i,
    x1: i * 18 + 8,
    x2: i * 18 + 8,
    y1: i * 4,
    y2: i * 4 + 12,
    stroke: color,
    strokeWidth: "1.5"
  })));

  /* ===== SOCD SECTION ===== */
  const SOCDSection = ({
    socdMode,
    setSocdMode,
    hotkey,
    hotkeyEnabled,
    setHotkeyEnabled,
    onApply,
    profiles,
    setProfiles,
    active,
    setActive
  }) => {
    const cur = profiles.find(p => p.id === active) || profiles[0];
    const updateActive = patch => setProfiles(ps => ps.map(p => p.id === active ? {
      ...p,
      ...patch
    } : p));
    const addProfile = () => {
      const next = `SOCD${profiles.length + 1}`;
      setProfiles([...profiles, {
        id: next,
        k1: "",
        k2: "",
        mode: 1
      }]);
      setActive(next);
    };
    const delActive = () => {
      if (profiles.length <= 1) return;
      const remaining = profiles.filter(p => p.id !== active);
      setProfiles(remaining);
      setActive(remaining[0].id);
    };
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "flex flex-wrap items-center gap-4 mb-5 pb-4 border-b border-white/[0.06]"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-slate-300"
    }, "Switch"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setHotkeyEnabled(!hotkeyEnabled),
      className: `relative w-10 h-5 rounded-full border transition-colors
                        ${hotkeyEnabled ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-white/[0.08]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                              ${hotkeyEnabled ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`
    }))), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[11px] text-slate-400"
    }, "Hotkey: ", /*#__PURE__*/React.createElement("span", {
      className: "text-slate-100"
    }, hotkey)), /*#__PURE__*/React.createElement("div", {
      className: "ml-auto"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => onApply && onApply(profiles, hotkeyEnabled),
      className: "px-5 h-9 rounded-md border border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] font-display text-[12px] uppercase tracking-[0.16em] shadow-[0_0_18px_var(--accent-glow)] hover:brightness-110"
    }, "Apply"))), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 lg:grid-cols-[200px_320px_1fr] gap-5"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-2"
    }, profiles.length, "/20 slots"), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-1.5 mb-3"
    }, profiles.map(p => /*#__PURE__*/React.createElement("button", {
      key: p.id,
      onClick: () => setActive(p.id),
      className: `flex items-center justify-between px-3 h-8 rounded-md border font-mono text-[12px] transition-all
                            ${active === p.id ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 text-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"}`
    }, /*#__PURE__*/React.createElement("span", null, p.id), p.k1 && p.k2 && /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-slate-500"
    }, p.k1, " \u2194 ", p.k2)))), /*#__PURE__*/React.createElement("div", {
      className: "flex gap-2"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: addProfile,
      className: "flex-1 flex items-center justify-center gap-1 h-8 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20 font-display text-[11px] uppercase tracking-[0.16em]"
    }, /*#__PURE__*/React.createElement(IPlus, {
      size: 12
    }), " Create"), /*#__PURE__*/React.createElement("button", {
      onClick: delActive,
      className: "flex-1 flex items-center justify-center gap-1 h-8 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-rose-400/40 hover:text-rose-300 font-display text-[11px] uppercase tracking-[0.16em]"
    }, /*#__PURE__*/React.createElement(ITrash, {
      size: 12
    }), " Delete"))), /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-3 mb-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex-1"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-1"
    }, "Key 1"), /*#__PURE__*/React.createElement("div", {
      className: `h-9 rounded-md border grid place-items-center font-mono text-[14px]
                               ${cur?.k1 ? "border-[var(--accent)]/50 text-[var(--accent)] bg-[var(--accent)]/10" : "border-white/[0.06] text-slate-500 bg-white/[0.02]"}`
    }, cur?.k1 || "—")), /*#__PURE__*/React.createElement("div", {
      className: "text-slate-500 mt-5"
    }, /*#__PURE__*/React.createElement(IUnlink, {
      size: 14
    })), /*#__PURE__*/React.createElement("div", {
      className: "flex-1"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.22em] text-slate-500 mb-1"
    }, "Key 2"), /*#__PURE__*/React.createElement("div", {
      className: `h-9 rounded-md border grid place-items-center font-mono text-[14px]
                               ${cur?.k2 ? "border-[var(--accent)]/50 text-[var(--accent)] bg-[var(--accent)]/10" : "border-white/[0.06] text-slate-500 bg-white/[0.02]"}`
    }, cur?.k2 || "—"))), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 gap-1.5 mb-4"
    }, [1, 2, 3, 4].map(m => /*#__PURE__*/React.createElement("button", {
      key: m,
      onClick: () => updateActive({
        mode: m
      }),
      className: `flex items-center gap-2 px-3 h-9 rounded-md border font-mono text-[12px] transition-all
                            ${cur?.mode === m ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 text-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `w-3 h-3 rounded-full border ${cur?.mode === m ? "border-[var(--accent)] bg-[var(--accent)]" : "border-slate-500"}`
    }), "Model ", m))), /*#__PURE__*/React.createElement("div", {
      className: "rounded-md border border-white/[0.06] bg-black/30 p-3 text-[11.5px] text-slate-400 leading-relaxed"
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-slate-200 font-display uppercase tracking-[0.18em] text-[10.5px] mb-2"
    }, "When both Key1 and Key2 fire:"), /*#__PURE__*/React.createElement("div", {
      className: "space-y-1.5 font-mono"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "Model 1"), " \xB7 First press wins; second is interrupted."), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "Model 2"), " \xB7 Key1 interrupts Key2."), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "Model 3"), " \xB7 Key2 interrupts Key1."), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "Model 4"), " \xB7 Later-triggered key wins (Snap Tap).")))), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-4"
    }, /*#__PURE__*/React.createElement(KeyGrid, {
      title: "Basic Keys",
      keys: BASIC_KEYS,
      picked: cur?.k1,
      onPick: k => updateActive({
        k1: cur?.k1 ? cur.k1 : k,
        k2: cur?.k1 && !cur?.k2 ? k : cur?.k2
      })
    }), /*#__PURE__*/React.createElement(KeyGrid, {
      title: "Extended Keys",
      keys: EXTENDED_KEYS,
      picked: cur?.k2,
      onPick: k => updateActive({
        k2: k
      })
    }))));
  };

  /* ===== OTHER SECTION ===== */
  const OtherSection = () => {
    const [winLock, setWinLock] = useState({
      win: true,
      shiftTab: false,
      altTab: false,
      altF4: false
    });
    // Always render the toggle on Windows — the bridge probe was racing the
    // first paint and the option would silently disappear.
    const isWindows = typeof navigator !== "undefined" && /Windows/i.test(navigator.userAgent || "");
    const [autostart, setAutostart] = useState({
      supported: isWindows,
      enabled: false
    });
    useEffect(() => {
      let cancelled = false;
      const probe = () => {
        if (!window.pywebview?.api?.get_autostart) return;
        window.pywebview.api.get_autostart().then(r => {
          if (cancelled || !r || !r.ok) return;
          setAutostart({
            supported: !!r.supported || isWindows,
            enabled: !!r.enabled
          });
        }).catch(() => {});
      };
      probe(); // try now
      const id = setInterval(probe, 600); // retry until bridge is ready
      return () => {
        cancelled = true;
        clearInterval(id);
      };
    }, []);
    const toggleAutostart = async () => {
      const next = !autostart.enabled;
      setAutostart(s => ({
        ...s,
        enabled: next
      }));
      if (!window.pywebview?.api?.set_autostart) return;
      const r = await window.pywebview.api.set_autostart(next);
      if (!(r && r.ok)) setAutostart(s => ({
        ...s,
        enabled: !next
      }));
    };
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("nav", {
      className: "flex items-center gap-1 border-b border-white/[0.06] mb-5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "relative flex items-center gap-2 px-2 h-10 -mb-px font-display text-[12px] uppercase tracking-[0.16em] text-[var(--accent)]"
    }, /*#__PURE__*/React.createElement(IGrid, {
      size: 13
    }), " Settings", /*#__PURE__*/React.createElement("span", {
      className: "absolute left-0 right-0 -bottom-px h-px bg-[var(--accent)] shadow-[0_0_8px_var(--accent-glow)]"
    }))), autostart.supported && /*#__PURE__*/React.createElement("div", {
      className: "mb-6 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 max-w-md flex items-center justify-between"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[12px] uppercase tracking-[0.18em] text-slate-200"
    }, "Start on launch"), /*#__PURE__*/React.createElement("div", {
      className: "text-[11.5px] text-slate-400 mt-1"
    }, "Open Aether automatically when you sign in to Windows.")), /*#__PURE__*/React.createElement("button", {
      onClick: toggleAutostart,
      className: `relative w-12 h-6 rounded-full border transition-colors shrink-0 ml-4
                        ${autostart.enabled ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-white/[0.08]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `absolute top-0.5 rounded-full transition-all
                              ${autostart.enabled ? "left-[26px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`,
      style: {
        width: 18,
        height: 18
      }
    }))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[12px] uppercase tracking-[0.18em] text-slate-200 mb-3"
    }, "If Win Lock is ON:"), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-3 max-w-md"
    }, [{
      id: "win",
      label: "Disable Windows key"
    }, {
      id: "shiftTab",
      label: "Disable Shift+Tab"
    }, {
      id: "altTab",
      label: "Disable Alt+Tab"
    }, {
      id: "altF4",
      label: "Disable Alt+F4"
    }].map(o => /*#__PURE__*/React.createElement("label", {
      key: o.id,
      className: "flex items-center gap-2.5 cursor-pointer select-none"
    }, /*#__PURE__*/React.createElement("span", {
      onClick: () => setWinLock(w => ({
        ...w,
        [o.id]: !w[o.id]
      })),
      className: `w-4 h-4 rounded border grid place-items-center transition
                                ${winLock[o.id] ? "border-[var(--accent)] bg-[var(--accent)]/20" : "border-white/15 bg-white/[0.02]"}`
    }, winLock[o.id] && /*#__PURE__*/React.createElement(ICheck, {
      size: 10,
      className: "text-[var(--accent)]"
    })), /*#__PURE__*/React.createElement("span", {
      className: "text-[12.5px] text-slate-300"
    }, o.label))))));
  };
  const _Old_OtherSection_remove = () => {
    const [tab, setTab] = useState("device");
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(SubTabs, {
      active: tab,
      onChange: setTab,
      tabs: [{
        id: "device",
        label: "Device",
        icon: /*#__PURE__*/React.createElement(ICpu, {
          size: 13
        })
      }, {
        id: "firmware",
        label: "Firmware",
        icon: /*#__PURE__*/React.createElement(IDownload, {
          size: 13
        })
      }, {
        id: "import",
        label: "Import / Export",
        icon: /*#__PURE__*/React.createElement(ILayers, {
          size: 13
        })
      }, {
        id: "about",
        label: "About",
        icon: /*#__PURE__*/React.createElement(ISettings, {
          size: 13
        })
      }]
    }), tab === "device" && /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 md:grid-cols-4 gap-3"
    }, [{
      label: "Model",
      value: "WIN60 HE",
      color: "accent"
    }, {
      label: "Firmware",
      value: "v2.14.0"
    }, {
      label: "USB",
      value: "0x4d9:0x0a1c"
    }, {
      label: "Switch profile",
      value: "Aether X1"
    }, {
      label: "Polling",
      value: "8 KHz",
      color: "ok"
    }, {
      label: "Latency",
      value: "0.62 ms",
      color: "ok"
    }, {
      label: "N-Key Rollover",
      value: "Full NKRO"
    }, {
      label: "Onboard memory",
      value: "128 KB"
    }].map(s => /*#__PURE__*/React.createElement("div", {
      key: s.label,
      className: "rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[9.5px] uppercase tracking-[0.22em] text-slate-500"
    }, s.label), /*#__PURE__*/React.createElement("div", {
      className: `font-mono text-[13px] mt-1 ${s.color === "accent" ? "text-[var(--accent)]" : s.color === "ok" ? "text-emerald-300" : "text-slate-100"}`
    }, s.value)))), tab === "firmware" && /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 max-w-2xl"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between mb-3"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[14px] text-slate-100 uppercase tracking-[0.16em]"
    }, "Firmware"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[11px] text-slate-500 mt-1"
    }, "Current: v2.14.0 \xB7 Stable")), /*#__PURE__*/React.createElement(Chip, {
      color: "ok"
    }, "Up to date")), /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-slate-400 leading-relaxed mb-4"
    }, "Manually flash a signed firmware blob via the WebHID interface. The keyboard will enter bootloader mode and re-enumerate."), /*#__PURE__*/React.createElement("div", {
      className: "flex gap-2"
    }, /*#__PURE__*/React.createElement("button", {
      className: "px-4 h-9 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[12px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25"
    }, /*#__PURE__*/React.createElement("span", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement(IDownload, {
      size: 12
    }), "Check for updates")), /*#__PURE__*/React.createElement("button", {
      className: "px-4 h-9 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 font-display text-[12px] uppercase tracking-[0.16em] hover:border-white/20"
    }, "Load .bin"))), tab === "import" && /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 md:grid-cols-2 gap-4 max-w-3xl"
    }, /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[13px] text-slate-100 uppercase tracking-[0.16em] mb-2"
    }, "Export profile"), /*#__PURE__*/React.createElement("p", {
      className: "text-[11.5px] text-slate-400 mb-3"
    }, "Dumps the current profile as a JSON file you can share or back up."), /*#__PURE__*/React.createElement("button", {
      className: "px-4 h-9 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[11.5px] uppercase tracking-[0.16em]"
    }, "Export JSON")), /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[13px] text-slate-100 uppercase tracking-[0.16em] mb-2"
    }, "Import profile"), /*#__PURE__*/React.createElement("p", {
      className: "text-[11.5px] text-slate-400 mb-3"
    }, "Loads a profile from disk and flashes it to the keyboard."), /*#__PURE__*/React.createElement("button", {
      className: "px-4 h-9 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 font-display text-[11.5px] uppercase tracking-[0.16em] hover:border-white/20"
    }, "Pick file"))), tab === "about" && /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 max-w-xl"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[14px] text-slate-100 uppercase tracking-[0.18em]"
    }, "Aether"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[11px] text-slate-500 mt-1 mb-4"
    }, "Web app v0.4.2 \xB7 WebHID driver"), /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-slate-400 leading-relaxed"
    }, "An open driver for magnetic Hall Effect keyboards. Talks to the WIN60 HE via raw HID byte packets, exposing per-key actuation, rapid trigger, SOCD resolution, and a full RGB lighting engine.")));
  };

  /* ===== Gamepad: virtual-pad capture + per-key control mapping ===== */
  const PAD_KEYS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "Space", "Enter", "L-Shift", "L-Ctrl", "Up", "Down", "Left", "Right"];
  const PAD_AXES = [{
    id: "LX",
    label: "Left Stick X",
    stick: true
  }, {
    id: "LY",
    label: "Left Stick Y",
    stick: true
  }, {
    id: "RX",
    label: "Right Stick X",
    stick: true
  }, {
    id: "RY",
    label: "Right Stick Y",
    stick: true
  }, {
    id: "LT",
    label: "Left Trigger",
    stick: false
  }, {
    id: "RT",
    label: "Right Trigger",
    stick: false
  }, {
    id: "BTN_A",
    label: "Button A",
    stick: false,
    btn: true
  }, {
    id: "BTN_B",
    label: "Button B",
    stick: false,
    btn: true
  }, {
    id: "BTN_X",
    label: "Button X",
    stick: false,
    btn: true
  }, {
    id: "BTN_Y",
    label: "Button Y",
    stick: false,
    btn: true
  }, {
    id: "BTN_LB",
    label: "Bumper L",
    stick: false,
    btn: true
  }, {
    id: "BTN_RB",
    label: "Bumper R",
    stick: false,
    btn: true
  }];
  const axisMeta = id => PAD_AXES.find(a => a.id === id) || PAD_AXES[0];
  const GamepadSection = ({
    connected,
    enabled,
    onToggle,
    map,
    onApplyMap,
    defaultMap,
    error,
    onInstallDriver
  }) => {
    const rows = map || [];
    const setRow = (i, patch) => onApplyMap(rows.map((r, j) => j === i ? {
      ...r,
      ...patch
    } : r));
    const addRow = () => onApplyMap([...rows, {
      key: "W",
      axis: "RT",
      direction: 1,
      threshold_mm: 1.5
    }]);
    const removeRow = i => onApplyMap(rows.filter((_, j) => j !== i));
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 mb-5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[13px] uppercase tracking-[0.18em] text-slate-100 flex items-center gap-2"
    }, /*#__PURE__*/React.createElement(IZap, {
      size: 15
    }), " Virtual Gamepad"), /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-slate-400 mt-1.5 max-w-xl"
    }, "Streams live key travel into a system gamepad \u2014 press a key deeper for more throttle / steering. Maps below drive the analog axes & buttons. ", !connected && /*#__PURE__*/React.createElement("span", {
      className: "text-amber-400/80"
    }, "Connect the board to capture."))), /*#__PURE__*/React.createElement("button", {
      onClick: () => onToggle(!enabled),
      disabled: !connected,
      className: `relative w-12 h-6 rounded-full border transition-colors shrink-0 ml-4
                        ${!connected ? "opacity-40 cursor-not-allowed" : ""}
                        ${enabled ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-white/[0.08]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `absolute top-0.5 w-4.5 h-4.5 rounded-full transition-all
                              ${enabled ? "left-[26px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`,
      style: {
        width: 18,
        height: 18
      }
    }))), /*#__PURE__*/React.createElement("div", {
      className: "mt-3 font-mono text-[11px]"
    }, enabled ? /*#__PURE__*/React.createElement("span", {
      className: "text-emerald-400"
    }, "\u25CF Capturing \u2192 \"Aula Win60 HE Virtual Gamepad\"") : /*#__PURE__*/React.createElement("span", {
      className: "text-slate-500"
    }, "\u25CB Idle")), error && /*#__PURE__*/React.createElement("div", {
      className: "mt-3 rounded-md border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11.5px] text-rose-100 flex items-center justify-between gap-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono"
    }, error.msg), error.needsDriver && /*#__PURE__*/React.createElement("button", {
      onClick: onInstallDriver,
      className: "shrink-0 px-3 h-7 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25"
    }, "Install ViGEmBus"))), /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-white/[0.06] bg-white/[0.02] p-5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between mb-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-slate-300"
    }, "Key \u2192 Control Mapping"), /*#__PURE__*/React.createElement("div", {
      className: "flex gap-2"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => onApplyMap(defaultMap.map(r => ({
        ...r
      }))),
      className: "px-3 h-8 rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-300 font-display text-[10.5px] uppercase tracking-[0.16em] hover:border-white/20 flex items-center gap-1.5"
    }, /*#__PURE__*/React.createElement(IRefresh, {
      size: 12
    }), " Driving Defaults"), /*#__PURE__*/React.createElement("button", {
      onClick: addRow,
      className: "px-3 h-8 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25 flex items-center gap-1.5"
    }, /*#__PURE__*/React.createElement(IPlus, {
      size: 12
    }), " Add"))), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-[1fr_1.4fr_1.2fr_28px] gap-2 px-1 mb-1.5 font-mono text-[9.5px] uppercase tracking-[0.18em] text-slate-500"
    }, /*#__PURE__*/React.createElement("span", null, "Key"), /*#__PURE__*/React.createElement("span", null, "Control"), /*#__PURE__*/React.createElement("span", null, "Behaviour"), /*#__PURE__*/React.createElement("span", null)), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-2"
    }, rows.map((r, i) => {
      const meta = axisMeta(r.axis);
      return /*#__PURE__*/React.createElement("div", {
        key: i,
        className: "grid grid-cols-[1fr_1.4fr_1.2fr_28px] gap-2 items-center"
      }, /*#__PURE__*/React.createElement("select", {
        value: r.key,
        onChange: e => setRow(i, {
          key: e.target.value
        }),
        className: "h-9 rounded-md bg-black/30 border border-white/[0.06] px-2 font-mono text-[12px] text-slate-100 outline-none focus:border-white/20"
      }, PAD_KEYS.map(k => /*#__PURE__*/React.createElement("option", {
        key: k,
        value: k
      }, k))), /*#__PURE__*/React.createElement("select", {
        value: r.axis,
        onChange: e => setRow(i, {
          axis: e.target.value
        }),
        className: "h-9 rounded-md bg-black/30 border border-white/[0.06] px-2 font-mono text-[12px] text-slate-100 outline-none focus:border-white/20"
      }, PAD_AXES.map(a => /*#__PURE__*/React.createElement("option", {
        key: a.id,
        value: a.id
      }, a.label))), meta.stick ? /*#__PURE__*/React.createElement("div", {
        className: "flex gap-1"
      }, [["−", -1], ["+", 1]].map(([lbl, val]) => /*#__PURE__*/React.createElement("button", {
        key: val,
        onClick: () => setRow(i, {
          direction: val
        }),
        className: `flex-1 h-9 rounded-md border font-mono text-[13px] transition-all
                                    ${(r.direction || 1) === val ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)]" : "border-white/[0.06] bg-white/[0.02] text-slate-300 hover:border-white/20"}`
      }, lbl))) : meta.btn ? /*#__PURE__*/React.createElement("div", {
        className: "flex items-center gap-2"
      }, /*#__PURE__*/React.createElement("input", {
        type: "range",
        className: "aether flex-1",
        min: 0.2,
        max: 4.0,
        step: 0.1,
        value: r.threshold_mm ?? 1.5,
        style: {
          "--pct": ((r.threshold_mm ?? 1.5) - 0.2) / 3.8 * 100 + "%"
        },
        onChange: e => setRow(i, {
          threshold_mm: parseFloat(e.target.value)
        })
      }), /*#__PURE__*/React.createElement("span", {
        className: "font-mono text-[10px] text-slate-400 w-12 text-right"
      }, (r.threshold_mm ?? 1.5).toFixed(1), "mm")) : /*#__PURE__*/React.createElement("span", {
        className: "font-mono text-[10px] text-slate-500 pl-1"
      }, "analog 0\u2192max"), /*#__PURE__*/React.createElement("button", {
        onClick: () => removeRow(i),
        className: "w-7 h-7 grid place-items-center rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-500 hover:text-rose-300 hover:border-rose-400/30"
      }, /*#__PURE__*/React.createElement(ITrash, {
        size: 12
      })));
    }), !rows.length && /*#__PURE__*/React.createElement("div", {
      className: "text-[12px] text-slate-500 py-4 text-center"
    }, "No mappings \u2014 add one or load driving defaults.")), /*#__PURE__*/React.createElement("p", {
      className: "text-[11px] text-slate-500 mt-4 leading-relaxed"
    }, "Sticks combine opposing keys (e.g. A=\u2212 and D=+ on Left Stick X). Triggers & sticks are analog \u2014 deeper press = larger value. Buttons fire past their threshold. Changes apply live while capturing.")));
  };
  window.AetherSections = {
    KeymapSection,
    ActuationSection,
    LightingSection,
    SOCDSection,
    GamepadSection,
    OtherSection,
    ActuationToolbar
  };
})();