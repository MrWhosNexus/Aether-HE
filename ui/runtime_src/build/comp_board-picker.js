(() => {
  /* ============================================================
     BoardPicker — multi-board chooser (PER_BOARD_PARITY_PLAN.md step 4).
  
     Renders NOTHING unless two or more REGISTERED boards are physically
     connected right now, so single-board users keep exactly today's UI.
  
     Rules:
     - The active board is marked; drivable connected boards can be switched
       to via select_board(slug).
     - Non-drivable boards (protocol not decoded — e.g. the Mini 60 HE Pro
       2.4GHz dongle) are listed but NOT selectable as drive targets, with the
       reason spelled out instead of a mute grey-out.
  
     Exposes window.AetherBoardPicker = { BoardPicker }.
     ============================================================ */
  const {
    useState,
    useEffect,
    useRef
  } = React;
  const I = window.AetherIcons || {};
  const IChevronD = I.IChevronD,
    ICheck = I.ICheck;

  // Why a board can't be driven, in words. `status` comes from the registry.
  const undrivableReason = b => {
    const name = b && b.name || "this board";
    return `${name} can be identified but not driven — its protocol hasn't been ` + `decoded, so Aether has no verified frames to send it.`;
  };
  function BoardRow({
    b,
    switching,
    onSelect
  }) {
    const selectable = b.drivable && !b.active && !switching;
    const inner = /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
      className: "flex items-center gap-2 min-w-0"
    }, /*#__PURE__*/React.createElement("span", {
      className: `inline-block w-1.5 h-1.5 rounded-full shrink-0
                          ${b.active ? "bg-[var(--good)]" : b.drivable ? "bg-[var(--text-faint)]" : "bg-[var(--warn)]"}`
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[13px] text-[var(--text)] truncate"
    }, b.name)), /*#__PURE__*/React.createElement("span", {
      className: "flex items-center gap-2 ml-auto shrink-0"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9px] uppercase tracking-[0.14em] text-[var(--text-faint)]"
    }, b.vidPid), b.active && /*#__PURE__*/React.createElement("span", {
      className: "flex items-center gap-1 font-mono text-[9px] uppercase tracking-[0.16em] text-[var(--good)]"
    }, ICheck && /*#__PURE__*/React.createElement(ICheck, {
      size: 10
    }), "Active"), !b.active && b.drivable && /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9px] uppercase tracking-[0.16em] text-[var(--accent)]"
    }, switching ? "…" : "Switch"), !b.drivable && /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9px] uppercase tracking-[0.16em] text-[var(--warn)]"
    }, "Not drivable")));
    if (selectable) {
      return /*#__PURE__*/React.createElement("button", {
        onClick: () => onSelect(b.slug),
        className: "w-full flex items-center gap-2 px-2.5 h-9 rounded-lg text-left transition-colors hover:bg-white/[0.04]"
      }, inner);
    }
    return /*#__PURE__*/React.createElement("div", {
      className: "w-full"
    }, /*#__PURE__*/React.createElement("div", {
      className: `w-full flex items-center gap-2 px-2.5 h-9 rounded-lg
                       ${b.active ? "bg-[var(--accent)]/10" : ""}`
    }, inner), !b.drivable && /*#__PURE__*/React.createElement("div", {
      className: "px-2.5 pb-2 -mt-0.5 text-[10.5px] leading-relaxed text-[var(--text-dim)]"
    }, undrivableReason(b)));
  }
  function BoardPicker({
    roster,
    active,
    switching,
    onSelect
  }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    useEffect(() => {
      const h = e => {
        if (ref.current && !ref.current.contains(e.target)) setOpen(false);
      };
      document.addEventListener("mousedown", h);
      return () => document.removeEventListener("mousedown", h);
    }, []);
    const connected = (roster || []).filter(b => b.connected);
    // Single-board (or no-data) machines: stay invisible — today's UI, untouched.
    if (connected.length < 2) return null;
    const current = active || connected.find(b => b.active) || null;
    const label = current ? current.name : "Select board";
    const doSelect = slug => {
      setOpen(false);
      onSelect && onSelect(slug);
    };
    return /*#__PURE__*/React.createElement("div", {
      ref: ref,
      className: "fixed z-[60]",
      style: {
        top: 62,
        right: 20
      }
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setOpen(o => !o),
      disabled: !!switching,
      title: "Multiple boards are connected \u2014 choose which one Aether drives",
      className: "flex items-center gap-2 h-[34px] pl-3 pr-2.5 rounded-[11px] border border-[var(--line)] bg-[color-mix(in_srgb,var(--ink)_70%,transparent)] backdrop-blur-xl text-[var(--text)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] transition-colors disabled:opacity-60"
    }, /*#__PURE__*/React.createElement("span", {
      className: "w-1.5 h-1.5 rounded-full shrink-0",
      style: {
        background: "var(--good)",
        boxShadow: "0 0 8px var(--good)"
      }
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-title text-[13px] tracking-[0.04em] uppercase"
    }, switching ? "Switching…" : label), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[9.5px] uppercase tracking-[0.2em] text-[var(--text-faint)]"
    }, connected.length, " boards"), IChevronD && /*#__PURE__*/React.createElement(IChevronD, {
      size: 12,
      className: `text-[var(--text-faint)] transition-transform ${open ? "rotate-180" : ""}`
    })), open && /*#__PURE__*/React.createElement("div", {
      className: "absolute top-full right-0 mt-1.5 w-[340px] p-1.5 menu-pop z-[61] animate-[fadeIn_140ms_ease-out]"
    }, /*#__PURE__*/React.createElement("div", {
      className: "px-2.5 pt-1.5 pb-2 font-mono text-[9px] uppercase tracking-[0.22em] text-[var(--text-faint)]"
    }, "Connected boards"), connected.map(b => /*#__PURE__*/React.createElement(BoardRow, {
      key: b.slug,
      b: b,
      switching: !!switching,
      onSelect: doSelect
    })), /*#__PURE__*/React.createElement("div", {
      className: "h-px bg-[var(--line)] my-1"
    }), /*#__PURE__*/React.createElement("div", {
      className: "px-2.5 py-1.5 text-[10px] leading-relaxed text-[var(--text-faint)]"
    }, "Switching disconnects the current board and rebinds Aether to the one you choose.")));
  }
  window.AetherBoardPicker = {
    BoardPicker
  };
})();