# WIN60 HE advanced keys: hardware capture checklist (for the user)

This checklist turns the SOURCE-ONLY decode in `aula-win60-advanced-keys-decode.md` into
wire evidence. You do it in the **vendor** web driver (https://hed.aulacn.com) with the
WIN 60 HE plugged in by USB. Aether stays closed the whole time, because only one program
should talk to the board. Budget about 20 minutes.

The vendor UI rewrites **both keymap layers, the macro table and all 40 advanced slots**
every time you press Apply. Your current remaps and macros are read from the board when the
page loads and written back unchanged. The last section removes everything this checklist
creates.

---

## A. Pick a capture method

### Method 1 (preferred): WebHID logging in the browser console
This sees only the vendor collection (usage page `0xFF1B`). **It never sees what you
type.**

1. Open https://hed.aulacn.com in Chrome or Edge and connect the keyboard as usual.
2. Press F12, open **Console**, paste the snippet below and press Enter. The console should
   print `Aether capture armed`.
3. Before each step below, type `__mark('D1')` (or whichever step it is) in the console.
   This labels the frames that follow.
4. When you are done, run `copy(JSON.stringify({frames: window.__aetherCap}))`. Paste the
   result into a new file, `docs/context/hed-aulacn-raw/webhid-capture-win60-advkeys.json`.
   The format matches the existing `webhid-capture-win60.json`.

```js
(() => {
  const log = window.__aetherCap = [];
  const hex = u8 => Array.from(u8, b => b.toString(16).padStart(2, '0')).join(' ');
  const u8of = d => d instanceof ArrayBuffer ? new Uint8Array(d)
                  : new Uint8Array(d.buffer, d.byteOffset, d.byteLength);
  window.__mark = name => log.push({dir: 'MARK', name, t: Date.now()});
  const send = HIDDevice.prototype.sendReport;
  HIDDevice.prototype.sendReport = function (id, data) {
    log.push({dir: 'OUT', reportId: id, hex: hex(u8of(data)), t: Date.now()});
    return send.call(this, id, data);
  };
  navigator.hid.getDevices().then(ds => ds.forEach(d => d.addEventListener('inputreport',
    e => log.push({dir: 'IN', reportId: e.reportId, hex: hex(u8of(e.data)), t: Date.now()}))));
  console.log('Aether capture armed');
})();
```

Limitations:
- A page reload clears the snippet, so step R1 (read-back after reload) needs Method 2.
  Alternatively, re-run the Playwright `addInitScript` harness used for the
  2026 `webhid-capture-win60.json` capture.
- If no `IN` lines appear, use Method 2 for the read-backs.

### Method 2: Wireshark + USBPcap (sees everything, including keystrokes)
1. Install Wireshark and tick **USBPcap** in its installer. Reboot if asked.
2. Start a capture on the USBPcap interface for the root hub the keyboard is on. If unsure,
   try each one and press a key.
3. Find the board's address with the display filter `usb.idVendor == 0x2e3c` (shown in the
   GET DESCRIPTOR response). Then use
   `usb.device_address == <addr> && (usb.capdata[0:2] == 01:22 || usb.capdata[0:2] == 01:18)`.
   On newer Wireshark the field is `usbhid.data`. Here the **first byte is the report id
   `01`**, so `01 22 …` on the wire is body `22 …` in this checklist.
4. If no interrupt OUT frames match, the browser is using control `SET_REPORT`. Add
   `|| usbhid.setup.bRequest == 0x09`.
5. **Privacy:** this method captures your typing too. Don't type anything private while it
   runs. Share only **File → Export Specified Packets** with the filter above applied.

---

## B. Steps, and what each frame should look like

Every body below is the 63-byte report body **without** the report id, with trailing zeros
omitted. `<n>` is the slot. Slots are assigned lowest-free-first, so on a board with no
advanced keys the three entries get slots 0, 1, 2 and the list labels them `1#DKS`, `2#MT`
and `3#TGL`.

Keymap entries are 4 bytes at `key_index*4` of the 528-byte layer. They are written as
`18 00 <chunkHi> <chunkLo> 38 …` with 56 bytes per chunk, so the entry is at body byte
`5 + (key_index*4) % 56` of chunk `(key_index*4) // 56`. Search the `18 00` frames for
`17 0n 0n 00`.

### R0: page load (baseline)
- **Do:** load the page and connect (or reload with Method 2 running).
- **Expect:** `OUT 22 80`, then 40 replies `IN 22 80 00 <00..27> 28 00 …`, all empty.
  Already confirmed by the old capture.

