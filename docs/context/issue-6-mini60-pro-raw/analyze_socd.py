"""Pull the SOCD record out of the wireless Advanced-Keys capture.

Ground truth from the vendor UI: Key1 = A, Key2 = D, behaviour "Key 1 Priority".
The SDK decode says advanced-key types live in the 512-byte key table via 0x22,
keyed by pageType, with SOCD = 11 (0x0B) and a record shaped
`[0x0B][mode][hidA][hidB]`.

A and D are HID usages 0x04 and 0x07, and their firmware key indices on this
board are 49 and 51 (row stride 16, Caps=48). So a correct decode should show a
record `0B <mode> 04 07` landing at table offset 49*4 and 51*4.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(HERE, "webhid-capture-socd-wireless.json")

PAYLOAD_AT = 8          # 32-byte wireless frames: 8-byte header, 24-byte payload
CHUNK = 24
REC = 4                 # key-table record size


def load():
    with open(CAP, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, str):          # evaluate() results are JSON strings
        d = json.loads(d)
    return d["frames"]


def bytes_of(e):
    return [int(x, 16) for x in e["hex"].split()] if e.get("hex") else []


def main():
    frames = load()
    writes = [e for e in frames if e.get("dir") == "OUT" and e.get("hex", "").startswith("AA 22")]
    print(f"0x22 SET_KEY frames: {len(writes)}")
    if not writes:
        return 1

    # reassemble the key table from the paged writes (offset is LE16 at [3..4])
    table = {}
    for e in writes:
        b = bytes_of(e)
        off = b[3] | (b[4] << 8)
        n = b[2]
        for i in range(n):
            if PAYLOAD_AT + i < len(b):
                table[off + i] = b[PAYLOAD_AT + i]
    size = max(table) + 1 if table else 0
    print(f"reassembled {len(table)} bytes spanning 0..{size - 1}")

    # every non-zero record, with its key index
    print("\nnon-empty key records (index: bytes):")
    hits = []
    for idx in range(size // REC + 1):
        rec = [table.get(idx * REC + j, 0) for j in range(REC)]
        if any(rec):
            hits.append((idx, rec))
    for idx, rec in hits[:24]:
        tag = ""
        if rec[0] == 0x0B:
            tag = "  <== SOCD (pageType 11)"
        elif rec[0] == 0x0C:
            tag = "  <== Rapid SOCD / RS (pageType 12)"
        elif rec[0] in (0x08, 0x09, 0x0A):
            tag = f"  <== advanced pageType {rec[0]}"
        print(f"  idx {idx:>3}: {' '.join(f'{v:02X}' for v in rec)}{tag}")

    socd = [(i, r) for i, r in hits if r[0] == 0x0B]
    print(f"\nSOCD records found: {len(socd)}")
    for idx, rec in socd:
        print(f"  key index {idx}: mode={rec[1]:#04x} hidA={rec[2]:#04x} hidB={rec[3]:#04x}")
    if len(socd) == 2:
        print("\n  Two records, one per key of the pair — matches the SDK's description")
        print("  that an SOCD binding is written to BOTH keys.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
