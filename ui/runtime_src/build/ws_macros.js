(() => {
  /* ============================================================
     Macros workspace — Aula Win60 HE macro slots (cmd 25) + key binds.
     Exports window.AetherWorkspaces.MACROS_WIDGETS — widget descriptors
       { id, title, default:{x,y,w,h}, min:{w,h}, render:(ctx)=>JSX }
     like every other workspace. Widgets talk to the bridge through ctx.apiCall
     ONLY (list_macros / read_macro / save_macro / delete_macro / bind_macro /
     unbind_macro — see app_web.py Api) and share state through a tiny local
     store, since widget frames are independent React roots of one workspace.
  
     Capability gate: the whole section is hidden by app.jsx unless the active
     board's registry flag `macros` is true (fail-open when no board data is
     available, like every other gate); each widget also re-checks at render
     so a board switch while the tab is open degrades to a notice.
     ============================================================ */
  const {
    useState,
    useEffect,
    useRef,
    useMemo
  } = React;
  const KB = window.AetherKeyboard || {};
  const KeyboardPanel = KB.KeyboardPanel;
  const KB_ROWS = KB.KB_ROWS || [];

  /* ===== board-context (looked up at render — components/ compile after
     workspaces/, see socd.jsx) ===== */
  const FALLBACK_BOARD_CTX = React.createContext(null);
  const useBoardSafe = () => {
    const B = window.AetherBoard;
    const val = React.useContext(B && B.BoardContext || FALLBACK_BOARD_CTX);
    return val || B && B.UNKNOWN_BOARD || null;
  };
  const macrosState = b => b && typeof b.capState === "function" ? b.capState("macros") : "unknown";

  /* ===== HID usage <-> labels (USB HID keyboard page 0x07) ===== */
  const HID_KEYS = [];
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").forEach((c, i) => HID_KEYS.push([c, 0x04 + i]));
  [["1", 0x1e], ["2", 0x1f], ["3", 0x20], ["4", 0x21], ["5", 0x22], ["6", 0x23], ["7", 0x24], ["8", 0x25], ["9", 0x26], ["0", 0x27], ["Enter", 0x28], ["Esc", 0x29], ["Back", 0x2a], ["Tab", 0x2b], ["Space", 0x2c], ["-_", 0x2d], ["=+", 0x2e], ["[{", 0x2f], ["]}", 0x30], ["\\|", 0x31], [";:", 0x33], ["'\"", 0x34], ["`~", 0x35], [",<", 0x36], [".>", 0x37], ["/?", 0x38], ["Caps", 0x39], ["F1", 0x3a], ["F2", 0x3b], ["F3", 0x3c], ["F4", 0x3d], ["F5", 0x3e], ["F6", 0x3f], ["F7", 0x40], ["F8", 0x41], ["F9", 0x42], ["F10", 0x43], ["F11", 0x44], ["F12", 0x45], ["PrtSc", 0x46], ["ScrLk", 0x47], ["Pause", 0x48], ["Ins", 0x49], ["Home", 0x4a], ["PgUp", 0x4b], ["Del", 0x4c], ["End", 0x4d], ["PgDn", 0x4e], ["Right", 0x4f], ["Left", 0x50], ["Down", 0x51], ["Up", 0x52], ["Menu", 0x65], ["L-Ctrl", 0xe0], ["L-Shift", 0xe1], ["L-Alt", 0xe2], ["L-Win", 0xe3], ["R-Ctrl", 0xe4], ["R-Shift", 0xe5], ["R-Alt", 0xe6], ["R-Win", 0xe7]].forEach(p => HID_KEYS.push(p));
  const HID_LABEL = {};
  HID_KEYS.forEach(([l, c]) => {
    HID_LABEL[c] = l;
  });
  const hidLabel = c => HID_LABEL[c] || "0x" + (c & 0xff).toString(16).toUpperCase().padStart(2, "0");

  /* KeyboardEvent.code -> HID usage, for the recorder. */
  const CODE_TO_HID = (() => {
    const m = {};
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").forEach((c, i) => {
      m["Key" + c] = 0x04 + i;
    });
    "1234567890".split("").forEach((d, i) => {
      m["Digit" + d] = 0x1e + i;
    });
    Object.assign(m, {
      Enter: 0x28,
      Escape: 0x29,
      Backspace: 0x2a,
      Tab: 0x2b,
      Space: 0x2c,
      Minus: 0x2d,
      Equal: 0x2e,
      BracketLeft: 0x2f,
      BracketRight: 0x30,
      Backslash: 0x31,
      Semicolon: 0x33,
      Quote: 0x34,
      Backquote: 0x35,
      Comma: 0x36,
      Period: 0x37,
      Slash: 0x38,
      CapsLock: 0x39,
      PrintScreen: 0x46,
      ScrollLock: 0x47,
      Pause: 0x48,
      Insert: 0x49,
      Home: 0x4a,
      PageUp: 0x4b,
      Delete: 0x4c,
      End: 0x4d,
      PageDown: 0x4e,
      ArrowRight: 0x4f,
      ArrowLeft: 0x50,
      ArrowDown: 0x51,
      ArrowUp: 0x52,
      ContextMenu: 0x65,
      ControlLeft: 0xe0,
      ShiftLeft: 0xe1,
      AltLeft: 0xe2,
      MetaLeft: 0xe3,
      ControlRight: 0xe4,
      ShiftRight: 0xe5,
      AltRight: 0xe6,
      MetaRight: 0xe7
    });
    for (let i = 1; i <= 12; i++) m["F" + i] = 0x3a + i - 1;
    return m;
  })();

  /* Design code -> key label, for the bindings list. */
  const LABEL_OF_CODE = {};
  KB_ROWS.flat().forEach(([label, _u, code]) => {
    LABEL_OF_CODE[code] = label;
  });

  /* Playback modes = macro slot header byte 1 (vendor getMacroType). Only 0 and
     1 were seen on the wire; 2 and 3 exist in the vendor UI but are unverified. */
  const PLAY_MODES = [{
    v: 0,
    label: "Once",
    hint: "Plays the sequence once per press.",
    verified: true
  }, {
    v: 1,
    label: "Repeat ×N",
    hint: "Plays the sequence N times per press.",
    verified: true
  }, {
    v: 2,
    label: "Toggle",
    hint: "Vendor macroType3 — press to start, press again to stop. NOT verified on hardware.",
    verified: false
  }, {
    v: 3,
    label: "Hold",
    hint: "Vendor macroType4 — repeats while held. NOT verified on hardware.",
    verified: false
  }];

  /* ===== shared store ===== */
  const store = {
    macros: [],
    // [{slot, name, play_mode, repeat_count, events:[{delay,hid,down}]}]
    bindings: {},
    // {designCode: slot}
    bindingsError: null,
    limits: {
      slots: 10,
      maxEvents: 62,
      maxDelay: 65535,
      maxRepeat: 65535,
      playModes: [0, 1, 2, 3]
    },
    sel: null,
    // selected slot (editor target)
    draft: null,
    // {slot, name, playMode, repeat, events:[{delay,hid,down}]}
    dirty: false,
    loaded: false,
    busy: false,
    status: null,
    // {tone:"ok"|"warn"|"bad", msg}
    listeners: new Set()
  };
  const emit = () => store.listeners.forEach(fn => {
    try {
      fn();
    } catch (e) {}
  });
  const useStore = () => {
    const [, force] = useState(0);
    useEffect(() => {
      const fn = () => force(n => n + 1);
      store.listeners.add(fn);
      return () => store.listeners.delete(fn);
    }, []);
    return store;
  };
  const setStatus = (tone, msg) => {
    store.status = msg ? {
      tone,
      msg,
      id: Date.now()
    } : null;
    emit();
    if (msg) setTimeout(() => {
      if (store.status && store.status.msg === msg) {
        store.status = null;
        emit();
      }
    }, 4500);
  };
  const macroAt = slot => store.macros.find(m => m.slot === slot) || null;
  const blankDraft = slot => ({
    slot,
    name: "",
    playMode: 0,
    repeat: 1,
    events: []
  });
  const draftFrom = m => ({
    slot: m.slot,
    name: m.name || "",
    playMode: m.play_mode || 0,
    repeat: Math.max(1, m.repeat_count || 1),
    events: (m.events || []).map(e => ({
      delay: e.delay | 0,
      hid: e.hid | 0,
      down: !!e.down
    }))
  });
  const selectSlot = slot => {
    store.sel = slot;
    const m = macroAt(slot);
    store.draft = m ? draftFrom(m) : blankDraft(slot);
    store.dirty = false;
    emit();
  };
  const updateDraft = patch => {
    store.draft = Object.assign({}, store.draft || blankDraft(store.sel == null ? 0 : store.sel), patch);
    store.dirty = true;
    emit();
  };
  const refresh = async (apiCall, quiet) => {
    if (!apiCall) return;
    store.busy = true;
    emit();
    try {
      const r = await apiCall("list_macros");
      if (r && r.ok) {
        store.macros = Array.isArray(r.macros) ? r.macros : [];
        store.bindings = r.bindings && typeof r.bindings === "object" ? r.bindings : {};
        store.bindingsError = r.bindings ? null : r.bindings_error || null;
        store.limits = {
          slots: r.slots || 10,
          maxEvents: r.max_events || 62,
          maxDelay: r.max_delay_ms || 65535,
          maxRepeat: r.max_repeat || 65535,
          playModes: Array.isArray(r.play_modes) ? r.play_modes : [0, 1, 2, 3]
        };
        store.loaded = true;
        if (store.sel != null && !store.dirty) {
          const m = macroAt(store.sel);
          store.draft = m ? draftFrom(m) : blankDraft(store.sel);
        }
        if (!quiet) setStatus("ok", `Read ${store.macros.length} macro${store.macros.length === 1 ? "" : "s"} from the board`);
      } else if (!quiet) {
        setStatus("bad", r && r.error || "list_macros failed");
      }
    } finally {
      store.busy = false;
      emit();
    }
  };

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
    title,
    small
  }) => /*#__PURE__*/React.createElement("button", {
    onClick: onClick,
    disabled: disabled,
    title: title,
    className: `${small ? "px-2 h-7 text-[10px]" : "px-3 h-9 text-[11px]"} rounded-md border font-display uppercase tracking-[0.16em] transition-all
                ${disabled ? "border-[var(--line)] bg-white/[0.02] text-[var(--text-faint)] cursor-not-allowed" : variant === "primary" ? "border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] hover:bg-[var(--accent)]/25 shadow-[0_0_12px_var(--accent-glow)]" : variant === "danger" ? "border-rose-400/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20" : variant === "rec" ? "border-rose-400/60 bg-rose-500/20 text-rose-200 shadow-[0_0_12px_rgba(244,63,94,0.45)]" : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] hover:text-[var(--text)]"}`
  }, children);
  const StatusLine = () => {
    const s = useStore();
    const st = s.status;
    return /*#__PURE__*/React.createElement("div", {
      className: "h-4 text-[11px] font-mono tracking-[0.12em] truncate"
    }, st && /*#__PURE__*/React.createElement("span", {
      className: st.tone === "ok" ? "text-[var(--accent)]" : st.tone === "warn" ? "text-amber-300/90" : "text-rose-300/90"
    }, st.msg));
  };
  const Gate = ({
    children
  }) => {
    const b = useBoardSafe();
    const st = macrosState(b);
    if (st === "yes" || st === "unknown") return children;
    return /*#__PURE__*/React.createElement("div", {
      className: "rounded-md border border-amber-400/35 bg-amber-500/[0.06] p-3"
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[10.5px] uppercase tracking-[0.18em] text-amber-300 mb-1"
    }, "Macros \xB7 unavailable"), /*#__PURE__*/React.createElement(Note, {
      tone: "warn"
    }, st === "wip" ? "This board's macro protocol is source-only (never verified on hardware) — nothing here is sent." : "The active board does not declare macro support."));
  };
  const bindingsOfSlot = slot => Object.keys(store.bindings).filter(c => store.bindings[c] === slot);

  /* ============================================================
     Widget: Key Grid (the selectable board; selection is shared via ctx)
     ============================================================ */
  function KeyGridWidget(ctx) {
    const {
      selectedKeys,
      setSelectedKeys,
      layer,
      ledMap,
      liveDepths
    } = ctx;
    return /*#__PURE__*/React.createElement("div", {
      className: "flex justify-center"
    }, KeyboardPanel ? React.createElement(KeyboardPanel, {
      mode: "keymap",
      layer: layer || "default",
      selectedKeys,
      setSelectedKeys,
      ledMap,
      showPill: false,
      compact: true,
      liveDepths
    }) : /*#__PURE__*/React.createElement("div", {
      className: "font-mono text-[11px] text-[var(--text-faint)]"
    }, "Keyboard render unavailable."));
  }

  /* ============================================================
     Widget: Macro Library — the 10 board slots
     ============================================================ */
  function LibraryWidget(ctx) {
    const s = useStore();
    const {
      apiCall,
      connected
    } = ctx;
    useEffect(() => {
      if (connected && !s.loaded && !s.busy) refresh(apiCall, true);
    }, [connected]);
    const slots = Array.from({
      length: s.limits.slots
    }, (_, i) => i);
    const doDelete = async () => {
      if (s.sel == null || !macroAt(s.sel)) return;
      const m = macroAt(s.sel);
      if (!window.confirm(`Erase macro slot ${s.sel + 1}${m.name ? ` ("${m.name}")` : ""} on the board and release its keys?`)) return;
      store.busy = true;
      emit();
      const r = await apiCall("delete_macro", s.sel);
      store.busy = false;
      if (r && r.ok) {
        setStatus("ok", `Slot ${s.sel + 1} erased${r.released && r.released.length ? ` · released ${r.released.map(c => LABEL_OF_CODE[c] || c).join(", ")}` : ""}`);
        store.dirty = false;
        await refresh(apiCall, true);
        selectSlot(s.sel);
      } else setStatus("bad", r && r.error || "delete failed");
    };
    return /*#__PURE__*/React.createElement(Gate, null, /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-3 h-full"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement(Btn, {
      onClick: () => refresh(apiCall),
      disabled: !connected || s.busy,
      small: true,
      title: "Re-read every slot from the board"
    }, "\u21BB Read board"), /*#__PURE__*/React.createElement(Btn, {
      onClick: doDelete,
      disabled: !connected || s.busy || s.sel == null || !macroAt(s.sel),
      variant: "danger",
      small: true
    }, "Erase slot"), /*#__PURE__*/React.createElement("span", {
      className: "ml-auto font-mono text-[10px] text-[var(--text-faint)] uppercase tracking-[0.18em]"
    }, s.macros.length, "/", s.limits.slots, " used")), !connected && /*#__PURE__*/React.createElement(Note, {
      tone: "warn"
    }, "Pair the keyboard to read its macro slots."), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 overflow-y-auto flex flex-col gap-1.5 pr-1"
    }, slots.map(slot => {
      const m = macroAt(slot);
      const active = s.sel === slot;
      const bound = bindingsOfSlot(slot);
      const mode = PLAY_MODES.find(p => p.v === (m ? m.play_mode : 0)) || PLAY_MODES[0];
      return /*#__PURE__*/React.createElement("button", {
        key: slot,
        onClick: () => selectSlot(slot),
        className: `w-full text-left px-3 py-2 rounded-md border transition-all
                            ${active ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 shadow-[0_0_10px_var(--accent-glow)]" : "border-[var(--line)] bg-white/[0.02] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`
      }, /*#__PURE__*/React.createElement("div", {
        className: "flex items-center gap-2"
      }, /*#__PURE__*/React.createElement("span", {
        className: `font-mono text-[10px] w-7 ${active ? "text-[var(--accent)]" : "text-[var(--text-faint)]"}`
      }, "M", slot + 1), /*#__PURE__*/React.createElement("span", {
        className: `font-display text-[12.5px] truncate ${m ? "text-[var(--text)]" : "text-[var(--text-faint)] italic"}`
      }, m ? m.name || `Macro ${slot + 1}` : "empty"), m && /*#__PURE__*/React.createElement("span", {
        className: "ml-auto flex items-center gap-1.5 shrink-0"
      }, /*#__PURE__*/React.createElement("span", {
        className: "font-mono text-[9px] text-[var(--text-faint)]"
      }, m.events.length, " ev"), /*#__PURE__*/React.createElement("span", {
        className: "chip"
      }, mode.label, m.play_mode === 1 ? ` ${m.repeat_count}` : ""))), bound.length > 0 && /*#__PURE__*/React.createElement("div", {
        className: "mt-1 flex flex-wrap gap-1"
      }, bound.map(c => /*#__PURE__*/React.createElement("span", {
        key: c,
        className: "px-1.5 py-0.5 rounded border border-[var(--accent)]/30 bg-[var(--accent)]/10 font-mono text-[9px] text-[var(--accent)]"
      }, LABEL_OF_CODE[c] || c))));
    })), /*#__PURE__*/React.createElement(StatusLine, null)));
  }

  /* ============================================================
     Widget: Macro Editor — record / compose steps, playback, save
     ============================================================ */
  function EditorWidget(ctx) {
    const s = useStore();
    const {
      apiCall,
      connected
    } = ctx;
    const [recording, setRecording] = useState(false);
    const [pickKey, setPickKey] = useState(0x04);
    const recRef = useRef(null);
    const lastT = useRef(0);
    const held = useRef(new Set());
    useEffect(() => {
      if (recording && recRef.current) recRef.current.focus();
    }, [recording]);
    const d = s.draft;
    const events = d ? d.events : [];
    const full = events.length >= s.limits.maxEvents;
    const push = (hid, down, delay) => {
      if (full) {
        setStatus("warn", `Slot holds at most ${s.limits.maxEvents} events`);
        return;
      }
      updateDraft({
        events: events.concat([{
          delay: Math.min(s.limits.maxDelay, Math.max(0, delay | 0)),
          hid,
          down
        }])
      });
    };
    const startRec = () => {
      if (!d) return;
      held.current = new Set();
      lastT.current = 0;
      setRecording(true);
    };
    const stopRec = () => {
      // close any key still held so the macro never leaves a key stuck down
      let evs = (store.draft ? store.draft.events : []).slice();
      held.current.forEach(hid => {
        if (evs.length < s.limits.maxEvents) evs.push({
          delay: 50,
          hid,
          down: false
        });
      });
      held.current = new Set();
      updateDraft({
        events: evs
      });
      setRecording(false);
    };
    const onRecKey = (e, down) => {
      // The native shell suppresses key events outside editable elements; the
      // recorder is a focused input so they reach us here, and we swallow them.
      e.preventDefault();
      e.stopPropagation();
      if (!recording) return;
      if (down && e.repeat) return; // OS auto-repeat
      if (e.code === "Escape" && !down && !held.current.has(0x29)) {
        stopRec();
        return;
      }
      const hid = CODE_TO_HID[e.code];
      if (hid == null) return;
      if (down && held.current.has(hid)) return;
      if (!down && !held.current.has(hid)) return;
      const now = performance.now();
      const delay = lastT.current ? Math.round(now - lastT.current) : 0;
      lastT.current = now;
      if (down) held.current.add(hid);else held.current.delete(hid);
      const cur = store.draft ? store.draft.events : [];
      if (cur.length >= s.limits.maxEvents) {
        setStatus("warn", `Slot full (${s.limits.maxEvents} events) — recording stopped`);
        stopRec();
        return;
      }
      updateDraft({
        events: cur.concat([{
          delay,
          hid,
          down
        }])
      });
    };
    const setEv = (i, patch) => updateDraft({
      events: events.map((e, j) => j === i ? Object.assign({}, e, patch) : e)
    });
    const delEv = i => updateDraft({
      events: events.filter((_, j) => j !== i)
    });
    const moveEv = (i, dir) => {
      const j = i + dir;
      if (j < 0 || j >= events.length) return;
      const n = events.slice();
      const t = n[i];
      n[i] = n[j];
      n[j] = t;
      updateDraft({
        events: n
      });
    };
    const unbalanced = useMemo(() => {
      const open = new Set();
      for (const e of events) {
        if (e.down) open.add(e.hid);else open.delete(e.hid);
      }
      return Array.from(open);
    }, [events]);
    const save = async () => {
      if (!d) return;
      if (!events.length) {
        setStatus("warn", "Add at least one step");
        return;
      }
      if (recording) stopRec();
      store.busy = true;
      emit();
      const r = await apiCall("save_macro", d.slot, d.name, events, d.playMode, d.playMode === 1 ? d.repeat : 1);
      store.busy = false;
      if (r && r.ok) {
        setStatus("ok", `Saved ${r.events} events to slot ${d.slot + 1}`);
        store.dirty = false;
        await refresh(apiCall, true);
        selectSlot(d.slot);
      } else setStatus("bad", r && r.error || "save failed");
    };
    if (!d) {
      return /*#__PURE__*/React.createElement(Gate, null, /*#__PURE__*/React.createElement("div", {
        className: "flex flex-col gap-3"
      }, /*#__PURE__*/React.createElement("ol", {
        className: "text-[12px] text-[var(--text-dim)] leading-relaxed space-y-2 font-mono"
      }, /*#__PURE__*/React.createElement("li", null, /*#__PURE__*/React.createElement("span", {
        className: "text-[var(--accent)]"
      }, "01."), " Pick a slot in the Macro Library (M1\u2013M10)."), /*#__PURE__*/React.createElement("li", null, /*#__PURE__*/React.createElement("span", {
        className: "text-[var(--accent)]"
      }, "02."), " Record keystrokes or add steps by hand; tune the delays."), /*#__PURE__*/React.createElement("li", null, /*#__PURE__*/React.createElement("span", {
        className: "text-[var(--accent)]"
      }, "03."), " ", /*#__PURE__*/React.createElement("span", {
        className: "text-[var(--text)]"
      }, "Save to board"), ", then bind it to a key in the Bind widget.")), /*#__PURE__*/React.createElement(Note, null, "Delays are the wait ", /*#__PURE__*/React.createElement("span", {
        className: "text-[var(--text)]"
      }, "before"), " each step, in milliseconds \u2014 the same convention as the vendor's recorder. The board stores up to ", s.limits.maxEvents, " steps per slot (a press and a release are two steps)."), /*#__PURE__*/React.createElement(StatusLine, null)));
    }
    return /*#__PURE__*/React.createElement(Gate, null, /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-3 h-full min-h-0"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-end gap-2"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex-1"
    }, /*#__PURE__*/React.createElement(Label, null, "Slot M", d.slot + 1, " \xB7 name (kept in Aether, the board stores only the steps)"), /*#__PURE__*/React.createElement("input", {
      className: "input",
      value: d.name,
      maxLength: 32,
      placeholder: `Macro ${d.slot + 1}`,
      onChange: e => updateDraft({
        name: e.target.value
      })
    }))), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 flex-wrap"
    }, !recording ? /*#__PURE__*/React.createElement(Btn, {
      onClick: startRec,
      disabled: full,
      variant: "primary",
      small: true
    }, "\u25CF Record") : /*#__PURE__*/React.createElement(Btn, {
      onClick: stopRec,
      variant: "rec",
      small: true
    }, "\u25A0 Stop (Esc)"), /*#__PURE__*/React.createElement("input", {
      ref: recRef,
      readOnly: true,
      value: recording ? "recording… type here" : "",
      placeholder: "click Record, then type",
      onKeyDown: e => onRecKey(e, true),
      onKeyUp: e => onRecKey(e, false),
      onBlur: () => {
        if (recording) stopRec();
      },
      className: `input flex-1 min-w-[140px] h-8 py-0 font-mono text-[11px] ${recording ? "border-rose-400/60 text-rose-200" : ""}`
    })), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 flex-wrap"
    }, /*#__PURE__*/React.createElement("select", {
      value: pickKey,
      onChange: e => setPickKey(+e.target.value),
      className: "input w-auto h-8 py-0 font-mono text-[11px]"
    }, HID_KEYS.map(([l, c]) => /*#__PURE__*/React.createElement("option", {
      key: c,
      value: c
    }, l))), /*#__PURE__*/React.createElement(Btn, {
      onClick: () => push(pickKey, true, 50),
      disabled: full,
      small: true
    }, "+ Down"), /*#__PURE__*/React.createElement(Btn, {
      onClick: () => push(pickKey, false, 50),
      disabled: full,
      small: true
    }, "+ Up"), /*#__PURE__*/React.createElement(Btn, {
      onClick: () => {
        push(pickKey, true, 50);
        setTimeout(() => push(pickKey, false, 50), 0);
      },
      disabled: full || events.length + 2 > s.limits.maxEvents,
      small: true
    }, "+ Tap"), /*#__PURE__*/React.createElement(Btn, {
      onClick: () => updateDraft({
        events: []
      }),
      disabled: !events.length,
      small: true
    }, "Clear")), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 min-h-[90px] overflow-y-auto rounded-md border border-[var(--line)] bg-[rgba(5,11,14,0.5)]"
    }, events.length === 0 ? /*#__PURE__*/React.createElement("div", {
      className: "p-3 font-mono text-[11px] text-[var(--text-faint)]"
    }, "No steps yet.") : events.map((e, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "flex items-center gap-2 px-2 h-8 border-b border-[var(--line)]/60 last:border-b-0"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9px] w-5 text-[var(--text-faint)]"
    }, i + 1), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] w-7 text-[var(--text-faint)]"
    }, "wait"), /*#__PURE__*/React.createElement("input", {
      type: "number",
      min: 0,
      max: s.limits.maxDelay,
      value: e.delay,
      onChange: ev => setEv(i, {
        delay: Math.max(0, Math.min(s.limits.maxDelay, +ev.target.value || 0))
      }),
      className: "input w-[72px] h-6 py-0 px-1.5 font-mono text-[11px] text-right"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9px] text-[var(--text-faint)]"
    }, "ms"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setEv(i, {
        down: !e.down
      }),
      title: "Toggle press / release",
      className: `w-8 h-6 rounded border font-mono text-[10px] ${e.down ? "border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)]" : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)]"}`
    }, e.down ? "▼" : "▲"), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[12px] text-[var(--text)] flex-1 truncate"
    }, hidLabel(e.hid)), /*#__PURE__*/React.createElement("button", {
      onClick: () => moveEv(i, -1),
      disabled: i === 0,
      className: "text-[var(--text-faint)] hover:text-[var(--text)] disabled:opacity-30 px-1"
    }, "\u2191"), /*#__PURE__*/React.createElement("button", {
      onClick: () => moveEv(i, 1),
      disabled: i === events.length - 1,
      className: "text-[var(--text-faint)] hover:text-[var(--text)] disabled:opacity-30 px-1"
    }, "\u2193"), /*#__PURE__*/React.createElement("button", {
      onClick: () => delEv(i),
      className: "text-[var(--text-faint)] hover:text-rose-300 px-1"
    }, "\u2715")))), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-3 font-mono text-[10px] text-[var(--text-faint)]"
    }, /*#__PURE__*/React.createElement("span", null, events.length, "/", s.limits.maxEvents, " steps"), unbalanced.length > 0 && /*#__PURE__*/React.createElement("span", {
      className: "text-amber-300/90"
    }, "held at end: ", unbalanced.map(hidLabel).join(", ")), s.dirty && /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "unsaved")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Label, null, "Playback (stored in the slot header)"), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-1.5 flex-wrap"
    }, PLAY_MODES.map(p => /*#__PURE__*/React.createElement("button", {
      key: p.v,
      onClick: () => updateDraft({
        playMode: p.v
      }),
      title: p.hint,
      className: `px-2.5 h-8 rounded-md border font-display text-[10.5px] uppercase tracking-[0.14em] transition-all
                            ${d.playMode === p.v ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 text-[var(--accent)]" : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:text-[var(--text)]"}
                            ${p.verified ? "" : "opacity-70"}`
    }, p.label, p.verified ? "" : " ?")), d.playMode === 1 && /*#__PURE__*/React.createElement("input", {
      type: "number",
      min: 1,
      max: s.limits.maxRepeat,
      value: d.repeat,
      onChange: e => updateDraft({
        repeat: Math.max(1, Math.min(s.limits.maxRepeat, +e.target.value || 1))
      }),
      className: "input w-[72px] h-8 py-0 px-2 font-mono text-[11px] text-right",
      title: "Repeat count"
    })), d.playMode >= 2 && /*#__PURE__*/React.createElement("div", {
      className: "mt-1"
    }, /*#__PURE__*/React.createElement(Note, {
      tone: "warn"
    }, "Toggle / Hold come from the vendor UI's option list and were never captured on the wire \u2014 the board may ignore them."))), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2"
    }, /*#__PURE__*/React.createElement(Btn, {
      onClick: save,
      disabled: !connected || s.busy || !events.length,
      variant: "primary"
    }, "Save to board"), /*#__PURE__*/React.createElement(Btn, {
      onClick: () => selectSlot(d.slot),
      disabled: !s.dirty,
      small: true
    }, "Revert"), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 min-w-0"
    }, /*#__PURE__*/React.createElement(StatusLine, null)))));
  }

  /* ============================================================
     Widget: Bind — point the selected key at the selected slot
     ============================================================ */
  function BindWidget(ctx) {
    const s = useStore();
    const {
      apiCall,
      connected,
      selectedKeys,
      selectedKey
    } = ctx;
    const codes = selectedKeys ? Array.from(selectedKeys) : [];
    const m = s.sel != null ? macroAt(s.sel) : null;
    const canBind = connected && !s.busy && codes.length > 0 && s.sel != null && !!m;
    const boundCodes = Object.keys(s.bindings);
    const bind = async () => {
      if (!canBind) return;
      store.busy = true;
      emit();
      let ok = 0,
        err = null;
      for (const code of codes) {
        const r = await apiCall("bind_macro", code, s.sel);
        if (r && r.ok) ok++;else {
          err = r && r.error || "bind failed";
          break;
        }
      }
      store.busy = false;
      if (err) setStatus("bad", err);else setStatus("ok", `Bound ${codes.map(c => LABEL_OF_CODE[c] || c).join(", ")} → M${s.sel + 1}`);
      await refresh(apiCall, true);
    };
    const unbind = async list => {
      if (!connected || !list.length) return;
      store.busy = true;
      emit();
      let err = null;
      for (const code of list) {
        const r = await apiCall("unbind_macro", code);
        if (!(r && r.ok)) {
          err = r && r.error || "unbind failed";
          break;
        }
      }
      store.busy = false;
      if (err) setStatus("bad", err);else setStatus("ok", `Restored ${list.map(c => LABEL_OF_CODE[c] || c).join(", ")}`);
      await refresh(apiCall, true);
    };
    return /*#__PURE__*/React.createElement(Gate, null, /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-3 h-full min-h-0"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-stretch gap-2"
    }, /*#__PURE__*/React.createElement("div", {
      className: "grid place-items-center px-3 min-w-[64px] rounded-md border border-[var(--line)] bg-white/[0.02] font-mono text-[11px] text-[var(--text-dim)]"
    }, codes.length > 1 ? `${codes.length} keys` : selectedKey ? LABEL_OF_CODE[selectedKey] || selectedKey : "None"), /*#__PURE__*/React.createElement("div", {
      className: "grid place-items-center text-[var(--text-faint)]"
    }, "\u2192"), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 rounded-md border border-[var(--line)] bg-white/[0.02] px-3 grid place-items-start py-1.5"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[12px] text-[var(--text)] truncate w-full"
    }, s.sel == null ? "—" : `M${s.sel + 1}${m ? ` · ${m.name || `Macro ${s.sel + 1}`}` : " · empty"}`), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
    }, "macro slot"))), /*#__PURE__*/React.createElement("div", {
      className: "flex gap-2"
    }, /*#__PURE__*/React.createElement(Btn, {
      onClick: () => unbind(codes.filter(c => c in s.bindings)),
      disabled: !connected || s.busy || !codes.some(c => c in s.bindings)
    }, "Unbind"), /*#__PURE__*/React.createElement(Btn, {
      onClick: bind,
      disabled: !canBind,
      variant: "primary"
    }, "Bind")), /*#__PURE__*/React.createElement("div", {
      className: "h-4 text-[11px] font-mono tracking-[0.14em]"
    }, !codes.length && /*#__PURE__*/React.createElement("span", {
      className: "text-amber-400/80"
    }, "Select a key on the Key Grid first."), codes.length > 0 && s.sel != null && !m && /*#__PURE__*/React.createElement("span", {
      className: "text-amber-400/80"
    }, "Slot M", s.sel + 1, " is empty \u2014 save a macro into it first."), codes.length > 0 && s.sel == null && /*#__PURE__*/React.createElement("span", {
      className: "text-amber-400/80"
    }, "Pick a macro in the Library.")), /*#__PURE__*/React.createElement(Note, null, "Binding rewrites the base keymap layer as a read-modify-write, so remaps and other bindings on the board are kept. The playback mode lives in the macro slot, so every key bound to a slot shares it."), /*#__PURE__*/React.createElement("div", {
      className: "flex-1 min-h-0 overflow-y-auto"
    }, /*#__PURE__*/React.createElement(Label, null, "Bound keys", s.bindingsError ? " · read failed" : ""), s.bindingsError && /*#__PURE__*/React.createElement(Note, {
      tone: "bad"
    }, s.bindingsError), !s.bindingsError && boundCodes.length === 0 && /*#__PURE__*/React.createElement(Note, null, "No key on the board points at a macro."), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-col gap-1"
    }, boundCodes.map(c => {
      const slot = s.bindings[c];
      const mm = macroAt(slot);
      return /*#__PURE__*/React.createElement("div", {
        key: c,
        className: "flex items-center gap-2 px-2 h-8 rounded-md border border-[var(--line)] bg-white/[0.02]"
      }, /*#__PURE__*/React.createElement("span", {
        className: "font-mono text-[12px] text-[var(--text)] w-14 truncate"
      }, LABEL_OF_CODE[c] || c), /*#__PURE__*/React.createElement("span", {
        className: "text-[var(--text-faint)]"
      }, "\u2192"), /*#__PURE__*/React.createElement("span", {
        className: "font-mono text-[11px] text-[var(--accent)] flex-1 truncate"
      }, "M", slot + 1, mm ? ` · ${mm.name || `Macro ${slot + 1}`}` : " · (empty slot)"), /*#__PURE__*/React.createElement("button", {
        onClick: () => unbind([c]),
        disabled: !connected || s.busy,
        className: "text-[var(--text-faint)] hover:text-rose-300 px-1 text-[11px]"
      }, "\u2715"));
    }))), /*#__PURE__*/React.createElement(StatusLine, null)));
  }
  const MACROS_WIDGETS = [{
    id: "keygrid",
    title: "Key Grid",
    default: {
      x: 40,
      y: 32,
      w: 760,
      h: 400
    },
    min: {
      w: 520,
      h: 320
    },
    render: KeyGridWidget
  }, {
    id: "library",
    title: "Macro Library",
    default: {
      x: 820,
      y: 32,
      w: 420,
      h: 400
    },
    min: {
      w: 300,
      h: 260
    },
    render: LibraryWidget
  }, {
    id: "editor",
    title: "Macro Editor",
    default: {
      x: 40,
      y: 456,
      w: 760,
      h: 520
    },
    min: {
      w: 520,
      h: 420
    },
    render: EditorWidget
  }, {
    id: "bind",
    title: "Bind to Key",
    default: {
      x: 820,
      y: 456,
      w: 420,
      h: 520
    },
    min: {
      w: 300,
      h: 340
    },
    render: BindWidget
  }];
  window.AetherWorkspaces = window.AetherWorkspaces || {};
  window.AetherWorkspaces.MACROS_WIDGETS = MACROS_WIDGETS;
})();