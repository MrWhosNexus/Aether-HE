(() => {
/* ============================================================
   UnsupportedNotices — honest failure surfacing
   (PER_BOARD_PARITY_PLAN.md step 4, "honest toasts").

   When any bridge call resolves {ok:false, unsupported:true, feature, error}
   the App pushes the backend's reason here instead of letting the call fail
   silently. Presentation-only: notices arrive via props, so nothing here
   runs (or renders) on a board where every operation is supported — on the
   Aula Win60 HE this component always renders null.

   Styling follows the app's existing timed flash-message idiom
   (ConfirmToast / settings.jsx toast): short uppercase display text on a
   bordered card, auto-dismissed by the owner.

   Exposes window.AetherNotices = { UnsupportedNotices }.
   ============================================================ */

function UnsupportedNotices({ notices, onDismiss }) {
  if (!notices || !notices.length) return null;
  return (
    <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[70] flex flex-col items-center gap-2 pointer-events-none">
      {notices.map(n => (
        <div key={n.id}
          className="pointer-events-auto flex items-center gap-3 pl-3.5 pr-2 py-2 rounded-xl
                     border bg-[color-mix(in_srgb,var(--ink)_90%,transparent)] backdrop-blur-md shadow-2xl
                     animate-[fadeIn_140ms_ease-out]"
          style={{ borderColor: "color-mix(in srgb, var(--warn) 45%, transparent)" }}>
          <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-[var(--warn)] shrink-0">
            Not supported
          </span>
          <span className="font-display text-[12px] text-[var(--text)] max-w-[420px]">
            {n.msg}
          </span>
          <button onClick={() => onDismiss && onDismiss(n.id)} aria-label="Dismiss"
            className="ml-1 w-6 h-6 grid place-items-center rounded-md text-[var(--text-faint)] hover:text-[var(--text)] hover:bg-white/[0.05]">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

window.AetherNotices = { UnsupportedNotices };
})();
