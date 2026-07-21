
(() => {
const { useState, useEffect, useRef, useMemo } = React;
const {
  IFolder, IKeyboard, IBulb, IGauge, ICrosshair, IGrid, IPlug, IPower,
  IChevron, IChevronD, ICheck, IEdit, IRefresh, IZap, ISave, ILink, IUnlink,
  IPalette, IActivity, IWaves, ISettings, ITrash, IPlus, ICpu, ILayers, IMore, IDownload
} = window.AetherIcons;

const { KeyboardPanel } = window.AetherKeyboard;
const { KeymapSection, ActuationSection, LightingSection, SOCDSection, GamepadSection, OtherSection, ActuationToolbar } = window.AetherSections;
const { ThemePopup, useTheme } = window.AetherTheme;

// Desktop-widget shell (foundation) + section widget registries.
const { Workspace, TopBar: DesktopTopBar, SECTION_DEFS } = window.AetherDesktop;
const SetupWizard = window.AetherWizard && window.AetherWizard.SetupWizard;
const BoardSubmit = window.AetherBoardSubmit && window.AetherBoardSubmit.BoardSubmit;

// Board awareness (PER_BOARD_PARITY_PLAN.md step 4) — all guarded so a missing
// component file degrades to exactly the previous single-board UI.
const AetherBoard = window.AetherBoard || {};
const BoardContext = AetherBoard.BoardContext;
const makeBoardContextValue = AetherBoard.makeBoardContextValue;
const BoardPicker = window.AetherBoardPicker && window.AetherBoardPicker.BoardPicker;
const UnsupportedNotices = window.AetherNotices && window.AetherNotices.UnsupportedNotices;

// Placeholder for sections not yet built by later waves — a single
// "coming soon" widget so the workspace surface isn't blank.
const comingSoon = (label) => [{
  id: "soon", title: label, default: { x: 60, y: 48, w: 420, h: 220 }, min: { w: 300, h: 160 },
  render: () => (
    <div className="grid place-items-center h-full text-center px-6">
      <div>
        <div className="font-title text-[22px] text-[var(--text)] mb-1">{label}</div>
        <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--text-faint)]">workspace coming soon</div>
      </div>
    </div>
  ),
}];

// Registry: section id → widget array, sourced from each workspace file's
// window.AetherWorkspaces.<SECTION>_WIDGETS export; falls back to a placeholder
// if a workspace file failed to load.
const wsArr = (key, label) => {
  const a = (window.AetherWorkspaces && window.AetherWorkspaces[key]) || [];
  return a.length ? a : comingSoon(label);
};
const WIDGETS = {
  actuation: wsArr("ACTUATION_WIDGETS", "Actuation"),
  keymap:    wsArr("KEYMAP_WIDGETS", "Keymap"),
  lighting:  wsArr("LIGHTING_WIDGETS", "Lighting"),
  socd:      wsArr("SOCD_WIDGETS", "SOCD"),
  gamepad:   wsArr("GAMEPAD_WIDGETS", "Gamepad"),
  settings:  wsArr("SETTINGS_WIDGETS", "Settings"),
};

/* ============================================================
   HID bridge — talks to the native Python Api (window.pywebview.api).
   Every control calls these with real, structured values; there is NO
   DOM/CSS scraping. Safely no-ops when run outside the webview.
   ============================================================ */
const getApi = () => (window.pywebview && window.pywebview.api) || null;

// Honest-failure tap: when the backend refuses an operation with
// {ok:false, unsupported:true, feature, error} (per-board capability gating),
// broadcast it so the App can surface the reason instead of the call failing
// silently. Results pass through UNCHANGED, so every existing caller behaves
// exactly as before — and on a fully-supported board (Aula Win60 HE) the
// backend never returns `unsupported`, so this never fires there.
const unsupportedListeners = new Set();
const emitUnsupported = (name, res) => {
  unsupportedListeners.forEach(fn => { try { fn(name, res); } catch {} });
};
const tapUnsupported = (name) => (r) => {
  if (r && r.ok === false && r.unsupported) emitUnsupported(name, r);
  return r;
};

const apiCall = (name, ...args) => {
  const api = getApi();
  if (!api || typeof api[name] !== "function")
    return Promise.resolve({ ok: false, error: "no bridge" });
  try { return Promise.resolve(api[name](...args)).then(tapUnsupported(name)); }
  catch (e) { return Promise.resolve({ ok: false, error: String(e) }); }
};

const hexToRgbArr = (hex) => {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 0, 0];
};
const rgbToHex = (rgb) =>
  "#" + (rgb || [0, 0, 0]).map(c => Math.max(0, Math.min(255, c | 0)).toString(16).padStart(2, "0")).join("");
// Lighting %→firmware steps. `max` comes from the active board's registry
// (lighting.brightnessMax/speedMax); the default 4 is the Win60 scale and
// makes these exactly the legacy functions (0% = off). Boards with a
// different scale (MINI 60 HE PRO: 0..5) pass their own max.
const briByte = (pct, max = 4) => (pct <= 0 ? 0 : Math.max(1, Math.min(max, Math.ceil((pct / 100) * max))));
const spdByte = (pct, max = 4) => Math.max(1, Math.min(max, Math.round((pct / 100) * (max - 1)) + 1));
// Firmware light modes (decoded from the official driver: cmd 7, byte5=mode,
// refreshColorView() defines each mode's controls). Each entry: the firmware
// mode byte, whether it uses a background color (2-color), a speed control, what
// kind of direction control it exposes, and whether Full-RGB applies.
// dir: "none" | "lr" (left/right) | "ud" (up/down) | "all" (4-way+gather/spread)
//      | "rotate" (CW/CCW) | "gather" (gather/spread).  custom (10) = per-key.
const FW_MODES = {
  static:   { byte: 0,  bg: false, speed: false, dir: "none",   full: false },
  breath:   { byte: 1,  bg: true,  speed: true,  dir: "none",   full: true },
  wave:     { byte: 2,  bg: true,  speed: true,  dir: "all",    full: true },
  neon:     { byte: 3,  bg: true,  speed: true,  dir: "none",   full: true },
  radar:    { byte: 4,  bg: true,  speed: true,  dir: "rotate", full: true },
  reactive: { byte: 6,  bg: true,  speed: true,  dir: "none",   full: true },
  cross:    { byte: 7,  bg: true,  speed: true,  dir: "gather", full: true },
  ripple:   { byte: 8,  bg: true,  speed: true,  dir: "none",   full: true },
  twinkle:  { byte: 9,  bg: true,  speed: true,  dir: "none",   full: true },
  custom:   { byte: 10, bg: false, speed: false, dir: "none",   full: false },
  fireworks:{ byte: 11, bg: true,  speed: true,  dir: "none",   full: true },
  frenzy:   { byte: 11, bg: true,  speed: true,  dir: "none",   full: true },
  speedres: { byte: 12, bg: true,  speed: false, dir: "ud",     full: true },
  autorip:  { byte: 14, bg: true,  speed: true,  dir: "none",   full: true },
  striation:{ byte: 15, bg: true,  speed: true,  dir: "lr",     full: true },
  aurora:   { byte: 16, bg: true,  speed: true,  dir: "none",   full: true },
};
const MODE_BYTE = Object.fromEntries(Object.entries(FW_MODES).map(([k, v]) => [k, v.byte]));
// SOCD key labels (BASIC/EXTENDED) → design data-code, from the keyboard layout.
const LABEL_TO_CODE = (() => {
  const map = {};
  ((window.AetherKeyboard && window.AetherKeyboard.KB_ROWS) || []).flat()
    .forEach(([label, _u, code]) => { if (label && code) map[label] = code; });
  return map;
})();

