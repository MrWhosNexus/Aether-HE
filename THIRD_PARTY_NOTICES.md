# Third-party notices

Aether HE is GPL-3.0-or-later. It includes or is built with the following
open-source components, each under its own license. Their license texts are
available at the links below and inside the respective packages in the
installed app's `_internal` folder.

## Bundled in the user interface

| Component | Version | License |
|---|---|---|
| [React](https://github.com/facebook/react) and React DOM | 18.3.1 | MIT |
| [Babel standalone](https://github.com/babel/babel) (build-time JSX compiler) | 7.x | MIT |
| [Tailwind CSS browser build](https://github.com/tailwindlabs/tailwindcss) | 4.3.0 | MIT |
| Icons in the style of [Lucide](https://github.com/lucide-icons/lucide) | - | ISC |
| [Inter](https://github.com/rsms/inter), [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono), [Rajdhani](https://fonts.google.com/specimen/Rajdhani) fonts | - | SIL Open Font License 1.1 |

## Bundled in the Windows app (Python packages)

| Component | License |
|---|---|
| [Python](https://www.python.org/) runtime | PSF License |
| [pywebview](https://github.com/r0x0r/pywebview) | BSD-3-Clause |
| [pythonnet](https://github.com/pythonnet/pythonnet), clr_loader | MIT |
| [hidapi](https://github.com/trezor/cython-hidapi) (cython-hidapi + HIDAPI) | BSD-3-Clause / GPL-3.0 (used under GPL-3.0-compatible terms) |
| [vgamepad](https://github.com/yannbouteiller/vgamepad) | MIT |
| [pystray](https://github.com/moses-palmer/pystray) | LGPL-3.0 (shipped as a separate, replaceable module) |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause (and bundled BSD/MIT/Zlib components) |
| [SoundCard](https://github.com/bastibe/SoundCard) | BSD-3-Clause |
| [cffi](https://github.com/python-cffi/cffi), pycparser | MIT-0, BSD-3-Clause |
| bottle, proxy_tools, six, typing_extensions | MIT / PSF |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) bootloader | GPL-2.0-or-later with the PyInstaller exception |

On Linux, evdev and pyusb (BSD) are used from the system or virtual
environment.

## Redistributed driver installer

| Component | License |
|---|---|
| [ViGEmBus](https://github.com/nefarius/ViGEmBus) installer (virtual gamepad bus driver, installed only if you choose to) | BSD-3-Clause, Copyright (c) Nefarius Software Solutions e.U. |

## Microsoft Edge WebView2

The Windows app uses the WebView2 runtime that ships with Windows 10/11. It is
not redistributed by Aether.
