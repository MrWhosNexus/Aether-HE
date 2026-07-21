(() => {
/* ============================================================
   Settings workspace — app configuration & profile management.
   Exports window.AetherWorkspaces.SETTINGS_WIDGETS — an array of widget descriptors:
     { id, title, default:{x,y,w,h}, min:{w,h}, render:(ctx)=>JSX }
   Each render() reads/calls ONLY ctx.* (state + handlers app.jsx passes down).
   ============================================================ */
const { useState, useEffect } = React;
const S = window.AetherSections || {};
const Slider = S.Slider, Chip = S.Chip, SubTabs = S.SubTabs, ToolbarButton = S.ToolbarButton;
const I = window.AetherIcons || {};
const ICheck = I.ICheck, IPlus = I.IPlus, ITrash = I.ITrash, IEdit = I.IEdit,
      IDownload = I.IDownload, IRefresh = I.IRefresh, ISettings = I.ISettings;

/* ===== Profiles widget ===== */
function ProfilesWidget(ctx) {
  const {
    profiles = [],
    activeId,
    activeProfileName = "Default",
    switchProfile,
    renameProfile,
    addProfile,
    duplicateProfile,
    deleteProfile,
  } = ctx;
  const [editId, setEditId] = useState(null);
  const [editName, setEditName] = useState("");
  const [toast, setToast] = useState(null);

  const flash = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2400);
  };

  const handleAdd = () => {
    if (addProfile) {
      addProfile();
      flash("Profile added");
    }
  };

  const handleSwitch = (id) => {
    if (switchProfile) {
      switchProfile(id);
    }
  };

  const handleStartEdit = (id, name) => {
    setEditId(id);
    setEditName(name);
  };

  const handleSaveEdit = (id) => {
    if (editName.trim() && renameProfile) {
      renameProfile(id, editName.trim());
      setEditId(null);
      flash(`Renamed to "${editName.trim()}"`);
    }
  };

  const handleDuplicate = (id) => {
    if (duplicateProfile) {
      duplicateProfile(id);
      flash("Profile duplicated");
    }
  };

  const handleDelete = (id) => {
    if (deleteProfile && profiles.length > 1) {
      deleteProfile(id);
      flash("Profile deleted");
    }
  };

  return (
    <div>
      <div className="mb-4">
        <div className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)] mb-2">
          Profile Management
        </div>
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="text-[13px] text-[var(--text)]">{profiles.length} profile{profiles.length !== 1 ? "s" : ""}</div>
          <button onClick={handleAdd}
            className="px-2.5 h-8 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[10.5px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25">
            {IPlus && <span className="inline mr-1">{IPlus && "+"}</span>}Add
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2 mb-4">
        {profiles.map(p => {
          const isActive = activeId === p.id;
          const isEditing = editId === p.id;
          return (
            <div key={p.id} className={`rounded-lg border p-3 transition-all ${
              isActive
                ? "border-[var(--accent)]/50 bg-[var(--accent)]/[0.06]"
                : "border-[var(--line)] bg-white/[0.02]"
            }`}>
              <div className="flex items-center justify-between gap-2">
                {isEditing ? (
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSaveEdit(p.id);
                      if (e.key === "Escape") setEditId(null);
                    }}
                    className="flex-1 h-7 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/10 px-2 text-[12px] text-[var(--text)] font-display outline-none"
                    autoFocus
                  />
                ) : (
                  <button onClick={() => handleSwitch(p.id)}
                    className={`flex-1 text-left px-2 h-7 rounded-md border transition-all ${
                      isActive
                        ? "border-[var(--accent)]/50 bg-[var(--accent)]/10 text-[var(--accent)]"
                        : "border-transparent bg-white/[0.02] text-[var(--text)] hover:border-[var(--line)]"
                    } font-display text-[12px]`}>
                    {p.name || "Untitled"}
                    {isActive && <span className="ml-2 text-[10px]">✓</span>}
                  </button>
                )}
                <div className="flex items-center gap-1">
                  {isEditing ? (
                    <>
                      <button onClick={() => handleSaveEdit(p.id)}
                        className="w-6 h-6 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] flex items-center justify-center text-[11px]">
                        ✓
                      </button>
                      <button onClick={() => setEditId(null)}
                        className="w-6 h-6 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] flex items-center justify-center text-[11px]">
                        ✕
                      </button>
                    </>
                  ) : (
                    <>
                      <button onClick={() => handleStartEdit(p.id, p.name || "Untitled")}
                        className="w-6 h-6 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] flex items-center justify-center text-[10px]"
                        title="Rename">
                        {IEdit ? "✎" : "E"}
                      </button>
                      <button onClick={() => handleDuplicate(p.id)}
                        className="w-6 h-6 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] flex items-center justify-center text-[9px]"
                        title="Duplicate">
                        ◈
                      </button>
                      <button onClick={() => handleDelete(p.id)} disabled={profiles.length <= 1}
                        className="w-6 h-6 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] hover:border-rose-400/40 hover:text-rose-300 disabled:opacity-40 flex items-center justify-center text-[10px]"
                        title="Delete">
                        ✕
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {toast && (
        <div className="mt-2 text-[11px] font-mono uppercase tracking-[0.16em] text-[var(--accent)]">
          ✓ {toast}
        </div>
      )}
    </div>
  );
}

/* ===== Theme widget ===== */
function ThemeWidget(ctx) {
  const {
    theme = "dark",
    setTheme,
    setThemeOpen,
  } = ctx;

  const themes = [
    { id: "dark", label: "Dark", desc: "Dim background, bright accents" },
    { id: "light", label: "Light", desc: "Bright background, muted accents" },
    { id: "auto", label: "Auto", desc: "Match system preference" },
  ];

  return (
    <div>
      <div className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)] mb-3">
        Appearance
      </div>

      <div className="flex flex-col gap-2 mb-4">
        {themes.map(t => (
          <button key={t.id} onClick={() => setTheme && setTheme(t.id)}
            className={`text-left rounded-lg border p-2.5 transition-all ${
              theme === t.id
                ? "border-[var(--accent)]/50 bg-[var(--accent)]/[0.06]"
                : "border-[var(--line)] bg-white/[0.02] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)]"
            }`}>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-display text-[12px] text-[var(--text)]">{t.label}</div>
                <div className="font-mono text-[10px] text-[var(--text-faint)] mt-0.5">{t.desc}</div>
              </div>
              {theme === t.id && <span className="text-[var(--accent)]">✓</span>}
            </div>
          </button>
        ))}
      </div>

      <button onClick={() => setThemeOpen && setThemeOpen(true)}
        className="w-full h-9 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[11px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25 transition-all">
        Customize Colors
      </button>
    </div>
  );
}

