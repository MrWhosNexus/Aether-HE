/* Theme customizer popup — palette (1-4 colors) + image backdrop */
(() => {
  const {
    useState,
    useEffect,
    useRef
  } = React;
  const {
    IPalette,
    IWaves,
    IDownload,
    ICheck,
    ITrash,
    IPlus,
    IRefresh
  } = window.AetherIcons;

  /* ===== Curated palettes (each up to 4 colors) ===== */
  const PALETTE_PRESETS = [{
    name: "Violet",
    colors: ["#9d4edd"]
  }, {
    name: "Azure",
    colors: ["#3b82f6"]
  }, {
    name: "Cyan",
    colors: ["#00f5ff"]
  }, {
    name: "Aurora",
    colors: ["#00f5ff", "#66ff8a"]
  }, {
    name: "Aether",
    colors: ["#9d4edd", "#00f5ff"]
  }, {
    name: "Nebula",
    colors: ["#9d4edd", "#ff3d6e"]
  }, {
    name: "Sunset",
    colors: ["#ff7a59", "#ffaa1f"]
  }, {
    name: "Vapor",
    colors: ["#5b8cff", "#ff35d1"]
  }, {
    name: "Pulse",
    colors: ["#ff3d6e", "#ffaa1f", "#39ff8a"]
  }, {
    name: "Rainbow",
    colors: ["#ff3d6e", "#ffaa1f", "#39ff8a", "#3b82f6"]
  }, {
    name: "Cosmic",
    colors: ["#9d4edd", "#00f5ff", "#66ff8a", "#ffaa1f"]
  }, {
    name: "Mono Slate",
    colors: ["#94a3b8"]
  }];
  const IMAGE_PRESETS = [{
    name: "Obsidian",
    url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><defs><radialGradient id='g' cx='30%' cy='20%' r='80%'><stop offset='0' stop-color='%239d4edd' stop-opacity='0.55'/><stop offset='0.55' stop-color='%23020308' stop-opacity='0.95'/><stop offset='1' stop-color='%23000000'/></radialGradient></defs><rect width='800' height='500' fill='url(%23g)'/></svg>`)
  }, {
    name: "Aurora",
    url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><defs><linearGradient id='g' x1='0' x2='1' y1='0' y2='1'><stop offset='0' stop-color='%2300f5ff' stop-opacity='0.45'/><stop offset='0.5' stop-color='%23030712' stop-opacity='0.9'/><stop offset='1' stop-color='%239d4edd' stop-opacity='0.45'/></linearGradient></defs><rect width='800' height='500' fill='url(%23g)'/></svg>`)
  }, {
    name: "Crimson",
    url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><defs><radialGradient id='g' cx='70%' cy='80%' r='90%'><stop offset='0' stop-color='%23ff3d6e' stop-opacity='0.55'/><stop offset='0.6' stop-color='%23090106' stop-opacity='0.95'/><stop offset='1' stop-color='%23000000'/></radialGradient></defs><rect width='800' height='500' fill='url(%23g)'/></svg>`)
  }, {
    name: "Mint",
    url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><defs><linearGradient id='g' x1='0' x2='1' y1='1' y2='0'><stop offset='0' stop-color='%2366ff8a' stop-opacity='0.35'/><stop offset='0.5' stop-color='%23040b09' stop-opacity='0.95'/><stop offset='1' stop-color='%2322d3ee' stop-opacity='0.45'/></linearGradient></defs><rect width='800' height='500' fill='url(%23g)'/></svg>`)
  }, {
    name: "Solar",
    url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><defs><radialGradient id='g' cx='50%' cy='50%' r='70%'><stop offset='0' stop-color='%23ffaa1f' stop-opacity='0.55'/><stop offset='0.4' stop-color='%23200a02' stop-opacity='0.95'/><stop offset='1' stop-color='%23000000'/></radialGradient></defs><rect width='800' height='500' fill='url(%23g)'/></svg>`)
  }, {
    name: "Carbon",
    url: "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 500'><rect width='800' height='500' fill='%23070a14'/><g stroke='%231a2235' stroke-width='1'>${Array.from({
      length: 40
    }).map((_, i) => `<line x1='${i * 20}' y1='0' x2='${i * 20}' y2='500'/>`).join('')}${Array.from({
      length: 25
    }).map((_, i) => `<line x1='0' y1='${i * 20}' x2='800' y2='${i * 20}'/>`).join('')}</g></svg>`)
  }];

  /* ===== Helpers ===== */
  function hexToRgb(hex) {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return m ? {
      r: parseInt(m[1], 16),
      g: parseInt(m[2], 16),
      b: parseInt(m[3], 16)
    } : null;
  }
  function isLight(hex) {
    const r = hexToRgb(hex);
    if (!r) return false;
    const L = 0.299 * r.r + 0.587 * r.g + 0.114 * r.b;
    return L > 160;
  }
  function glowFor(hex, alpha = 0.45) {
    const r = hexToRgb(hex);
    if (!r) return "rgba(255,255,255,0.3)";
    return `rgba(${r.r},${r.g},${r.b},${alpha})`;
  }
  const DEFAULT_THEME = {
    palette: ["#9d4edd"],
    // 1-4 colors
    gradientAngle: 135,
    useImage: false,
    image: null,
    imageOpacity: 0.6
  };
  function applyTheme(theme) {
    const root = document.documentElement;
    const colors = theme.palette && theme.palette.length ? theme.palette : ["#9d4edd"];
    const c1 = colors[0];
    root.style.setProperty("--accent", c1);
    root.style.setProperty("--accent-2", colors[1] || c1);
    root.style.setProperty("--accent-3", colors[2] || c1);
    root.style.setProperty("--accent-4", colors[3] || c1);
    root.style.setProperty("--accent-glow", glowFor(c1, 0.45));
    root.style.setProperty("--accent-fg", isLight(c1) ? "#0b0f19" : "#ffffff");
    const gradient = colors.length > 1 ? `linear-gradient(${theme.gradientAngle ?? 135}deg, ${colors.join(", ")})` : c1;
    root.style.setProperty("--accent-gradient", gradient);
    if (colors.length > 1) document.body.classList.add("accent-is-gradient");else document.body.classList.remove("accent-is-gradient");
    const bg = document.getElementById("__bg-image-layer");
    if (theme.useImage && theme.image && bg) {
      bg.style.backgroundImage = `url("${theme.image}")`;
      bg.style.opacity = theme.imageOpacity ?? 0.6;
      bg.style.display = "block";
    } else if (bg) {
      bg.style.display = "none";
    }
  }

  /* Migrate older themes (single accent / gradient mode) to palette */
  function migrate(t) {
    if (Array.isArray(t.palette)) return t;
    // Legacy structure
    const palette = [];
    if (t.mode === "gradient" && t.gradient) {
      palette.push(t.gradient.from, t.gradient.to);
    } else if (t.accent) {
      palette.push(t.accent);
    } else {
      palette.push("#9d4edd");
    }
    return {
      palette,
      gradientAngle: t.gradient?.angle ?? 135,
      useImage: t.mode === "image",
      image: t.image || null,
      imageOpacity: t.imageOpacity ?? 0.35
    };
  }

  /* ===== Public hook ===== */
  function useTheme() {
    const [theme, setThemeState] = useState(() => {
      try {
        const raw = JSON.parse(localStorage.getItem("aether-theme"));
        if (!raw) return DEFAULT_THEME;
        return {
          ...DEFAULT_THEME,
          ...migrate(raw)
        };
      } catch {
        return DEFAULT_THEME;
      }
    });
    useEffect(() => {
      applyTheme(theme);
      try {
        localStorage.setItem("aether-theme", JSON.stringify(theme));
      } catch {}
    }, [theme]);
    return [theme, setThemeState];
  }

  /* ===== Multi-color slot ===== */
  const ColorSlot = ({
    color,
    onChange,
    onRemove,
    removable
  }) => /*#__PURE__*/React.createElement("div", {
    className: "relative flex-1 min-w-0"
  }, /*#__PURE__*/React.createElement("div", {
    className: "relative h-16 rounded-2xl overflow-hidden ring-1 ring-white/10",
    style: {
      background: color,
      boxShadow: `0 0 24px ${color}55, inset 0 0 0 1px rgba(255,255,255,0.06)`
    }
  }, /*#__PURE__*/React.createElement("input", {
    type: "color",
    value: color,
    onChange: e => onChange(e.target.value),
    className: "absolute inset-0 opacity-0 cursor-pointer w-full h-full"
  }), /*#__PURE__*/React.createElement("span", {
    className: `absolute bottom-1.5 left-2 text-[10px] font-mono ${isLight(color) ? "text-black/70" : "text-white/80"} drop-shadow`,
    style: {
      textShadow: isLight(color) ? "none" : "0 1px 4px rgba(0,0,0,0.6)"
    }
  }, color.toUpperCase()), removable && /*#__PURE__*/React.createElement("button", {
    onClick: onRemove,
    title: "Remove",
    className: `absolute top-1.5 right-1.5 w-5 h-5 rounded-full grid place-items-center ${isLight(color) ? "bg-black/30 text-white" : "bg-white/80 text-black"} hover:scale-110 transition-transform`
  }, "\u2715")));
  const AddSlot = ({
    onAdd
  }) => /*#__PURE__*/React.createElement("button", {
    onClick: onAdd,
    className: "flex-1 min-w-0 h-16 rounded-2xl border-2 border-dashed border-white/15 bg-white/[0.02] text-slate-400 hover:border-white/30 hover:bg-white/[0.04] hover:text-white grid place-items-center transition-all"
  }, /*#__PURE__*/React.createElement("span", {
    className: "flex items-center gap-1.5 font-display text-[11px] uppercase tracking-[0.18em]"
  }, /*#__PURE__*/React.createElement(IPlus, {
    size: 13
  }), " Add"));

  /* ===== Popup ===== */
  const ThemePopup = ({
    open,
    onClose,
    theme,
    setTheme
  }) => {
    const [tab, setTab] = useState("palette");
    const [draft, setDraft] = useState(theme);
    const fileRef = useRef(null);
    useEffect(() => {
      if (open) {
        setDraft(theme);
        setTab("palette");
      }
    }, [open]);
    useEffect(() => {
      if (open) applyTheme(draft);
    }, [draft, open]);
    useEffect(() => {
      const onKey = e => {
        if (e.key === "Escape" && open) handleClose();
      };
      window.addEventListener("keydown", onKey);
      return () => window.removeEventListener("keydown", onKey);
    }, [open]);
    const handleClose = () => {
      applyTheme(theme);
      onClose();
    };
    const handleApply = () => {
      setTheme(draft);
      onClose();
    };
    const handleReset = () => {
      setDraft(DEFAULT_THEME);
    };
    const palette = draft.palette || ["#9d4edd"];
    const setSlot = (i, value) => {
      const p = [...palette];
      p[i] = value;
      setDraft(d => ({
        ...d,
        palette: p
      }));
    };
    const addSlot = () => {
      if (palette.length >= 4) return;
      const next = ["#00f5ff", "#ff3d6e", "#39ff8a"][palette.length - 1] || "#ffffff";
      setDraft(d => ({
        ...d,
        palette: [...palette, next]
      }));
    };
    const removeSlot = i => {
      if (palette.length <= 1) return;
      setDraft(d => ({
        ...d,
        palette: palette.filter((_, idx) => idx !== i)
      }));
    };
    const usePreset = colors => setDraft(d => ({
      ...d,
      palette: [...colors]
    }));
    const onImageFile = file => {
      if (!file) return;
      const reader = new FileReader();
      reader.onload = e => {
        setDraft(d => ({
          ...d,
          image: e.target.result,
          useImage: true
        }));
      };
      reader.readAsDataURL(file);
    };
    if (!open) return null;
    return /*#__PURE__*/React.createElement("div", {
      className: "fixed inset-0 z-[120] flex items-center justify-center",
      onMouseDown: e => {
        if (e.target === e.currentTarget) handleClose();
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "absolute inset-0 bg-black/65 backdrop-blur-md animate-[fadeIn_180ms_ease-out]"
    }), /*#__PURE__*/React.createElement("div", {
      className: "relative w-[680px] max-w-[92vw] max-h-[90vh] overflow-hidden rounded-3xl bg-[#0e1220]/95 border border-white/[0.06] shadow-[0_40px_120px_-20px_rgba(0,0,0,0.85),0_0_0_1px_rgba(255,255,255,0.04)_inset] animate-[popIn_220ms_cubic-bezier(.2,.9,.3,1.1)]"
    }, /*#__PURE__*/React.createElement("div", {
      className: "px-7 pt-6 pb-3 flex items-start justify-between"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "text-[11px] font-mono uppercase tracking-[0.28em] text-slate-500"
    }, "Appearance"), /*#__PURE__*/React.createElement("div", {
      className: "text-[22px] font-display font-semibold tracking-[0.02em] text-slate-50 mt-1"
    }, "Customize Theme"), /*#__PURE__*/React.createElement("div", {
      className: "text-[12px] text-slate-500 mt-1"
    }, "Pick up to 4 colors \u2014 they'll cascade through the app, accents and lighting.")), /*#__PURE__*/React.createElement("button", {
      onClick: handleClose,
      className: "w-9 h-9 rounded-full grid place-items-center text-slate-500 hover:text-slate-100 hover:bg-white/[0.06] transition-colors"
    }, "\u2715")), /*#__PURE__*/React.createElement("div", {
      className: "px-7 pb-1"
    }, /*#__PURE__*/React.createElement("div", {
      className: "inline-flex p-1 rounded-xl bg-white/[0.04] border border-white/[0.04]"
    }, [{
      id: "palette",
      label: "Palette",
      icon: /*#__PURE__*/React.createElement(IPalette, {
        size: 13
      })
    }, {
      id: "image",
      label: "Background",
      icon: /*#__PURE__*/React.createElement(IDownload, {
        size: 13
      })
    }].map(t => {
      const isActive = tab === t.id;
      return /*#__PURE__*/React.createElement("button", {
        key: t.id,
        onClick: () => setTab(t.id),
        className: `relative flex items-center gap-2 px-4 h-8 rounded-lg text-[12px] font-display uppercase tracking-[0.18em] transition-all
                              ${isActive ? "text-slate-50 bg-white/[0.08] shadow-[0_2px_10px_rgba(0,0,0,0.3)]" : "text-slate-400 hover:text-slate-200"}`
      }, t.icon, t.label);
    }))), /*#__PURE__*/React.createElement("div", {
      className: "px-7 py-5 overflow-y-auto max-h-[60vh]"
    }, tab === "palette" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "flex items-stretch gap-2.5 mb-4"
    }, palette.map((c, i) => /*#__PURE__*/React.createElement(ColorSlot, {
      key: i,
      color: c,
      onChange: v => setSlot(i, v),
      onRemove: () => removeSlot(i),
      removable: palette.length > 1
    })), palette.length < 4 && /*#__PURE__*/React.createElement(AddSlot, {
      onAdd: addSlot
    })), /*#__PURE__*/React.createElement("div", {
      className: "relative h-10 rounded-xl overflow-hidden ring-1 ring-white/10 mb-5",
      style: {
        background: palette.length > 1 ? `linear-gradient(${draft.gradientAngle ?? 135}deg, ${palette.join(", ")})` : palette[0]
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.25),transparent_55%)]"
    }), /*#__PURE__*/React.createElement("span", {
      className: "absolute bottom-1.5 right-3 font-mono text-[9.5px] uppercase tracking-[0.22em] text-white/80",
      style: {
        textShadow: "0 1px 4px rgba(0,0,0,0.5)"
      }
    }, palette.length === 1 ? "Solid" : `Gradient · ${palette.length} stops`)), palette.length > 1 && /*#__PURE__*/React.createElement("div", {
      className: "rounded-2xl bg-white/[0.025] border border-white/[0.05] p-4 mb-5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-1.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11.5px] uppercase tracking-[0.22em] text-slate-300"
    }, "Gradient angle"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[12px] text-slate-100"
    }, draft.gradientAngle ?? 135, "\xB0")), /*#__PURE__*/React.createElement("input", {
      type: "range",
      min: 0,
      max: 360,
      step: 1,
      value: draft.gradientAngle ?? 135,
      onChange: e => setDraft(d => ({
        ...d,
        gradientAngle: parseInt(e.target.value)
      })),
      className: "aether w-full",
      style: {
        "--pct": (draft.gradientAngle ?? 135) / 360 * 100 + "%"
      }
    })), /*#__PURE__*/React.createElement("div", {
      className: "text-[11px] font-mono uppercase tracking-[0.22em] text-slate-500 mb-2"
    }, "Presets"), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-2.5"
    }, PALETTE_PRESETS.map((p, i) => {
      const isSel = JSON.stringify(palette) === JSON.stringify(p.colors);
      return /*#__PURE__*/React.createElement("button", {
        key: i,
        onClick: () => usePreset(p.colors),
        className: `relative text-left p-2.5 rounded-xl border transition-all
                                  ${isSel ? "border-white/30 bg-white/[0.06]" : "border-white/[0.06] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]"}`
      }, /*#__PURE__*/React.createElement("div", {
        className: "flex gap-1 mb-1.5"
      }, p.colors.map((c, j) => /*#__PURE__*/React.createElement("span", {
        key: j,
        className: "flex-1 h-4 rounded-md ring-1 ring-white/10",
        style: {
          background: c,
          boxShadow: `0 0 8px ${c}55`
        }
      })), Array.from({
        length: 4 - p.colors.length
      }).map((_, j) => /*#__PURE__*/React.createElement("span", {
        key: `e${j}`,
        className: "flex-1 h-4 rounded-md bg-white/[0.04]"
      }))), /*#__PURE__*/React.createElement("div", {
        className: "flex items-center justify-between"
      }, /*#__PURE__*/React.createElement("span", {
        className: "font-display text-[11px] uppercase tracking-[0.14em] text-slate-200"
      }, p.name), isSel && /*#__PURE__*/React.createElement(ICheck, {
        size: 11,
        className: "text-[var(--accent)]"
      })));
    }))), tab === "image" && /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
      className: "flex items-center gap-2.5 mb-4 cursor-pointer"
    }, /*#__PURE__*/React.createElement("span", {
      onClick: () => setDraft(d => ({
        ...d,
        useImage: !d.useImage
      })),
      className: `w-5 h-5 rounded-md border grid place-items-center transition
                                  ${draft.useImage ? "border-[var(--accent)] bg-[var(--accent)]/20" : "border-white/15 bg-white/[0.02]"}`
    }, draft.useImage && /*#__PURE__*/React.createElement(ICheck, {
      size: 12,
      className: "text-[var(--accent)]"
    })), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[13px] uppercase tracking-[0.16em] text-slate-200"
    }, "Use background image")), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-3 gap-3 mb-5"
    }, IMAGE_PRESETS.map(p => {
      const active = draft.image === p.url;
      return /*#__PURE__*/React.createElement("button", {
        key: p.name,
        onClick: () => setDraft(d => ({
          ...d,
          image: p.url,
          useImage: true
        })),
        className: `relative aspect-[4/3] rounded-2xl overflow-hidden transition-all
                                  ${active ? "ring-2 ring-white/80 scale-[1.02]" : "ring-1 ring-white/10 hover:scale-[1.02]"}`,
        style: {
          background: `url("${p.url}") center/cover`
        }
      }, /*#__PURE__*/React.createElement("span", {
        className: "absolute bottom-2 left-2.5 text-[10.5px] font-display uppercase tracking-[0.18em] text-white/90",
        style: {
          textShadow: "0 1px 4px rgba(0,0,0,0.7)"
        }
      }, p.name), active && /*#__PURE__*/React.createElement("span", {
        className: "absolute top-2 right-2 w-5 h-5 rounded-full bg-white/85 grid place-items-center"
      }, /*#__PURE__*/React.createElement(ICheck, {
        size: 11,
        className: "text-black",
        strokeWidth: 3
      })));
    })), /*#__PURE__*/React.createElement("div", {
      className: "rounded-2xl bg-white/[0.025] border border-white/[0.05] p-4 mb-3"
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-[11px] font-mono uppercase tracking-[0.22em] text-slate-500 mb-2"
    }, "Upload custom image"), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-3"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => fileRef.current?.click(),
      className: "flex-1 h-11 rounded-lg border border-dashed border-white/15 bg-white/[0.025] hover:border-white/30 hover:bg-white/[0.05] text-slate-300 hover:text-white text-[12px] font-display uppercase tracking-[0.18em] transition-all"
    }, /*#__PURE__*/React.createElement("span", {
      className: "flex items-center justify-center gap-2"
    }, /*#__PURE__*/React.createElement(IDownload, {
      size: 13
    }), " Choose image")), draft.image && /*#__PURE__*/React.createElement("button", {
      onClick: () => setDraft(d => ({
        ...d,
        image: null
      })),
      className: "w-11 h-11 rounded-lg border border-white/[0.08] bg-white/[0.025] hover:bg-rose-500/15 hover:border-rose-400/40 text-slate-400 hover:text-rose-300 transition-colors grid place-items-center",
      title: "Remove"
    }, /*#__PURE__*/React.createElement(ITrash, {
      size: 14
    })), /*#__PURE__*/React.createElement("input", {
      ref: fileRef,
      type: "file",
      accept: "image/*",
      className: "hidden",
      onChange: e => onImageFile(e.target.files?.[0])
    }))), draft.image && draft.useImage && /*#__PURE__*/React.createElement("div", {
      className: "rounded-2xl bg-white/[0.025] border border-white/[0.05] p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-baseline justify-between mb-2"
    }, /*#__PURE__*/React.createElement("span", {
      className: "text-[11px] font-mono uppercase tracking-[0.22em] text-slate-500"
    }, "Opacity"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[12px] text-slate-200"
    }, Math.round((draft.imageOpacity ?? 0.35) * 100), "%")), /*#__PURE__*/React.createElement("input", {
      type: "range",
      min: 5,
      max: 100,
      step: 1,
      value: Math.round((draft.imageOpacity ?? 0.35) * 100),
      onChange: e => setDraft(d => ({
        ...d,
        imageOpacity: parseInt(e.target.value) / 100
      })),
      className: "aether w-full",
      style: {
        "--pct": (draft.imageOpacity ?? 0.35) * 100 + "%"
      }
    })))), /*#__PURE__*/React.createElement("div", {
      className: "px-7 py-4 border-t border-white/[0.05] bg-black/20 flex items-center justify-between"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: handleReset,
      className: "flex items-center gap-1.5 px-3 h-9 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-white/[0.04] text-[12px] font-display uppercase tracking-[0.18em] transition-colors"
    }, /*#__PURE__*/React.createElement(IRefresh, {
      size: 13
    }), " Reset"), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: handleClose,
      className: "px-5 h-10 rounded-lg border border-white/[0.08] bg-white/[0.025] text-slate-300 hover:text-white hover:border-white/20 text-[12px] font-display uppercase tracking-[0.18em] transition-all"
    }, "Cancel"), /*#__PURE__*/React.createElement("button", {
      onClick: handleApply,
      className: "px-6 h-10 rounded-lg font-display text-[12px] uppercase tracking-[0.18em] text-[var(--accent-fg)] transition-all hover:brightness-110",
      style: {
        background: `var(--accent-gradient, var(--accent))`,
        boxShadow: "0 10px 30px -8px var(--accent-glow)"
      }
    }, "Apply")))));
  };

  /* ===== Reusable multi-color picker (1-4 colors) for other settings ===== */
  const ColorPalettePicker = ({
    colors,
    onChange,
    max = 4,
    label
  }) => {
    const setSlot = (i, value) => {
      const p = [...colors];
      p[i] = value;
      onChange(p);
    };
    const add = () => {
      if (colors.length >= max) return;
      const seeds = ["#9d4edd", "#00f5ff", "#ff3d6e", "#ffaa1f"];
      onChange([...colors, seeds[colors.length] || "#ffffff"]);
    };
    const remove = i => {
      if (colors.length <= 1) return;
      onChange(colors.filter((_, idx) => idx !== i));
    };
    return /*#__PURE__*/React.createElement("div", null, label && /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[11px] uppercase tracking-[0.22em] text-slate-400 mb-2"
    }, label), /*#__PURE__*/React.createElement("div", {
      className: "flex items-stretch gap-2"
    }, colors.map((c, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "relative w-12 h-12"
    }, /*#__PURE__*/React.createElement("div", {
      className: "relative w-full h-full rounded-xl overflow-hidden ring-1 ring-white/10",
      style: {
        background: c,
        boxShadow: `0 0 12px ${c}55`
      }
    }, /*#__PURE__*/React.createElement("input", {
      type: "color",
      value: c,
      onChange: e => setSlot(i, e.target.value),
      className: "absolute inset-0 opacity-0 cursor-pointer w-full h-full"
    })), colors.length > 1 && /*#__PURE__*/React.createElement("button", {
      onClick: () => remove(i),
      title: "Remove",
      className: "absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-slate-900 ring-1 ring-white/20 text-slate-300 hover:text-rose-300 grid place-items-center text-[9px]"
    }, "\u2715"))), colors.length < max && /*#__PURE__*/React.createElement("button", {
      onClick: add,
      className: "w-12 h-12 rounded-xl border-2 border-dashed border-white/15 bg-white/[0.02] text-slate-400 hover:border-white/30 hover:bg-white/[0.04] hover:text-white grid place-items-center transition-all"
    }, /*#__PURE__*/React.createElement(IPlus, {
      size: 14
    }))));
  };
  window.AetherTheme = {
    ThemePopup,
    useTheme,
    applyTheme,
    DEFAULT_THEME,
    ColorPalettePicker
  };
})();