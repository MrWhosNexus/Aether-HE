# Multi-board support + Aula HE board families (session synthesis)

Status as of this session. Captures the multi-board refactor, the decoded `0C45`
protocol, and the **hard-data** identification of every submitted board (from
underside-label photos, not issue titles). Pairs with `data/board_registry.json`
(authoritative) and `protocol_sonix.py` (the decode).

## What shipped (branch `feature/multi-board-support`)
- **Board registry** (`boards.py` + `data/board_registry.json`): detect the
  connected board by USB VID/PID, pick its vendor `usage_page`, keymap, and
  protocol module. Falls back to the Win60 default so existing behaviour is
  unchanged.
- **`aula_device.AulaDevice(profile)`**: opens each board's own vendor interface
  (e.g. `0xFF68` for the 0C45 board vs `0xFF1B` for Win60). Default path identical.
- **`app_web.Api`**: selects board + keymap on init; exposes `get_board()` for the
  (future) UI board picker. Driving logic unchanged.
- **`protocol_sonix.py`**: decoded `0C45` "0xAA-framed" vendor protocol — lighting
  cmd `0x23`, per-key actuation/RT cmd `0x27` — reverse-engineered from the issue
  #4 USBPcap capture. Golden-tested byte-for-byte (`tests/test_protocol_sonix.py`).
- **`ui/layouts/*.json`**: provisional keymaps for all submitted boards (4× 60%,
  1× 65%/68-key), passing the strict validator. Firmware indices are provisional
  (cloned from Win60 stride) pending hardware bring-up.

## The decode (0C45:80A1, AULA MINI60HE Max) — verified
Transport is NOT the Win60 protocol. Frames are 64-byte **interrupt OUT on
endpoint `0x04`**, magic `0xAA`: `[0]=0xAA [1]=cmd [2]=len [3..4]=16-bit LE page
offset`. Vendor config collection at usage page `0xFF68`.
- `0x23` lighting: `[6]=01 [8]=mode [9..12]=RGBA [16]=flag [17]=brightness
  [18]=speed [22..23]=0xAA55`. Reproduces all 5 captured frames exactly.
- `0x27` actuation/RT: 8-byte/key records `[enable][mode][press BE16][release BE16][0][0]`
  in 0.01 mm units, paged in 56-byte (`0x38`) pages. **Single-frame encoding
  verified; full multi-frame table mapping (18 offsets 0x0..0x3b8) is UNVERIFIED.**
- The capture was over USB; MINI60HE is a wireless tri-mode board, so this is the
  **wired path only**.

## Board families — from underside labels (HARD DATA, not titles)
There are **four distinct controller families**, not one product line. Marketing
names ("Win60 HE", "Pro", "Max") cut across families and do NOT imply shared
firmware. A shared VID is shared OEM silicon, not a proven shared protocol.

| Family | VID | Boards (label / issue) | Power | Tool | Decoded? |
|---|---|---|---|---|---|
| Win60 HE (standard) | `2E3C` | Aula Win60 HE | wired | aulacn | yes (on-HW) |
| **MINI 60 HE** | `0C45` | MINI60HE Max `80A1` (#4); MINI60HE Pro `FEFE` (#6) | battery / tri-mode | aulacn | **#4 yes**, #6 no |
| **WINxxHE MAX** | `1CA2` | WIN60HE MAX `1902` (#5, aulastar); WIN68HE MAX `1901` (#7, aulacn/Suoai) | wired ~500 mA | aulastar / aulacn | no |
| SayoDevice | `8089` | WIN 60 HE Pro `0009` (#3, SI-2825C / CH32V307RBT6) | wired | SayoDevice | no |

Key, provable points:
- **"Win60 HE" spans three chips**: standard `2E3C`, "Pro" (#3) `8089` SayoDevice,
  "Max" (#5) `1CA2`. Same name, three controllers.
- **"Max" spans two lines**: `0C45` MINI60HE Max (#4) and `1CA2` WIN60HE Max (#5).
- **Real protocol-sharing pairs** (same line, likely shared firmware, still
  unconfirmed without a capture each): #4↔#6 (`0C45` MINI60HE, strong — same line),
  #5↔#7 (`1CA2` WINxxHE MAX, moderate — same line, different web portals).

## Drivable rule (locked by test)
A board is `drivable` ONLY with its own decoded protocol. Guards against the
shared-VID fallacy (caught + fixed for #6 mid-session). Only `2E3C` and `0C45:80A1`
are drivable; everything else is layout + identity until captures arrive.

## Open / next
- Bring-up #4 on hardware: confirm key-index stride from travel reports, then wire
  `protocol_sonix` into the `Api` driving path.
- Capture needed: `1CA2` (unblocks #5+#7 candidate), `8089` SayoDevice (#3), and a
  `0C45:FEFE` confirmation for #6.
- Verify the 65% win68 layout against the issue #7 photo; verify all firmware indices.
- Outreach posted on issues #3/#5/#6/#7 requesting HID dump + protocol captures;
  #1 closed as duplicate of #4.