// Keymap target label → USB HID usage code (page 0x07). Used by Remap Key.
const HID_BY_LABEL = (() => {
  const m = {};
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").forEach((c, i) => { m[c] = 0x04 + i; });
  // number row (label forms used by BASIC_KEYS): 1..9 then 0
  [["1!", 0x1e], ["2@", 0x1f], ["3#", 0x20], ["$4", 0x21], ["5%", 0x22],
   ["6^", 0x23], ["7&", 0x24], ["8*", 0x25], ["9(", 0x26], ["0)", 0x27]]
    .forEach(([k, v]) => { m[k] = v; });
  Object.assign(m, {
    "Enter": 0x28, "Esc": 0x29, "Back": 0x2a, "Tab": 0x2b, "Space": 0x2c,
    "-_": 0x2d, "=+": 0x2e, "{[": 0x2f, "}]": 0x30, "\\|": 0x31, ";:": 0x33,
    "'\"": 0x34, "`~": 0x35, ",<": 0x36, ".>": 0x37, "/?": 0x38, "Caps": 0x39,
    "F1": 0x3a, "F2": 0x3b, "F3": 0x3c, "F4": 0x3d, "F5": 0x3e, "F6": 0x3f,
    "F7": 0x40, "F8": 0x41, "F9": 0x42, "F10": 0x43, "F11": 0x44, "F12": 0x45,
    "PrtSc": 0x46, "ScrLk": 0x47, "Pause": 0x48, "Ins": 0x49, "Home": 0x4a,
    "PgUp": 0x4b, "Del": 0x4c, "End": 0x4d, "PgDn": 0x4e, "Right": 0x4f,
    "Left": 0x50, "Down": 0x51, "Up": 0x52, "Menu": 0x65, "<>": 0x64,
    "L-Ctrl": 0xe0, "L-Shift": 0xe1, "L-Alt": 0xe2, "L-Win": 0xe3,
    "R-Ctrl": 0xe4, "R-Shift": 0xe5, "R-Alt": 0xe6, "R-Win": 0xe7,
  });
  return m;
})();

// Profiles are dynamic (add/rename/duplicate/delete) and live in settings.json.
// SEED_PROFILE is the very first profile created on a fresh install; everything
// else is created at runtime by the user.
const SEED_PROFILE = { id: "p1", name: "Default", state: {} };

// Migrate the old per-key blob shape ({"profile-p1": {...}, "profile-p2": {...}})
// to the new {profiles:[...], activeProfile, globals} shape so nobody loses
// their existing settings file.
const migrateSettings = (raw) => {
  if (!raw || typeof raw !== "object") return null;
  if (Array.isArray(raw.profiles)) return raw;   // already new shape
  const profs = [];
  for (const k of Object.keys(raw)) {
    if (!k.startsWith("profile-")) continue;
    const id = k.slice("profile-".length);
    const nm = id === "default" ? "Default" : id.toUpperCase();
    profs.push({ id, name: nm, state: raw[k] || {} });
  }
  if (!profs.length) return null;
  return { profiles: profs, activeProfile: profs[0].id, globals: {} };
};

const NAV = [
  { id: "keymap",    label: "Keymap",    icon: <IKeyboard size={14}/> },
  { id: "lighting",  label: "Lighting",  icon: <IBulb size={14}/> },
  { id: "actuation", label: "Actuation", icon: <IGauge size={14}/> },
  { id: "socd",      label: "SOCD",      icon: <ICrosshair size={14}/> },
  { id: "gamepad",   label: "Gamepad",   icon: <IZap size={14}/> },
  { id: "other",     label: "Settings",  icon: <ISettings size={14}/> },
];

/* ============================================================
   Profile dropdown — list, switch, rename, duplicate, delete, add new
   ============================================================ */
const ProfileDropdown = ({ profiles, activeId, onChange, onRename, onAdd, onDuplicate, onDelete }) => {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState("");
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setEditing(null); } };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const current = profiles.find(p => p.id === activeId) || profiles[0];
  if (!current) return null;
  const startEdit = (p) => { setEditing(p.id); setDraft(p.name); };
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
  const handleDelete = (p) => {
    if (profiles.length <= 1) { window.alert("You need at least one profile."); return; }
    if (!window.confirm(`Delete "${p.name}"? This can't be undone.`)) return;
    onDelete(p.id);
  };
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2.5 pl-2 pr-3 h-9 rounded-xl hover:bg-white/[0.04] transition-colors">
        <span className="grid place-items-center w-6 h-6 rounded-md bg-white/[0.04] text-[var(--text-dim)]">
          <IFolder size={12}/>
        </span>
        <span className="font-display text-[14px] font-medium text-[var(--text)]">{current.name}</span>
        <IChevronD size={13} className={`text-[var(--text-faint)] transition-transform ${open ? "rotate-180" : ""}`}/>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1.5 w-[280px] p-1.5 menu-pop z-50 animate-[fadeIn_140ms_ease-out]">
          {profiles.map(p => {
            const active = p.id === activeId;
            if (editing === p.id) {
              return (
                <div key={p.id} className="px-1.5 h-9 flex items-center">
                  <input autoFocus value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(null); }}
                    onBlur={commit}
                    className="input w-full h-7 px-2 text-[var(--text)] font-display text-[13px] outline-none"/>
                </div>
              );
            }
            return (
              <div key={p.id}
                className={`w-full flex items-center gap-1 pl-2.5 pr-1 h-9 rounded-lg transition-colors
                            ${active ? "bg-[var(--accent)]/15 text-[var(--text)]" : "text-[var(--text-dim)] hover:bg-white/[0.04] hover:text-[var(--text)]"}`}>
                <button onClick={() => { onChange(p.id); setOpen(false); }}
                  className="flex-1 flex items-center gap-2 text-left min-w-0">
                  <span className="font-display text-[13px] truncate">{p.name}</span>
                  {active && <ICheck size={12} className="text-[var(--accent)] shrink-0"/>}
                </button>
                <button onClick={(e) => { e.stopPropagation(); startEdit(p); }} title="Rename"
                  className="text-[var(--text-faint)] hover:text-[var(--text)] px-1.5 h-7 grid place-items-center">
                  <IEdit size={11}/>
                </button>
                <button onClick={(e) => { e.stopPropagation(); onDuplicate(p.id); }} title="Duplicate"
                  className="text-[var(--text-faint)] hover:text-[var(--text)] px-1.5 h-7 grid place-items-center">
                  <ILink size={11}/>
                </button>
                <button onClick={(e) => { e.stopPropagation(); handleDelete(p); }} title="Delete"
                  disabled={profiles.length <= 1}
                  className="text-[var(--text-faint)] hover:text-rose-300 disabled:text-[var(--text-faint)] disabled:cursor-not-allowed px-1.5 h-7 grid place-items-center">
                  <ITrash size={11}/>
                </button>
              </div>
            );
          })}
          <div className="h-px bg-[var(--line)] my-1.5"/>
          <button onClick={handleAdd}
            className="w-full flex items-center gap-2 pl-2.5 pr-1.5 h-9 rounded-lg text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors">
            <IPlus size={12}/>
            <span className="font-display text-[12.5px] uppercase tracking-[0.14em]">New profile</span>
          </button>
        </div>
      )}
    </div>
  );
};

/* ============================================================
   Top bar — Notion-style page header
   ============================================================ */
