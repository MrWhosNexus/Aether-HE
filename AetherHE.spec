# PyInstaller spec for AETHER HE (Windows).
# Build:  venv-web\Scripts\pyinstaller --clean --noconfirm AetherHE.spec
# Output: dist\AetherHE\AetherHE.exe  (+ adjacent _internal\)
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

datas = [("ui", "ui")]
# vgamepad ships its ViGEm client DLL as package data; collect it so the frozen
# build can talk to the bus driver without an external install of the package.
datas += collect_data_files("vgamepad")
binaries = collect_dynamic_libs("vgamepad")

hidden = [
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
]

a = Analysis(
    ["app_web.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Legacy Tk UI is not used by app_web.py — keep it out of the bundle.
        "customtkinter", "tkinter",
        # Pure-Python USB helper, not on the lighting/actuation hot path.
        "usb",
    ],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AetherHE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                # no terminal window
    icon="ui/assets/logo.png" if False else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AetherHE",
)
