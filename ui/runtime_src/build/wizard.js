(() => {
  /* ============================================================
     SetupWizard — first-run guided setup for AetherHE.
     Exposes window.AetherWizard = { SetupWizard }.
     Plain JSX, global React (no libs). Glass panels + Impact (.font-title)
     titles, matching desktop.jsx / sections.jsx styling. UI ONLY — reads/calls
     ctx.* and window.pywebview.api.* exactly like the existing sections.
  
     4 steps:
       1) Board selection   (drivable registry boards only — decoded protocol)
       2) Board layout preview (reuses window.AetherKeyboard.KeyboardPanel, read-only)
       3) Animation how-to  (points at the Lighting workspace)
       4) JSON import       (returning users: file -> parse -> ctx.applyState)
  
     Persistence:
       - board choice -> localStorage "aether-board"
       - done flag    -> localStorage "aether-setup-done" = "1"
         (coordinator can key first-run detection off the missing flag /
          missing settings file, and re-open via ctx.setWizardOpen(true).)
     ============================================================ */
  const {
    useState,
    useEffect,
    useMemo,
    useRef
  } = React;
  const BOARD_ISSUE_URL = "https://github.com/MrWhosNexus/Aether-HE/issues/new?template=add-a-board.yml";
  const LS_BOARD = "aether-board";
  const LS_DONE = "aether-setup-done";

  /* Static fallback list — mirrors the data/board_registry.json entries the
     registry marks OFFERED (`offerInUi`), used only when the live roster isn't up
     yet (no bridge, plain-browser preview). Keep it in step with the registry:
     the live roster is authoritative, this is just what shows before it loads.
  
     Offered is stricter than drivable. Boards deliberately NOT offered, each for
     a stated reason in the registry's `_offerNote`:
       aula-kp-te153     — decoded by family, never run on a physical KP-TE153
       aula-win60he-pro  — SayoDevice; captures decode, but nobody owns the board
       aula-mini60he-max — decoded from a contributor capture, never hardware-run
     They stay in the registry so a plugged-in board is still detected, named and
     drawn with an honest explanation — they are simply never pickable here. */
  const BOARDS = [{
    slug: "aula-win60-he",
    name: "Aula Win60 HE",
    form: "60%",
    status: "supported"
  }, {
    slug: "aula-win68-he",
    name: "Aula WIN 68 HE",
    form: "65%",
    status: "bringup"
  }, {
    slug: "aula-mini60he-pro",
    name: "Aula Mini 60 HE Pro (wired)",
    form: "60%",
    status: "supported"
  }, {
    slug: "aula-mini60he-pro-24g",
    name: "Aula Mini 60 HE Pro (2.4GHz)",
    form: "60%",
    status: "supported"
  }];
  const STATUS_LABEL = {
    supported: "Supported",
    bringup: "Bring-up"
  };

  /* The boards the wizard offers = registry entries the registry says may be
     OFFERED (`offered`, resolved from `offerInUi`), which is a stricter thing
     than `drivable`. A board can have a fully decoded protocol and still not
     belong in a picker — e.g. decoded from a contributor's capture but never
     run on physical hardware by anyone. Reading `offered` keeps that judgement
     in the registry as data instead of re-deriving it at each UI site, where
     the two inevitably drift.
  
     `offered` is undefined on older payloads, so fall back to `drivable` — that
     preserves today's behaviour for any board that declares nothing.
  
     Prefers the LIVE roster the app already fetched over the bridge
     (ctx.board.roster mirrors list_boards() — see board-context.jsx), so the
     wizard tracks the registry with no rebuild; falls back to the static mirror
     above. Filter is NOT on `connected`: an offered board appears whether or not
     it is plugged in right now. */
  const drivableBoards = ctx => {
    const roster = ctx && ctx.board && Array.isArray(ctx.board.roster) ? ctx.board.roster : [];
    const live = roster.filter(b => b && (b.offered !== undefined ? b.offered : b.drivable));
    if (live.length) {
      return live.map(b => ({
        slug: b.slug,
        name: b.name,
        form: b.formFactor || "",
        status: b.status || "bringup"
      }));
    }
    return BOARDS;
  };

  /* Recognised-but-not-drivable boards that are attached RIGHT NOW (identity-only
     registry entries — e.g. the 2.4GHz dongles). Not pickable, but if one is
     plugged in the wizard says so honestly instead of silently hiding it. */
  const recognisedUndrivable = ctx => {
    const roster = ctx && ctx.board && Array.isArray(ctx.board.roster) ? ctx.board.roster : [];
    return roster.filter(b => b && b.connected && !b.drivable);
  };
  const STEPS = ["Board", "Layout", "Animations", "Import"];

  /* ---- persistence helpers ---- */
  const loadBoard = () => {
    try {
      return localStorage.getItem(LS_BOARD) || "aula-win60-he";
    } catch {
      return "aula-win60-he";
    }
  };
  const saveBoard = slug => {
    try {
      localStorage.setItem(LS_BOARD, slug);
    } catch {}
  };
  const markDone = () => {
    try {
      localStorage.setItem(LS_DONE, "1");
    } catch {}
  };

  /* ============================================================
     Step 1 — Board selection.
     ============================================================ */
  function StepBoard({
    board,
    setBoard,
    ctx,
    onClose
  }) {
    const boards = drivableBoards(ctx);
    const detected = recognisedUndrivable(ctx);
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", {
      className: "font-title",
      style: {
        fontSize: 28,
        letterSpacing: "0.04em",
        marginBottom: 6
      }
    }, "SELECT YOUR BOARD"), /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 12.5,
        opacity: 0.7,
        marginBottom: 16
      }
    }, "Every board listed here has a decoded protocol \u2014 Aether can drive it today. More are being brought up. Don't see yours?", " ", /*#__PURE__*/React.createElement("a", {
      href: BOARD_ISSUE_URL,
      target: "_blank",
      rel: "noopener noreferrer",
      style: {
        color: "var(--accent)",
        textDecoration: "underline"
      }
    }, "Submit your board"), "."), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 10
      }
    }, boards.map(b => {
      const on = board === b.slug;
      return /*#__PURE__*/React.createElement("button", {
        key: b.slug,
        onClick: () => setBoard(b.slug),
        className: "glass",
        style: {
          textAlign: "left",
          padding: "12px 14px",
          borderRadius: 10,
          cursor: "pointer",
          outline: on ? "2px solid var(--accent)" : "1px solid var(--line)",
          boxShadow: on ? "0 0 18px var(--accent-glow)" : "none",
          transition: "all 150ms"
        }
      }, /*#__PURE__*/React.createElement("div", {
        className: "font-title",
        style: {
          fontSize: 15,
          letterSpacing: "0.02em"
        }
      }, b.name), /*#__PURE__*/React.createElement("div", {
        style: {
          fontSize: 11,
          opacity: 0.65,
          marginTop: 4,
          display: "flex",
          gap: 8,
          alignItems: "center"
        }
      }, /*#__PURE__*/React.createElement("span", null, b.form), /*#__PURE__*/React.createElement("span", {
        style: {
          padding: "1px 7px",
          borderRadius: 999,
          fontSize: 9.5,
          textTransform: "uppercase",
          letterSpacing: "0.12em",
          color: b.status === "supported" ? "var(--accent)" : "var(--text-dim)",
          border: "1px solid var(--line)"
        }
      }, STATUS_LABEL[b.status] || b.status)));
    })), detected.length > 0 && /*#__PURE__*/React.createElement("div", {
      className: "glass",
      style: {
        marginTop: 12,
        padding: "10px 14px",
        borderRadius: 10,
        fontSize: 12,
        opacity: 0.8,
        lineHeight: 1.5
      }
    }, detected.map(b => /*#__PURE__*/React.createElement("div", {
      key: b.slug
    }, "Detected ", /*#__PURE__*/React.createElement("strong", null, b.name), " (", b.vidPid, ") \u2014 Aether recognises it, but its protocol hasn't been decoded yet, so it can't be set up here."))), /*#__PURE__*/React.createElement("button", {
      className: "btn",
      onClick: () => {
        onClose();
        ctx && ctx.setSubmitOpen && ctx.setSubmitOpen(true);
      },
      style: {
        marginTop: 14
      }
    }, "My board isn\u2019t listed \u2192 Submit it"));
  }

  /* ============================================================
     Step 2 — Board layout preview (reuse KeyboardPanel, read-only).
     ============================================================ */
  function StepLayout({
    board,
    ctx
  }) {
    const KB = window.AetherKeyboard || {};
    const KeyboardPanel = KB.KeyboardPanel;
    const boards = drivableBoards(ctx);
    const info = boards.find(b => b.slug === board) || boards[0];
    // Read-only preview: a frozen empty selection + no-op setter so nothing is
    // editable and no device is needed. Only the Win60 HE layout is bundled in
    // keyboard.jsx today; other boards show the layout note instead.
    const emptySel = useMemo(() => new Set(), []);
    const noop = useRef(() => {}).current;
    const canRender = board === "aula-win60-he" && typeof KeyboardPanel === "function";
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", {
      className: "font-title",
      style: {
        fontSize: 28,
        letterSpacing: "0.04em",
        marginBottom: 6
      }
    }, info.name.toUpperCase(), " \xB7 LAYOUT"), /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 12.5,
        opacity: 0.7,
        marginBottom: 16
      }
    }, "This is your board's key layout. Later you'll click keys here to scope actuation, remaps and lighting \u2014 no device needed to look around."), canRender ? /*#__PURE__*/React.createElement("div", {
      style: {
        pointerEvents: "none"
      }
    }, React.createElement(KeyboardPanel, {
      mode: "keymap",
      layer: "default",
      selectedKeys: emptySel,
      setSelectedKeys: noop,
      actuationPoint: 1.70,
      rtPress: 0.05,
      rtRelease: 0.05,
      showPill: false,
      compact: true
    })) : /*#__PURE__*/React.createElement("div", {
      className: "glass",
      style: {
        padding: 20,
        borderRadius: 10,
        textAlign: "center"
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "font-title",
      style: {
        fontSize: 16
      }
    }, "Layout preview coming soon"), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        opacity: 0.65,
        marginTop: 6
      }
    }, "The interactive layout for ", info.name, " lands when its bring-up completes.")));
  }

  /* ============================================================
     Step 3 — Animation how-to (static instructional content + small preview).
     ============================================================ */
  function StepAnimations({
    ctx
  }) {
    const goLighting = () => {
      if (ctx && typeof ctx.setSection === "function") ctx.setSection("lighting");
    };
    const steps = [["Open Lighting", "Jump to the Lighting workspace from the top bar."], ["Pick a pattern", "Choose an effect (Wave, Ripple, Aurora, Rain…) and set its colors."], ["Tune it", "Adjust brightness, speed and direction — changes stream live to the board."], ["Scope per-key", "Select keys on the board to paint per-key colors on top of the effect."]];
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", {
      className: "font-title",
      style: {
        fontSize: 28,
        letterSpacing: "0.04em",
        marginBottom: 6
      }
    }, "SET UP LIGHTING"), /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 12.5,
        opacity: 0.7,
        marginBottom: 16
      }
    }, "Aether streams multi-color animations from the host in real time. Here's the short version \u2014 the full controls live in the Lighting workspace."), /*#__PURE__*/React.createElement("div", {
      className: "glass",
      style: {
        padding: 12,
        borderRadius: 10,
        marginBottom: 16,
        overflow: "hidden"
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 4
      }
    }, Array.from({
      length: 14
    }).map((_, i) => /*#__PURE__*/React.createElement("span", {
      key: i,
      style: {
        flex: 1,
        height: 22,
        borderRadius: 4,
        background: `hsl(${i * 26 % 360} 85% 55%)`,
        animation: "aetherWizPulse 1.6s ease-in-out infinite",
        animationDelay: `${i * 0.08}s`
      }
    }))), /*#__PURE__*/React.createElement("style", null, `@keyframes aetherWizPulse{0%,100%{opacity:.35}50%{opacity:1}}`)), /*#__PURE__*/React.createElement("ol", {
      style: {
        display: "grid",
        gap: 10,
        margin: 0,
        padding: 0,
        listStyle: "none"
      }
    }, steps.map(([t, d], i) => /*#__PURE__*/React.createElement("li", {
      key: i,
      style: {
        display: "flex",
        gap: 12,
        alignItems: "flex-start"
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-title",
      style: {
        width: 26,
        height: 26,
        borderRadius: 999,
        flexShrink: 0,
        display: "grid",
        placeItems: "center",
        fontSize: 13,
        border: "1px solid var(--accent)",
        color: "var(--accent)"
      }
    }, i + 1), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-title",
      style: {
        fontSize: 13.5,
        letterSpacing: "0.02em"
      }
    }, t), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12,
        opacity: 0.68,
        marginTop: 2
      }
    }, d))))), /*#__PURE__*/React.createElement("button", {
      onClick: goLighting,
      className: "glass font-title",
      style: {
        marginTop: 16,
        padding: "8px 16px",
        borderRadius: 8,
        cursor: "pointer",
        color: "var(--accent)",
        outline: "1px solid var(--accent)",
        fontSize: 12
      }
    }, "Open Lighting workspace"));
  }

  /* ============================================================
     Step 4 — JSON import (returning users).
     ============================================================ */
  function StepImport({
    ctx
  }) {
    const [status, setStatus] = useState({
      kind: "idle",
      msg: ""
    });
    const fileRef = useRef(null);
    const applyImported = parsed => {
      // Accept either a full settings blob {profiles:[...]} or a bare state object.
      let state = parsed;
      if (parsed && Array.isArray(parsed.profiles) && parsed.profiles.length) {
        const aid = parsed.activeProfile;
        const active = parsed.profiles.find(p => p.id === aid) || parsed.profiles[0];
        state = active && active.state || {};
      }
      if (ctx && typeof ctx.applyState === "function") ctx.applyState(state);
      // Persist through the same bridge the app uses (best-effort; the app's
      // own save effect will also mirror the applied state after hydration).
      try {
        const api = window.pywebview && window.pywebview.api;
        if (api && api.save_settings && parsed && Array.isArray(parsed.profiles)) {
          Promise.resolve(api.save_settings(parsed)).catch(() => {});
        }
      } catch {}
    };
    const onFile = e => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const parsed = JSON.parse(String(reader.result));
          applyImported(parsed);
          setStatus({
            kind: "ok",
            msg: `Imported ${file.name} — settings applied.`
          });
        } catch (err) {
          setStatus({
            kind: "err",
            msg: "Couldn't parse that file — is it a valid Aether JSON?"
          });
        }
      };
      reader.onerror = () => setStatus({
        kind: "err",
        msg: "Couldn't read that file."
      });
      reader.readAsText(file);
    };
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", {
      className: "font-title",
      style: {
        fontSize: 28,
        letterSpacing: "0.04em",
        marginBottom: 6
      }
    }, "IMPORT SETTINGS"), /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 12.5,
        opacity: 0.7,
        marginBottom: 16
      }
    }, "Returning from another install? Import an exported Aether settings JSON to restore your profiles, lighting, actuation and SOCD in one shot. New here? Just skip this and hit Finish."), /*#__PURE__*/React.createElement("div", {
      className: "glass",
      style: {
        padding: 20,
        borderRadius: 10,
        textAlign: "center"
      }
    }, /*#__PURE__*/React.createElement("input", {
      ref: fileRef,
      type: "file",
      accept: "application/json,.json",
      onChange: onFile,
      style: {
        display: "none"
      }
    }), /*#__PURE__*/React.createElement("button", {
      onClick: () => fileRef.current && fileRef.current.click(),
      className: "font-title",
      style: {
        padding: "10px 20px",
        borderRadius: 8,
        cursor: "pointer",
        fontSize: 13,
        color: "var(--accent)",
        outline: "1px solid var(--accent)",
        background: "transparent"
      }
    }, "Choose settings JSON\u2026"), status.kind !== "idle" && /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 12,
        fontSize: 12,
        color: status.kind === "err" ? "#fca5a5" : "var(--accent)"
      }
    }, status.msg)));
  }

  /* ============================================================
     SetupWizard — modal overlay orchestrating the 4 steps.
     Props: { open, onClose, ctx }
     ============================================================ */
  function SetupWizard({
    open,
    onClose,
    ctx
  }) {
    const [step, setStep] = useState(0);
    const [board, setBoardState] = useState(loadBoard);

    // Reset to first step each time the wizard is (re)opened.
    useEffect(() => {
      if (open) setStep(0);
    }, [open]);

    // If the remembered board is no longer offered (e.g. an identity-only slug
    // left over from an older build), snap to the first drivable board.
    useEffect(() => {
      if (!open) return;
      const boards = drivableBoards(ctx);
      if (boards.length && !boards.some(b => b.slug === board)) {
        setBoardState(boards[0].slug);
        saveBoard(boards[0].slug);
      }
    }, [open]);
    const setBoard = slug => {
      setBoardState(slug);
      saveBoard(slug);
    };
    const finish = () => {
      saveBoard(board);
      markDone();
      // If the coordinator wired a board setter into ctx, tell it too.
      if (ctx && typeof ctx.setBoard === "function") ctx.setBoard(board);
      if (typeof onClose === "function") onClose();
    };
    const close = () => {
      if (typeof onClose === "function") onClose();
    };
    if (!open) return null;
    const last = step === STEPS.length - 1;
    const c = ctx || {};
    let body = null;
    if (step === 0) body = /*#__PURE__*/React.createElement(StepBoard, {
      board: board,
      setBoard: setBoard,
      ctx: c,
      onClose: close
    });else if (step === 1) body = /*#__PURE__*/React.createElement(StepLayout, {
      board: board,
      ctx: c
    });else if (step === 2) body = /*#__PURE__*/React.createElement(StepAnimations, {
      ctx: c
    });else body = /*#__PURE__*/React.createElement(StepImport, {
      ctx: c
    });
    return /*#__PURE__*/React.createElement("div", {
      role: "dialog",
      "aria-modal": "true",
      "aria-label": "Aether first-run setup",
      style: {
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(3,7,10,0.72)",
        backdropFilter: "blur(6px)",
        display: "grid",
        placeItems: "center",
        padding: 24
      },
      onClick: e => {
        if (e.target === e.currentTarget) close();
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "glass",
      style: {
        width: "min(1060px, 96vw)",
        maxHeight: "90vh",
        overflow: "auto",
        borderRadius: 16,
        padding: 28,
        position: "relative",
        border: "1px solid var(--line)"
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: close,
      title: "Close",
      "aria-label": "Close setup",
      style: {
        position: "absolute",
        top: 14,
        right: 16,
        background: "transparent",
        border: "none",
        color: "var(--text-dim)",
        fontSize: 20,
        cursor: "pointer",
        lineHeight: 1
      }
    }, "\xD7"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 8,
        marginBottom: 22
      }
    }, STEPS.map((label, i) => /*#__PURE__*/React.createElement("div", {
      key: label,
      style: {
        display: "flex",
        alignItems: "center",
        gap: 8
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-title",
      style: {
        fontSize: 10.5,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: i === step ? "var(--accent)" : "var(--text-faint)"
      }
    }, label), i < STEPS.length - 1 && /*#__PURE__*/React.createElement("span", {
      style: {
        width: 18,
        height: 1,
        background: "var(--line)"
      }
    })))), /*#__PURE__*/React.createElement("div", {
      style: {
        minHeight: 320
      }
    }, body), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginTop: 24,
        borderTop: "1px solid var(--line)",
        paddingTop: 18
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: close,
      className: "font-title",
      style: {
        background: "transparent",
        border: "none",
        color: "var(--text-dim)",
        fontSize: 11.5,
        letterSpacing: "0.1em",
        cursor: "pointer",
        textTransform: "uppercase"
      }
    }, "Skip setup"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: "flex",
        gap: 10
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setStep(s => Math.max(0, s - 1)),
      disabled: step === 0,
      className: "glass font-title",
      style: {
        padding: "8px 18px",
        borderRadius: 8,
        fontSize: 12,
        cursor: step === 0 ? "not-allowed" : "pointer",
        opacity: step === 0 ? 0.4 : 1
      }
    }, "Back"), last ? /*#__PURE__*/React.createElement("button", {
      onClick: finish,
      className: "font-title",
      style: {
        padding: "8px 22px",
        borderRadius: 8,
        fontSize: 12,
        cursor: "pointer",
        color: "var(--accent)",
        outline: "1px solid var(--accent)",
        background: "var(--accent-glow, transparent)"
      }
    }, "Finish") : /*#__PURE__*/React.createElement("button", {
      onClick: () => setStep(s => Math.min(STEPS.length - 1, s + 1)),
      className: "font-title",
      style: {
        padding: "8px 22px",
        borderRadius: 8,
        fontSize: 12,
        cursor: "pointer",
        color: "var(--accent)",
        outline: "1px solid var(--accent)",
        background: "transparent"
      }
    }, "Next")))));
  }
  window.AetherWizard = {
    SetupWizard
  };
})();