/* ===== Backup/Import widget ===== */
function BackupWidget(ctx) {
  const { applyState } = ctx;
  const [message, setMessage] = useState("");

  const handleExport = () => {
    try {
      const state = {
        timestamp: new Date().toISOString(),
        app: "AetherHE",
        profiles: [],
        settings: {},
      };
      const json = JSON.stringify(state, null, 2);
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `aether-backup-${Date.now()}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setMessage("Settings exported");
      setTimeout(() => setMessage(""), 2400);
    } catch (e) {
      setMessage("Export failed");
      setTimeout(() => setMessage(""), 2400);
    }
  };

  const handleImport = async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/json";
    input.onchange = async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        if (applyState && typeof applyState === "function") {
          applyState(data);
          setMessage("Settings imported");
          setTimeout(() => setMessage(""), 2400);
        }
      } catch (err) {
        setMessage("Import failed");
        setTimeout(() => setMessage(""), 2400);
      }
    };
    input.click();
  };

  return (
    <div>
      <div className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)] mb-3">
        Settings
      </div>

      <p className="text-[11.5px] text-[var(--text-faint)] leading-relaxed mb-4">
        Export or import your configuration. Backups include profiles, keymaps, lighting effects, and all settings.
      </p>

      <div className="flex flex-col gap-2">
        <button onClick={handleExport}
          className="h-9 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[11px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25 transition-all">
          {IDownload ? "↓" : "Export"} Export
        </button>
        <button onClick={handleImport}
          className="h-9 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[11px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25 transition-all">
          {IDownload ? "↑" : "Import"} Import
        </button>
      </div>

      {message && (
        <div className="mt-3 text-[11px] font-mono uppercase tracking-[0.16em] text-[var(--accent)]">
          ✓ {message}
        </div>
      )}
    </div>
  );
}

/* ===== About/Update widget ===== */
function AboutWidget(ctx) {
  const { setWizardOpen, setSubmitOpen } = ctx;
  const [version, setVersion] = useState("—");
  // `info` holds the check_update() result — apply_update REQUIRES the asset
  // url/name from it (Api.apply_update(asset_url, asset_name)); calling it bare
  // raises a missing-argument TypeError.
  const [updateState, setUpdateState] = useState({ phase: "idle", msg: "", info: null });

  useEffect(() => {
    const api = window.pywebview?.api;
    if (!api?.app_version) return;
    api.app_version().then(r => {
      if (r?.ok) setVersion(r.version);
    }).catch(() => {});
  }, []);

  const checkUpdate = async () => {
    const api = window.pywebview?.api;
    if (!api?.check_update) return;
    setUpdateState({ phase: "checking", msg: "Checking for updates…", info: null });
    try {
      const r = await api.check_update();
      if (!r?.ok) {
        // Surface the real reason (rate limit, offline, DNS) instead of a bare
        // "Check failed" — this is the only place the user can see it.
        setUpdateState({ phase: "error", msg: `Check failed: ${r?.error || "unknown error"}`, info: null });
        return;
      }
      // updater.check_for_update() returns `update` / `latest` / `asset_url`.
      // (It has never returned `available` or `version`: reading those meant
      // this button reported "You're up to date" even when a release existed.)
      if (r.update) {
        setUpdateState({ phase: "available", msg: `Update available: v${r.latest}`, info: r });
      } else if (r.newer) {
        // Newer release exists but ships no asset this OS can install.
        setUpdateState({ phase: "uptodate", msg: `v${r.latest} available, but no installer for this platform`, info: null });
      } else {
        setUpdateState({ phase: "uptodate", msg: "You're up to date", info: null });
      }
    } catch (e) {
      setUpdateState({ phase: "error", msg: `Check failed: ${e}`, info: null });
    }
  };

  const applyUpdate = async () => {
    const api = window.pywebview?.api;
    const info = updateState.info;
    if (!api?.apply_update || !info?.asset_url) return;
    setUpdateState(s => ({ ...s, phase: "installing", msg: "Downloading…" }));
    try {
      const r = await api.apply_update(info.asset_url, info.asset_name);
      if (!r?.ok) {
        setUpdateState(s => ({ ...s, phase: "error", msg: `Installation failed: ${r?.error || "unknown error"}` }));
        return;
      }
      // Windows launches the installer and the app must quit; Flatpak installs
      // in place and needs a manual restart. Say which one happened.
      const msg = r.quit ? "Installer launched — Aether will close and reopen."
                : r.restart ? "Update installed — quit and reopen Aether to apply it."
                : r.path ? `Downloaded to ${r.path}` : "Update complete";
      setUpdateState(s => ({ ...s, phase: "installed", msg }));
    } catch (e) {
      setUpdateState(s => ({ ...s, phase: "error", msg: `Installation failed: ${e}` }));
    }
  };

  const openWizard = () => {
    if (setWizardOpen) setWizardOpen(true);
  };

  return (
    <div>
      <div className="font-display text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)] mb-3">
        About
      </div>

      <div className="rounded-lg border border-[var(--line)] bg-white/[0.02] p-3 mb-4">
        <div className="flex items-baseline justify-between mb-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-faint)]">Version</span>
          <span className="font-display text-[13px] text-[var(--text)]">{version}</span>
        </div>
        <div className="font-mono text-[9px] text-[var(--text-faint)]">AetherHE Desktop Controller</div>
      </div>

      <div className="flex flex-col gap-2 mb-4">
        <button onClick={checkUpdate} disabled={updateState.phase === "checking"}
          className="h-9 rounded-md border border-[var(--accent)]/50 bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[11px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25 disabled:opacity-50 transition-all">
          {IRefresh ? "↻" : "Check"} Check for Updates
        </button>
        {(updateState.phase === "available" || updateState.phase === "installing") && (
          <button onClick={applyUpdate} disabled={updateState.phase === "installing"}
            className="h-9 rounded-md border border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--accent)] font-display text-[11px] uppercase tracking-[0.16em] hover:bg-[var(--accent)]/25 disabled:opacity-50 transition-all">
            {updateState.phase === "installing" ? "Installing…" : "Install Update"}
          </button>
        )}
        <button onClick={openWizard}
          className="h-9 rounded-md border border-[var(--line)] bg-white/[0.02] text-[var(--text-dim)] font-display text-[11px] uppercase tracking-[0.16em] hover:border-[color-mix(in_srgb,var(--accent)_30%,transparent)] transition-all">
          Setup Wizard
        </button>
        <button className="btn" onClick={() => setSubmitOpen && setSubmitOpen(true)}>
          Submit a board
        </button>
      </div>

      {updateState.msg && (
        <div className={`text-[11px] font-mono uppercase tracking-[0.16em] ${
          updateState.phase === "error" ? "text-rose-300" : "text-[var(--text-faint)]"
        }`}>
          {updateState.msg}
        </div>
      )}
    </div>
  );
}

/* ===== Widget array export ===== */
const SETTINGS_WIDGETS = [
  { id: "profiles", title: "Profiles",      default: { x: 40,  y: 32,  w: 380, h: 380 }, min: { w: 300, h: 280 }, render: ProfilesWidget },
  { id: "theme",    title: "Theme",         default: { x: 440, y: 32,  w: 340, h: 280 }, min: { w: 280, h: 220 }, render: ThemeWidget },
  { id: "backup",   title: "Backup",        default: { x: 40,  y: 432, w: 380, h: 240 }, min: { w: 300, h: 180 }, render: BackupWidget },
  { id: "about",    title: "About/Update",  default: { x: 440, y: 432, w: 340, h: 320 }, min: { w: 280, h: 240 }, render: AboutWidget },
];

window.AetherWorkspaces = window.AetherWorkspaces || {};
window.AetherWorkspaces.SETTINGS_WIDGETS = SETTINGS_WIDGETS;
})();
