# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

datas = [
    ("ui", "ui"),
    ("data", "data"),
    ("vendor/ViGEmBus_Setup.exe", "vendor"),
]
datas += collect_data_files("vgamepad")
binaries = collect_dynamic_libs("vgamepad")

hidden = [
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
    "validate_keymap",
]

a = Analysis(
    ["app_web.py"],
    pathex=["tools"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "customtkinter", "tkinter",
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
    console=False,
    icon="ui/assets/logo.ico",
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
