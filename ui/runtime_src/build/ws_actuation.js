(() => {
  /* ============================================================
     Actuation workspace — the REFERENCE workspace for the desktop-widget shell.
     Exports window.AetherWorkspaces.ACTUATION_WIDGETS — an array of widget descriptors:
       { id, title, default:{x,y,w,h}, min:{w,h}, render:(ctx)=>JSX }
     Each render() reads/calls ONLY ctx.* (state + handlers app.jsx passes down).
     Control JSX + telemetry (SwitchRender depth math, live depth) reused verbatim
     from the old ActuationSection via window.AetherSections shared primitives.
     ============================================================ */
  const {
    useState
  } = React;
  const S = window.AetherSections || {};
  const Slider = S.Slider,
    Chip = S.Chip,
    SwitchRender = S.SwitchRender;
  const I = window.AetherIcons || {};
  const ICheck = I.ICheck,
    ICrosshair = I.ICrosshair;

  /* Shared apply-button class + confirm toast (from ActuationSection). */
  const applyBtnCls = enabled => `px-4 h-9 rounded-md border font-display text-[12px] uppercase tracking-[0.16em] transition-all ${enabled ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_18px_var(--accent-glow)] hover:brightness-110" : "border-[var(--line)] bg-white/[0.02] text-[var(--text-faint)] cursor-not-allowed"}`;
  const useFlash = () => {
    const [confirm, setConfirm] = useState(null);
    const flash = msg => {
      setConfirm(msg);
      setTimeout(() => setConfirm(null), 2400);
    };
    return [confirm, flash];
  };
  const ConfirmToast = ({
    confirm
  }) => confirm ? /*#__PURE__*/React.createElement("span", {
    className: "font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--accent)]"
  }, "\u2713 ", confirm) : null;

  /* ===== Travel widget (actuation point + rapid trigger + live switch render) ===== */
  function TravelWidget(ctx) {
    const {
      actuation,
      setActuation,
      rtPress,
      setRtPress,
      rtRelease,
      setRtRelease,
      rtEnabled,
      setRtEnabled,
      travelTest,
      setTravelTest,
      liveMax = 0,
      selectedKeys,
      applyActuation
    } = ctx;
    const selectedCount = selectedKeys ? selectedKeys.size : 0;
    const scope = selectedCount > 0 ? `${selectedCount} selected key${selectedCount > 1 ? "s" : ""}` : "no keys (select some)";
    const canApply = selectedCount > 0;
    const [confirm, flash] = useFlash();
    const handleApplyTravel = () => {
      if (!canApply || !applyActuation) return;
      applyActuation();
      const rt = rtEnabled ? ` · RT press ${rtPress.toFixed(2)}mm / release ${rtRelease.toFixed(2)}mm` : "";
      flash(`Wrote ${actuation.toFixed(2)}mm to ${selectedCount} key${selectedCount === 1 ? "" : "s"}${rt}`);
    };
    return /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-5"
    }, /*#__PURE__*/React.createElement("div", {
      className: "glass p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center justify-between mb-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]"
    }, "Travel Test"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setTravelTest(!travelTest),
      className: `relative w-10 h-5 rounded-full border transition-colors
                        ${travelTest ? "bg-[var(--accent)]/30 border-[var(--accent)]/60" : "bg-white/[0.04] border-[var(--line)]"}`
    }, /*#__PURE__*/React.createElement("span", {
      className: `absolute top-0.5 w-3.5 h-3.5 rounded-full transition-all
                              ${travelTest ? "left-[20px] bg-[var(--accent)] shadow-[0_0_10px_var(--accent-glow)]" : "left-0.5 bg-slate-400"}`
    }))), /*#__PURE__*/React.createElement(SwitchRender, {
      depth: travelTest ? liveMax : actuation,
      actuation: actuation
    })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-[var(--text-dim)] mb-3"
    }, "Select keys on the board, set the actuation point, then press ", /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "Apply"), " \u2014 only the selected keys are written. Nothing is sent while you move the slider."), /*#__PURE__*/React.createElement("div", {
      className: "mb-5 inline-flex items-center gap-2 px-3 h-7 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/[0.06]"
    }, /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-dim)]"
    }, "Applying to"), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11px] uppercase tracking-[0.16em] text-[var(--accent)]"
    }, scope)), /*#__PURE__*/React.createElement("div", {
      className: "mb-5"
    }, /*#__PURE__*/React.createElement(Slider, {
      label: "Key Trigger Travel",
      value: actuation,
      min: 0.1,
      max: 3.4,
      step: 0.05,
      unit: "mm",
      onChange: setActuation
    }), /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 mt-2"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: () => setActuation(Math.max(0.1, actuation - 0.05)),
      className: "w-7 h-7 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"
    }, "\u2212"), /*#__PURE__*/React.createElement("div", {
      className: "px-3 h-7 rounded-md border border-[var(--line)] bg-white/[0.02] grid place-items-center font-mono text-[12px] text-[var(--text)]"
    }, actuation.toFixed(2), " mm"), /*#__PURE__*/React.createElement("button", {
      onClick: () => setActuation(Math.min(4.0, actuation + 0.05)),
      className: "w-7 h-7 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"
    }, "+"))), /*#__PURE__*/React.createElement("label", {
      className: "flex items-center gap-2 cursor-pointer select-none mb-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: `w-4 h-4 rounded border grid place-items-center transition
                            ${rtEnabled ? "border-[var(--accent)] bg-[var(--accent)]/20" : "border-[var(--line)] bg-white/[0.02]"}`,
      onClick: () => setRtEnabled(!rtEnabled)
    }, rtEnabled && ICheck && /*#__PURE__*/React.createElement(ICheck, {
      size: 10,
      className: "text-[var(--accent)]"
    })), /*#__PURE__*/React.createElement("input", {
      type: "checkbox",
      checked: rtEnabled,
      onChange: e => setRtEnabled(e.target.checked),
      className: "sr-only"
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[11.5px] uppercase tracking-[0.16em] text-[var(--text)]"
    }, "Rapid Trigger"), Chip && /*#__PURE__*/React.createElement(Chip, {
      color: "accent"
    }, "RT")), /*#__PURE__*/React.createElement("p", {
      className: "text-[11.5px] text-[var(--text-faint)] leading-relaxed mb-4"
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
    })), /*#__PURE__*/React.createElement("div", {
      className: "mt-6 flex items-center gap-3"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: handleApplyTravel,
      disabled: !canApply,
      className: applyBtnCls(canApply)
    }, "Apply to ", selectedCount || 0, " key", selectedCount === 1 ? "" : "s"), confirm ? /*#__PURE__*/React.createElement(ConfirmToast, {
      confirm: confirm
    }) : /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
    }, canApply ? "writes only the selected keys" : "select keys on the board to enable"))));
  }

  /* ===== Dead Band widget ===== */
  function DeadBandWidget(ctx) {
    const {
      deadTop,
      setDeadTop,
      deadBottom,
      setDeadBottom,
      selectedKeys,
      applyDeadband
    } = ctx;
    const selectedCount = selectedKeys ? selectedKeys.size : 0;
    const canApply = selectedCount > 0;
    const [confirm, flash] = useFlash();
    const handleApplyDead = () => {
      if (!canApply || !applyDeadband) return;
      applyDeadband();
      flash(`Wrote dead band ${(deadTop ?? 0.04).toFixed(2)}/${(deadBottom ?? 0.05).toFixed(2)}mm to ${selectedCount} key${selectedCount === 1 ? "" : "s"}`);
    };
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-[var(--text-dim)] mb-5"
    }, "Configure the dead-band region near the keycap's rest and bottom-out positions \u2014 noise inside this band is ignored. Press ", /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, "Apply"), " to write to the selected keys."), /*#__PURE__*/React.createElement("div", {
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
    })), /*#__PURE__*/React.createElement("div", {
      className: "mt-6 flex items-center gap-3"
    }, /*#__PURE__*/React.createElement("button", {
      onClick: handleApplyDead,
      disabled: !canApply,
      className: applyBtnCls(canApply)
    }, "Apply to ", selectedCount || 0, " key", selectedCount === 1 ? "" : "s"), confirm ? /*#__PURE__*/React.createElement(ConfirmToast, {
      confirm: confirm
    }) : /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--text-faint)]"
    }, canApply ? "writes only the selected keys" : "select keys on the board to enable")));
  }

  /* ===== Switch widget ===== */
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
  function SwitchWidget(ctx) {
    const {
      switchId,
      handlePickSwitch
    } = ctx;
    const cur = SWITCHES.find(s => s.id === (switchId || "hm1")) || SWITCHES[0];
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-[var(--text-dim)] mb-5"
    }, "Select the magnetic switch profile installed in your board. Calibration curves load automatically."), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 gap-3 mb-5"
    }, SWITCHES.map(s => {
      const active = (switchId || "hm1") === s.id;
      return /*#__PURE__*/React.createElement("button", {
        key: s.id,
        onClick: () => handlePickSwitch && handlePickSwitch(s.id),
        className: `text-left rounded-lg border p-3 transition-all
                        ${active ? "border-[var(--accent)]/50 bg-[var(--accent)]/[0.06] shadow-[0_0_14px_var(--accent-glow)]" : "border-[var(--line)] bg-white/[0.02] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`
      }, /*#__PURE__*/React.createElement("div", {
        className: "flex items-center gap-2"
      }, /*#__PURE__*/React.createElement("div", {
        className: "font-display text-[14px] text-[var(--text)]"
      }, s.name), /*#__PURE__*/React.createElement("span", {
        className: "w-2.5 h-2.5 rounded-full",
        style: {
          background: s.dot,
          boxShadow: `0 0 8px ${s.dot}`
        }
      })), /*#__PURE__*/React.createElement("div", {
        className: "font-mono text-[10px] text-[var(--text-faint)] uppercase tracking-[0.18em] mt-0.5"
      }, s.sub));
    })), /*#__PURE__*/React.createElement("div", {
      className: "rounded-xl border border-[var(--line)] bg-[rgba(5,11,14,0.5)] p-4"
    }, /*#__PURE__*/React.createElement("div", {
      className: "flex items-center gap-2 mb-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: "w-2.5 h-2.5 rounded-full",
      style: {
        background: cur.dot,
        boxShadow: `0 0 8px ${cur.dot}`
      }
    }), /*#__PURE__*/React.createElement("span", {
      className: "font-display text-[13px] text-[var(--text)]"
    }, cur.name), /*#__PURE__*/React.createElement("span", {
      className: "font-mono text-[10px] text-[var(--text-faint)] uppercase tracking-[0.18em]"
    }, cur.maker, " \xB7 ", cur.sub)), /*#__PURE__*/React.createElement("div", {
      className: "grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3 font-mono text-[11px]"
    }, [["Total Travel", cur.travel], ["Actuation Range", cur.range], ["Initial Force", cur.force], ["Sensing", cur.poles + " Hall"], ["Rated Life", cur.life + " presses"], ["Tech", "Magnetic / Analog"]].map(([k, v]) => /*#__PURE__*/React.createElement("div", {
      key: k
    }, /*#__PURE__*/React.createElement("div", {
      className: "text-[var(--text-faint)] uppercase tracking-[0.14em] text-[9.5px]"
    }, k), /*#__PURE__*/React.createElement("div", {
      className: "text-[var(--text)] mt-0.5"
    }, v))))));
  }

  /* ===== Polling Rate widget ===== */
  function PollingWidget(ctx) {
    const {
      polling,
      handleSetPolling
    } = ctx;
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      className: "text-[12px] text-[var(--text-dim)] mb-5"
    }, "Switch the polling rate of the device. The keyboard will restart and disconnect briefly after switching."), /*#__PURE__*/React.createElement("div", {
      className: "flex flex-wrap gap-2"
    }, [1, 2, 4, 8].map(p => /*#__PURE__*/React.createElement("button", {
      key: p,
      onClick: () => handleSetPolling(p),
      className: `px-4 h-9 rounded-md border font-display text-[12px] uppercase tracking-[0.16em] transition-all
                        ${polling === p ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_18px_var(--accent-glow)]" : "border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"}`
    }, p, "KHz"))), /*#__PURE__*/React.createElement("div", {
      className: "mt-6 p-4 rounded-lg border border-[var(--line)] bg-[rgba(5,11,14,0.5)] font-mono text-[11px] text-[var(--text-dim)] leading-relaxed"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--text-faint)]"
    }, "current"), " \xB7 ", /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--accent)]"
    }, polling, "000 Hz"), " \xB7 ", (1000 / polling).toFixed(2), "ms tick"), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("span", {
      className: "text-[var(--text-faint)]"
    }, "latency"), " \xB7 ~", (0.5 + 1 / polling).toFixed(2), "ms end-to-end")));
  }

  /* ===== Calibration widget ===== */
  function CalibrationWidget(ctx) {
    const {
      calibrating,
      handleCalibrate
    } = ctx;
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[12px] uppercase tracking-[0.18em] text-[var(--text)] mb-3"
    }, "Key Calibration"), /*#__PURE__*/React.createElement("button", {
      onClick: () => handleCalibrate && handleCalibrate(!calibrating),
      className: "px-5 h-10 rounded-md border border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)] font-display text-[12px] uppercase tracking-[0.18em] shadow-[0_0_18px_var(--accent-glow)] mb-5"
    }, calibrating ? "Stop Calibration" : "Start Calibration"), /*#__PURE__*/React.createElement("div", {
      className: "font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)] mb-2"
    }, "Calibration steps:"), /*#__PURE__*/React.createElement("ol", {
      className: "space-y-2 text-[12px] text-[var(--text-dim)] max-w-2xl"
    }, ["Click the Start Calibration button", "Press the required key (Hit bottom)", "Wait for the corresponding key to change color, and the key calibration is complete", "Click the Stop Calibration button"].map((step, i) => /*#__PURE__*/React.createElement("li", {
      key: i,
      className: "flex items-start gap-3"
    }, /*#__PURE__*/React.createElement("span", {
      className: "shrink-0 grid place-items-center w-5 h-5 rounded border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent)] font-mono text-[10px]"
    }, i + 1), /*#__PURE__*/React.createElement("span", null, step)))));
  }
  const ACTUATION_WIDGETS = [{
    id: "travel",
    title: "Travel",
    default: {
      x: 40,
      y: 32,
      w: 680,
      h: 430
    },
    min: {
      w: 420,
      h: 320
    },
    render: TravelWidget
  }, {
    id: "dead",
    title: "Dead Band",
    default: {
      x: 736,
      y: 32,
      w: 460,
      h: 300
    },
    min: {
      w: 320,
      h: 240
    },
    render: DeadBandWidget
  }, {
    id: "switch",
    title: "Switch",
    default: {
      x: 736,
      y: 352,
      w: 460,
      h: 430
    },
    min: {
      w: 340,
      h: 300
    },
    render: SwitchWidget
  }, {
    id: "poll",
    title: "Polling Rate",
    default: {
      x: 40,
      y: 488,
      w: 380,
      h: 300
    },
    min: {
      w: 300,
      h: 240
    },
    render: PollingWidget
  }, {
    id: "calib",
    title: "Calibration",
    default: {
      x: 440,
      y: 488,
      w: 456,
      h: 360
    },
    min: {
      w: 340,
      h: 280
    },
    render: CalibrationWidget
  }];
  window.AetherWorkspaces = window.AetherWorkspaces || {};
  window.AetherWorkspaces.ACTUATION_WIDGETS = ACTUATION_WIDGETS;
})();