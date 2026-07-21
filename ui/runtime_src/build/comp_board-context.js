(() => {
  /* ============================================================
     Board-awareness context — wave "UI board-awareness" of
     docs/context/PER_BOARD_PARITY_PLAN.md (step 4).
  
     Exposes window.AetherBoard = {
       BoardContext, useBoard, capState, makeBoardContextValue, UNKNOWN_BOARD
     }.
  
     The context VALUE shape (the locked contract for the next wave of
     workspace files):
  
       {
         board:        object|null   // get_board().active verbatim:
                                     //   {slug, name, vidPid, formFactor, status,
                                     //    capabilities, drivable, lighting?, actuation?}
         roster:       array         // list_boards().boards verbatim (adds
                                     //   `connected` + `active` booleans per entry)
         capabilities: object|null   // board.capabilities pass-through; values are
                                     //   true | false | "wip"
         lighting:     object|null   // board.lighting pass-through (per-board mode
                                     //   table + slider scales). null until the
                                     //   backend serializes the block in get_board.
         actuation:    object|null   // board.actuation pass-through (deadzoneScope,
                                     //   ranges, switches). Same null caveat.
         drivable:     bool          // protocol wired for the active board
         cap(name)          -> true | false | "wip" | undefined (raw flag)
         capState(name)     -> "yes" | "no" | "wip" | "unknown"
         isSupported(name)  -> bool  // ONLY true for a hard `true`. "wip" means
                                     // SOURCE-ONLY (read from vendor driver source,
                                     // never verified on hardware) and MUST be
                                     // treated as unavailable — label it
                                     // "unverified", don't drive it.
         selectBoard(slug)  -> Promise<select_board result>
         refreshBoards()    -> Promise
         switching:    bool          // a select_board round-trip is in flight
       }
  
     Fail-open rule: when NO board data is available at all (bridge not up,
     get_board failed, running in a plain browser) capState() returns "unknown"
     and isSupported() returns true, so the UI renders exactly like today's
     Win60-only build. The UI gate is cosmetic; the backend is the enforcement
     layer (unsupported ops return {ok:false, unsupported:true} regardless).
     ============================================================ */

  const BoardContext = React.createContext(null);

  // Normalize one capability flag. `caps` may be null (no board data).
  const capState = (caps, name) => {
    if (!caps || typeof caps !== "object") return "unknown";
    const v = caps[name];
    if (v === true) return "yes";
    if (v === "wip") return "wip";
    return "no"; // false or missing — registry semantics: absent flag = false
  };

  // Build the full context value from App-owned state + actions.
  const makeBoardContextValue = ({
    board,
    roster,
    selectBoard,
    refreshBoards,
    switching
  }) => {
    const caps = board && board.capabilities || null;
    return {
      board: board || null,
      roster: Array.isArray(roster) ? roster : [],
      capabilities: caps,
      lighting: board && board.lighting || null,
      actuation: board && board.actuation || null,
      drivable: !!(board && board.drivable),
      cap: name => caps ? caps[name] : undefined,
      capState: name => capState(caps, name),
      isSupported: name => caps ? caps[name] === true : true,
      // fail-open on unknown
      selectBoard: selectBoard || (() => Promise.resolve({
        ok: false,
        error: "no bridge"
      })),
      refreshBoards: refreshBoards || (() => Promise.resolve()),
      switching: !!switching
    };
  };

  // What consumers get if they render outside the provider (or the provider has
  // no data yet): behave exactly like the pre-board-awareness UI.
  const UNKNOWN_BOARD = makeBoardContextValue({
    board: null,
    roster: []
  });
  const useBoard = () => React.useContext(BoardContext) || UNKNOWN_BOARD;
  window.AetherBoard = {
    BoardContext,
    useBoard,
    capState,
    makeBoardContextValue,
    UNKNOWN_BOARD
  };
})();