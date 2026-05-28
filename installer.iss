; Inno Setup script for AETHER HE.
; Build:  iscc installer.iss
; Output: dist\AetherHE-Setup.exe (single-file installer with Start Menu /
; Desktop shortcuts, Add/Remove Programs entry, ViGEmBus auto-install on
; first run, and a proper uninstaller).

#define MyAppName        "AETHER HE"
#define MyAppVersion     "0.1.10"
#define MyAppPublisher   "MrWhosNexus"
#define MyAppURL         "https://github.com/MrWhosNexus/aether-linux-app"
#define MyAppExeName     "AetherHE.exe"
#define MyOutputDir      "dist"

[Setup]
AppId={{F3A4D8C2-6E22-4F4B-8C5E-7B8A1E2D3F40}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\AetherHE
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#MyOutputDir}
OutputBaseFilename=AetherHE-Setup
SetupIconFile=ui\assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startmenuicon"; Description: "Create a Start &Menu shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "autostart"; Description: "Start {#MyAppName} when I sign in to Windows"; GroupDescription: "Startup:"; Flags: unchecked
Name: "installvigem"; Description: "Install ViGEmBus driver (needed for virtual gamepad)"; GroupDescription: "Drivers:"; Flags: checkedonce

[Files]
; Bundle the entire PyInstaller output (AetherHE.exe + _internal/).
Source: "dist\AetherHE\AetherHE.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AetherHE\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Auto-start at login if the user asked for it.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AetherHE"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; ViGEmBus kernel driver (silent /quiet install). Skipped if user unchecked.
Filename: "{app}\_internal\vendor\ViGEmBus_Setup.exe"; Parameters: "/quiet /norestart"; StatusMsg: "Installing ViGEmBus driver..."; Flags: waituntilterminated; Tasks: installvigem
; Offer to launch on Finish.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Best-effort cleanup of the autostart key (the [Registry] uninsdeletevalue
; already handles it, but if the user enabled autostart from inside the app
; it lives under the same value name).
Filename: "{cmd}"; Parameters: "/C reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v AetherHE /f"; Flags: runhidden
