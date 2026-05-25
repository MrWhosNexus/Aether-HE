
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

/* ============================================================
   HID bridge — talks to the native Python Api (window.pywebview.api).
   Every control calls these with real, structured values; there is NO
   DOM/CSS scraping. Safely no-ops when run outside the webview.
   ============================================================ */
const getApi = () => (window.pywebview && window.pywebview.api) || null;
const apiCall = (name, ...args) => {
  const api = getApi();
  if (!api || typeof api[name] !== "function")
    return Promise.resolve({ ok: false, error: "no bridge" });
  try { return Promise.resolve(api[name](...args)); }
  catch (e) { return Promise.resolve({ ok: false, error: String(e) }); }
};

const hexToRgbArr = (hex) => {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 0, 0];
};
const rgbToHex = (rgb) =>
  "#" + (rgb || [0, 0, 0]).map(c => Math.max(0, Math.min(255, c | 0)).toString(16).padStart(2, "0")).join("");
// Lighting %→firmware steps (AULA brightness 1..4, speed 1..4; 0% = off).
const briByte = (pct) => (pct <= 0 ? 0 : Math.max(1, Math.min(4, Math.ceil((pct / 100) * 4))));
const spdByte = (pct) => Math.max(1, Math.min(4, Math.round((pct / 100) * 3) + 1));
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

const PROFILES = [
  { id: "default", name: "Profile Default" },
  { id: "p1",      name: "Profile 1", editable: true },
  { id: "p2",      name: "Profile 2", editable: true },
  { id: "p3",      name: "Profile 3", editable: true },
  { id: "p4",      name: "Profile 4", editable: true },
];

const NAV = [
  { id: "keymap",    label: "Keymap",    icon: <IKeyboard size={14}/> },
  { id: "lighting",  label: "Lighting",  icon: <IBulb size={14}/> },
  { id: "actuation", label: "Actuation", icon: <IGauge size={14}/> },
  { id: "socd",      label: "SOCD",      icon: <ICrosshair size={14}/> },
  { id: "gamepad",   label: "Gamepad",   icon: <IZap size={14}/> },
  { id: "other",     label: "Other",     icon: <IGrid size={14}/> },
];

/* ============================================================
   Profile dropdown
   ============================================================ */
