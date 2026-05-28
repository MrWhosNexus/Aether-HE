(() => {
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
  const {
    KeyboardPanel
  } = window.AetherKeyboard;
  const {
    KeymapSection,
    ActuationSection,
    LightingSection,
    SOCDSection,
    GamepadSection,
    OtherSection,
    ActuationToolbar
  } = window.AetherSections;
  const {
    ThemePopup,
    useTheme
  } = window.AetherTheme;

  /* ============================================================
     HID bridge — talks to the native Python Api (window.pywebview.api).
     Every control calls these with real, structured values; there is NO
     DOM/CSS scraping. Safely no-ops when run outside the webview.
     ============================================================ */
  const getApi = () => window.pywebview && window.pywebview.api || null;
  const apiCall = (name, ...args) => {
    const api = getApi();
    if (!api || typeof api[name] !== "function") return Promise.resolve({
      ok: false,
      error: "no bridge"
    });
    try {
      return Promise.resolve(api[name](...args));
    } catch (e) {
      return Promise.resolve({
        ok: false,
        error: String(e)
      });
    }
  };
  const hexToRgbArr = hex => {
    const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
    return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 0, 0];
  };
  const rgbToHex = rgb => "#" + (rgb || [0, 0, 0]).map(c => Math.max(0, Math.min(255, c | 0)).toString(16).padStart(2, "0")).join("");
  // Lighting %→firmware steps (AULA brightness 1..4, speed 1..4; 0% = off).
  const briByte = pct => pct <= 0 ? 0 : Math.max(1, Math.min(4, Math.ceil(pct / 100 * 4)));
  const spdByte = pct => Math.max(1, Math.min(4, Math.round(pct / 100 * 3) + 1));
  // Firmware light modes (decoded from the official driver: cmd 7, byte5=mode,
  // refreshColorView() defines each mode's controls). Each entry: the firmware
  // mode byte, whether it uses a background color (2-color), a speed control, what
  // kind of direction control it exposes, and whether Full-RGB applies.
  // dir: "none" | "lr" (left/right) | "ud" (up/down) | "all" (4-way+gather/spread)
  //      | "rotate" (CW/CCW) | "gather" (gather/spread).  custom (10) = per-key.
  const FW_MODES = {
    static: {
      byte: 0,
      bg: false,
      speed: false,
      dir: "none",
      full: false
    },
    breath: {
      byte: 1,
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    wave: {
      byte: 2,
      bg: true,
      speed: true,
      dir: "all",
      full: true
    },
    neon: {
      byte: 3,
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    radar: {
      byte: 4,
      bg: true,
      speed: true,
      dir: "rotate",
      full: true
    },
    reactive: {
      byte: 6,
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    cross: {
      byte: 7,
      bg: true,
      speed: true,
      dir: "gather",
      full: true
    },
    ripple: {
      byte: 8,
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    twinkle: {
      byte: 9,
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    custom: {
      byte: 10,
      bg: false,
      speed: false,
      dir: "none",
      full: false
    },
    fireworks: {
      byte: 11,
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    frenzy: {
      byte: 11,
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    speedres: {
      byte: 12,
      bg: true,
      speed: false,
      dir: "ud",
      full: true
    },
    autorip: {
      byte: 14,
      bg: true,
      speed: true,
      dir: "none",
      full: true
    },
    striation: {
      byte: 15,
      bg: true,
      speed: true,
      dir: "lr",
      full: true
    },
    aurora: {
      byte: 16,
      bg: true,
      speed: true,
      dir: "none",
      full: true
    }
  };
  const MODE_BYTE = Object.fromEntries(Object.entries(FW_MODES).map(([k, v]) => [k, v.byte]));
  // SOCD key labels (BASIC/EXTENDED) → design data-code, from the keyboard layout.
  const LABEL_TO_CODE = (() => {
    const map = {};
    (window.AetherKeyboard && window.AetherKeyboard.KB_ROWS || []).flat().forEach(([label, _u, code]) => {
      if (label && code) map[label] = code;
    });
    return map;
  })();

  // Keymap target label → USB HID usage code (page 0x07). Used by Remap Key.
  const HID_BY_LABEL = (() => {
    const m = {};
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").forEach((c, i) => {
      m[c] = 0x04 + i;
    });
    // number row (label forms used by BASIC_KEYS): 1..9 then 0
    [["1!", 0x1e], ["2@", 0x1f], ["3#", 0x20], ["$4", 0x21], ["5%", 0x22], ["6^", 0x23], ["7&", 0x24], ["8*", 0x25], ["9(", 0x26], ["0)", 0x27]].forEach(([k, v]) => {
      m[k] = v;
    });
    Object.assign(m, {
      "Enter": 0x28,
      "Esc": 0x29,
      "Back": 0x2a,
      "Tab": 0x2b,
      "Space": 0x2c,
      "-_": 0x2d,
      "=+": 0x2e,
      "{[": 0x2f,
      "}]": 0x30,
      "\\|": 0x31,
      ";:": 0x33,
      "'\"": 0x34,
      "`~": 0x35,
      ",<": 0x36,
      ".>": 0x37,
      "/?": 0x38,
      "Caps": 0x39,
      "F1": 0x3a,
      "F2": 0x3b,
      "F3": 0x3c,
      "F4": 0x3d,
      "F5": 0x3e,
      "F6": 0x3f,
      "F7": 0x40,
      "F8": 0x41,
      "F9": 0x42,
      "F10": 0x43,
      "F11": 0x44,
      "F12": 0x45,
      "PrtSc": 0x46,
      "ScrLk": 0x47,
      "Pause": 0x48,
      "Ins": 0x49,
      "Home": 0x4a,
      "PgUp": 0x4b,
      "Del": 0x4c,
      "End": 0x4d,
      "PgDn": 0x4e,
      "Right": 0x4f,
      "Left": 0x50,
      "Down": 0x51,
      "Up": 0x52,
      "Menu": 0x65,
      "<>": 0x64,
      "L-Ctrl": 0xe0,
      "L-Shift": 0xe1,
      "L-Alt": 0xe2,
      "L-Win": 0xe3,
      "R-Ctrl": 0xe4,
      "R-Shift": 0xe5,
      "R-Alt": 0xe6,
      "R-Win": 0xe7
    });
    return m;
  })();

  // Profiles are dynamic (add/rename/duplicate/delete) and live in settings.json.
  // SEED_PROFILE is the very first profile created on a fresh install; everything
  // else is created at runtime by the user.
  const SEED_PROFILE = {
    id: "p1",
    name: "Default",
    state: {}
  };

  // Migrate the old per-key blob shape ({"profile-p1": {...}, "profile-p2": {...}})
  // to the new {profiles:[...], activeProfile, globals} shape so nobody loses
  // their existing settings file.
  const migrateSettings = raw => {
    if (!raw || typeof raw !== "object") return null;
    if (Array.isArray(raw.profiles)) return raw; // already new shape
    const profs = [];
    for (const k of Object.keys(raw)) {
      if (!k.startsWith("profile-")) continue;
      const id = k.slice("profile-".length);
      const nm = id === "default" ? "Default" : id.toUpperCase();
      profs.push({
        id,
        name: nm,
        state: raw[k] || {}
      });
    }
    if (!profs.length) return null;
    return {
      profiles: profs,
      activeProfile: profs[0].id,
      globals: {}
    };
  };
  const NAV = [{
    id: "keymap",
    label: "Keymap",
    icon: /*#__PURE__*/React.createElement(IKeyboard, {
      size: 14
    })
  }, {
    id: "lighting",
    label: "Lighting",
    icon: /*#__PURE__*/React.createElement(IBulb, {
      size: 14
    })
  }, {
    id: "actuation",
    label: "Actuation",
    icon: /*#__PURE__*/React.createElement(IGauge, {
      size: 14
    })
  }, {
    id: "socd",
    label: "SOCD",
    icon: /*#__PURE__*/React.createElement(ICrosshair, {
      size: 14
    })
  }, {
    id: "gamepad",
    label: "Gamepad",
    icon: /*#__PURE__*/React.createElement(IZap, {
      size: 14
    })
  }, {
    id: "other",
    label: "Settings",
    icon: /*#__PURE__*/React.createElement(ISettings, {
      size: 14
    })
  }];

  /* ============================================================
     Profile dropdown — list, switch, rename, duplicate, delete, add new
     ============================================================ */
  const ProfileDropdown = ({
    profiles,
    activeId,
    onChange,
    onRename,
    onAdd,
    onDuplicate,
    onDelete
  }) => {
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const [draft, setDraft] = useState("");
    const ref = useRef(null);
    useEffect(() => {
      const h = e => {
        if (ref.current && !ref.current.contains(e.target)) {
          setOpen(false);
          setEditing(null);
        }
      };
      document.addEventListener("mousedown", h);
      return () => document.removeEventListener("mousedown", h);
    }, []);
    const current = profiles.find(p => p.id === activeId) || profiles[0];
    if (!current) return null;
    const startEdit = p => {
      setEditing(p.id);
      setDraft(p.name);
    };
    const commit = () => {
      if (editing && onRename && draft.trim()) onRename(editing, draft.trim());
      setEditing(null);
    };
    const handleAdd = () => {
      const name = (window.prompt("New profile name", `Profile ${profiles.length + 1}`) || "").trim();
      if (!name) return;
      const dup = window.confirm("Start from a copy of the current profile? (Cancel = start blank.)");
      onAdd(name, dup);
      setOpen(false);
    };
    const handleDelete = p => {
      if (profiles.length <= 1) {
        window.alert("You need at least one profile.");
        return;
      }
      if (!window.confirm(`Delete "${p.name}"? This can't be undone.`)) return;
      onDelete(p.id);
    };
    return /*#__PURE__*/React.createElement("div", {
      className: "relative",
      ref: ref
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(o => !o),
      className: "flex items-center gap-2.5 pl-2 pr-3 h-9 rounded-xl hover:bg-white/[0.04] transition-colors"
    }, /*#__PURE__*/React.createElement("span", {
      className: "grid place-items-center w-6 h-6 rounded-md bg-white/[0.04] text-slate-400"
    }, /*#__PURE__*/React.createElement(IFolder, {
      size: 12
    })), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[14px] font-medium text-slate-100"
    }, current.name), /*#__PURE__*/React.createElement(IChevronD, {
      size: 13,
      className: `text-slate-500 transition-transform ${open ? "rotate-180" : ""}`
    })), open && /*#__PURE__*/React.createElement("div", {
      className: "absolute top-full left-0 mt-1.5 w-[280px] rounded-xl p-1.5 menu-pop z-50 animate-[fadeIn_140ms_ease-out]"
    }, profiles.map(p => {
      const active = p.id === activeId;
      if (editing === p.id) {
        return /*#__PURE__*/React.createElement("div", {
          key: p.id,
          className: "px-1.5 h-9 flex items-center"
        }, /*#__PURE__*/React.createElement("input", {
          autoFocus: true,
          value: draft,
          onChange: e => setDraft(e.target.value),
          onKeyDown: e => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setEditing(null);
          },
          onBlur: commit,
          className: "w-full h-7 px-2 rounded bg-black/40 border border-white/20 text-slate-100 font-display text-[13px] outline-none"
        }));
      }
      return /*#__PURE__*/React.createElement("div", {
        key: p.id,
        className: `w-full flex items-center gap-1 pl-2.5 pr-1 h-9 rounded-lg transition-colors
                            ${active ? "bg-[var(--accent)]/15 text-slate-100" : "text-slate-300 hover:bg-white/[0.04] hover:text-slate-100"}`
      }, /*#__PURE__*/React.createElement("button", {
        onClick: () => {
          onChange(p.id);
          setOpen(false);
        },
        className: "flex-1 flex items-center gap-2 text-left min-w-0"
      }, /*#__PURE__*/React.createElement("span", {
        className: "font-display text-[13px] truncate"
      }, p.name), active && /*#__PURE__*/React.createElement(ICheck, {
        size: 12,
        className: "text-[var(--accent)] shrink-0"
      })), /*#__PURE__*/React.createElement("button", {
        onClick: e => {
          e.stopPropagation();
          startEdit(p);
        },
        title: "Rename",
        className: "text-slate-500 hover:text-slate-200 px-1.5 h-7 grid place-items-center"
      }, /*#__PURE__*/React.createElement(IEdit, {
        size: 11
      })), /*#__PURE__*/React.createElement("button", {
        onClick: e => {
          e.stopPropagation();
          onDuplicate(p.id);
        },
        title: "Duplicate",
        className: "text-slate-500 hover:text-slate-200 px-1.5 h-7 grid place-items-center"
      }, /*#__PURE__*/React.createElement(ILink, {
        size: 11
      })), /*#__PURE__*/React.createElement("button", {
        onClick: e => {
          e.stopPropagation();
          handleDelete(p);
        },
        title: "Delete",
        disabled: profiles.length <= 1,
        className: "text-slate-500 hover:text-rose-300 disabled:text-slate-700 disabled:cursor-not-allowed px-1.5 h-7 grid place-items-center"
      }, /*#__PURE__*/React.createElement(ITrash, {
        size: 11
      })));
    }), /*#__PURE__*/React.createElement("div", {
      className: "h-px bg-white/[0.06] my-1.5"
    }), /*#__PURE__*/React.createElement("button", {
      onClick: handleAdd,
      className: "w-full flex items-center gap-2 pl-2.5 pr-1.5 h-9 rounded-lg text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors"
    }, /*#__PURE__*/React.createElement(IPlus, {
      size: 12
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[12.5px] uppercase tracking-[0.14em]"
    }, "New profile"))));
  };

  /* ============================================================
     Top bar — Notion-style page header
     ============================================================ */
  const TopBar = ({
    profiles,
    activeId,
    onProfileChange,
    onRenameProfile,
    onAddProfile,
    onDuplicateProfile,
    onDeleteProfile,
    connected,
    connecting,
    onTogglePair,
    autoConnect,
    setAutoConnect,
    onOpenTheme,
    onOpenSettings,
    saveStatus
  }) => /*#__PURE__*/React.createElement("header", {
    className: "sticky top-0 z-40 bg-[var(--bg-0)]/70 backdrop-blur-xl border-b border-white/[0.04]"
  }, /*#__PURE__*/React.createElement("div", {
    className: "max-w-[1400px] mx-auto px-6 lg:px-10 h-14 flex items-center gap-3"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-3"
  }, /*#__PURE__*/React.createElement("img", {
    src: window.__resources && window.__resources.logo || "assets/logo.png",
    alt: "",
    className: "w-8 h-8 drop-shadow-[0_4px_14px_rgba(157,78,221,0.55)]"
  }), /*#__PURE__*/React.createElement("div", {
    className: "hidden md:block leading-tight"
  }, /*#__PURE__*/React.createElement("div", {
    className: "font-display text-[16px] font-bold tracking-[0.14em] text-white"
  }, "Aether"))), /*#__PURE__*/React.createElement("span", {
    className: "mx-3 h-5 w-px bg-white/[0.06]"
  }), /*#__PURE__*/React.createElement(ProfileDropdown, {
    profiles: profiles,
    activeId: activeId,
    onChange: onProfileChange,
    onRename: onRenameProfile,
    onAdd: onAddProfile,
    onDuplicate: onDuplicateProfile,
    onDelete: onDeleteProfile
  }), saveStatus && /*#__PURE__*/React.createElement("span", {
    className: `ml-2 font-mono text-[10px] uppercase tracking-[0.18em] transition-opacity
                          ${saveStatus === "saving" ? "text-slate-500" : saveStatus === "saved" ? "text-emerald-400/80" : "text-rose-400/80"}`
  }, saveStatus === "saving" ? "saving…" : saveStatus === "saved" ? "✓ saved" : "save failed"), /*#__PURE__*/React.createElement("div", {
    className: "ml-auto flex items-center gap-2"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center gap-2 pl-2.5 pr-3 h-9 rounded-xl border border-white/[0.05] bg-white/[0.025]"
  }, /*#__PURE__*/React.createElement("span", {
    className: `relative inline-block w-1.5 h-1.5 rounded-full pulse-ring ${connected ? "bg-emerald-400 text-emerald-400" : "bg-slate-500 text-slate-500"}`
  }), /*#__PURE__*/React.createElement("span", {
    className: "font-display text-[12.5px] tracking-[0.04em] text-slate-100"
  }, "WIN 60 HE"), /*#__PURE__*/React.createElement("span", {
    className: `font-mono text-[9.5px] uppercase tracking-[0.2em] ml-1 ${connected ? "text-emerald-300/85" : "text-slate-500"}`
  }, connected ? "Linked" : "Offline")), /*#__PURE__*/React.createElement("label", {
    className: "flex items-center gap-1.5 pl-2 pr-2.5 h-9 rounded-xl border border-white/[0.05] bg-white/[0.025] cursor-pointer select-none",
    title: "Connect to the keyboard automatically when the app opens"
  }, /*#__PURE__*/React.createElement("span", {
    onClick: () => setAutoConnect(!autoConnect),
    className: `w-3.5 h-3.5 rounded border grid place-items-center transition
                            ${autoConnect ? "border-[var(--accent)] bg-[var(--accent)]/20" : "border-white/15 bg-white/[0.02]"}`
  }, autoConnect && /*#__PURE__*/React.createElement(ICheck, {
    size: 9,
    className: "text-[var(--accent)]"
  })), /*#__PURE__*/React.createElement("span", {
    className: "font-display text-[10px] uppercase tracking-[0.16em] text-slate-400"
  }, "Auto")), /*#__PURE__*/React.createElement("button", {
    onClick: onOpenTheme,
    className: "flex items-center gap-2 pl-2.5 pr-3 h-9 rounded-xl border border-white/[0.05] bg-white/[0.025] text-slate-300 hover:text-white hover:border-white/15 transition-colors"
  }, /*#__PURE__*/React.createElement("span", {
    className: "w-3.5 h-3.5 rounded-full ring-1 ring-white/15",
    style: {
      background: "var(--accent-gradient, var(--accent))"
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "font-display text-[12px] uppercase tracking-[0.16em]"
  }, "Theme")), /*#__PURE__*/React.createElement("button", {
    onClick: onTogglePair,
    disabled: connecting,
    className: `flex items-center gap-2 pl-2.5 pr-3 h-9 rounded-xl border transition-all disabled:opacity-60
                      ${connected ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/15" : "border-[var(--accent)]/40 bg-[var(--accent)]/12 text-[var(--accent)] hover:bg-[var(--accent)]/20"}`
  }, connected ? /*#__PURE__*/React.createElement(IPower, {
    size: 13
  }) : /*#__PURE__*/React.createElement(IPlug, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    className: "font-display text-[12px] uppercase tracking-[0.16em]"
  }, connecting ? "…" : connected ? "Connected" : "Pair")), /*#__PURE__*/React.createElement("button", {
    title: "Settings",
    onClick: onOpenSettings,
    className: "w-9 h-9 rounded-xl border border-white/[0.05] bg-white/[0.025] text-slate-400 hover:text-white hover:border-white/15 grid place-items-center transition-colors"
  }, /*#__PURE__*/React.createElement(ISettings, {
    size: 14
  })))));

  /* ============================================================
     Segmented pill nav
     ============================================================ */
  const SectionNav = ({
    section,
    setSection
  }) => /*#__PURE__*/React.createElement("div", {
    className: "flex justify-center"
  }, /*#__PURE__*/React.createElement("div", {
    className: "inline-flex gap-1 p-1 rounded-2xl border border-white/[0.05] bg-white/[0.02] backdrop-blur-md"
  }, NAV.map(n => {
    const active = section === n.id;
    return /*#__PURE__*/React.createElement("button", {
      key: n.id,
      onClick: () => setSection(n.id),
      className: `relative flex items-center gap-2 px-4 h-9 rounded-xl font-display text-[12px] uppercase tracking-[0.18em] transition-all
                        ${active ? "pill-active" : "text-slate-400 hover:text-slate-100 hover:bg-white/[0.03]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: active ? "text-[var(--accent)]" : ""
    }, n.icon), n.label);
  })));

  /* ============================================================
     Hero — keyboard preview card
     ============================================================ */
  const HeroCard = ({
    children,
    badge,
    breadcrumb
  }) => /*#__PURE__*/React.createElement("section", {
    className: "surface rounded-3xl px-6 lg:px-10 py-7 relative overflow-hidden"
  }, /*#__PURE__*/React.createElement("div", {
    "aria-hidden": true,
    className: "absolute -top-32 left-1/2 -translate-x-1/2 w-[820px] h-[420px] rounded-[50%] opacity-30 pointer-events-none blur-3xl",
    style: {
      background: "var(--accent-gradient, var(--accent))"
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "relative"
  }, /*#__PURE__*/React.createElement("div", {
    className: "flex items-center justify-between mb-5"
  }, /*#__PURE__*/React.createElement("div", {
    className: "font-mono text-[10px] uppercase tracking-[0.28em] text-slate-500"
  }, breadcrumb), badge), children));

  /* ============================================================
     App
     ============================================================ */
  function App() {
    const [theme, setTheme] = useTheme();
    const [themeOpen, setThemeOpen] = useState(false);

    // Connection is OFF until the user pairs (or auto-connect is enabled).
    const [connected, setConnected] = useState(false);
    const [connecting, setConnecting] = useState(false);
    const [autoConnect, setAutoConnect] = useState(() => {
      try {
        return localStorage.getItem("aether-autoconnect") === "1";
      } catch {
        return false;
      }
    });
    const [section, setSection] = useState("actuation");

    // Dynamic profile list + the currently active id.
    const [profiles, setProfiles] = useState([{
      ...SEED_PROFILE
    }]);
    const [activeId, setActiveId] = useState(SEED_PROFILE.id);
    // The big "is settings ready to start saving" flag. Stays true (= block saves)
    // until the first hydration attempt finishes, success or fail.
    const [hydrated, setHydrated] = useState(false);
    const [saveStatus, setSaveStatus] = useState(null); // null | "saving" | "saved" | "error"

    const [layer, setLayer] = useState("default");

    // Empty by default. Actuation/dead-band changes are only sent for the
    // selected keys; with nothing selected they're a no-op (use "Select All" to
    // hit every key) so the whole board is never overwritten by accident.
    const [selectedKeys, setSelectedKeys] = useState(() => new Set());
    const [actuation, setActuation] = useState(1.70);
    const [rtPress, setRtPress] = useState(0.05);
    const [rtRelease, setRtRelease] = useState(0.05);
    const [rtEnabled, setRtEnabled] = useState(false);
    const [polling, setPolling] = useState(8);
    const [travelTest, setTravelTest] = useState(false);
    const [liveDepths, setLiveDepths] = useState(null); // real per-key travel (mm)
    const [lightFrame, setLightFrame] = useState(null); // live effect frame {code:[r,g,b]}
    const [calibrating, setCalibrating] = useState(false);
    const [calibratedKeys, setCalibratedKeys] = useState(() => new Set()); // codes confirmed calibrated by firmware
    const [lightNonce, setLightNonce] = useState(0); // bump to force-resend lighting (e.g. after calibration)
    const [deadTop, setDeadTop] = useState(0.04);
    const [deadBottom, setDeadBottom] = useState(0.05);
    const [switchId, setSwitchId] = useState("hm1");

    // Gamepad: virtual-pad capture + key→control mappings.
    const DEFAULT_PAD_MAP = [{
      key: "A",
      axis: "LX",
      direction: -1,
      threshold_mm: 1.5
    }, {
      key: "D",
      axis: "LX",
      direction: 1,
      threshold_mm: 1.5
    }, {
      key: "W",
      axis: "RT",
      direction: 1,
      threshold_mm: 1.5
    }, {
      key: "S",
      axis: "LT",
      direction: 1,
      threshold_mm: 1.5
    }, {
      key: "Space",
      axis: "BTN_A",
      direction: 1,
      threshold_mm: 1.0
    }];
    const [gamepadOn, setGamepadOn] = useState(false);
    const [gamepadMap, setGamepadMap] = useState(DEFAULT_PAD_MAP);

    // Out-of-the-box: RGB radar (user pref).
    const [colors, setColors] = useState(["#ff0040", "#ff8a00", "#ffd400", "#1eff7a", "#00b7ff", "#9d4edd"]);
    const [bgColor, setBgColor] = useState("#000000");
    const [perKeyColors, setPerKeyColors] = useState({});
    const [zones, setZones] = useState([]); // effect zones for Custom mode
    const [pattern, setPattern] = useState("radar");
    const [brightness, setBrightness] = useState(100);
    const [speed, setSpeed] = useState(60);
    const [power, setPower] = useState(true);
    const [fullColor, setFullColor] = useState(false); // rainbow / full-spectrum
    const [direction, setDirection] = useState(0); // 0→ 1← 2↑ 3↓
    const [striOrient, setStriOrient] = useState("v"); // striation: v|h|both
    const [bgBright, setBgBright] = useState(100); // background brightness %

    const [socdMode, setSocdMode] = useState("last");
    const [hotkey] = useState("Fn + R-Shift");
    const [hotkeyEnabled, setHotkeyEnabled] = useState(true);
    // SOCD profiles live here (not inside SOCDSection) so they persist + save.
    const [socdProfiles, setSocdProfiles] = useState([{
      id: "SOCD1",
      k1: "A",
      k2: "D",
      mode: 1,
      active: true
    }, {
      id: "SOCD2",
      k1: "W",
      k2: "S",
      mode: 1
    }]);
    const [socdActive, setSocdActive] = useState("SOCD1");

    // ---- per-profile persistence ----------------------------------------------
    // applyingRef blocks the save effect while we hydrate (mount OR profile
    // switch). Starts true so the very first render doesn't clobber the file
    // before load_settings has a chance to run.
    const applyingRef = useRef(true);
    const collectState = () => ({
      pattern,
      colors,
      bgColor,
      brightness,
      speed,
      power,
      fullColor,
      direction,
      striOrient,
      bgBright,
      perKeyColors,
      zones,
      actuation,
      rtPress,
      rtRelease,
      rtEnabled,
      polling,
      deadTop,
      deadBottom,
      switchId,
      socdProfiles,
      socdActive,
      hotkeyEnabled,
      socdMode,
      layer,
      gamepadMap
    });
    const applyState = s => {
      if (!s) return;
      applyingRef.current = true;
      const set = (v, fn) => {
        if (v !== undefined) fn(v);
      };
      set(s.pattern, setPattern);
      set(s.colors, setColors);
      set(s.bgColor, setBgColor);
      set(s.brightness, setBrightness);
      set(s.speed, setSpeed);
      set(s.power, setPower);
      set(s.fullColor, setFullColor);
      set(s.direction, setDirection);
      set(s.bgBright, setBgBright);
      set(s.striOrient, setStriOrient);
      set(s.perKeyColors, setPerKeyColors);
      set(s.zones, setZones);
      set(s.actuation, setActuation);
      set(s.rtPress, setRtPress);
      set(s.rtRelease, setRtRelease);
      set(s.rtEnabled, setRtEnabled);
      set(s.polling, setPolling);
      set(s.deadTop, setDeadTop);
      set(s.deadBottom, setDeadBottom);
      set(s.switchId, setSwitchId);
      set(s.socdProfiles, setSocdProfiles);
      set(s.socdActive, setSocdActive);
      set(s.hotkeyEnabled, setHotkeyEnabled);
      set(s.socdMode, setSocdMode);
      set(s.layer, setLayer);
      set(s.gamepadMap, setGamepadMap);
      setTimeout(() => {
        applyingRef.current = false;
      }, 80);
    };

    // Hydrate from settings.json once the pywebview bridge is ready. We poll
    // because Edge WebView2 sometimes mounts the bridge after first render, and
    // a one-shot load misses the window — which is the bug that made nothing
    // ever persist.
    useEffect(() => {
      let cancelled = false;
      const tryLoad = async (attempt = 0) => {
        if (cancelled) return;
        if (!window.pywebview?.api?.load_settings) {
          if (attempt < 50) setTimeout(() => tryLoad(attempt + 1), 100);else {
            applyingRef.current = false;
            setHydrated(true);
          }
          return;
        }
        try {
          const r = await window.pywebview.api.load_settings();
          if (cancelled) return;
          const migrated = r && r.ok ? migrateSettings(r.settings) : null;
          if (migrated && migrated.profiles && migrated.profiles.length) {
            setProfiles(migrated.profiles);
            const aid = migrated.activeProfile && migrated.profiles.find(p => p.id === migrated.activeProfile) ? migrated.activeProfile : migrated.profiles[0].id;
            setActiveId(aid);
            const active = migrated.profiles.find(p => p.id === aid);
            if (active?.state) applyState(active.state);
            if (migrated.globals?.autoConnect !== undefined) setAutoConnect(!!migrated.globals.autoConnect);
            if (migrated.globals?.section) setSection(migrated.globals.section);
          }
        } catch {}
        setTimeout(() => {
          applyingRef.current = false;
          setHydrated(true);
        }, 100);
      };
      tryLoad();
      return () => {
        cancelled = true;
      };
    }, []);

    // Mirror the live state into the active profile's `state` slot whenever
    // anything changes — but only after hydration. Saves immediately (no
    // debounce) because Python json.dump is microseconds and a close-too-fast
    // window was a real source of "settings didn't persist". A tiny 120ms debounce
    // coalesces bursts (sliders) without risking lost writes on quick exits.
    const saveTimer = useRef(null);
    useEffect(() => {
      if (!hydrated || applyingRef.current) return;
      const state = collectState();
      setProfiles(ps => {
        const next = ps.map(p => p.id === activeId ? {
          ...p,
          state
        } : p);
        // Persist the whole blob (profiles + active id + globals).
        clearTimeout(saveTimer.current);
        saveTimer.current = setTimeout(() => {
          if (!window.pywebview?.api?.save_settings) return;
          setSaveStatus("saving");
          const blob = {
            profiles: next,
            activeProfile: activeId,
            globals: {
              autoConnect,
              section
            }
          };
          Promise.resolve(window.pywebview.api.save_settings(blob)).then(r => {
            setSaveStatus(r && r.ok ? "saved" : "error");
            setTimeout(() => setSaveStatus(null), 1400);
          }).catch(() => {
            setSaveStatus("error");
            setTimeout(() => setSaveStatus(null), 1400);
          });
        }, 120);
        return next;
      });
    }, [hydrated, activeId, pattern, colors, bgColor, brightness, speed, power, fullColor, direction, striOrient, bgBright, perKeyColors, zones, actuation, rtPress, rtRelease, rtEnabled, polling, deadTop, deadBottom, switchId, socdProfiles, socdActive, hotkeyEnabled, socdMode, layer, gamepadMap, autoConnect, section]);

    // Force a synchronous flush before the window closes / page unloads, so the
    // 120ms debounce never costs us the last edit.
    useEffect(() => {
      const flush = () => {
        if (!window.pywebview?.api?.save_settings || !hydrated) return;
        const state = collectState();
        const ps = profiles.map(p => p.id === activeId ? {
          ...p,
          state
        } : p);
        try {
          window.pywebview.api.save_settings({
            profiles: ps,
            activeProfile: activeId,
            globals: {
              autoConnect,
              section
            }
          });
        } catch {}
      };
      window.addEventListener("beforeunload", flush);
      window.addEventListener("pagehide", flush);
      return () => {
        window.removeEventListener("beforeunload", flush);
        window.removeEventListener("pagehide", flush);
      };
    });

    // ---- profile management actions -------------------------------------------
    const switchProfile = id => {
      if (id === activeId) return;
      const p = profiles.find(x => x.id === id);
      if (!p) return;
      setActiveId(id);
      applyState(p.state || {});
    };
    const renameProfile = (id, name) => {
      setProfiles(ps => ps.map(p => p.id === id ? {
        ...p,
        name
      } : p));
    };
    const addProfile = (name, duplicateCurrent = false) => {
      const newId = "p_" + Date.now().toString(36);
      const seed = duplicateCurrent ? collectState() : {};
      setProfiles(ps => [...ps, {
        id: newId,
        name: name || `Profile ${ps.length + 1}`,
        state: seed
      }]);
      // Switch to it; if duplicating we already have the right state in memory.
      setActiveId(newId);
      if (!duplicateCurrent) applyState({});
    };
    const duplicateProfile = id => {
      const src = profiles.find(p => p.id === id);
      if (!src) return;
      const newId = "p_" + Date.now().toString(36);
      setProfiles(ps => [...ps, {
        id: newId,
        name: `${src.name} (copy)`,
        state: JSON.parse(JSON.stringify(src.state || {}))
      }]);
    };
    const deleteProfile = id => {
      if (profiles.length <= 1) return;
      const remain = profiles.filter(p => p.id !== id);
      setProfiles(remain);
      if (activeId === id) {
        setActiveId(remain[0].id);
        applyState(remain[0].state || {});
      }
    };
    const keyboardMode = section === "actuation" ? "actuation" : section === "lighting" ? "lighting" : section === "socd" ? "socd" : "keymap";
    const ledMap = useMemo(() => {
      if (section !== "lighting") return {};
      const m = {};
      // Effect color depends on pattern. For "static" all keys = colors[0].
      // For others we cycle palette across keys. bgColor underlies un-effect keys.
      window.AetherKeyboard.KB_ROWS.flat().forEach(([_, __, code], idx) => {
        if (perKeyColors[code]) {
          m[code] = perKeyColors[code];
          return;
        }
        if (pattern === "static") {
          m[code] = colors[0];
          return;
        }
        // Simulated effect: every nth key gets an effect color, rest = bg
        const hit = idx % 6 === 0 || colors.length === 1;
        m[code] = hit ? colors[idx % colors.length] : bgColor;
      });
      return m;
    }, [section, colors, bgColor, perKeyColors, pattern]);
    const selectedKey = useMemo(() => Array.from(selectedKeys)[0] || null, [selectedKeys]);

    /* ===== HID bridge: handlers ===== */
    // Pair button -> real connect / disconnect.
    const togglePair = () => {
      if (connecting) return;
      setConnecting(true);
      if (connected) {
        apiCall("disconnect").then(() => {
          setConnected(false);
          setLiveDepths(null);
        }).finally(() => setConnecting(false));
      } else {
        apiCall("connect").then(r => setConnected(!!(r && r.ok))).finally(() => setConnecting(false));
      }
    };

    // Polling change restarts the board, so only ever send it on an explicit click.
    const handleSetPolling = p => {
      setPolling(p);
      if (connected) apiCall("set_poll", p);
    };
    const handleCalibrate = start => {
      setCalibrating(start);
      if (start) setCalibratedKeys(new Set());
      apiCall("calibrate", start, false); // lighting keeps running during calibration
    };

    // Gamepad: push the current map then toggle capture on/off.
    const [gamepadError, setGamepadError] = useState(null); // {msg, needsDriver}
    const handleGamepadToggle = on => {
      setGamepadOn(on);
      if (on) {
        setGamepadError(null);
        apiCall("set_gamepad_map", gamepadMap);
      }
      apiCall("set_gamepad_capture", on).then(r => {
        if (!(r && r.ok)) {
          setGamepadOn(false);
          setGamepadError({
            msg: r && r.error || "failed",
            needsDriver: !!(r && r.needs_vigembus)
          });
        } else {
          setGamepadError(null);
        }
      });
    };
    const handleInstallVigem = async () => {
      setGamepadError({
        msg: "installing ViGEmBus (approve the UAC prompt)…",
        needsDriver: false,
        installing: true
      });
      const r = await apiCall("install_vigembus");
      if (r && r.ok) setGamepadError({
        msg: "ViGEmBus installed — try capture again.",
        needsDriver: false
      });else setGamepadError({
        msg: r && r.error || "install failed",
        needsDriver: true
      });
    };
    const handleGamepadMapApply = map => {
      setGamepadMap(map);
      if (gamepadOn) apiCall("set_gamepad_map", map);
    };
    const handlePickSwitch = id => {
      setSwitchId(id);
      const map = {
        hm1: 1,
        hh1: 2,
        cy1: 3,
        tc1: 5
      };
      if (connected) apiCall("set_switch_codes", Array.from(selectedKeys), map[id] || 1);
    };

    // Effect zones (Custom mode): a group of keys running their own effect.
    const addZone = () => {
      const codes = Array.from(selectedKeys);
      if (!codes.length) return;
      setZones(zs => [...zs, {
        id: Date.now(),
        codes,
        mode: "twinkle",
        colors: ["#ff1f5a", "#00f5ff"],
        speed: 60
      }]);
    };
    const updateZone = (id, patch) => setZones(zs => zs.map(z => z.id === id ? {
      ...z,
      ...patch
    } : z));
    const removeZone = id => setZones(zs => zs.filter(z => z.id !== id));
    const handleSocdApply = profiles => {
      const pairs = (profiles || []).filter(p => p.k1 && p.k2).map(p => ({
        model: p.mode || 1,
        key1: LABEL_TO_CODE[p.k1] || p.k1,
        key2: LABEL_TO_CODE[p.k2] || p.k2
      }));
      if (pairs.length) apiCall("set_socd", pairs);
    };

    /* ===== HID bridge: effects (push state to the board) ===== */
    // Persist the auto-connect preference.
    useEffect(() => {
      try {
        localStorage.setItem("aether-autoconnect", autoConnect ? "1" : "0");
      } catch {}
    }, [autoConnect]);

    // One-shot auto-connect on launch, only if the user opted in. Waits for the
    // pywebview bridge to be injected (it arrives asynchronously after load).
    const didAuto = useRef(false);
    useEffect(() => {
      const go = () => {
        if (didAuto.current) return;
        didAuto.current = true;
        if (!autoConnect) return;
        setConnecting(true);
        apiCall("connect").then(r => setConnected(!!(r && r.ok))).finally(() => setConnecting(false));
      };
      if (getApi()) go();else window.addEventListener("pywebviewready", go, {
        once: true
      });
      return () => window.removeEventListener("pywebviewready", go);
    }, []);

    // Lighting. ALL animated effects run on the HOST per-key engine so their
    // behaviour is consistent and matches the names (auto Ripple/Cross/Fireworks,
    // distinct Striation, directional flow, etc.) regardless of color count.
    // Only Static and Full-RGB use the firmware mode. `section` is intentionally
    // NOT a dependency: switching tabs never re-sends.
    const lightTimer = useRef(null);
    useEffect(() => {
      if (!connected) return;
      if (pattern === "custom") return; // custom effect (below) owns the engine
      clearTimeout(lightTimer.current);
      lightTimer.current = setTimeout(() => {
        // Unified brightness: do NOT pre-scale the bg by bgBright here. The host
        // engine applies the main `brightness` to both fg and bg equally, so any
        // pre-scaling here would make the bg dimmer than the effect colors by
        // exactly the bgBright ratio (the two used to fight).
        const bgScaled = hexToRgbArr(bgColor);
        // Animated effects run on the HOST per-key engine so they can show the
        // full multi-color palette (firmware effects only hold one fg+bg). Only
        // Static and Full-RGB use the firmware mode directly.
        const useHost = power && !fullColor && pattern !== "static";
        if (useHost) {
          apiCall("start_multicolor", pattern, colors.map(hexToRgbArr), bgScaled, brightness, speed, direction, striOrient);
        } else {
          apiCall("stop_multicolor");
          const [r, g, b] = hexToRgbArr(colors[0] || "#ffffff");
          const [br, bg, bb] = bgScaled;
          apiCall("set_light", MODE_BYTE[pattern] ?? 0, r, g, b, briByte(brightness), spdByte(speed), br, bg, bb, direction, power, fullColor ? 1 : 0);
        }
      }, 70);
      return () => clearTimeout(lightTimer.current);
    }, [connected, pattern, colors, bgColor, brightness, speed, power, fullColor, direction, bgBright, striOrient, lightNonce, calibrating]);

    // Custom mode: effect zones if any are defined (each key group runs its own
    // animated effect), otherwise static per-key colors.
    useEffect(() => {
      if (!connected || pattern !== "custom") return;
      if (zones.length) {
        // Unified brightness: do NOT pre-scale the bg by bgBright here. The host
        // engine applies the main `brightness` to both fg and bg equally, so any
        // pre-scaling here would make the bg dimmer than the effect colors by
        // exactly the bgBright ratio (the two used to fight).
        const bgScaled = hexToRgbArr(bgColor);
        apiCall("start_zones", zones.map(z => ({
          codes: z.codes,
          mode: z.mode,
          colors: (z.colors || []).map(hexToRgbArr),
          bg: bgScaled,
          // keys outside zones + zone backdrops use it
          brightness,
          speed: z.speed != null ? z.speed : speed,
          direction
        })));
      } else {
        apiCall("stop_multicolor");
        const map = {};
        Object.entries(perKeyColors || {}).forEach(([code, hex]) => {
          map[code] = hexToRgbArr(hex);
        });
        apiCall("set_custom_colors", map, briByte(brightness), spdByte(speed));
      }
    }, [connected, pattern, perKeyColors, brightness, speed, zones, direction, bgColor, bgBright, lightNonce, calibrating]);

    // Actuation / Rapid Trigger: EXPLICIT apply only.
    //
    // Earlier versions streamed slider changes to the device on every selection
    // or value change. That stream-on-change model had a fatal UX failure: the
    // global `selectedKeys` set leaks across tabs (Lighting "Select All" stays
    // selected when you enter Actuation), so the very first slider movement
    // would silently push the new travel to every key. Worse, debouncing only
    // hides the symptom — by the time the user notices the slider has moved
    // off where they want, the firmware has already committed the write to a
    // selection they didn't realise was active.
    //
    // The driver-style fix is the one the user expected all along: select keys,
    // pick values, click Apply. The slider value is local React state until
    // they hit Apply, at which point we write to EXACTLY the selection shown in
    // the badge ("N selected"). Nothing else can race the write.
    const applyActuation = () => {
      if (!connected) return;
      const codes = Array.from(selectedKeys);
      if (codes.length === 0) return;
      const mode = rtEnabled ? 13 : 0;
      apiCall("set_trigger_codes", codes, actuation, rtEnabled ? rtPress : 0, rtEnabled ? rtRelease : 0, mode);
    };
    const applyDeadband = () => {
      if (!connected) return;
      const codes = Array.from(selectedKeys);
      if (codes.length === 0) return;
      apiCall("set_deadband_codes", codes, deadTop, deadBottom);
    };

    // Travel Test: stream live analog depth for ALL keys (so any keypress shows,
    // not just the selected ones) and mirror it onto the on-screen board.
    useEffect(() => {
      if (!connected || !travelTest) {
        if (connected) apiCall("close_analog");
        setLiveDepths(null);
        return;
      }
      apiCall("open_analog_codes", []); // [] = all keys
      let alive = true;
      const id = setInterval(() => {
        apiCall("read_live").then(d => {
          if (alive && d && typeof d === "object" && !(d.ok === false)) setLiveDepths(d);
        });
      }, 33); // ~30fps — smooth enough for visual depth, doesn't starve the lighting stream
      return () => {
        alive = false;
        clearInterval(id);
      };
    }, [connected, travelTest]);

    // Calibration: the firmware reports each key the moment it's calibrated. Poll
    // those codes and mark them — they light up green both on screen and (driven by
    // Python) on the physical board. Lighting is killed on the Python side at start.
    useEffect(() => {
      if (!connected || !calibrating) return;
      let alive = true;
      let lastCount = 0,
        lastChange = Date.now();
      const finish = () => {
        if (!alive) return;
        alive = false;
        clearInterval(id);
        handleCalibrate(false);
      };
      const id = setInterval(() => {
        apiCall("read_calibrated").then(r => {
          if (!alive || !r || r.ok === false || !Array.isArray(r.codes)) return;
          setCalibratedKeys(prev => {
            if (r.codes.length === prev.size && r.codes.every(c => prev.has(c))) return prev;
            return new Set(r.codes);
          });
          if (r.codes.length !== lastCount) {
            lastCount = r.codes.length;
            lastChange = Date.now();
          }
          // Auto-finish: firmware "done" signal, OR no new key calibrated for 3s
          // after at least one was (so you're never stuck waiting on the button).
          if (r.done) return finish();
          if (lastCount > 0 && Date.now() - lastChange > 3000) return finish();
        });
      }, 80);
      return () => {
        alive = false;
        clearInterval(id);
      };
    }, [connected, calibrating]);

    // Mirror the live host effect onto the IN-APP keyboard: poll the current frame
    // while on the Lighting tab and paint each key with its real animated color.
    // The host engine streams cmd-9 pages to the board at 120fps under the GIL;
    // a tight polling loop here starves it and makes the board look choppy.
    // 50ms (~20fps) is plenty for the on-screen mirror and leaves the engine room.
    useEffect(() => {
      if (!connected || section !== "lighting") {
        setLightFrame(null);
        return;
      }
      let alive = true;
      const id = setInterval(() => {
        apiCall("get_light_frame").then(f => {
          if (!alive) return;
          setLightFrame(f && typeof f === "object" && !(f.ok === false) && Object.keys(f).length ? f : null);
        });
      }, 50);
      return () => {
        alive = false;
        clearInterval(id);
      };
    }, [connected, section]);

    // Deepest currently-pressed key, for the switch-cutaway animation.
    const liveMax = useMemo(() => {
      if (!liveDepths) return 0;
      let m = 0;
      for (const k in liveDepths) {
        const v = +liveDepths[k] || 0;
        if (v > m) m = v;
      }
      return m;
    }, [liveDepths]);

    // Live effect colors for the in-app keyboard (overrides the static preview).
    const ledMapLive = useMemo(() => {
      if (!lightFrame) return null;
      const m = {};
      for (const code in lightFrame) m[code] = rgbToHex(lightFrame[code]);
      return m;
    }, [lightFrame]);

    // Hero badge & breadcrumb vary by section
    const breadcrumb = useMemo(() => {
      const profName = (profiles.find(p => p.id === activeId) || {}).name || "Profile";
      const secName = NAV.find(n => n.id === section)?.label || "";
      return `${profName} · ${secName}`;
    }, [profiles, activeId, section]);
    const heroBadge = section === "actuation" ? /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement(Stat, {
      label: "Actuation",
      value: `${actuation.toFixed(2)}mm`
    }), /*#__PURE__*/React.createElement(Stat, {
      label: "Polling",
      value: `${polling}KHz`
    }), /*#__PURE__*/React.createElement(Stat, {
      label: "Selected",
      value: `${selectedKeys.size}`
    })) : section === "lighting" ? /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement(Stat, {
      label: "Mode",
      value: pattern
    }), /*#__PURE__*/React.createElement(Stat, {
      label: "Brightness",
      value: `${Math.round(brightness)}%`
    }), /*#__PURE__*/React.createElement(Stat, {
      label: "Colors",
      value: `${colors.length}`
    })) : section === "socd" ? /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement(Stat, {
      label: "Hotkey",
      value: hotkey
    })) : section === "keymap" ? /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 p-1 rounded-xl border border-white/[0.06] bg-white/[0.02]"
    }, ["default", "fn"].map(l => /*#__PURE__*/React.createElement("button", {
      key: l,
      onClick: () => setLayer(l),
      className: `px-3 h-7 rounded-lg font-display text-[11px] uppercase tracking-[0.16em] transition-all
                      ${layer === l ? "bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]" : "text-slate-400 hover:text-slate-100"}`
    }, l === "default" ? "Default Layer" : "Fn Layer"))) : null;
    const leftSlot = section === "actuation" ? /*#__PURE__*/React.createElement(ActuationToolbar, {
      onSelectAll: () => {
        const all = new Set(window.AetherKeyboard.KB_ROWS.flat().map(([_, __, c]) => c));
        setSelectedKeys(all);
      },
      onSelectInvert: () => {
        const all = window.AetherKeyboard.KB_ROWS.flat().map(([_, __, c]) => c);
        setSelectedKeys(prev => new Set(all.filter(c => !prev.has(c))));
      },
      onDeselectAll: () => setSelectedKeys(new Set()),
      onResetTrigger: () => {
        setActuation(1.70);
        setRtPress(0.05);
        setRtRelease(0.05);
      }
    }) : null;
    return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(TopBar, {
      profiles: profiles,
      activeId: activeId,
      onProfileChange: switchProfile,
      onRenameProfile: renameProfile,
      onAddProfile: addProfile,
      onDuplicateProfile: duplicateProfile,
      onDeleteProfile: deleteProfile,
      connected: connected,
      connecting: connecting,
      onTogglePair: togglePair,
      autoConnect: autoConnect,
      setAutoConnect: setAutoConnect,
      onOpenTheme: () => setThemeOpen(true),
      onOpenSettings: () => setSection("other"),
      saveStatus: saveStatus
    }), /*#__PURE__*/React.createElement("main", {
      className: "max-w-[1400px] mx-auto px-6 lg:px-10 py-7 flex flex-col gap-6"
    }, /*#__PURE__*/React.createElement(SectionNav, {
      section: section,
      setSection: setSection
    }), /*#__PURE__*/React.createElement(HeroCard, {
      breadcrumb: breadcrumb,
      badge: heroBadge
    }, /*#__PURE__*/React.createElement(KeyboardPanel, {
      mode: keyboardMode,
      layer: layer,
      selectedKeys: selectedKeys,
      setSelectedKeys: setSelectedKeys,
      actuationPoint: actuation,
      rtPress: rtEnabled ? rtPress : 0,
      rtRelease: rtEnabled ? rtRelease : 0,
      ledMap: ledMapLive || ledMap,
      accent: theme.accent,
      showPill: false,
      leftSlot: leftSlot,
      liveDepths: liveDepths,
      calibrating: calibrating,
      calibratedCodes: calibratedKeys
    })), /*#__PURE__*/React.createElement("section", {
      key: section,
      className: "surface rounded-3xl px-6 lg:px-10 py-7 section-anim"
    }, section === "keymap" && /*#__PURE__*/React.createElement(KeymapSection, {
      selectedKey: selectedKey,
      selectedCount: selectedKeys.size,
      onRemap: label => {
        const hid = HID_BY_LABEL[label];
        if (connected && hid != null && selectedKeys.size) apiCall("set_remap", Array.from(selectedKeys), hid);
      },
      onResetKey: () => {
        if (connected && selectedKeys.size) apiCall("reset_remap", Array.from(selectedKeys));
      }
    }), section === "actuation" && /*#__PURE__*/React.createElement(ActuationSection, {
      actuation: actuation,
      setActuation: setActuation,
      rtPress: rtPress,
      setRtPress: setRtPress,
      rtRelease: rtRelease,
      setRtRelease: setRtRelease,
      rtEnabled: rtEnabled,
      setRtEnabled: setRtEnabled,
      polling: polling,
      setPolling: handleSetPolling,
      travelTest: travelTest,
      setTravelTest: setTravelTest,
      calibrating: calibrating,
      onCalibrate: handleCalibrate,
      deadTop: deadTop,
      setDeadTop: setDeadTop,
      deadBottom: deadBottom,
      setDeadBottom: setDeadBottom,
      switchId: switchId,
      onPickSwitch: handlePickSwitch,
      liveDepth: liveMax,
      selectedCount: selectedKeys.size,
      onApplyActuation: applyActuation,
      onApplyDeadband: applyDeadband
    }), section === "lighting" && /*#__PURE__*/React.createElement(LightingSection, {
      colors: colors,
      setColors: setColors,
      bgColor: bgColor,
      setBgColor: setBgColor,
      perKeyColors: perKeyColors,
      setPerKeyColors: setPerKeyColors,
      pattern: pattern,
      setPattern: setPattern,
      brightness: brightness,
      setBrightness: setBrightness,
      speed: speed,
      setSpeed: setSpeed,
      power: power,
      setPower: setPower,
      fullColor: fullColor,
      setFullColor: setFullColor,
      direction: direction,
      setDirection: setDirection,
      striOrient: striOrient,
      setStriOrient: setStriOrient,
      bgBright: bgBright,
      setBgBright: setBgBright,
      zones: zones,
      onAddZone: addZone,
      onUpdateZone: updateZone,
      onRemoveZone: removeZone,
      selectedKeys: selectedKeys,
      onSelectAll: () => {
        const all = new Set(window.AetherKeyboard.KB_ROWS.flat().map(([_, __, c]) => c));
        setSelectedKeys(all);
      },
      onClearSelection: () => setSelectedKeys(new Set())
    }), section === "socd" && /*#__PURE__*/React.createElement(SOCDSection, {
      socdMode: socdMode,
      setSocdMode: setSocdMode,
      hotkey: hotkey,
      hotkeyEnabled: hotkeyEnabled,
      setHotkeyEnabled: setHotkeyEnabled,
      onApply: handleSocdApply,
      profiles: socdProfiles,
      setProfiles: setSocdProfiles,
      active: socdActive,
      setActive: setSocdActive
    }), section === "gamepad" && /*#__PURE__*/React.createElement(GamepadSection, {
      connected: connected,
      enabled: gamepadOn,
      onToggle: handleGamepadToggle,
      map: gamepadMap,
      onApplyMap: handleGamepadMapApply,
      defaultMap: DEFAULT_PAD_MAP,
      error: gamepadError,
      onInstallDriver: handleInstallVigem
    }), section === "other" && /*#__PURE__*/React.createElement(OtherSection, {
      activeProfileName: (profiles.find(p => p.id === activeId) || {}).name || "Profile",
      onResetProfile: () => {
        if (!window.confirm("Reset this profile to defaults? This can't be undone.")) return;
        applyState({});
      }
    }))), /*#__PURE__*/React.createElement(ThemePopup, {
      open: themeOpen,
      onClose: () => setThemeOpen(false),
      theme: theme,
      setTheme: setTheme
    }));
  }
  const Stat = ({
    label,
    value
  }) => /*#__PURE__*/React.createElement("div", {
    className: "flex items-baseline gap-1.5 px-3 py-1.5 rounded-xl border border-white/[0.05] bg-white/[0.02]"
  }, /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[9px] uppercase tracking-[0.22em] text-slate-500"
  }, label), /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[12px] text-slate-100"
  }, value));
  ReactDOM.createRoot(document.getElementById("root")).render(/*#__PURE__*/React.createElement(App, null));
})();