> **Provenance (Aether upstream).** Contributor-supplied read-backs from one physical AULA F75 HE,
> taken 2026-10-21/23 on firmware V1.55 by xpLayA (fork `xpLayA/Aether-HE` @ `9a70ec6`, where they
> live under `fixtures/f75/`). They are **not a vendor-driver capture** and no maintainer owns this
> board. They are test data only: `tests/test_f75.py` and `tests/test_protocol_mini60.py` read them.
> The bring-up scripts named below (`docs/context/f75-bringup/*.py`) were **not** copied here: they
> import the fork's paths and write to a keyboard. Read them at that fork commit if needed.
> Also in this folder: `dongle_info.json` (0x10 reply over the 2.4 GHz receiver, with battery),
> `keytable_before.json`, `custom_led_before.json`, `dks_before.json` (before-states of the probes
> below) and `bt_report_descriptor.txt` (Bluetooth LE report map: no vendor collection).

# AULA F75 HE hardware captures (2026-10-21)

Read from a physical F75 HE (38A6:2729, fw interface 0xFF68, 64-byte frames) with the
bring-up scripts in `docs/context/f75-bringup/`. Golden inputs for the Rust port's parsers.

- `backup.json` — full read-only snapshot: 0x10 device info, 0x13 lighting reply (`light_raw`,
  whole 64-byte frame), and the reassembled tables as hex: 0x17 actuation (1008 B, all zero =
  factory), 0x12 key table (512 B), 0x14 custom LED (504 B, all zero), 0x11 config (64 B).
- `light_before.json` — a 0x13 reply frame (stored mode 0x0B Drifting, colorMode 1, bri 5, speed 3).
- `act_before.json` — the 0x17 actuation table before the W round-trip (hex).

Verified outcomes: see the `aula-f75-he` entry's `_note`s in `data/board_registry.json`.

## Travel-test probe (2026-10-21): no live depth
`docs/context/f75-bringup/f75_travel_probe.py` sent the SDK's `SET_SIMULATION_TEST_ON` (`AA 66 00…`),
listened 9 s and 16 s, then always sent `SET_SIMULATION_TEST_OFF` (`AA 67 00…`). The board acked
(`55 66 00…`) within 3 ms but produced **no `0xFB` reports** on the 0xFF68 interface or passively on its
five other collections. The vendor UI never calls this mode; its live travel display uses calibration
mode (0x64, preceded by a calibration wipe), which Aether never sends. Live depth is therefore not
offered for this board. Not tried: `0x60 GET_MAGNETIC_AXIS_KEY_STATUS` (never referenced, format unknown).

## Stored per-key colours probe (2026-10-21): 0x24 works
`docs/context/f75-bringup/f75_custom_led_rt.py` read 0x13 + 0x14 (all zero), wrote a hue sweep with
`0x24` (all 9 pages acked `55 24 …`), set mode 20, read 0x14 back (byte-exact), held 6 s, then wrote
the original table back and restored the exact lighting block (both verified). Before-state:
`custom_led_before.json`. Nobody watched the keys during the hold,
so the visible result is unconfirmed; the GUI's paint + Apply is the visual check.

## Key table + DKS probe (2026-10-21): 0x22 / 0x18 / 0x28 work
`docs/context/f75-bringup/f75_keytable_rt.py`: every page of every write acked (`55 22`/`55 28`) and read
back byte-exact for: a no-op 0x22, TGL on F12, MT on F12 (tap F12 / hold F11 / 250 ms), RS and SOCD
(mode 3) on the F11+F12 pair, a no-op 0x28, and DKS slot 0 bound to F12 (0x28 then 0x22). Both original
tables restored exactly. Before-state: `keytable_before.json` (identical to `backup.json`'s key table),
`dks_before.json` (all zero). Key-table tail bytes 504..511 read zero. Feel not yet tested.
