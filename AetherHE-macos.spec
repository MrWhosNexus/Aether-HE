# PyInstaller spec for AETHER HE (macOS).
# Build:  ./build_macos.sh          (wraps: pyinstaller --clean --noconfirm AetherHE-macos.spec)
# Output: dist/AetherHE.app
#
# Deliberately separate from AetherHE.spec rather than branched inside it: the
# two platforms disagree on nearly every field (webview backend, gamepad payload,
# icon format, and .app vs onedir), so one file with sys.platform branches would
# be harder to read than two honest ones.
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from version import __version__

block_cipher = None

datas = [
    ("ui", "ui"),
    # Multi-board registry + board defs (boards.py reads HERE/data/...); without
    # this the frozen app can't resolve non-Win60 boards and warns on startup.
    ("data", "data"),
    # NOTE: no vendor/ViGEmBus_Setup.exe here — it is a Windows kernel driver and
    # macOS has no virtual-gamepad backend at all (gamepad.MACOS_UNSUPPORTED_REASON).
]

hidden = [
    # macOS renders through WKWebView via pyobjc, not Edge WebView2.
    "webview.platforms.cocoa",
    # device_state.py imports this via a runtime sys.path.insert(".../tools"),
    # which PyInstaller's static analysis can't follow — bundle it explicitly
    # (with tools/ on pathex so the module is resolvable at build time).
    "validate_keymap",
    # Resolved by NAME from data/board_registry.json's `protocol` field, so they
    # appear in NO static import graph. The Flatpak manifest copies them for the
    # same reason; tests/test_packaging.py pins both. Omitting them is the exact
    # bug class that shipped in 0.3.0 and nearly again in 0.4.0.
    "protocol",
    "protocol_mini60",
    "protocol_magnet",
    "protocol_sonix",
    "protocol_sayo",
]

a = Analysis(
    ["app_web.py"],
    pathex=["tools"],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Legacy Tk UI is not used by app_web.py — keep it out of the bundle.
        "customtkinter", "tkinter",
        # Pure-Python USB helper, not on the lighting/actuation hot path.
        "usb",
        # Windows/Linux gamepad backends: neither can exist on macOS, and
        # bundling them would make the "no backend" path look like a bug.
        "vgamepad", "evdev",
        # Windows webview stack.
        "clr_loader", "pythonnet",
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

app = BUNDLE(
    coll,
    name="AetherHE.app",
    icon="ui/assets/logo.icns",
    bundle_identifier="io.github.mrwhosnexus.AetherHE",
    version=__version__,
    info_plist={
        "CFBundleName": "AETHER HE",
        "CFBundleDisplayName": "AETHER HE",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        # pywebview's cocoa backend targets modern WKWebView; 11.0 is also the
        # floor for the arm64 slice this builds.
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSHumanReadableCopyright": "AETHER HE — MrWhosNexus",
        # A keyboard is not a camera: Input Monitoring (kTCCServiceListenEvent)
        # has NO Info.plist usage-description key, so there is deliberately none
        # here. The grant is made in System Settings; aula_device surfaces the
        # deep link when an open fails.
    },
)