const TopBar = ({ profiles, activeId, onProfileChange, onRenameProfile, onAddProfile, onDuplicateProfile, onDeleteProfile,
                   connected, connecting, onTogglePair, autoConnect, setAutoConnect, onOpenTheme, onOpenSettings, saveStatus }) => (
  <header className="sticky top-0 z-40 bg-[var(--ink)]/70 backdrop-blur-xl border-b border-[var(--line)]">
    <div className="max-w-[1400px] mx-auto px-6 lg:px-10 h-14 flex items-center gap-3">
      {/* Logo + name */}
      <div className="flex items-center gap-3">
        <img src={(window.__resources && window.__resources.logo) || "assets/logo.png"} alt="" className="w-8 h-8 drop-shadow-[0_4px_14px_rgba(157,78,221,0.55)]"/>
        <div className="hidden md:block leading-tight">
          <div className="font-display text-[16px] font-bold tracking-[0.14em] text-[var(--text)]">Aether</div>
        </div>
      </div>

      <span className="mx-3 h-5 w-px bg-[var(--line)]"/>

      {/* Profile selector */}
      <ProfileDropdown profiles={profiles} activeId={activeId}
        onChange={onProfileChange} onRename={onRenameProfile}
        onAdd={onAddProfile} onDuplicate={onDuplicateProfile} onDelete={onDeleteProfile}/>

      {/* Save status — fades in for ~1.5s after a successful save */}
      {saveStatus && (
        <span className={`ml-2 font-mono text-[10px] uppercase tracking-[0.18em] transition-opacity
                          ${saveStatus === "saving" ? "text-[var(--text-faint)]"
                            : saveStatus === "saved" ? "text-emerald-400/80"
                            : "text-rose-400/80"}`}>
          {saveStatus === "saving" ? "saving…" : saveStatus === "saved" ? "✓ saved" : "save failed"}
        </span>
      )}

      {/* Right cluster */}
      <div className="ml-auto flex items-center gap-2">
        {/* Device status */}
        <div className="flex items-center gap-2 pl-2.5 pr-3 h-9 rounded-xl border border-[var(--line)]">
          <span className={`relative inline-block w-1.5 h-1.5 rounded-full pulse-ring ${connected ? "bg-[var(--good)] text-[var(--good)]" : "bg-[var(--text-faint)] text-[var(--text-faint)]"}`}/>
          <span className="font-display text-[12.5px] tracking-[0.04em] text-[var(--text)]">WIN 60 HE</span>
          <span className={`font-mono text-[9.5px] uppercase tracking-[0.2em] ml-1 ${connected ? "text-[var(--good)]/85" : "text-[var(--text-faint)]"}`}>{connected ? "Linked" : "Offline"}</span>
        </div>

        {/* Auto-connect on launch */}
        <label className="flex items-center gap-1.5 pl-2 pr-2.5 h-9 rounded-xl border border-[var(--line)] cursor-pointer select-none"
               title="Connect to the keyboard automatically when the app opens">
          <span onClick={() => setAutoConnect(!autoConnect)}
                className={`w-3.5 h-3.5 rounded border grid place-items-center transition
                            ${autoConnect ? "border-[var(--accent)] bg-[var(--accent)]/20" : "border-[var(--line)] bg-white/[0.02]"}`}>
            {autoConnect && <ICheck size={9} className="text-[var(--accent)]"/>}
          </span>
          <span className="font-display text-[10px] uppercase tracking-[0.16em] text-[var(--text-dim)]">Auto</span>
        </label>

        {/* Theme btn */}
        <button onClick={onOpenTheme}
          className="flex items-center gap-2 pl-2.5 pr-3 h-9 rounded-xl border border-[var(--line)] text-[var(--text-dim)] hover:text-[var(--text)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] transition-colors">
          <span className="w-3.5 h-3.5 rounded-full ring-1 ring-white/15"
                style={{ background: "var(--accent-gradient, var(--accent))" }}/>
          <span className="font-display text-[12px] uppercase tracking-[0.16em]">Theme</span>
        </button>

        {/* Pair / connection — drives the real HID connect/disconnect */}
        <button onClick={onTogglePair} disabled={connecting}
          className={`flex items-center gap-2 pl-2.5 pr-3 h-9 rounded-xl border transition-all disabled:opacity-60
                      ${connected
                        ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/15"
                        : "border-[var(--accent)]/40 bg-[var(--accent)]/12 text-[var(--accent)] hover:bg-[var(--accent)]/20"}`}>
          {connected ? <IPower size={13}/> : <IPlug size={13}/>}
          <span className="font-display text-[12px] uppercase tracking-[0.16em]">
            {connecting ? "…" : connected ? "Connected" : "Pair"}
          </span>
        </button>

        <button title="Settings" onClick={onOpenSettings}
          className="w-9 h-9 rounded-xl border border-[var(--line)] text-[var(--text-dim)] hover:text-[var(--text)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] grid place-items-center transition-colors">
          <ISettings size={14}/>
        </button>
      </div>
    </div>
  </header>
);

/* ============================================================
   Segmented pill nav
   ============================================================ */
const SectionNav = ({ section, setSection }) => (
  <div className="flex justify-center">
    <div className="inline-flex gap-1 p-1 rounded-2xl border border-[var(--line)] backdrop-blur-md">
      {NAV.map(n => {
        const active = section === n.id;
        return (
          <button key={n.id} onClick={() => setSection(n.id)}
            className={`relative flex items-center gap-2 px-4 h-9 rounded-xl font-display text-[12px] uppercase tracking-[0.18em] transition-all
                        ${active ? "pill-active" : "text-[var(--text-dim)] hover:text-[var(--text)] hover:bg-white/[0.03]"}`}>
            <span className={active ? "text-[var(--accent)]" : ""}>{n.icon}</span>
            {n.label}
          </button>
        );
      })}
    </div>
  </div>
);

/* ============================================================
   Hero — keyboard preview card
   ============================================================ */
const HeroCard = ({ children, badge, breadcrumb }) => (
  <section className="surface rounded-3xl px-6 lg:px-10 py-7 relative overflow-hidden">
    {/* Soft accent halo behind keyboard */}
    <div aria-hidden className="absolute -top-32 left-1/2 -translate-x-1/2 w-[820px] h-[420px] rounded-[50%] opacity-30 pointer-events-none blur-3xl"
         style={{ background: "var(--accent-gradient, var(--accent))" }}/>
    <div className="relative">
      <div className="flex items-center justify-between mb-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-[var(--text-faint)]">{breadcrumb}</div>
        {badge}
      </div>
      {children}
    </div>
  </section>
);

/* ============================================================
   App
   ============================================================ */
