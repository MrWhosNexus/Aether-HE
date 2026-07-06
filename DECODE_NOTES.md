# Decode Notes — Aula "DryRun Test 60" (aula-dryrun-test-60)

## Source

- Schema: `aether-board-submission/1` @ `2026-07-06T00:00:00Z`
- VID / PID: `0x2E3C` / `0xC365`
- Manufacturer / product: Aula / Test HE
- Usage page: `0xFF1B` (vendor-defined)
- Interface claimed: `2`
- `report_len`: **64 bytes**
- `input_capture.reports`: 1 sample at `t = 5 ms`, hex `01 ab 00`
- `output_pcap.attached`: **false** — no host→device traffic was captured.
- `hid_descriptor_b64`: empty, so we cannot introspect the declared input/output reports either.
- `meta.switch_type`: Hall-effect. `meta.form_factor` / `meta.size`: 60%.

## Slug derivation

`meta.brand = "Aula"`, `meta.model = "DryRun Test 60"` →
filesystem-safe kebab-case **`aula-dryrun-test-60`**, matching `registry_entry.slug`
and the `keymap` filename `ui/layouts/aula-dryrun-test-60.json`.
Protocol module: **`protocol_aula_dryrun_test_60`**.

## What I inferred (with confidence)

| Inference | Confidence | Reason |
|---|---|---|
| 60% ANSI form factor, ~61 keys | **High** | Vendor metadata + size_template `generic-60`. |
| Hall-effect switches | **High** | `meta.switch_type`. |
| Byte 0 of input reports is a report id | **Medium** | All Aula HE captures I have ever seen start with `0x01`; only 1 sample here though. |
| Byte 1 of input reports carries a vendor scan code | **Low–Medium** | Consistent with a single key seen (`keys_seen: 1`). |
| Byte 2 is either a press/release flag **or** a low-resolution actuation-depth byte | **Low** | Two competing hypotheses; both are implemented as advisory code paths in the adapter. |
| 61 trailing zero bytes in this single report are padding | **Low** | They could be a 62-bit NKRO bitmap, mod bits, or simply unused padding — indistinguishable from one capture. |

## What I deliberately did NOT infer

Because `output_pcap.attached == false`, the following are explicitly **unknown**
and are flagged as such in `protocol_adapter.self_test()`. No bytes are invented.

- Lighting / per-key RGB commands (mode, brightness, color, addressing).
- Actuation-point tuning commands.
- Rapid-trigger configuration commands.
- Macro / profile storage commands.
- Any feature-report opcode table.
- Any secondary input endpoints (media keys, mouse mode, etc.).

In consequence, `registry_entry.capabilities.lighting` and
`capabilities.perKeyRgb` are set to **`false`** (not `true` like the example
in the prompt) until verified. This is conservative: many Aula HE boards ship
with RGB, but this submission does not prove it.

## Fields that a human MUST verify on hardware before promoting from `experimental`

1. Capture **multiple** input reports covering: press, release, N-key rollover,
   rapid-trigger sweeps, and analog depth at multiple points. Use those to
   confirm whether byte 1 is the scan code and byte 2 is actuation depth, or
   vice versa, or whether the device uses a 62-bit bitmap layout instead.
2. Confirm the **report id space**: is `0x01` the only input report, or does
   the device also expose media / mouse / consumer-control reports?
3. Capture an **output pcap** (USBPcap / Wireshark on a host running the
   vendor configuration tool) and from it derive:
   - the lighting opcode(s) and per-key RGB addressing;
   - whether actuation-point / rapid-trigger tuning go via feature reports
     or output reports, and their opcode;
   - any boot-keyboard / NKRO toggle commands.
4. Validate the `Fn` key at `index 59` (right side of the bottom row).
   Currently mapped to a generic `ContextMenu` placeholder (`hidCode 0x65`).
   Aula boards commonly use this slot as a layer / Fn key with vendor-defined
   behavior — without more data I cannot tell which.
5. Validate that `interface_number: 2` is actually the input endpoint carrying
   `report_len: 64`. Some Aula devices expose a boot keyboard on interface 0
   and vendor reports on a higher index; both must be enumerated.
6. Re-derive the layout against an actual photo / CAD / per-key measurement;
   the layout file shipped here is a generic 60% ANSI placeholder.

## Open questions

- Is `report_len: 64` fixed or padded? The single 3-byte capture cannot tell.
- Does the device expose a boot-protocol mode for BIOS use?
- Are there macro/profile storage commands?
- Is there a vendor-specific usage table under `0xFF1B`, or is the device just
  carrying standard HID usage codes through a vendor page wrapper?

Until items 1–3 above are completed on hardware, this entry must remain
`status: "experimental"`.