(() => {
  /* ============================================================
     SOCD model numbering (Aula Win60 HE family, cmd 0x24 PRCS).
  
     The UI and the saved profiles hold the vendor's own number: "Model 1" ..
     "Model 4" (hed.aulacn.com prcsModel1..4). The WIRE byte is that number
     minus one, 0..3. CONFIRMED-BY-CAPTURE: picking "Model2" in the vendor
     driver wrote the entry `01 01 04 07`
     (docs/context/hed-aulacn-raw/WIN60_CAPTURE_NOTES.md, section 7).
  
     What each model does, from the vendor's own strings:
       Model 1 (wire 0)  the key pressed FIRST is interrupted: last press wins
       Model 2 (wire 1)  Key 1 interrupts Key 2
       Model 3 (wire 2)  Key 2 interrupts Key 1
       Model 4 (wire 3)  the later key is not sent and interrupts the first
  
     Until this fix Aether sent the label verbatim (`model: p.mode || 1`), so
     every pair ran one model later than its label and "Model 4" sent 4, a
     value the firmware does not implement.
  
     SAVED PROFILES. A state written by those builds holds the byte that went
     to the keyboard. migrateState renumbers it ONCE so the keyboard keeps
     doing what it did: old 1/2/3 (wire 1/2/3) become Model 2/3/4. Old 4 was
     never a real model; its label promised "later key wins", which is
     Model 1. The state is then stamped `socdRev: SOCD_REV`, so running the
     migration again changes nothing; app.jsx's collectState writes the same
     stamp on every save and backup.
  
     Pure functions, no React: tested in node (tests/test_socd_model.py).
     Exposes window.AetherSocd.
     ============================================================ */
  const SOCD_REV = 2;
  const SOCD_MODELS = [1, 2, 3, 4];
  const SOCD_MODEL_TEXT = {
    1: "Last press wins: the key pressed first is interrupted (Snap Tap).",
    2: "Key 1 interrupts Key 2.",
    3: "Key 2 interrupts Key 1.",
    4: "Neutral: the later key is not sent and interrupts the first."
  };

  // A stored mode as a valid model number (1..4); anything else is Model 1.
  const modelOf = mode => {
    const n = Number(mode);
    return Number.isInteger(n) && n >= 1 && n <= 4 ? n : 1;
  };

  // Model number -> the byte set_socd puts on the wire (0..3).
  const wireModel = mode => modelOf(mode) - 1;

  // The byte a pre-fix build sent for a stored mode -> today's model number.
  const LEGACY_TO_MODEL = {
    1: 2,
    2: 3,
    3: 4,
    4: 1
  };
  const migrateState = state => {
    if (!state || typeof state !== "object" || Array.isArray(state)) return state;
    if (Number(state.socdRev) >= SOCD_REV) return state;
    if (!Array.isArray(state.socdProfiles)) return state; // nothing stored yet
    return {
      ...state,
      socdProfiles: state.socdProfiles.map(p => p && typeof p === "object" ? {
        ...p,
        mode: LEGACY_TO_MODEL[Number(p.mode)] || 1
      } : p),
      socdRev: SOCD_REV
    };
  };
  window.AetherSocd = {
    SOCD_REV,
    SOCD_MODELS,
    SOCD_MODEL_TEXT,
    modelOf,
    wireModel,
    migrateState
  };
})();