// Startup update gate: first-run opt-out prompt + the auto-install overlay.
// Driven by App's `updGate` state machine (idle | firstrun | updating | done | error).
function UpdateGate({ gate, onChoose, onDismiss }) {
  if (!gate || gate.phase === "idle") return null;
  // Above the setup wizard (zIndex 9999): on a true first run the update
  // decision is asked first, then dismisses to reveal onboarding underneath.
  const backdrop = "fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm";
  const card = "w-[430px] max-w-[92vw] rounded-2xl border border-[var(--line)] bg-[#0b1016] shadow-2xl p-5";
  const btnPrimary = "px-3 h-9 rounded-md border border-[var(--accent)]/40 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25";
  const btnGhost = "px-3 h-9 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]";
  if (gate.phase === "firstrun") {
    return (
      <div className={backdrop}>
        <div className={card}>
          <div className="font-display text-[14px] uppercase tracking-[0.16em] text-[var(--text)]">Keep Aether up to date?</div>
          <div className="text-[12.5px] text-[var(--text-dim)] mt-2 leading-relaxed">
            Aether can install new releases automatically when you open it. You can change this any time in Settings.
          </div>
          <div className="mt-4 flex gap-2">
            <button onClick={() => onChoose(true)} className={btnPrimary}>Yes, auto-update</button>
            <button onClick={() => onChoose(false)} className={btnGhost}>No, I'll check manually</button>
          </div>
        </div>
      </div>
    );
  }
  const dismissable = gate.phase === "done" || gate.phase === "error";
  return (
    <div className={backdrop}>
      <div className={card}>
        <div className="font-display text-[14px] uppercase tracking-[0.16em] text-[var(--text)]">
          {gate.phase === "error" ? "Update error" : "Updating Aether"}
        </div>
        <div className={`text-[12.5px] mt-2 leading-relaxed ${gate.phase === "error" ? "text-rose-300/90" : "text-[var(--text-dim)]"}`}>
          {gate.msg || "Working…"}
        </div>
        {gate.phase === "updating" && (
          <div className="mt-3 h-1 rounded-full bg-white/[0.06] overflow-hidden">
            <div className="h-full bg-[var(--accent)]/70 animate-pulse" style={{ width: "40%" }}/>
          </div>
        )}
        {dismissable && (
          <div className="mt-4 flex justify-end">
            <button onClick={onDismiss} className={btnGhost}>{gate.phase === "done" ? "OK" : "Dismiss"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

function App() {
  const [theme, setTheme] = useTheme();
  const [themeOpen, setThemeOpen] = useState(false);
  // First-run setup wizard: open until the user finishes/skips it once.
  const [wizardOpen, setWizardOpen] = useState(() => {
    try { return localStorage.getItem("aether-setup-done") !== "1"; } catch { return false; }
  });
  const closeWizard = () => {
    try { localStorage.setItem("aether-setup-done", "1"); } catch {}
    setWizardOpen(false);
  };
  const [submitOpen, setSubmitOpen] = useState(false);

  // ---- auto-update on launch (first-run opt-out) ----
  // On mount, read the persisted preference: null -> first-run prompt; true ->
  // silently check and auto-install; false -> nothing. The updating overlay only
  // appears once an update is confirmed, so there is no flash when up to date.
  const [updGate, setUpdGate] = useState({ phase: "idle", info: null, msg: "" });
  const updRan = useRef(false);
  const dismissUpdate = () => setUpdGate({ phase: "idle", info: null, msg: "" });
  const runUpdateFlow = async (api, showChecking) => {
    if (showChecking) setUpdGate({ phase: "updating", info: null, msg: "Checking for updates…" });
    let chk;
    try { chk = await api.check_update(); }
    catch { if (showChecking) dismissUpdate(); return; }
    if (!chk || !chk.ok || !chk.update) { if (showChecking) dismissUpdate(); return; }
    setUpdGate({ phase: "updating", info: chk, msg: `Updating Aether to v${chk.latest}…` });
    // Poll download progress so the launch overlay reports movement rather than
    // sitting on one line for a ~20 MB download.
    let poll = null;
    if (api.update_progress) {
      poll = setInterval(async () => {
        try {
          const p = await api.update_progress();
          if (!p?.ok) return;
          const mb = (n) => (n / 1048576).toFixed(1);
          if (p.phase === "downloading" && p.total) {
            setUpdGate(g => g.phase === "updating"
              ? { ...g, msg: `Downloading v${chk.latest}… ${p.pct}%  (${mb(p.done)} / ${mb(p.total)} MB)` } : g);
          } else if (p.phase === "verified") {
            setUpdGate(g => g.phase === "updating" ? { ...g, msg: "Verifying download…" } : g);
          }
        } catch {}
      }, 400);
    }
    const stopPoll = () => { if (poll) { clearInterval(poll); poll = null; } };
    try {
      const r = await api.apply_update(chk.asset_url, chk.asset_name,
                                       chk.asset_size, chk.asset_sha256);
      stopPoll();
      if (!r || !r.ok) { setUpdGate({ phase: "error", info: chk, msg: r?.error || "update failed" }); return; }
      if (r.quit) setUpdGate({ phase: "done", info: chk, msg: "Installer launched — Aether will close and reopen." });
      else if (r.restart) setUpdGate({ phase: "done", info: chk, msg: "Update installed — quit and reopen Aether to apply it." });
      else setUpdGate({ phase: "done", info: chk, msg: r.path ? `Downloaded to ${r.path}` : "Downloaded." });
    } catch (e) { stopPoll(); setUpdGate({ phase: "error", info: chk, msg: String(e) }); }
  };
  const chooseAutoUpdate = async (yes) => {
    const api = getApi();
    try { await api?.set_auto_update?.(yes); } catch {}
    if (yes) await runUpdateFlow(api, true);
    else dismissUpdate();
  };
  useEffect(() => {
    let tries = 0, timer = null;
    const run = async () => {
      const api = getApi();
      if (!api?.get_auto_update) { if (tries++ < 40) timer = setTimeout(run, 200); return; }
      if (updRan.current) return;
      updRan.current = true;
      let pref;
      try { const r = await api.get_auto_update(); pref = r && r.autoUpdate; } catch { return; }
      if (pref === null || pref === undefined) setUpdGate({ phase: "firstrun", info: null, msg: "" });
      else if (pref === true) runUpdateFlow(api, false);
    };
    run();
    return () => { if (timer) clearTimeout(timer); };
  }, []);

  // User zoom multiplier (top-bar − / % / + control), on top of the auto-fit.
  const [uiZoom, setUiZoom] = useState(() => {
    const v = parseFloat(localStorage.getItem("aether-zoom"));
    return v > 0 ? v : 1;
  });
  useEffect(() => { try { localStorage.setItem("aether-zoom", String(uiZoom)); } catch {} }, [uiZoom]);

  // Scale only the WORKSPACE (widgets) to the window — the top bar stays fixed.
  // CSS `zoom` (not transform) scales the coordinate system itself, so widget
  // drag/resize pointer math stays correct. Fit the design canvas to the area
  // below the top bar, then apply the user's zoom multiplier.
  useEffect(() => {
    const DESIGN_W = 1480, DESIGN_H = 900, TOPBAR = 64;
    const fit = () => {
      const base = Math.min(window.innerWidth / DESIGN_W, (window.innerHeight - TOPBAR) / DESIGN_H);
      const el = document.getElementById("desktop-main");
      if (el) el.style.setProperty("--ws-zoom", String(Math.max(0.4, Math.min(base * uiZoom, 2.4))));
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [uiZoom]);

  // Ctrl + mouse wheel over the workspace zooms in/out.
  useEffect(() => {
    const el = document.getElementById("desktop-main");
    if (!el) return;
    const onWheel = (e) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      const step = e.deltaY < 0 ? 0.08 : -0.08;
      setUiZoom(z => Math.max(0.5, Math.min(2, +(z + step).toFixed(2))));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Connection is OFF until the user pairs (or auto-connect is enabled).
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [autoConnect, setAutoConnect] = useState(() => {
    try { return localStorage.getItem("aether-autoconnect") === "1"; } catch { return false; }
  });
  const [section, setSection] = useState("actuation");

  // ---- board awareness (additive; single-board path unchanged) --------------
  // `board` mirrors get_board().active; `boardRoster` mirrors list_boards().boards
  // (each entry carries live `connected` / `active` flags). Stays null/[] when
  // the bridge is absent, which renders exactly the pre-board-awareness UI.
  const [board, setBoard] = useState(null);
  const [boardRoster, setBoardRoster] = useState([]);
  const [boardSwitching, setBoardSwitching] = useState(false);
  // Honest-failure notices: [{id, feature, msg}] fed by the apiCall unsupported tap.
  const [boardNotices, setBoardNotices] = useState([]);

  // Dynamic profile list + the currently active id.
  const [profiles, setProfiles] = useState([{ ...SEED_PROFILE }]);
  const [activeId, setActiveId] = useState(SEED_PROFILE.id);
  // The big "is settings ready to start saving" flag. Stays true (= block saves)
  // until the first hydration attempt finishes, success or fail.
  const [hydrated, setHydrated] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null);   // null | "saving" | "saved" | "error"

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
  const [liveDepths, setLiveDepths] = useState(null);   // real per-key travel (mm)
  const [lightFrame, setLightFrame] = useState(null);   // live effect frame {code:[r,g,b]}
  const [calibrating, setCalibrating] = useState(false);
  const [calibratedKeys, setCalibratedKeys] = useState(() => new Set()); // codes confirmed calibrated by firmware
  const [lightNonce, setLightNonce] = useState(0);   // bump to force-resend lighting (e.g. after calibration)
  const [deadTop, setDeadTop] = useState(0.04);
  const [deadBottom, setDeadBottom] = useState(0.05);
  const [switchId, setSwitchId] = useState("hm1");
  // Per-key actuation as the firmware actually stores it. Populated by reading
  // the device on connect and after every Apply so the board renders each key
  // with its own value instead of mirroring the global slider everywhere.
  const [perKeyActuation, setPerKeyActuation] = useState({});

  // Gamepad: virtual-pad capture + key→control mappings.
  const DEFAULT_PAD_MAP = [
    { key: "A", axis: "LX", direction: -1, threshold_mm: 1.5 },
    { key: "D", axis: "LX", direction: 1, threshold_mm: 1.5 },
    { key: "W", axis: "RT", direction: 1, threshold_mm: 1.5 },
    { key: "S", axis: "LT", direction: 1, threshold_mm: 1.5 },
    { key: "Space", axis: "BTN_A", direction: 1, threshold_mm: 1.0 },
  ];
  const [gamepadOn, setGamepadOn] = useState(false);
  const [gamepadMap, setGamepadMap] = useState(DEFAULT_PAD_MAP);

  // Out-of-the-box: RGB radar (user pref).
  const [colors, setColors] = useState(["#ff0040", "#ff8a00", "#ffd400", "#1eff7a", "#00b7ff", "#9d4edd"]);
  const [bgColor, setBgColor] = useState("#000000");
  const [perKeyColors, setPerKeyColors] = useState({});
  const [zones, setZones] = useState([]);   // effect zones for Custom mode
  const [pattern, setPattern] = useState("radar");
  const [brightness, setBrightness] = useState(100);
  const [speed, setSpeed] = useState(60);
  const [power, setPower] = useState(true);
  const [fullColor, setFullColor] = useState(false);  // rainbow / full-spectrum
  const [direction, setDirection] = useState(0);      // 0→ 1← 2↑ 3↓
  const [striOrient, setStriOrient] = useState("v");   // striation: v|h|both
  const [bgBright, setBgBright] = useState(100);       // background brightness %

  const [socdMode, setSocdMode] = useState("last");
  const [hotkey] = useState("Fn + R-Shift");
  const [hotkeyEnabled, setHotkeyEnabled] = useState(true);
  // SOCD profiles live here (not inside SOCDSection) so they persist + save.
  const [socdProfiles, setSocdProfiles] = useState([
    { id: "SOCD1", k1: "A", k2: "D", mode: 1, active: true },
    { id: "SOCD2", k1: "W", k2: "S", mode: 1 },
  ]);
  const [socdActive, setSocdActive] = useState("SOCD1");

  // ---- per-profile persistence ----------------------------------------------
  // applyingRef blocks the save effect while we hydrate (mount OR profile
  // switch). Starts true so the very first render doesn't clobber the file
  // before load_settings has a chance to run.
  const applyingRef = useRef(true);
  const collectState = () => ({
    pattern, colors, bgColor, brightness, speed, power, fullColor, direction,
    striOrient, bgBright, perKeyColors, zones,
    actuation, rtPress, rtRelease, rtEnabled, polling,
    deadTop, deadBottom, switchId,
    socdProfiles, socdActive, hotkeyEnabled, socdMode,
    layer, gamepadMap,
  });
  const applyState = (s) => {
    if (!s) return;
    applyingRef.current = true;
    const set = (v, fn) => { if (v !== undefined) fn(v); };
    set(s.pattern, setPattern); set(s.colors, setColors); set(s.bgColor, setBgColor);
    set(s.brightness, setBrightness); set(s.speed, setSpeed); set(s.power, setPower);
    set(s.fullColor, setFullColor); set(s.direction, setDirection); set(s.bgBright, setBgBright);
    set(s.striOrient, setStriOrient);
    set(s.perKeyColors, setPerKeyColors); set(s.zones, setZones);
    set(s.actuation, setActuation); set(s.rtPress, setRtPress); set(s.rtRelease, setRtRelease);
    set(s.rtEnabled, setRtEnabled); set(s.polling, setPolling);
    set(s.deadTop, setDeadTop); set(s.deadBottom, setDeadBottom); set(s.switchId, setSwitchId);
    set(s.socdProfiles, setSocdProfiles); set(s.socdActive, setSocdActive);
    set(s.hotkeyEnabled, setHotkeyEnabled); set(s.socdMode, setSocdMode); set(s.layer, setLayer);
    set(s.gamepadMap, setGamepadMap);
    setTimeout(() => { applyingRef.current = false; }, 80);
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
        if (attempt < 50) setTimeout(() => tryLoad(attempt + 1), 100);
        else {
          applyingRef.current = false;
          setHydrated(true);
        }
        return;
      }
      try {
        const r = await window.pywebview.api.load_settings();
        if (cancelled) return;
        const migrated = (r && r.ok) ? migrateSettings(r.settings) : null;
        if (migrated && migrated.profiles && migrated.profiles.length) {
          setProfiles(migrated.profiles);
          const aid = migrated.activeProfile && migrated.profiles.find(p => p.id === migrated.activeProfile)
                      ? migrated.activeProfile : migrated.profiles[0].id;
          setActiveId(aid);
          const active = migrated.profiles.find(p => p.id === aid);
          if (active?.state) applyState(active.state);
          if (migrated.globals?.autoConnect !== undefined) setAutoConnect(!!migrated.globals.autoConnect);
          if (migrated.globals?.section) setSection(migrated.globals.section === "other" ? "settings" : migrated.globals.section);
        }
      } catch {}
      setTimeout(() => { applyingRef.current = false; setHydrated(true); }, 100);
    };
    tryLoad();
    return () => { cancelled = true; };
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
      const next = ps.map(p => p.id === activeId ? { ...p, state } : p);
      // Persist the whole blob (profiles + active id + globals).
      clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        if (!window.pywebview?.api?.save_settings) return;
        setSaveStatus("saving");
        const blob = { profiles: next, activeProfile: activeId,
                       globals: { autoConnect, section } };
        Promise.resolve(window.pywebview.api.save_settings(blob)).then(r => {
          setSaveStatus(r && r.ok ? "saved" : "error");
          setTimeout(() => setSaveStatus(null), 1400);
        }).catch(() => {
          setSaveStatus("error"); setTimeout(() => setSaveStatus(null), 1400);
        });
      }, 120);
      return next;
    });
  }, [hydrated, activeId, pattern, colors, bgColor, brightness, speed, power, fullColor, direction,
      striOrient, bgBright, perKeyColors, zones, actuation, rtPress, rtRelease, rtEnabled, polling,
      deadTop, deadBottom, switchId, socdProfiles, socdActive, hotkeyEnabled, socdMode, layer,
      gamepadMap, autoConnect, section]);

  // Force a synchronous flush before the window closes / page unloads, so the
  // 120ms debounce never costs us the last edit.
  useEffect(() => {
    const flush = () => {
      if (!window.pywebview?.api?.save_settings || !hydrated) return;
      const state = collectState();
      const ps = profiles.map(p => p.id === activeId ? { ...p, state } : p);
      try { window.pywebview.api.save_settings({ profiles: ps, activeProfile: activeId,
                                                  globals: { autoConnect, section } }); } catch {}
    };
    window.addEventListener("beforeunload", flush);
    window.addEventListener("pagehide", flush);
    return () => { window.removeEventListener("beforeunload", flush); window.removeEventListener("pagehide", flush); };
  });

  // ---- profile management actions -------------------------------------------
  const switchProfile = (id) => {
    if (id === activeId) return;
    const p = profiles.find(x => x.id === id);
    if (!p) return;
    setActiveId(id);
    applyState(p.state || {});
  };
  const renameProfile = (id, name) => {
    setProfiles(ps => ps.map(p => p.id === id ? { ...p, name } : p));
  };
  const addProfile = (name, duplicateCurrent = false) => {
    const newId = "p_" + Date.now().toString(36);
    const seed = duplicateCurrent ? collectState() : {};
    setProfiles(ps => [...ps, { id: newId, name: name || `Profile ${ps.length + 1}`, state: seed }]);
    // Switch to it; if duplicating we already have the right state in memory.
    setActiveId(newId);
    if (!duplicateCurrent) applyState({});
  };
  const duplicateProfile = (id) => {
    const src = profiles.find(p => p.id === id);
    if (!src) return;
    const newId = "p_" + Date.now().toString(36);
    setProfiles(ps => [...ps, { id: newId, name: `${src.name} (copy)`,
                                state: JSON.parse(JSON.stringify(src.state || {})) }]);
  };
  const deleteProfile = (id) => {
    if (profiles.length <= 1) return;
    const remain = profiles.filter(p => p.id !== id);
    setProfiles(remain);
    if (activeId === id) {
      setActiveId(remain[0].id);
      applyState(remain[0].state || {});
    }
  };

  const keyboardMode = section === "actuation" ? "actuation"
                      : section === "lighting" ? "lighting"
                      : section === "socd"     ? "socd"
                                                : "keymap";

  const ledMap = useMemo(() => {
    if (section !== "lighting") return {};
    const m = {};
    // Effect color depends on pattern. For "static" all keys = colors[0].
    // For others we cycle palette across keys. bgColor underlies un-effect keys.
    // COLOR HONESTY: previewSimColor (workspaces/lighting.jsx, shared with the
    // verification harness) knows that a mode dispatching to the BOARD's
    // firmware only ever receives colors[0] + bgColor — so the schematic must
    // not scatter the rest of the palette (the out-of-the-box seed above
    // contains #ffd400: that is the literal yellow that appeared inside a
    // purple firmware twinkle over white). For legacy grid ids on host-engine
    // boards (the shipped Win60 surface) and when the helper is missing, the
    // inline sim below is byte-identical to the previous shipped code.
    const LBH = window.AetherWorkspaces && window.AetherWorkspaces.LIGHTING_BOARD;
    const bl = (board && board.lighting) || null;
    window.AetherKeyboard.KB_ROWS.flat().forEach(([_, __, code], idx) => {
      if (perKeyColors[code]) { m[code] = perKeyColors[code]; return; }
      if (LBH && LBH.previewSimColor) {
        m[code] = LBH.previewSimColor(bl, { pattern, colors, bgColor }, idx);
        return;
      }
      if (pattern === "static") { m[code] = colors[0]; return; }
      // Simulated effect: every nth key gets an effect color, rest = bg
      const hit = (idx % 6 === 0) || colors.length === 1;
      m[code] = hit ? colors[idx % colors.length] : bgColor;
    });
    return m;
  }, [section, colors, bgColor, perKeyColors, pattern, board]);

  const selectedKey = useMemo(() => Array.from(selectedKeys)[0] || null, [selectedKeys]);

  /* ===== HID bridge: handlers ===== */
  // Pair button -> real connect / disconnect.
  const togglePair = () => {
    if (connecting) return;
    setConnecting(true);
    if (connected) {
      apiCall("disconnect")
        .then(() => { setConnected(false); setLiveDepths(null); })
        .finally(() => setConnecting(false));
    } else {
      apiCall("connect")
        .then(r => setConnected(!!(r && r.ok)))
        .finally(() => setConnecting(false));
    }
  };

  /* ===== board awareness: fetch, switch, honest failures ===== */
  // Refresh the active board + the live roster. Safe no-op without a bridge.
  const refreshBoards = async () => {
    try {
      const g = await apiCall("get_board");
      if (g && g.active !== undefined) setBoard(g.active || null);
      const l = await apiCall("list_boards");
      if (l && l.ok && Array.isArray(l.boards)) setBoardRoster(l.boards);
    } catch {}
  };

  // Fetch once when the bridge comes up, then poll slowly so plugging in a
  // second board (or pulling one) updates the picker without a restart.
  useEffect(() => {
    let alive = true, timer = null, iv = null, tries = 0;
    const boot = () => {
      if (!alive) return;
      if (!getApi()) { if (tries++ < 50) timer = setTimeout(boot, 200); return; }
      refreshBoards();
      iv = setInterval(() => { if (alive) refreshBoards(); }, 5000);
    };
    boot();
    return () => { alive = false; if (timer) clearTimeout(timer); if (iv) clearInterval(iv); };
  }, []);

  // Explicit board switch: select_board tears down the Python session and
  // rebinds device + driver + keymap; mirror that teardown in UI state, then
  // reconnect to the newly selected board. Only ever runs from the picker —
  // a single-board machine can never reach this code path.
  const selectBoard = async (slug) => {
    if (boardSwitching) return { ok: false, error: "switch in progress" };
    setBoardSwitching(true);
    try {
      const r = await apiCall("select_board", slug);
      if (!r || !r.ok) return r || { ok: false, error: "select_board failed" };
      setConnected(false);
      setLiveDepths(null); setLightFrame(null);
      setTravelTest(false); setCalibrating(false); setCalibratedKeys(new Set());
      setPerKeyActuation({}); setGamepadOn(false);
      if (r.active) setBoard(r.active);
      const c = await apiCall("connect");
      setConnected(!!(c && c.ok));
      await refreshBoards();
      return r;
    } finally {
      setBoardSwitching(false);
    }
  };

  // Surface {unsupported:true} results (backend capability gate) as visible,
  // auto-expiring notices with the backend's own reason string.
  useEffect(() => {
    const onUnsupported = (name, res) => {
      // Prefer the backend's reason; fall back to the feature name, never the
      // raw api method name, so the notice reads like the rest of the app.
      const msg = (res && res.error) ||
        `${(res && res.feature) || name} is not supported on this board`;
      const id = Date.now() + Math.random();
      setBoardNotices(ns => ns.some(n => n.msg === msg)
        ? ns : [...ns.slice(-3), { id, feature: res && res.feature, msg }]);
      setTimeout(() => setBoardNotices(ns => ns.filter(n => n.id !== id)), 6000);
    };
    unsupportedListeners.add(onUnsupported);
    return () => unsupportedListeners.delete(onUnsupported);
  }, []);
  const dismissBoardNotice = (id) => setBoardNotices(ns => ns.filter(n => n.id !== id));

  // Keep the active-board snapshot fresh across connect/disconnect (the 5s
  // roster poll would catch it anyway; this just makes it immediate).
  useEffect(() => { if (getApi()) refreshBoards(); }, [connected]);

  // The capability context value — the locked contract for the next wave
  // (shape documented in components/board-context.jsx). Also exposed to the
  // current widget files as ctx.board.
  const boardCtx = makeBoardContextValue
    ? makeBoardContextValue({ board, roster: boardRoster, selectBoard, refreshBoards, switching: boardSwitching })
    : null;

  // Polling change restarts the board, so only ever send it on an explicit click.
  const handleSetPolling = (p) => { setPolling(p); if (connected) apiCall("set_poll", p); };

  const handleCalibrate = (start) => {
    setCalibrating(start);
    if (start) setCalibratedKeys(new Set());
    apiCall("calibrate", start, false);   // lighting keeps running during calibration
  };

  // Gamepad: push the current map then toggle capture on/off.
  const [gamepadError, setGamepadError] = useState(null);   // {msg, needsDriver}
  const handleGamepadToggle = (on) => {
    setGamepadOn(on);
    if (on) { setGamepadError(null); apiCall("set_gamepad_map", gamepadMap); }
    apiCall("set_gamepad_capture", on).then(r => {
      if (!(r && r.ok)) {
        setGamepadOn(false);
        setGamepadError({ msg: (r && r.error) || "failed", needsDriver: !!(r && r.needs_vigembus) });
      } else {
        setGamepadError(null);
      }
    });
  };
  const handleInstallVigem = async () => {
    setGamepadError({ msg: "installing ViGEmBus (approve the UAC prompt)…", needsDriver: false, installing: true });
    const r = await apiCall("install_vigembus");
    if (r && r.ok) setGamepadError({ msg: "ViGEmBus installed — try capture again.", needsDriver: false });
    else setGamepadError({ msg: (r && r.error) || "install failed", needsDriver: true });
  };
  const handleGamepadMapApply = (map) => {
    setGamepadMap(map);
    if (gamepadOn) apiCall("set_gamepad_map", map);
  };

  const handlePickSwitch = (id) => {
    setSwitchId(id);
    const map = { hm1: 1, hh1: 2, cy1: 3, tc1: 5 };
    if (connected) apiCall("set_switch_codes", Array.from(selectedKeys), map[id] || 1);
  };

  // Effect zones (Custom mode): a group of keys running their own effect.
  const addZone = () => {
    const codes = Array.from(selectedKeys);
    if (!codes.length) return;
    setZones(zs => [...zs, {
      id: Date.now(), codes, mode: "twinkle",
      colors: ["#ff1f5a", "#00f5ff"], speed: 60,
    }]);
  };
  const updateZone = (id, patch) => setZones(zs => zs.map(z => z.id === id ? { ...z, ...patch } : z));
  const removeZone = (id) => setZones(zs => zs.filter(z => z.id !== id));

  const handleSocdApply = (profiles) => {
    const pairs = (profiles || [])
      .filter(p => p.k1 && p.k2)
      .map(p => ({ model: p.mode || 1, key1: LABEL_TO_CODE[p.k1] || p.k1, key2: LABEL_TO_CODE[p.k2] || p.k2 }));
    if (pairs.length) apiCall("set_socd", pairs);
  };

  /* ===== HID bridge: effects (push state to the board) ===== */
  // Persist the auto-connect preference.
  useEffect(() => {
    try { localStorage.setItem("aether-autoconnect", autoConnect ? "1" : "0"); } catch {}
  }, [autoConnect]);

  // One-shot auto-connect on launch, only if the user opted in. Fires once,
  // after hydration resolves `autoConnect` from settings.json, so a persisted
  // preference is honored. Guarded by a ref so it never fires twice.
  const didAuto = useRef(false);
  useEffect(() => {
    if (!hydrated || didAuto.current) return;
    didAuto.current = true;
    if (autoConnect && !connected) togglePair();
  }, [hydrated]);

  // Auto-reconnect watchdog: while Auto is on, poll the real device state and
  // (re)connect whenever the board appears — covers unplug/replug, not just
  // launch. Uses refs so the long-lived interval never reads stale state.
  const connectedRef = useRef(connected); connectedRef.current = connected;
  const connectingRef = useRef(connecting); connectingRef.current = connecting;
  useEffect(() => {
    if (!hydrated || !autoConnect) return;
    let alive = true, busy = false;
    const tick = async () => {
      if (!alive || busy || connectingRef.current) return;
      busy = true;
      try {
        const s = await apiCall("status");
        const isOpen = !!(s && s.connected);
        if (isOpen) {
          if (!connectedRef.current) setConnected(true);
        } else {
          if (connectedRef.current) { setConnected(false); setLiveDepths(null); }
          const r = await apiCall("connect");
          if (alive && r && r.ok) setConnected(true);
        }
      } catch {}
      busy = false;
    };
    const id = setInterval(tick, 2500);
    return () => { alive = false; clearInterval(id); };
  }, [hydrated, autoConnect]);

  // Lighting. ALL animated effects run on the HOST per-key engine so their
  // behaviour is consistent and matches the names (auto Ripple/Cross/Fireworks,
  // distinct Striation, directional flow, etc.) regardless of color count.
  // Only Static and Full-RGB use the firmware mode. `section` is intentionally
  // NOT a dependency: switching tabs never re-sends.
  //
  // PER-BOARD DISPATCH: the firmware-vs-host decision and every byte of the
  // resulting call are built by buildLightCalls (workspaces/lighting.jsx, one
  // source of truth shared with the verification harness) from THE ACTIVE
  // BOARD's registry mode table — never from the hardcoded Win60 MODE_BYTE
  // table, whose `?? 0` fallback meant LIGHTS OFF on the MINI 60 HE PRO.
  // When there is no board mode table at all (no bridge / board fetch failed)
  // buildLightCalls returns null and the legacy branch below runs — exactly
  // today's shipped code path, byte for byte.
  //
  // `board` is read through a ref and keyed by slug so the 5s roster poll
  // (which rebuilds the object identity) never re-sends lighting; a genuine
  // board switch (slug change) re-resolves and re-sends once.
  const boardRef = useRef(null);
  boardRef.current = board;
  const boardSlug = (board && board.slug) || null;
  const lightTimer = useRef(null);
  useEffect(() => {
    if (!connected) return;
    if (pattern === "custom") return;   // custom effect (below) owns the engine
    clearTimeout(lightTimer.current);
    lightTimer.current = setTimeout(() => {
      // Unified brightness: do NOT pre-scale the bg by bgBright here. The host
      // engine applies the main `brightness` to both fg and bg equally, so any
      // pre-scaling here would make the bg dimmer than the effect colors by
      // exactly the bgBright ratio (the two used to fight).
      const bgScaled = hexToRgbArr(bgColor);
      const bl = (boardRef.current && boardRef.current.lighting) || null;
      const LB = window.AetherWorkspaces && window.AetherWorkspaces.LIGHTING_BOARD;
      const built = (LB && LB.buildLightCalls)
        ? LB.buildLightCalls(bl, { pattern, power, fullColor, colors, bgColor,
                                   brightness, speed, direction, striOrient })
        : null;
      if (built) {
        built.calls.forEach(c => apiCall(...c));
        // Honest fallback: the selected mode exists on neither this board's
        // firmware nor the host engine — static was shown instead of silently
        // sending a byte that may mean OFF. Same notice pipe as the backend's
        // {unsupported:true} results.
        if (built.notice) {
          const msg = built.notice;
          const id = Date.now() + Math.random();
          setBoardNotices(ns => ns.some(n => n.msg === msg)
            ? ns : [...ns.slice(-3), { id, feature: "lighting", msg }]);
          setTimeout(() => setBoardNotices(ns => ns.filter(n => n.id !== id)), 6000);
        }
        return;
      }
      // Legacy path (no board mode table): today's shipped Win60-era code.
      // Animated effects run on the HOST per-key engine so they can show the
      // full multi-color palette (firmware effects only hold one fg+bg). Only
      // Static and Full-RGB use the firmware mode directly.
      const useHost = power && !fullColor && pattern !== "static";
      if (useHost) {
        apiCall("start_multicolor", pattern, colors.map(hexToRgbArr),
                bgScaled, brightness, speed, direction, striOrient);
      } else {
        apiCall("stop_multicolor");
        const [r, g, b] = hexToRgbArr(colors[0] || "#ffffff");
        const [br, bg, bb] = bgScaled;
        apiCall("set_light", MODE_BYTE[pattern] ?? 0, r, g, b,
                briByte(brightness), spdByte(speed), br, bg, bb, direction, power,
                fullColor ? 1 : 0);
      }
    }, 70);
    return () => clearTimeout(lightTimer.current);
  }, [connected, pattern, colors, bgColor, brightness, speed, power, fullColor, direction, bgBright, striOrient, lightNonce, calibrating, boardSlug]);

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
        bg: bgScaled,                 // keys outside zones + zone backdrops use it
        brightness,
        speed: z.speed != null ? z.speed : speed,
        direction,
      })));
    } else {
      apiCall("stop_multicolor");
      const map = {};
      Object.entries(perKeyColors || {}).forEach(([code, hex]) => { map[code] = hexToRgbArr(hex); });
      // Brightness/speed steps on THIS board's scale (Win60: 4 == the default,
      // so its bytes are unchanged; MINI 60 HE PRO: 5).
      const bl = (boardRef.current && boardRef.current.lighting) || null;
      apiCall("set_custom_colors", map,
              briByte(brightness, (bl && bl.brightnessMax) || 4),
              spdByte(speed, (bl && bl.speedMax) || 4));
    }
  }, [connected, pattern, perKeyColors, brightness, speed, zones, direction, bgColor, bgBright, lightNonce, calibrating, boardSlug]);

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
  // Read every key's stored actuation back from the firmware, normalise it to
  // {code: mm}, and stash it on JS state so the board can render per-key.
  const refreshPerKeyActuation = async () => {
    if (!connected) return;
    const r = await apiCall("verify_actuation", []);
    if (!r || r.ok === false || !r.actuation_mm) return;
    setPerKeyActuation(r.actuation_mm);
  };
  // On connect, snapshot per-key actuation once so the board reflects reality
  // before the user touches anything.
  useEffect(() => { if (connected) refreshPerKeyActuation(); }, [connected]);

  const applyActuation = async () => {
    if (!connected) return;
    const codes = Array.from(selectedKeys);
    if (codes.length === 0) return;
    const mode = rtEnabled ? 13 : 0;
    await apiCall("set_trigger_codes", codes, actuation,
                  rtEnabled ? rtPress : 0, rtEnabled ? rtRelease : 0, mode);
    // Optimistic update so the board reflects the change instantly. Skip the
    // 132-key read-back here — it takes ~5 s and we already know what was
    // written; the next connect/manual refresh re-syncs from the firmware.
    setPerKeyActuation(prev => {
      const next = { ...prev };
      for (const c of codes) next[c] = actuation;
      return next;
    });
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
    apiCall("open_analog_codes", []);   // [] = all keys
    let alive = true;
    const id = setInterval(() => {
      apiCall("read_live").then(d => {
        if (alive && d && typeof d === "object" && !(d.ok === false)) {
          setLiveDepths(prev => JSON.stringify(prev) === JSON.stringify(d) ? prev : d);
        }
      });
    }, 33);   // ~30fps — smooth enough for visual depth, doesn't starve the lighting stream
    return () => { alive = false; clearInterval(id); };
  }, [connected, travelTest]);

  // Calibration: the firmware reports each key the moment it's calibrated. Poll
  // those codes and mark them — they light up green both on screen and (driven by
  // Python) on the physical board. Lighting is killed on the Python side at start.
  useEffect(() => {
    if (!connected || !calibrating) return;
    let alive = true;
    let lastCount = 0, lastChange = Date.now();
    const finish = () => { if (!alive) return; alive = false; clearInterval(id); handleCalibrate(false); };
    const id = setInterval(() => {
      apiCall("read_calibrated").then(r => {
        if (!alive || !r || r.ok === false || !Array.isArray(r.codes)) return;
        setCalibratedKeys(prev => {
          if (r.codes.length === prev.size && r.codes.every(c => prev.has(c))) return prev;
          return new Set(r.codes);
        });
        if (r.codes.length !== lastCount) { lastCount = r.codes.length; lastChange = Date.now(); }
        // Auto-finish: firmware "done" signal, OR no new key calibrated for 3s
        // after at least one was (so you're never stuck waiting on the button).
        if (r.done) return finish();
        if (lastCount > 0 && Date.now() - lastChange > 3000) return finish();
      });
    }, 80);
    return () => { alive = false; clearInterval(id); };
  }, [connected, calibrating]);

  // Mirror the live host effect onto the IN-APP keyboard: poll the current frame
  // while on the Lighting tab and paint each key with its real animated color.
  // The host engine streams cmd-9 pages to the board at 60fps under the GIL;
  // a tight polling loop here starves it and makes the board look choppy.
  // 50ms (~20fps) is plenty for the on-screen mirror and leaves the engine room.
  useEffect(() => {
    if (!connected || section !== "lighting") { setLightFrame(null); return; }
    let alive = true;
    const id = setInterval(() => {
      apiCall("get_light_frame").then(f => {
        if (!alive) return;
        const valid = f && typeof f === "object" && !(f.ok === false) && Object.keys(f).length ? f : null;
        setLightFrame(prev => JSON.stringify(prev) === JSON.stringify(valid) ? prev : valid);
      });
    }, 50);
    return () => { alive = false; clearInterval(id); };
  }, [connected, section]);

  // Deepest currently-pressed key, for the switch-cutaway animation.
  const liveMax = useMemo(() => {
    if (!liveDepths) return 0;
    let m = 0;
    for (const k in liveDepths) { const v = +liveDepths[k] || 0; if (v > m) m = v; }
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

  const heroBadge = section === "actuation" ? (
    <div className="flex items-center gap-2">
      <Stat label="Actuation" value={`${actuation.toFixed(2)}mm`}/>
      <Stat label="Polling"   value={`${polling}KHz`}/>
      <Stat label="Selected"  value={`${selectedKeys.size}`}/>
    </div>
  ) : section === "lighting" ? (
    <div className="flex items-center gap-2">
      <Stat label="Mode"       value={pattern}/>
      <Stat label="Brightness" value={`${Math.round(brightness)}%`}/>
      <Stat label="Colors"     value={`${colors.length}`}/>
    </div>
  ) : section === "socd" ? (
    <div className="flex items-center gap-2">
      <Stat label="Hotkey" value={hotkey}/>
    </div>
  ) : section === "keymap" ? (
    <div className="flex items-center gap-2 p-1 rounded-xl border border-[var(--line)] bg-white/[0.02]">
      {["default","fn"].map(l => (
        <button key={l} onClick={() => setLayer(l)}
          className={`px-3 h-7 rounded-lg font-display text-[11px] uppercase tracking-[0.16em] transition-all
                      ${layer === l
                        ? "bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]"
                        : "text-[var(--text-dim)] hover:text-[var(--text)]"}`}>
          {l === "default" ? "Default Layer" : "Fn Layer"}
        </button>
      ))}
    </div>
  ) : null;

  const leftSlot = section === "actuation" ? (
    <ActuationToolbar
      onSelectAll={() => {
        const all = new Set(window.AetherKeyboard.KB_ROWS.flat().map(([_,__,c]) => c));
        setSelectedKeys(all);
      }}
      onSelectInvert={() => {
        const all = window.AetherKeyboard.KB_ROWS.flat().map(([_,__,c]) => c);
        setSelectedKeys(prev => new Set(all.filter(c => !prev.has(c))));
      }}
      onDeselectAll={() => setSelectedKeys(new Set())}
      onResetTrigger={() => { setActuation(1.70); setRtPress(0.05); setRtRelease(0.05); }}
    />
  ) : null;

  // Selection helpers (were the ActuationToolbar / lighting select-all actions).
  const selectAllKeys = () => {
    const all = new Set(window.AetherKeyboard.KB_ROWS.flat().map(([_,__,c]) => c));
    setSelectedKeys(all);
  };
  const selectInvertKeys = () => {
    const all = window.AetherKeyboard.KB_ROWS.flat().map(([_,__,c]) => c);
    setSelectedKeys(prev => new Set(all.filter(c => !prev.has(c))));
  };
  const deselectAllKeys = () => setSelectedKeys(new Set());
  const resetTrigger = () => { setActuation(1.70); setRtPress(0.05); setRtRelease(0.05); };
  const remapSelected = (label) => {
    const hid = HID_BY_LABEL[label];
    if (connected && hid != null && selectedKeys.size) apiCall("set_remap", Array.from(selectedKeys), hid);
  };
  const resetRemapSelected = () => {
    if (connected && selectedKeys.size) apiCall("reset_remap", Array.from(selectedKeys));
  };

  /* ============================================================
     ctx — the single object every workspace widget reads from. Carries ALL
     existing state + handlers (no new backend). Section files (ACTUATION_WIDGETS
     etc.) call only ctx.* — this is the LOCKED contract for parallel waves.
     ============================================================ */
  const ctx = {
    // bridge + connection
    apiCall, connected, connecting, togglePair,
    autoConnect, setAutoConnect,
    // profiles / persistence
    profiles, activeId, switchProfile, renameProfile, addProfile, duplicateProfile, deleteProfile, applyState,
    activeProfileName: (profiles.find(p => p.id === activeId) || {}).name || "Profile",
    // theme
    theme, setTheme, themeOpen, setThemeOpen,
    setWizardOpen, setSubmitOpen,
    // section
    section, setSection,
    // key selection (shared across workspaces)
    selectedKeys, setSelectedKeys, selectedKey,
    selectAllKeys, selectInvertKeys, deselectAllKeys,
    // actuation / rapid trigger
    actuation, setActuation, rtPress, setRtPress, rtRelease, setRtRelease,
    rtEnabled, setRtEnabled, resetTrigger,
    applyActuation, applyDeadband, refreshPerKeyActuation, perKeyActuation,
    deadTop, setDeadTop, deadBottom, setDeadBottom,
    switchId, handlePickSwitch,
    polling, handleSetPolling,
    // travel test + calibration telemetry
    travelTest, setTravelTest, liveDepths, liveMax,
    calibrating, handleCalibrate, calibratedKeys,
    // keymap
    layer, setLayer, HID_BY_LABEL, remapSelected, resetRemapSelected,
    // lighting
    colors, setColors, bgColor, setBgColor, perKeyColors, setPerKeyColors,
    pattern, setPattern, brightness, setBrightness, speed, setSpeed,
    power, setPower, fullColor, setFullColor, direction, setDirection,
    striOrient, setStriOrient, bgBright, setBgBright,
    zones, addZone, updateZone, removeZone,
    ledMap, ledMapLive,
    // socd
    socdMode, setSocdMode, hotkey, hotkeyEnabled, setHotkeyEnabled, handleSocdApply,
    socdProfiles, setSocdProfiles, socdActive, setSocdActive,
    // gamepad
    gamepadOn, handleGamepadToggle, gamepadMap, handleGamepadMapApply, DEFAULT_PAD_MAP,
    gamepadError, handleInstallVigem,
    // board awareness — same object as the React BoardContext value; workspaces
    // may read either ctx.board or window.AetherBoard.useBoard(). Contract in
    // components/board-context.jsx. null only if board-context.jsx failed to load.
    board: boardCtx,
  };

  // The whole existing tree, unchanged — board-awareness overlays are appended
  // after <main> and the tree is (optionally) wrapped in the BoardContext
  // provider below.
  const tree = (
    <>
      <DesktopTopBar
        sections={SECTION_DEFS}
        active={section}
        onSelect={setSection}
        connected={connected} connecting={connecting} onTogglePair={togglePair}
        autoConnect={autoConnect} setAutoConnect={setAutoConnect}
        onOpenSettings={() => setSection("settings")}
        zoom={uiZoom} setZoom={setUiZoom}
      />

      <main id="desktop-main" className="desktop-main">
        <Workspace section={section} widgets={WIDGETS[section] || []} ctx={ctx}/>
      </main>

      {/* Board picker — lists the registry's OFFERED boards (same flag as the
          wizard) once the live roster arrives; renders null without a bridge. */}
      {BoardPicker && (
        <BoardPicker roster={boardRoster} active={board}
                     switching={boardSwitching} onSelect={selectBoard}/>
      )}

      {/* Honest failure surfacing for {unsupported:true} results. Renders null
          when there are no notices (always, on fully-supported boards). */}
      {UnsupportedNotices && (
        <UnsupportedNotices notices={boardNotices} onDismiss={dismissBoardNotice}/>
      )}

      {/* Theme Customizer popup (preserved; surfaced by the Settings workspace) */}
      <ThemePopup open={themeOpen} onClose={() => setThemeOpen(false)} theme={theme} setTheme={setTheme}/>

      {/* First-run setup wizard (reopenable from Settings via ctx.setWizardOpen). */}
      {SetupWizard && <SetupWizard open={wizardOpen} onClose={closeWizard} ctx={ctx}/>}

      {/* Board submission modal (opened from wizard's board step or Settings). */}
      {BoardSubmit && <BoardSubmit open={submitOpen} onClose={() => setSubmitOpen(false)} />}

      {/* Auto-update gate: first-run opt-out prompt + auto-install overlay. */}
      <UpdateGate gate={updGate} onChoose={chooseAutoUpdate} onDismiss={dismissUpdate}/>
    </>
  );

  // Provide the capability context for the next wave of workspaces. When the
  // context module is missing the tree renders bare — identical to before.
  return (BoardContext && boardCtx)
    ? <BoardContext.Provider value={boardCtx}>{tree}</BoardContext.Provider>
    : tree;
}

const Stat = ({ label, value }) => (
  <div className="flex items-baseline gap-1.5 px-3 py-1.5 rounded-xl border border-[var(--line)] bg-white/[0.02]">
    <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-[var(--text-faint)]">{label}</span>
    <span className="font-mono text-[12px] text-[var(--text)]">{value}</span>
  </div>
);

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
})();
