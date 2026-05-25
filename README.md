# AETHER HE — Aula WIN60 HE Controller (Linux / CachyOS)

Desktop controller for the Aula Win60 HE Hall-effect keyboard
(VID `0x2E3C`, PID `0xC365`). The UI is the exact **Claude Design**
("AETHER HE // Keyboard Hub") rendered natively; HID is bridged to Python.

## Run

```sh
./run.sh            # or:  venv-web/bin/python app_web.py
```

## Architecture

- **`app_web.py`** — renders `ui/index.html` (the standalone React/Tailwind
  design export) in a GTK/WebKit window via **pywebview**. WebKit has no WebHID,
  so a Python `Api` (`window.pywebview.api`) is exposed and an injected JS bridge:
  - **auto-connects** to the board (HID chip, bottom-right),
  - **mirrors** the on-screen keyboard's colors to the board's global lighting
    command (averaged — the hardware command is global),
  - uses real firmware lighting modes only; host/demo effect streaming is disabled.
- **`aula_device.py`** — thread-safe hidapi wrapper + decoded protocol
  (`build_lighting`, `build_select`, `parse_travel`).
- **`effects.py`** — legacy host-driven effects module, no longer exposed by the app.
- **`gamepad.py`** — analog key travel → virtual Xbox-style pad via uinput.
- `main.py` — earlier CustomTkinter reimplementation (superseded by the webview).

## Setup (one time)

```sh
# webview venv (needs system gi + WebKit2, so --system-site-packages)
python -m venv --system-site-packages venv-web
venv-web/bin/pip install pywebview hidapi evdev

# udev: keyboard HID + uinput (gamepad) without sudo
sudo cp 99-aula.rules 99-uinput.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG input "$USER"     # for /dev/uinput; re-login or `newgrp input`
```

## Status

| Feature | State |
|---|---|
| Exact design UI | ✅ rendered natively |
| Connect / status | ✅ auto-connect bridge |
| Lighting (color, static) | ✅ mirrored to board |
| Host/demo effects | Disabled |
| Analog gamepad | ✅ `gamepad.py` (needs uinput rule) |
| Actuation / SOCD / Remap / Profiles | ⬜ UI present; **HID wiring pending packet captures** |

## Capturing more protocol

The board's per-feature commands are reverse-engineered from the official
WebHID driver. See `capture_analog.js` and the notes in `aula_device.py`.
Actuation, SOCD, remap, and polling each need a capture before their controls
can drive hardware (lighting is the one fully wired).
