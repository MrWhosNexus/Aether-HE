You are drafting keyboard support for the AetherHE controller from a hardware
submission. Output ONLY the four delimited blocks below — no prose outside them.

Submission (schema aether-board-submission/1):
{submission}

Board model: infer a filesystem-safe kebab-case slug from meta.brand + meta.model.
The registry entry MUST have status "experimental". The layout must be shape
{"_meta":..., "type":..., "keys":[...]} sized from meta.size / size_template.
The protocol adapter is BEST-EFFORT from the input_capture reports (input side
only; you cannot know lighting/output commands unless a pcap was attached — say so
in the notes rather than guessing output bytes). Mark the adapter AI-DRAFTED/UNVERIFIED.

=== FILE: registry_entry.json ===
<the single board object to append to data/board_registry.json's "boards" array>
=== FILE: layout.json ===
<the ui/layouts/<slug>.json content>
=== FILE: protocol_adapter.py ===
<the protocol_<slug>.py content, commented AI-DRAFTED — UNVERIFIED>
=== FILE: DECODE_NOTES.md ===
<your analysis: what you inferred, confidence, and exactly what a human must verify on hardware>