### D1: create a DKS and bind it
1. Open **Keys → Advanced** (`高级按键`, tab `keyManu4`).
2. Click **+** at the end of the advanced list. The editor opens with **DKS** selected.
3. Click the first key box on the left (row 1) and choose **A** from the key picker on the right.
4. In row 1 of the 4×4 grid, **click** (don't drag) the circle under column 1 (1.5 mm ↓) and
   the circle under column 4 (1.5 mm ↑).
5. Leave the column 1/4 trigger at 1.5 mm. Click **OK (确认)**.
   - **Expect: no HID frames.** The editor saves to the browser only.
6. On the keyboard picture, select **J** (base layer, `默认层`). Then click the list item
   **1#DKS** and answer **OK** to the apply prompt.
7. **Expect (SOURCE-ONLY prediction):**
   - The `18 00` base keymap chunks carry `17 00 00 00` at J's entry.
   - The `18 02` Fn chunks are unchanged.
   - Then 40 `22 …` writes, of which slot 0 is:
     `22 00 00 00 32 01 0F 1E 1E 0F 00 04 00 00 01 00 00 01`
   - Slots 1..39 are `22 <n> 00 00 32` followed by zeros.
   - If byte 7 and byte 8 are **not** `1E` (3.0 mm), note what they are. The decode infers
     30 from max travel 3.4 mm minus 0.4.
8. **Feel test:** in Notepad, press J slowly to the bottom and let go. You should get "a" at
   1.5 mm going down and another "a" at 1.5 mm coming up.

### D2: DKS hold bar (pins the meaning of step code 2)
1. Hover **1#DKS** and click the pencil.
2. **Drag** the row-1 column-1 circle rightwards until the bar snaps to column 2. Click OK.
3. Select J and click **Apply (应用)**.
4. **Expect:** slot 0 = `22 00 00 00 32 01 0F 1E 1E 0F 00 04 00 00 02 00 00 01`. A bar from
   point 1 to point 2 should write `02` at point 1 and `00` at point 2.
5. **Feel test:** "a" is held from 1.5 mm until bottom-out, then tapped again on the way up.
   Write down what actually happens.
6. Optional, for code 3: add a second bar in row 1 that starts at column 2 and runs to
   column 3. Expect `02 03 00 01`.

### M1: create a Mod-Tap and bind it
1. Click **+**, choose **MT**.
2. In the left box ("单击触发按键", single click) choose **Esc**.
3. In the right box ("长按触发按键", long press) choose **L-Ctrl**.
4. Leave the slider at **150 ms**. Click OK. Expect no HID frames.
5. Select **Caps Lock** on the picture, click **2#MT**, and answer OK.
6. **Expect:**
   - Caps Lock's keymap entry is `17 01 01 00`.
   - Slot 1 = `22 01 00 00 32 02 00 E0 00 00 00 29 00 00 0F`.
   - Note the order: **hold (L-Ctrl `E0`) comes before tap (Esc `29`)**. If the capture shows
     tap first, the decode is wrong.
   - Slot 0 still holds the D2 frame.
7. **Feel test:** a quick tap on Caps Lock gives Esc. Holding it gives Ctrl (hold it and press C).

### M2: Mod-Tap duration unit
1. Edit **2#MT** and move the slider to **500 ms**. Click OK.
2. Select Caps Lock and click **Apply**.
3. **Expect:** slot 1 byte 14 = `32` (50, i.e. 500 ms ÷ 10). Every other byte stays as in M1.

### T1: create a Toggle and bind it
1. Click **+**, choose **TGL**, and pick **L-Shift** in the single box. Click OK.
2. Select **K**, click **3#TGL**, and answer OK.
3. **Expect:**
   - K's keymap entry is `17 02 02 00`.
   - Slot 2 = `22 02 00 00 32 03 00 E1 00 00`.
4. **Feel test:** press K once and Shift stays latched (letters come out upper-case). Press K
   again to release it.

### R1: read-back (Method 2, or the Playwright harness)
1. Reload the page with the capture running.
2. **Expect** the replies to use the **same payload bytes** with a read header:
   - `IN 22 80 00 00 28 01 0F 1E 1E 0F 00 04 00 00 02 00 00 01`
   - `IN 22 80 00 01 28 02 00 E0 00 00 00 29 00 00 32`
   - `IN 22 80 00 02 28 03 00 E1 00 00`
   - `IN 22 80 00 <03..27> 28 00` for the rest
   - In the `18 80` keymap read, J, Caps Lock and K carry `17 00 00 00`, `17 01 01 00` and
     `17 02 02 00`.

### X1: delete (restores the board)
1. Hover **2#MT** and click the trash icon. **This applies straight away, with no prompt.**
   The source fires Apply programmatically. If no frames appear, select any key and click
   **Apply** yourself.
2. **Expect:**
   - Slot 1 = `22 01 00 00 32` followed by zeros.
   - Caps Lock's keymap entry is back to `00 39 00 00`.
   - Slots 0 and 2 are unchanged.
3. Delete **1#DKS** and **3#TGL** the same way.
4. The last pass should be 40 empty slots, with J = `00 0D 00 00` and K = `00 0E 00 00`.
5. Feel-test J, K and Caps Lock to confirm they type normally again.

---

## C. What to send back
- The JSON (Method 1) or the filtered `.pcapng` (Method 2), with the step marks.
- One line per feel test: what happened.
- Anything that differed from an **Expect** line. Each mismatch maps to an open question in
  `aula-win60-advanced-keys-decode.md` section 8.

When the D1, M1 and T1 frames match byte-for-byte, the golden tests in
`tests/test_win60_advkeys_wip.py` can be re-labelled CONFIRMED-BY-CAPTURE. Only then should
the builders be wired, and only behind a `"wip"` capability in `data/board_registry.json`.