const ProfileDropdown = ({ value, onChange, names = {}, onRename }) => {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState("");
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setEditing(null); } };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const nameOf = (p) => names[p.id] || p.name;
  const current = PROFILES.find(p => p.id === value) || PROFILES[0];
  const startEdit = (p) => { setEditing(p.id); setDraft(nameOf(p)); };
  const commit = () => {
    if (editing && onRename) onRename(editing, draft.trim());
    setEditing(null);
  };
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2.5 pl-2 pr-3 h-9 rounded-xl hover:bg-white/[0.04] transition-colors">
        <span className="grid place-items-center w-6 h-6 rounded-md bg-white/[0.04] text-slate-400">
          <IFolder size={12}/>
        </span>
        <span className="font-display text-[14px] font-medium text-slate-100">{nameOf(current)}</span>
        <IChevronD size={13} className={`text-slate-500 transition-transform ${open ? "rotate-180" : ""}`}/>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1.5 w-[240px] rounded-xl p-1.5 menu-pop z-50 animate-[fadeIn_140ms_ease-out]">
          {PROFILES.map(p => {
            const active = p.id === value;
            if (editing === p.id) {
              return (
                <div key={p.id} className="px-1.5 h-9 flex items-center">
                  <input autoFocus value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(null); }}
                    onBlur={commit}
                    className="w-full h-7 px-2 rounded bg-black/40 border border-white/20 text-slate-100 font-display text-[13px] outline-none"/>
                </div>
              );
            }
            return (
              <div key={p.id}
                className={`w-full flex items-center justify-between gap-2 pl-2.5 pr-1.5 h-9 rounded-lg transition-colors
                            ${active ? "bg-[var(--accent)]/15 text-slate-100" : "text-slate-300 hover:bg-white/[0.04] hover:text-slate-100"}`}>
                <button onClick={() => { onChange(p.id); setOpen(false); }}
                  className="flex-1 flex items-center gap-2 text-left">
                  <span className="font-display text-[13px]">{nameOf(p)}</span>
                  {active && <ICheck size={12} className="text-[var(--accent)]"/>}
                </button>
                <button onClick={(e) => { e.stopPropagation(); startEdit(p); }} title="Rename"
                  className="text-slate-500 hover:text-slate-200 px-1">
                  <IEdit size={11}/>
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

/* ============================================================
   Top bar — Notion-style page header
   ============================================================ */
const TopBar = ({ profile, setProfile, profileNames, onRenameProfile, connected, connecting, onTogglePair, autoConnect, setAutoConnect, onOpenTheme }) => (
  <header className="sticky top-0 z-40 bg-[var(--bg-0)]/70 backdrop-blur-xl border-b border-white/[0.04]">
    <div className="max-w-[1400px] mx-auto px-6 lg:px-10 h-14 flex items-center gap-3">
      {/* Logo + name */}
      <div className="flex items-center gap-3">
        <img src={(window.__resources && window.__resources.logo) || "assets/logo.png"} alt="" className="w-8 h-8 drop-shadow-[0_4px_14px_rgba(157,78,221,0.55)]"/>
        <div className="hidden md:block leading-tight">
          <div className="font-display text-[16px] font-bold tracking-[0.14em] text-white">Aether</div>
        </div>
      </div>

      <span className="mx-3 h-5 w-px bg-white/[0.06]"/>

      {/* Profile selector */}
      <ProfileDropdown value={profile} onChange={setProfile}
        names={profileNames} onRename={onRenameProfile}/>

      {/* Right cluster */}
      <div className="ml-auto flex items-center gap-2">
        {/* Device status */}
        <div className="flex items-center gap-2 pl-2.5 pr-3 h-9 rounded-xl border border-white/[0.05] bg-white/[0.025]">
          <span className={`relative inline-block w-1.5 h-1.5 rounded-full pulse-ring ${connected ? "bg-emerald-400 text-emerald-400" : "bg-slate-500 text-slate-500"}`}/>
          <span className="font-display text-[12.5px] tracking-[0.04em] text-slate-100">WIN 60 HE</span>
          <span className={`font-mono text-[9.5px] uppercase tracking-[0.2em] ml-1 ${connected ? "text-emerald-300/85" : "text-slate-500"}`}>{connected ? "Linked" : "Offline"}</span>
        </div>

        {/* Auto-connect on launch */}
        <label className="flex items-center gap-1.5 pl-2 pr-2.5 h-9 rounded-xl border border-white/[0.05] bg-white/[0.025] cursor-pointer select-none"
               title="Connect to the keyboard automatically when the app opens">
          <span onClick={() => setAutoConnect(!autoConnect)}
                className={`w-3.5 h-3.5 rounded border grid place-items-center transition
                            ${autoConnect ? "border-[var(--accent)] bg-[var(--accent)]/20" : "border-white/15 bg-white/[0.02]"}`}>
            {autoConnect && <ICheck size={9} className="text-[var(--accent)]"/>}
          </span>
          <span className="font-display text-[10px] uppercase tracking-[0.16em] text-slate-400">Auto</span>
        </label>

        {/* Theme btn */}
        <button onClick={onOpenTheme}
          className="flex items-center gap-2 pl-2.5 pr-3 h-9 rounded-xl border border-white/[0.05] bg-white/[0.025] text-slate-300 hover:text-white hover:border-white/15 transition-colors">
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

        <button title="Settings"
          className="w-9 h-9 rounded-xl border border-white/[0.05] bg-white/[0.025] text-slate-400 hover:text-white hover:border-white/15 grid place-items-center transition-colors">
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
    <div className="inline-flex gap-1 p-1 rounded-2xl border border-white/[0.05] bg-white/[0.02] backdrop-blur-md">
      {NAV.map(n => {
        const active = section === n.id;
        return (
          <button key={n.id} onClick={() => setSection(n.id)}
            className={`relative flex items-center gap-2 px-4 h-9 rounded-xl font-display text-[12px] uppercase tracking-[0.18em] transition-all
                        ${active ? "pill-active" : "text-slate-400 hover:text-slate-100 hover:bg-white/[0.03]"}`}>
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
        <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-slate-500">{breadcrumb}</div>
        {badge}
      </div>
      {children}
    </div>
  </section>
);

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
    try { return localStorage.getItem("aether-autoconnect") === "1"; } catch { return false; }
  });
  const [section, setSection] = useState("actuation");
  const [profile, setProfile] = useState("p1");
  const [layer, setLayer] = useState("default");

  // Empty by default → actuation/dead-band/switch apply to ALL keys until you
  // pick a subset (set_trigger_codes treats an empty selection as every key).
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

  const [colors, setColors] = useState(["#a6143a"]);   // darker default (user pref)
  const [bgColor, setBgColor] = useState("#000000");
  const [perKeyColors, setPerKeyColors] = useState({});
  const [zones, setZones] = useState([]);   // effect zones for Custom mode
  const [pattern, setPattern] = useState("twinkle");
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

  // Editable per-profile names (persisted globally).
  const [profileNames, setProfileNames] = useState(() => {
    try { return JSON.parse(localStorage.getItem("aether-profile-names")) || {}; }
    catch { return {}; }
  });
  useEffect(() => {
    try { localStorage.setItem("aether-profile-names", JSON.stringify(profileNames)); } catch {}
  }, [profileNames]);

  // ---- per-profile persistence: every setting saved under its profile and
  // reloaded on switch, so profiles keep their own settings (and survive reload).
  const applyingRef = useRef(false);
  const applySettings = (s) => {
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
  useEffect(() => {                       // load on profile change / mount
    try {
      const s = JSON.parse(localStorage.getItem("aether-profile-" + profile));
      if (s) applySettings(s);
    } catch {}
  }, [profile]);
  useEffect(() => {                       // save (skipped while a load is applying)
    if (applyingRef.current) return;
    const s = { pattern, colors, bgColor, brightness, speed, power, fullColor, direction,
      striOrient, bgBright, perKeyColors, zones, actuation, rtPress, rtRelease, rtEnabled, polling,
      deadTop, deadBottom, switchId, socdProfiles, socdActive, hotkeyEnabled, socdMode, layer,
      gamepadMap };
    try { localStorage.setItem("aether-profile-" + profile, JSON.stringify(s)); } catch {}
  }, [profile, pattern, colors, bgColor, brightness, speed, power, fullColor, direction,
      striOrient, bgBright, perKeyColors, zones, actuation, rtPress, rtRelease, rtEnabled, polling,
      deadTop, deadBottom, switchId, socdProfiles, socdActive, hotkeyEnabled, socdMode, layer,
      gamepadMap]);

  const keyboardMode = section === "actuation" ? "actuation"
                      : section === "lighting" ? "lighting"
                      : section === "socd"     ? "socd"
                                                : "keymap";

  const ledMap = useMemo(() => {
    if (section !== "lighting") return {};
    const m = {};
    // Effect color depends on pattern. For "static" all keys = colors[0].
    // For others we cycle palette across keys. bgColor underlies un-effect keys.
    window.AetherKeyboard.KB_ROWS.flat().forEach(([_, __, code], idx) => {
      if (perKeyColors[code]) { m[code] = perKeyColors[code]; return; }
      if (pattern === "static") { m[code] = colors[0]; return; }
      // Simulated effect: every nth key gets an effect color, rest = bg
      const hit = (idx % 6 === 0) || colors.length === 1;
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
      apiCall("disconnect")
        .then(() => { setConnected(false); setLiveDepths(null); })
        .finally(() => setConnecting(false));
    } else {
      apiCall("connect")
        .then(r => setConnected(!!(r && r.ok)))
        .finally(() => setConnecting(false));
    }
  };

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
    if (getApi()) go();
    else window.addEventListener("pywebviewready", go, { once: true });
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
    if (pattern === "custom") return;   // custom effect (below) owns the engine
    clearTimeout(lightTimer.current);
    lightTimer.current = setTimeout(() => {
      const bf = Math.max(0, Math.min(1, bgBright / 100));
      const bgScaled = hexToRgbArr(bgColor).map(c => Math.round(c * bf));
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
  }, [connected, pattern, colors, bgColor, brightness, speed, power, fullColor, direction, bgBright, striOrient, lightNonce, calibrating]);

  // Custom mode: effect zones if any are defined (each key group runs its own
  // animated effect), otherwise static per-key colors.
  useEffect(() => {
    if (!connected || pattern !== "custom") return;
    if (zones.length) {
      const bf = Math.max(0, Math.min(1, bgBright / 100));
      const bgScaled = hexToRgbArr(bgColor).map(c => Math.round(c * bf));
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
      apiCall("set_custom_colors", map, briByte(brightness), spdByte(speed));
    }
  }, [connected, pattern, perKeyColors, brightness, speed, zones, direction, bgColor, bgBright, lightNonce, calibrating]);

  // Actuation / Rapid Trigger for the selected keys. Guarded to the Actuation
  // tab and `section` is not a dep, so tab switches don't push trigger packets.
  const trigTimer = useRef(null);
  useEffect(() => {
    if (!connected || section !== "actuation") return;
    const codes = Array.from(selectedKeys);
    clearTimeout(trigTimer.current);
    trigTimer.current = setTimeout(() => {
      // Firmware trigger mode (from the driver): 0 = fixed actuation point,
      // 13 = rapid trigger with separate press/release sensitivity. (The old
      // hardcoded "2" was invalid, so the board ignored the actuation setting.)
      const mode = rtEnabled ? 13 : 0;
      apiCall("set_trigger_codes", codes, actuation, rtEnabled ? rtPress : 0, rtEnabled ? rtRelease : 0, mode);
    }, 90);
    return () => clearTimeout(trigTimer.current);
  }, [connected, actuation, rtEnabled, rtPress, rtRelease, selectedKeys]);

  // Dead band for the selected keys (applies when the band sliders move).
  const deadTimer = useRef(null);
  useEffect(() => {
    if (!connected || section !== "actuation") return;
    clearTimeout(deadTimer.current);
    deadTimer.current = setTimeout(() => {
      apiCall("set_deadband_codes", Array.from(selectedKeys), deadTop, deadBottom);
    }, 110);
    return () => clearTimeout(deadTimer.current);
  }, [connected, deadTop, deadBottom, selectedKeys]);

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
        if (alive && d && typeof d === "object" && !(d.ok === false)) setLiveDepths(d);
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
  // The host engine streams cmd-9 pages to the board at 120fps under the GIL;
  // a tight polling loop here starves it and makes the board look choppy.
  // 50ms (~20fps) is plenty for the on-screen mirror and leaves the engine room.
  useEffect(() => {
    if (!connected || section !== "lighting") { setLightFrame(null); return; }
    let alive = true;
    const id = setInterval(() => {
      apiCall("get_light_frame").then(f => {
        if (!alive) return;
        setLightFrame(f && typeof f === "object" && !(f.ok === false) && Object.keys(f).length ? f : null);
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
    const profName = PROFILES.find(p => p.id === profile)?.name || "Profile";
    const secName = NAV.find(n => n.id === section)?.label || "";
    return `${profName} · ${secName}`;
  }, [profile, section]);

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
    <div className="flex items-center gap-2 p-1 rounded-xl border border-white/[0.06] bg-white/[0.02]">
      {["default","fn"].map(l => (
        <button key={l} onClick={() => setLayer(l)}
          className={`px-3 h-7 rounded-lg font-display text-[11px] uppercase tracking-[0.16em] transition-all
                      ${layer === l
                        ? "bg-[var(--accent)] text-[var(--accent-fg)] shadow-[0_0_14px_var(--accent-glow)]"
                        : "text-slate-400 hover:text-slate-100"}`}>
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

  return (
    <>
      <TopBar
        profile={profile} setProfile={setProfile}
        profileNames={profileNames}
        onRenameProfile={(id, name) => setProfileNames(n => ({ ...n, [id]: name }))}
        connected={connected} connecting={connecting} onTogglePair={togglePair}
        autoConnect={autoConnect} setAutoConnect={setAutoConnect}
        onOpenTheme={() => setThemeOpen(true)}
      />

      <main className="max-w-[1400px] mx-auto px-6 lg:px-10 py-7 flex flex-col gap-6">
        <SectionNav section={section} setSection={setSection}/>

        <HeroCard breadcrumb={breadcrumb} badge={heroBadge}>
          <KeyboardPanel
            mode={keyboardMode}
            layer={layer}
            selectedKeys={selectedKeys}
            setSelectedKeys={setSelectedKeys}
            actuationPoint={actuation}
            rtPress={rtEnabled ? rtPress : 0}
            rtRelease={rtEnabled ? rtRelease : 0}
            ledMap={ledMapLive || ledMap}
            accent={theme.accent}
            showPill={false}
            leftSlot={leftSlot}
            liveDepths={liveDepths}
            calibrating={calibrating}
            calibratedCodes={calibratedKeys}
          />
        </HeroCard>

        {/* Section content card */}
        <section key={section} className="surface rounded-3xl px-6 lg:px-10 py-7 section-anim">
          {section === "keymap"    && (
            <KeymapSection
              selectedKey={selectedKey}
              selectedCount={selectedKeys.size}
              onRemap={(label) => {
                const hid = HID_BY_LABEL[label];
                if (connected && hid != null && selectedKeys.size)
                  apiCall("set_remap", Array.from(selectedKeys), hid);
              }}
              onResetKey={() => {
                if (connected && selectedKeys.size)
                  apiCall("reset_remap", Array.from(selectedKeys));
              }}
            />
          )}
          {section === "actuation" && (
            <ActuationSection
              actuation={actuation} setActuation={setActuation}
              rtPress={rtPress} setRtPress={setRtPress}
              rtRelease={rtRelease} setRtRelease={setRtRelease}
              rtEnabled={rtEnabled} setRtEnabled={setRtEnabled}
              polling={polling} setPolling={handleSetPolling}
              travelTest={travelTest} setTravelTest={setTravelTest}
              calibrating={calibrating} onCalibrate={handleCalibrate}
              deadTop={deadTop} setDeadTop={setDeadTop}
              deadBottom={deadBottom} setDeadBottom={setDeadBottom}
              switchId={switchId} onPickSwitch={handlePickSwitch}
              liveDepth={liveMax}
              selectedCount={selectedKeys.size}
            />
          )}
          {section === "lighting" && (
            <LightingSection
              colors={colors} setColors={setColors}
              bgColor={bgColor} setBgColor={setBgColor}
              perKeyColors={perKeyColors} setPerKeyColors={setPerKeyColors}
              pattern={pattern} setPattern={setPattern}
              brightness={brightness} setBrightness={setBrightness}
              speed={speed} setSpeed={setSpeed}
              power={power} setPower={setPower}
              fullColor={fullColor} setFullColor={setFullColor}
              direction={direction} setDirection={setDirection}
              striOrient={striOrient} setStriOrient={setStriOrient}
              bgBright={bgBright} setBgBright={setBgBright}
              zones={zones} onAddZone={addZone} onUpdateZone={updateZone} onRemoveZone={removeZone}
              selectedKeys={selectedKeys}
              onSelectAll={() => {
                const all = new Set(window.AetherKeyboard.KB_ROWS.flat().map(([_,__,c]) => c));
                setSelectedKeys(all);
              }}
              onClearSelection={() => setSelectedKeys(new Set())}
            />
          )}
          {section === "socd" && (
            <SOCDSection
              socdMode={socdMode} setSocdMode={setSocdMode}
              hotkey={hotkey}
              hotkeyEnabled={hotkeyEnabled} setHotkeyEnabled={setHotkeyEnabled}
              onApply={handleSocdApply}
              profiles={socdProfiles} setProfiles={setSocdProfiles}
              active={socdActive} setActive={setSocdActive}
            />
          )}
          {section === "gamepad" && (
            <GamepadSection
              connected={connected}
              enabled={gamepadOn} onToggle={handleGamepadToggle}
              map={gamepadMap} onApplyMap={handleGamepadMapApply}
              defaultMap={DEFAULT_PAD_MAP}
              error={gamepadError} onInstallDriver={handleInstallVigem}
            />
          )}
          {section === "other" && <OtherSection/>}
        </section>
      </main>

      {/* Theme Customizer popup */}
      <ThemePopup open={themeOpen} onClose={() => setThemeOpen(false)} theme={theme} setTheme={setTheme}/>
    </>
  );
}

const Stat = ({ label, value }) => (
  <div className="flex items-baseline gap-1.5 px-3 py-1.5 rounded-xl border border-white/[0.05] bg-white/[0.02]">
    <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-slate-500">{label}</span>
    <span className="font-mono text-[12px] text-slate-100">{value}</span>
  </div>
);

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
})();
