(() => {
  /* ============================================================
     Lighting workspace — window.AetherWorkspaces.LIGHTING_WIDGETS.
     Control JSX ported verbatim from the old LightingSection (sections.jsx)
     and split across four widget bodies. Color values (hex swatches, style=
     {{background:c}}, PatternPreview) are byte-identical — these are real
     device RGB values, never re-tokenized.
     ============================================================ */
  const {
    useState,
    useEffect,
    useRef,
    useMemo
  } = React;
  const S = window.AetherSections || {};
  const Slider = S.Slider,
    Chip = S.Chip,
    SubTabs = S.SubTabs,
    ToolbarButton = S.ToolbarButton;
  const I = window.AetherIcons || {};
  const IPlus = I.IPlus;

  /* ===== shared static data (verbatim from sections.jsx) ===== */
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
  const PRESET_PALETTES = [["#9d4edd"], ["#00f5ff"], ["#ff3d6e"], ["#39ff8a"], ["#9d4edd", "#00f5ff"], ["#ff7a59", "#ffaa1f"], ["#ff3d6e", "#ffaa1f", "#39ff8a"], ["#ff3d6e", "#ffaa1f", "#39ff8a", "#3b82f6"]];
  const BG_SWATCHES = ["#000000", "#0b0f19", "#1a0833", "#001318", "#0a1f10", "#241400", "#2a0814", "#ffffff"];

  /* PatternPreview — verbatim from sections.jsx (real RGB color prop). */
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

  /* Preview "kind" for a given firmware pattern id (best-effort mapping). */
  const previewKindFor = pattern => {
    if (pattern === "static") return "static";
    if (pattern === "wave" || pattern === "aurora" || pattern === "tide" || pattern === "comet") return "wave";
    if (pattern === "reactive" || pattern === "cross" || pattern === "speedres") return "react";
    if (pattern === "ripple" || pattern === "autorip" || pattern === "radar") return "ripple";
    if (pattern === "breath" || pattern === "neon") return "breathe";
    if (pattern === "rain" || pattern === "twinkle" || pattern === "fireworks" || pattern === "frenzy" || pattern === "striation") return "rain";
    return "static";
  };

  /* ===== Effect zones panel (custom mode) — verbatim behavior from sections.jsx ===== */
  const ZonesPanel = ({
    zones,
    selectedKeys,
    onAdd,
    onUpdate,
    onRemove
  }) => /*#__PURE__*/React.createElement("div", {
    className: "glass p-4"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center justify-between mb-3"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "font-display text-[12px] uppercase tracking-[0.18em] text-[var(--text)]"
  }, "Effect Zones"), /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[10px] text-[var(--text-faint)] mt-0.5"
  }, "Select keys on the board, add a zone, give it its own effect")), /*#__PURE__*/React.createElement("button", {
    onClick: onAdd,
    disabled: !selectedKeys || selectedKeys.size === 0,
    className: "px-2.5 h-8 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] disabled:opacity-40 font-display text-[10.5px] uppercase tracking-[0.16em]"
  }, "+ Zone (", selectedKeys?.size ?? 0, ")")), (!zones || zones.length === 0) && /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[11px] text-[var(--text-faint)]"
  }, "No zones yet \u2014 select keys, then click \"+ Zone\". Keys outside every zone stay off."), /*#__PURE__*/React.createElement("div", {
    className: "flex flex-col gap-2"
  }, (zones || []).map(z => /*#__PURE__*/React.createElement("div", {
    key: z.id,
    className: "rounded-lg border border-[var(--line)] bg-[rgba(5,11,14,0.35)] p-2.5"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-2 mb-2"
  }, /*#__PURE__*/React.createElement("select", {
    value: z.mode,
    onChange: e => onUpdate(z.id, {
      mode: e.target.value
    }),
    className: "flex-1 h-8 rounded-md bg-[rgba(5,11,14,0.5)] border border-[var(--line)] text-[var(--text)] font-display text-[11px] uppercase tracking-[0.12em] px-2 outline-none"
  }, ZONE_MODES.map(m => /*#__PURE__*/React.createElement("option", {
    key: m.id,
    value: m.id
  }, m.label))), /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[10px] text-[var(--text-faint)] whitespace-nowrap"
  }, z.codes.length, " keys"), /*#__PURE__*/React.createElement("button", {
    onClick: () => onRemove(z.id),
    title: "Remove zone",
    className: "w-7 h-7 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-rose-300 hover:border-rose-400/40"
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
    className: "absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-slate-900 ring-1 ring-white/20 text-[var(--text-dim)] hover:text-rose-300 grid place-items-center text-[9px]"
  }, "\u2715"))), (z.colors || []).length < 4 && /*#__PURE__*/React.createElement("button", {
    onClick: () => onUpdate(z.id, {
      colors: [...(z.colors || []), "#ffffff"]
    }),
    className: "w-7 h-7 rounded-md border-2 border-dashed border-[var(--line)] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] grid place-items-center text-[12px]"
  }, "+")), /*#__PURE__*/React.createElement("div", {
    className: "flex-1 flex items-center gap-2"
  }, /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
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

  /* ============================================================
     Widget 1 — Mode Picker: firmware pattern grid, power/full-RGB,
     brightness/speed sliders, direction, striation orientation.
     ============================================================ */
  /* DirectionDial — an angle picker for effect flow direction. The firmware
     supports 4 cardinal directions (right0 left1 up2 down3), so the dial snaps
     to the nearest. Drag or click anywhere on the ring to set the angle. */
  const DIR_BYTE_AT = [0, 2, 1, 3]; // round(angle/90)%4 -> byte
  const DIR_ANGLE_OF = {
    0: 0,
    2: 90,
    1: 180,
    3: 270
  };
  const DIR_NAME = {
    0: "Right",
    1: "Left",
    2: "Up",
    3: "Down"
  };
  function DirectionDial({
    direction,
    setDirection
  }) {
    const ref = useRef(null);
    const angle = DIR_ANGLE_OF[direction] != null ? DIR_ANGLE_OF[direction] : 0;
    const pick = e => {
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      let a = Math.atan2(r.top + r.height / 2 - e.clientY, e.clientX - (r.left + r.width / 2)) * 180 / Math.PI;
      if (a < 0) a += 360;
      setDirection(DIR_BYTE_AT[Math.round(a / 90) % 4]);
    };
    const marks = [["→", 0, {
      right: 6,
      top: "50%",
      transform: "translateY(-50%)"
    }], ["↑", 2, {
      top: 6,
      left: "50%",
      transform: "translateX(-50%)"
    }], ["←", 1, {
      left: 6,
      top: "50%",
      transform: "translateY(-50%)"
    }], ["↓", 3, {
      bottom: 6,
      left: "50%",
      transform: "translateX(-50%)"
    }]];
    return /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-4"
    }, /*#__PURE__*/React.createElement("div", {
      ref: ref,
      onPointerDown: e => {
        e.currentTarget.setPointerCapture(e.pointerId);
        pick(e);
      },
      onPointerMove: e => e.buttons && pick(e),
      style: {
        width: 112,
        height: 112,
        cursor: "pointer",
        touchAction: "none"
      },
      className: "relative rounded-full border border-[var(--line)] bg-white/[0.02]"
    }, marks.map(([glyph, byte, css]) => /*#__PURE__*/React.createElement("span", {
      key: byte,
      style: {
        position: "absolute",
        fontSize: 11,
        ...css,
        color: direction === byte ? "var(--accent)" : "var(--text-faint)"
      }
    }, glyph)), /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        left: "50%",
        top: "50%",
        width: 44,
        height: 3,
        borderRadius: 3,
        background: "linear-gradient(90deg, transparent, var(--accent))",
        transformOrigin: "left center",
        transform: `rotate(${-angle}deg)`,
        boxShadow: "0 0 10px var(--accent-glow)",
        transition: "transform 0.2s var(--ease-out)"
      }
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        position: "absolute",
        left: "50%",
        top: "50%",
        width: 8,
        height: 8,
        marginLeft: -4,
        marginTop: -4,
        borderRadius: "50%",
        background: "var(--accent)"
      }
    })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--text-faint)]"
    }, "Angle"), /*#__PURE__*/React.createElement("div", {
      className: "font-title text-[20px] text-[var(--text)] leading-tight"
    }, DIR_NAME[direction] || "Right"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] text-[var(--text-faint)] mt-0.5"
    }, angle, "\xB0 \xB7 snaps to 4-way")));
  }
  function ModePickerWidget(ctx) {
    const {
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
      setStriOrient
    } = ctx;
    const fullColorOk = pattern !== "static" && pattern !== "custom";
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-end gap-4 mb-1"
    }, fullColorOk && /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2",
      title: "Cycle the full RGB spectrum (rainbow) instead of the chosen colors"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]"
    }, "Full RGB"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setFullColor(!fullColor),
      className: `relative w-10 h-5 rounded-full border transition-colors
                          ${fullColor ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-[var(--line)]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                                ${fullColor ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`
    }))), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]"
    }, "Power"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setPower(!power),
      className: `relative w-10 h-5 rounded-full border transition-colors
                        ${power ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-[var(--line)]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                              ${power ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`
    })))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2"
    }, "Light Mode"), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-1.5"
    }, LIGHT_MODES.map(m => {
      const active = pattern === m.id;
      return /*#__PURE__*/React.createElement("button", {
        key: m.id,
        onClick: () => setPattern(m.id),
        className: `h-9 rounded-lg border font-display text-[11px] tracking-[0.06em] flex items-center justify-center gap-1.5 transition-all
                            ${active ? "border-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]" : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`,
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
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]"
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
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]"
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
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2"
    }, "Direction"), /*#__PURE__*/React.createElement(DirectionDial, {
      direction: direction,
      setDirection: setDirection
    })), pattern === "striation" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2"
    }, "Stripe Orientation"), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-1.5 max-w-[260px]"
    }, [["Vertical", "v", "▥"], ["Horizontal", "h", "▤"], ["Both", "both", "▦"]].map(([lbl, val, ic]) => {
      const active = (striOrient || "v") === val;
      return /*#__PURE__*/React.createElement("button", {
        key: val,
        onClick: () => setStriOrient && setStriOrient(val),
        className: `h-9 rounded-lg border text-[11px] uppercase tracking-[0.12em] flex items-center justify-center gap-1.5 transition-all
                              ${active ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] shadow-[0_0_12px_var(--accent-glow)]" : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`
      }, /*#__PURE__*/React.createElement("span", {
        className: "text-[14px]"
      }, ic), lbl);
    }))));
  }

  /* ============================================================
     Widget 2 — Color Palette: effect-colors palette + presets + background color.
     ============================================================ */
  function ColorPaletteWidget(ctx) {
    const {
      colors,
      setColors,
      bgColor,
      setBgColor,
      pattern
    } = ctx;
    const palette = colors || [];
    const [activeSlot, setActiveSlot] = useState(0);
    const setSlot = (i, value) => {
      const p = [...palette];
      p[i] = value;
      setColors(p);
    };
    const addSlot = () => {
      if (palette.length >= 4) return;
      const seeds = ["#663390", "#009fa6", "#a62848", "#a66e14"];
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
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-4"
    }, pattern !== "custom" ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]"
    }, "Effect colors \xB7 ", palette.length, "/4"), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-3"
    }, palette.length > 0 && /*#__PURE__*/React.createElement("button", {
      onClick: () => setColors([]),
      className: "font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--text-dim)] hover:text-rose-300"
    }, "Clear all"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-[var(--text-faint)]"
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
      className: "flex-1 min-w-0 h-16 rounded-2xl border-2 border-dashed border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] hover:bg-white/[0.04] hover:text-white grid place-items-center transition-all"
    }, /*#__PURE__*/React.createElement("span", {
      className: "flex items-center gap-1.5 font-display text-[11px] uppercase tracking-[0.18em]"
    }, IPlus && /*#__PURE__*/React.createElement(IPlus, {
      size: 13
    }), " Add"))), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-4 gap-2"
    }, PRESET_PALETTES.map((p, i) => /*#__PURE__*/React.createElement("button", {
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
    }))))))) : /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[11px] text-[var(--text-faint)]"
    }, "Custom mode drives colors per Effect Zone (see the Effect Preview widget) \u2014 the shared palette is hidden while Custom is active."), /*#__PURE__*/React.createElement("div", {
      className: "glass p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-2.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]"
    }, "Background color"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-[var(--text-faint)]"
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
      className: "flex-1 h-10 px-3 rounded-lg bg-[rgba(5,11,14,0.5)] border border-[var(--line)] font-mono text-[12px] text-[var(--text)] outline-none focus:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"
    }), /*#__PURE__*/React.createElement("button", {
      onClick: () => setBgColor("#000000"),
      className: "px-2.5 h-10 rounded-lg border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-white hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] font-display text-[10.5px] uppercase tracking-[0.16em]"
    }, "Off")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-1.5 mt-2.5"
    }, BG_SWATCHES.map(c => /*#__PURE__*/React.createElement("button", {
      key: c,
      onClick: () => setBgColor(c),
      className: `w-6 h-6 rounded-md ring-1 ${bgColor.toLowerCase() === c.toLowerCase() ? "ring-white scale-110" : "ring-white/15 hover:scale-105"} transition-transform`,
      style: {
        background: c
      },
      title: c
    })))));
  }

  /* ============================================================
     Widget 3 — Effect Preview: live SVG pattern preview + Custom effect zones.
     ============================================================ */
  function EffectPreviewWidget(ctx) {
    const {
      pattern,
      colors,
      bgColor,
      zones,
      addZone,
      updateZone,
      removeZone,
      selectedKeys
    } = ctx;
    const palette = colors || [];
    const previewColor = palette[0] || bgColor || "#9d4edd";
    const kind = previewKindFor(pattern);
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "glass p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-1"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]"
    }, "Preview"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-[var(--text-faint)] uppercase tracking-[0.16em]"
    }, pattern)), /*#__PURE__*/React.createElement(PatternPreview, {
      kind: kind,
      color: previewColor
    })), pattern === "custom" && /*#__PURE__*/React.createElement(ZonesPanel, {
      zones: zones,
      selectedKeys: selectedKeys,
      onAdd: addZone,
      onUpdate: updateZone,
      onRemove: removeZone
    }), pattern !== "custom" && /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[11px] text-[var(--text-faint)]"
    }, "Switch Light Mode to \"Custom\" (Mode Picker widget) to build per-zone effects here."));
  }

  /* ============================================================
     Widget 4 — Per-key Paint: assign/clear the active palette color to
     the current key selection.
     ============================================================ */
  function PerKeyPaintWidget(ctx) {
    const {
      colors,
      perKeyColors,
      setPerKeyColors,
      selectedKeys,
      setSelectedKeys,
      ledMap
    } = ctx;
    const palette = colors || [];
    const [activeSlot, setActiveSlot] = useState(0);
    const selCount = selectedKeys ? selectedKeys.size : 0;
    const assignToSelection = () => {
      if (!selectedKeys || selectedKeys.size === 0) return;
      const c = palette[activeSlot] || palette[0] || "#ffffff";
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
    const selectAll = () => {
      if (!setSelectedKeys) return;
      setSelectedKeys(new Set(Object.keys(ledMap || {})));
    };
    const clearSelection = () => {
      if (!setSelectedKeys) return;
      setSelectedKeys(new Set());
    };
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-4"
    }, palette.length > 0 && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)] mb-2"
    }, "Active slot"), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, palette.map((c, i) => /*#__PURE__*/React.createElement("button", {
      key: i,
      onClick: () => setActiveSlot(i),
      className: `w-9 h-9 rounded-lg ring-1 transition-all ${activeSlot === i ? "ring-2 ring-white/80 scale-110" : "ring-white/10 hover:scale-105"}`,
      style: {
        background: c,
        boxShadow: `0 0 12px ${c}55`
      },
      title: c.toUpperCase()
    })))), /*#__PURE__*/React.createElement("div", {
      className: "glass p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between mb-3"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[12px] uppercase tracking-[0.18em] text-[var(--text)]"
    }, "Per-key colors"), /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] text-[var(--text-faint)] mt-0.5"
    }, selCount, " key", selCount === 1 ? "" : "s", " selected \xB7 Ctrl/\u2318-click to toggle")), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-1.5"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: selectAll,
      className: "px-2.5 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-white hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] font-display text-[10.5px] uppercase tracking-[0.16em]"
    }, "Select all"), /*#__PURE__*/React.createElement("button", {
      onClick: clearSelection,
      className: "px-2.5 h-8 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-white hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] font-display text-[10.5px] uppercase tracking-[0.16em]"
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
      className: "px-3 h-10 rounded-lg border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-white hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] disabled:opacity-40 font-display text-[11.5px] uppercase tracking-[0.18em]"
    }, "Reset"))));
  }

  /* ============================================================
     Widget 5 — Live Keyboard: the real board painted with the live animated
     effect frame (ctx.ledMapLive, polled from get_light_frame on the Lighting
     tab). Click keys to build a selection for Per-key Paint. This is the
     animated keyboard preview from the previous UI.
     ============================================================ */
  function LiveKeyboardWidget(ctx) {
    const KB = window.AetherKeyboard || {};
    const KeyboardPanel = KB.KeyboardPanel;
    const {
      ledMap,
      perKeyColors,
      selectedKeys,
      setSelectedKeys,
      connected,
      apiCall
    } = ctx;
    const [lightFrame, setLightFrame] = useState(null);
    useEffect(() => {
      if (!connected) {
        setLightFrame(null);
        return;
      }
      let alive = true;
      const id = setInterval(() => {
        apiCall("get_light_frame").then(f => {
          if (!alive) return;
          const valid = f && typeof f === "object" && !(f.ok === false) && Object.keys(f).length ? f : null;
          setLightFrame(prev => JSON.stringify(prev) === JSON.stringify(valid) ? prev : valid);
        });
      }, 50);
      return () => {
        alive = false;
        clearInterval(id);
      };
    }, [connected]);
    const ledMapLive = useMemo(() => {
      if (!lightFrame) return null;
      const m = {};
      const rgbToHex = rgb => {
        if (!rgb) return "";
        const r = rgb[0].toString(16).padStart(2, "0");
        const g = rgb[1].toString(16).padStart(2, "0");
        const b = rgb[2].toString(16).padStart(2, "0");
        return `#${r}${g}${b}`;
      };
      for (const code in lightFrame) m[code] = rgbToHex(lightFrame[code]);
      return m;
    }, [lightFrame]);
    if (typeof KeyboardPanel !== "function") {
      return /*#__PURE__*/React.createElement("div", {
        className: "font-mono text-[11px] text-[var(--text-faint)] p-2"
      }, "keyboard layout unavailable");
    }
    return /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-2"
    }, !connected && /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
    }, "connect the board to see the live effect"), /*#__PURE__*/React.createElement("div", {
      className: "flex justify-center"
    }, React.createElement(KeyboardPanel, {
      mode: "lighting",
      layer: "default",
      ledMap: ledMapLive || ledMap,
      perKeyOverride: perKeyColors,
      selectedKeys: selectedKeys || new Set(),
      setSelectedKeys: setSelectedKeys || (() => {}),
      showPill: false
    })));
  }

  /* ============================================================
     Layout — Live Keyboard is the hero (wide, top); controls below/around.
     ============================================================ */
  const LIGHTING_WIDGETS = [{
    id: "live",
    title: "Live Keyboard",
    default: {
      x: 40,
      y: 32,
      w: 1000,
      h: 330
    },
    min: {
      w: 560,
      h: 240
    },
    render: LiveKeyboardWidget
  }, {
    id: "mode",
    title: "Mode Picker",
    default: {
      x: 40,
      y: 382,
      w: 460,
      h: 520
    },
    min: {
      w: 340,
      h: 420
    },
    render: ModePickerWidget
  }, {
    id: "palette",
    title: "Color Palette",
    default: {
      x: 520,
      y: 382,
      w: 460,
      h: 460
    },
    min: {
      w: 340,
      h: 340
    },
    render: ColorPaletteWidget
  }, {
    id: "preview",
    title: "Effect Preview",
    default: {
      x: 1000,
      y: 382,
      w: 380,
      h: 460
    },
    min: {
      w: 300,
      h: 300
    },
    render: EffectPreviewWidget
  }, {
    id: "perkey",
    title: "Per-key Paint",
    default: {
      x: 1060,
      y: 32,
      w: 380,
      h: 330
    },
    min: {
      w: 340,
      h: 260
    },
    render: PerKeyPaintWidget
  }];
  window.AetherWorkspaces = window.AetherWorkspaces || {};
  window.AetherWorkspaces.LIGHTING_WIDGETS = LIGHTING_WIDGETS;
})();