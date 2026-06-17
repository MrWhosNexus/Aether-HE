# Submit your keyboard to Aether

Aether started as a controller for **one** board (the Aula Win60 HE). The goal now is
to support **many** — and the fastest way there is you. If you submit a bit of info
about your keyboard, your board's layout gets drawn into the app, and from there we
work together to light it up, tune actuation, and add the rest.

**You do not need to be technical to help.** There are two tiers:

| Tier | Who | What you give | What it gets you |
|------|-----|---------------|------------------|
| 🟢 **Required** | Anyone | Model, VID/PID, photos, your OS | Your board on the roadmap + its layout drawn |
| 🔵 **Advanced (optional)** | Comfortable with a terminal | HID dump, `keymap.json`, protocol captures | Your board becomes *buildable* much faster |

Fill in what you can. The maintainer handles the hard parts for everyone else.

👉 **The easiest way to submit is the [Add my keyboard issue form](https://github.com/MrWhosNexus/Aether-HE/issues/new?template=add-a-board.yml).**
This doc explains each field and gives copy-paste templates.

---

## 🟢 Required info (everyone)

### 1. Brand & exact model
Whatever is printed on the box or the underside label — e.g. `Aula F75`, `Womier SK71`.

### 2. Switch type & size
Hall-effect/magnetic, mechanical, or optical — and the form factor (60%, 65%, 75%, TKL…).
Hall-effect boards get adjustable actuation and rapid-trigger; mechanical boards get
lighting and remapping.

### 3. USB VID & PID
Two short hex numbers that identify your board to the computer. Easiest way:

```bash
# from the repo root, with deps installed (pip install -r requirements.txt)
python tools/list_hid.py
```

Find your keyboard in the list and copy the `VID:PID` line (e.g. `2E3C:C365`).

<details>
<summary>No Python? Get VID/PID from the OS instead</summary>

- **Windows:** Device Manager → Keyboards / HID devices → your board → *Properties* →
  *Details* → *Hardware Ids*. Look for `HID\VID_2E3C&PID_C365` — those are your VID and PID.
- **Linux:** run `lsusb` and find your board; the `ID 2e3c:c365` part is `VID:PID`.
- **macOS:** *System Information* → *USB* → select the keyboard → *Vendor ID* / *Product ID*.
</details>

### 4. Official software / driver
The app you use today to control the board's lighting or actuation (name + download link).
This is the single most useful thing for the advanced work — the protocol is reverse-engineered
from watching what that app sends.

### 5. Photos
- A clear **top-down** photo of the whole board (used to draw the layout).
- A photo of the **underside label** (confirms model + IDs).

### 6. Your OS
Windows / Linux / macOS — so we know where to test with you.

That's it for the required tier. [Open the issue form](https://github.com/MrWhosNexus/Aether-HE/issues/new?template=add-a-board.yml) and you're done. 🎉

---

## 🔵 Advanced (optional) — speeds everything up

Each item below is independent. Do any subset.

### A. HID interface dump
Tells Aether *which* interface to talk to. Paste the full output of:

```bash
python tools/list_hid.py 2E3C        # your VID in hex; or just `python tools/list_hid.py`
```

The interface flagged `usage_page >= 0xFF00` (e.g. `0xFF1B` on Aula) is almost always the
vendor "config" collection lighting/actuation commands go to.

### B. Layout — `keymap.json`
This is the heart of "your board layout." Aether describes every key in one JSON file
(`ui/keymap.json`). Each key has:

| Field | Meaning |
|-------|---------|
| `index` | **Firmware key index** — the number the board uses internally to address this key (for per-key RGB and travel reports). See *Finding the stride* below. |
| `name` | Label shown on the key, e.g. `"Esc"`, `"1!"`. |
| `code` | Logical key code (Chromium-style), e.g. `"Escape"`, `"Digit1"`, `"KeyQ"`. Use `"KeyFn"` for the Fn/layer key. |
| `hidCode` | USB HID usage code in hex, e.g. `"29"` for Esc. ([HID usage table reference](https://usb.org/sites/default/files/hut1_5.pdf), §10.) |
| `x`, `y` | Top-left pixel position in the diagram (any consistent scale; ~38px per 1u works well). |
| `width`, `height` | Key size in pixels (a 1u key ≈ `35`; spacebar is much wider). |

Copy-paste skeleton (first row shown — extend for your whole board):

```json
{
  "type": "us",
  "keys": [
    {"index": "22", "name": "Esc", "code": "Escape", "hidCode": "29", "width": "35", "height": "35", "x": "10",  "y": "15"},
    {"index": "23", "name": "1!",  "code": "Digit1", "hidCode": "1E", "width": "35", "height": "35", "x": "48",  "y": "15"},
    {"index": "24", "name": "2@",  "code": "Digit2", "hidCode": "1F", "width": "35", "height": "35", "x": "86",  "y": "15"}
  ]
}
```

> Don't want to hand-build JSON? **Just send the top-down photo.** The maintainer can
> trace the layout from it — this template is for people who'd rather do it themselves.

### C. Finding the stride (the `index` numbers)
Most of these boards address keys as a matrix: `index = row * STRIDE + column`. On the Aula
Win60 the stride is **22** (so row 0 starts at index 0, row 1 at 22, row 2 at 44…). The Aula
keymap happens to start its first visible key at index 22 (second matrix row).

To find your stride, use **travel/actuation reports** (Hall-effect boards): press keys one at
a time while watching the vendor app's device log, and note the per-key index it reports.
Two keys in the same column, one row apart, differ by exactly the stride. If you're not sure,
leave it blank and note "stride unknown" — it can be derived during bring-up.

### D. Protocol captures
The reverse-engineering gold. Capture what the official app sends for:
- **Lighting** — set a solid color / change an effect and capture the HID report.
- **Actuation** — change the actuation point (Hall-effect boards).
- **Per-key RGB** — set individual key colors, if the app supports it.

How to capture:
- **WebHID drivers (run in Chrome/Edge):** open `chrome://device-log`, reproduce the action,
  and copy the `sendReport`/`HID` lines. (This is exactly how the Aula protocol was decoded —
  see `docs/context/aula-win60-protocol-capture.md`.)
- **Native drivers:** use **Wireshark + USBPcap** (Windows) or **`usbmon`/Wireshark** (Linux)
  to record the USB traffic while you change a setting.

Paste the logs or attach the capture files. Even one clean "set solid red" capture is hugely
useful.

---

## What happens after you submit

1. **Triaged** — your board gets the `new-board` label and lands on the roadmap.
2. **Layout drawn** — your `keymap.json` is added (from your file or your photo).
3. **Bring-up, together** — we wire the protocol (using your captures, or by decoding the
   official driver) and you test development builds on your actual hardware.
4. **Shipped** — your board becomes a first-class Aether target, and your captures help the
   next person with a similar board.

The more of the 🔵 advanced tier you can provide, the faster step 3 goes — but the 🟢 required
tier alone is enough to get started. Thank you for getting involved. 🙌

---

### Reference: how Aether is wired today
For the curious, the existing Aula implementation is the template every new board follows:
- Device identity & interface selection — [`aula_device.py`](../aula_device.py) (`AULA_VID`, `AULA_PID`, `find_vendor_interface`).
- Reverse-engineered packet builders — [`protocol.py`](../protocol.py).
- Key index ↔ name ↔ xy mapping — [`device_state.py`](../device_state.py) (`KeyMap`) + [`ui/keymap.json`](../ui/keymap.json).
- Protocol/effect engineering notes — [`docs/context/`](context/).
