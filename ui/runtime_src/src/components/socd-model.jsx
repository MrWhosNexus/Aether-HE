(() => {
/* ============================================================
   SOCD model numbering (Aula Win60 HE family, cmd 0x24 PRCS).

   The UI, the saved profiles AND the bridge (set_socd /
   apply_profile_to_board `model`) hold the vendor's own number: "Model 1" ..
   "Model 4" (hed.aulacn.com prcsModel1..4). Nothing here knows a wire value:
   each board's DRIVER turns the number into its own byte.
     Win60 family (cmd 0x24 PRCS): byte = number - 1, 0..3
       (drivers/win60.py). CONFIRMED-BY-CAPTURE: picking "Model2" in the
       vendor driver wrote the entry `01 01 04 07`
       (docs/context/hed-aulacn-raw/WIN60_CAPTURE_NOTES.md, section 7).
     MINI 60 HE PRO, WIN 68 HE Max: the number goes through unchanged
       (1..4), exactly as before this numbering was fixed. Sending those
       boards a zero-based value shifted them by one and made 0 an error.

   What each model does, from the vendor's own strings:
     Model 1 (wire 0)  the key pressed FIRST is interrupted: last press wins
     Model 2 (wire 1)  Key 1 interrupts Key 2
     Model 3 (wire 2)  Key 2 interrupts Key 1
     Model 4 (wire 3)  the later key is not sent and interrupts the first

   Until this fix Aether sent the label verbatim (`model: p.mode || 1`), so
   every pair ran one model later than its label and "Model 4" sent 4, a
   value the firmware does not implement.

   SAVED PROFILES. A state written by those builds holds the byte that went
   to the keyboard. migrateState renumbers it ONCE so a Win60 keeps doing
   what it did: old 1/2/3 (wire 1/2/3) become Model 2/3/4. Old 4 was never a
   real model; its label promised "later key wins", which is Model 1. A row
   with no mode (or 0) was sent as `p.mode || 1`, wire 1, so it becomes
   Model 2 as well. The state is then stamped `socdRev: SOCD_REV`, so
   running the migration again changes nothing; app.jsx's collectState
   writes the same stamp on every save and backup.

   WHICH BOARD a saved state was written for is not recorded anywhere:
   profiles are global, not per board. The renumbering therefore assumes the
   Win60 PRCS path, which is the only one where a saved model ever reached a
   keyboard in a normal build: the MINI 60 HE PRO driver refuses the bridge's
   pairs (they carry no key-table index), and the WIN 68 HE Max driver writes
   SOCD only under AETHER_EXPERIMENTAL=magnet. A profile used with that
   experimental board is renumbered too and so sends one model later than
   it did; re-pick the model there.

   Pure functions, no React: tested in node (tests/test_socd_model.py).
   Exposes window.AetherSocd.
   ============================================================ */
const SOCD_REV = 2;
const SOCD_MODELS = [1, 2, 3, 4];
const SOCD_MODEL_TEXT = {
  1: "Last press wins: the key pressed first is interrupted (Snap Tap).",
  2: "Key 1 interrupts Key 2.",
  3: "Key 2 interrupts Key 1.",
  4: "Neutral: the later key is not sent and interrupts the first.",
};

// A stored mode as a valid model number (1..4); anything else is Model 1.
const modelOf = (mode) => {
  const n = Number(mode);
  return Number.isInteger(n) && n >= 1 && n <= 4 ? n : 1;
};

// The byte a pre-fix build sent for a stored mode -> today's model number.
const LEGACY_TO_MODEL = { 1: 2, 2: 3, 3: 4, 4: 1 };
// What that build put on the wire for a stored mode: `p.mode || 1`.
const legacySent = (mode) => Number(mode) || 1;

const migrateState = (state) => {
  if (!state || typeof state !== "object" || Array.isArray(state)) return state;
  if (Number(state.socdRev) >= SOCD_REV) return state;
  if (!Array.isArray(state.socdProfiles)) return state;   // nothing stored yet
  return {
    ...state,
    socdProfiles: state.socdProfiles.map(p =>
      (p && typeof p === "object") ? { ...p, mode: LEGACY_TO_MODEL[legacySent(p.mode)] || 1 } : p),
    socdRev: SOCD_REV,
  };
};

window.AetherSocd = { SOCD_REV, SOCD_MODELS, SOCD_MODEL_TEXT, modelOf, migrateState };
})();
