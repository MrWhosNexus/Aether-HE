You are drafting keyboard support for the AetherHE controller from a hardware
submission. Output ONLY the four delimited blocks below — no prose, no markdown
fences, no ```json wrappers inside the blocks. Each JSON block must be a single
valid JSON value that `json.loads` can parse directly.

Submission (schema aether-board-submission/1):
{submission}

Rules:
- slug: filesystem-safe kebab-case from meta.brand + meta.model, e.g. "aula-win60-he".
- The registry entry status MUST be exactly "experimental".
- The protocol adapter is BEST-EFFORT from input_capture reports (INPUT side only;
  you cannot know lighting/output commands unless a pcap was attached — say so in the
  notes, do NOT invent output bytes). Comment it "AI-DRAFTED — UNVERIFIED".
- Use the EXACT field names shown in the examples. Do not rename or nest differently.

=== FILE: registry_entry.json ===
The single board object to append to data/board_registry.json "boards". EXACT keys
required: slug, name, vid, pid, usage_page, formFactor, protocol, keymap,
capabilities, status. `protocol` names the adapter module (e.g. "protocol_<slug_underscored>").
`keymap` is "ui/layouts/<slug>.json". Example (match this shape exactly):
{
  "slug": "aula-win60-he",
  "name": "Aula Win60 HE",
  "vid": "0x2E3C",
  "pid": "0xC365",
  "usage_page": "0xFF1B",
  "formFactor": "60%",
  "protocol": "protocol_aula_win60_he",
  "keymap": "ui/layouts/aula-win60-he.json",
  "capabilities": { "actuation": true, "lighting": true, "perKeyRgb": true },
  "status": "experimental"
}

=== FILE: layout.json ===
Shape: {"_meta": {...}, "type": "us", "keys": [ ... ]}. EVERY key object MUST have
ALL of these fields: index, name, code, hidCode, width, height, x, y (values may be
strings). `code` is the browser event code (Escape, Digit1, KeyA, ControlLeft, …);
`hidCode` is the USB HID usage in hex (e.g. "29" for Escape, "1E" for 1). Produce a
sensible full physical layout for the board's size (meta.size). Example of two keys
(match this shape exactly for every key):
{
  "_meta": { "board": "Aula Win60 HE", "formFactor": "60%", "status": "experimental" },
  "type": "us",
  "keys": [
    { "index": "0", "name": "Esc", "code": "Escape", "hidCode": "29", "width": "35", "height": "35", "x": "10", "y": "15" },
    { "index": "1", "name": "1!", "code": "Digit1", "hidCode": "1E", "width": "35", "height": "35", "x": "48", "y": "15" }
  ]
}

=== FILE: protocol_adapter.py ===
The protocol_<slug_underscored>.py content. Comment the top "AI-DRAFTED — UNVERIFIED,
needs on-hardware validation". Best-effort input parsing inferred from the reports.

=== FILE: DECODE_NOTES.md ===
Your analysis: what you inferred from the input reports, your confidence, and exactly
what a human must verify on hardware (especially lighting/output, which is unknown
without a pcap).
