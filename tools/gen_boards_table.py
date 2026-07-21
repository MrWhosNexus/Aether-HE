#!/usr/bin/env python3
"""gen_boards_table.py — keep the README supported-boards table in sync with data.

`data/boards.json` is the single source of truth for which keyboards Aether
supports. This script renders that list into the Markdown table in README.md,
between the BOARDS markers, and always appends the "Your board? -> Submit it"
call-to-action row.

TWO lists are rendered, and the split is the point. `boards` is the SUPPORTED
table: only keyboards Aether can actually drive (the registry entries with
`offerInUi` true). `recognized` is an identify-only sentence rendered under the
table: boards Aether detects, names and draws but cannot drive. They are not
advertised as supported, but they are not hidden either — a user whose board is
recognised-but-not-driveable should read that fact here rather than wonder why
the app names their keyboard and then does nothing. `recognized` is optional:
a boards.json without it renders exactly the old block.

Workflow:
    # after merging support for a new board, add it to data/boards.json, then:
    python tools/gen_boards_table.py --write     # rewrite the README table
    python tools/gen_boards_table.py --check      # verify in sync (used by CI; read-only)

The table lives between these exact lines in README.md:
    <!-- BOARDS:START -->
    <!-- BOARDS:END -->
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOARDS_PATH = os.path.join(ROOT, "data", "boards.json")
README_PATH = os.path.join(ROOT, "README.md")
START = "<!-- BOARDS:START -->"
END = "<!-- BOARDS:END -->"
SUBMIT_URL = "https://github.com/MrWhosNexus/Aether-HE/issues/new?template=add-a-board.yml"


def _cell(v):
    """Render a lighting/actuation capability cell."""
    if v is True:
        return "✅"
    if v is False:
        return "—"
    if isinstance(v, str) and v.lower() in ("wip", "partial"):
        return "🚧"
    return "—"


def render_table(boards):
    lines = [
        "| Keyboard | Switches | Lighting | Actuation | Status |",
        "|----------|----------|----------|-----------|--------|",
    ]
    for b in boards:
        lines.append(
            f"| {b['name']} | {b.get('switches', '—')} | "
            f"{_cell(b.get('lighting'))} | {_cell(b.get('actuation'))} | "
            f"{b.get('status', '—')} |"
        )
    lines.append(
        f"| **Your board?** | — | — | — | **[Submit it →]({SUBMIT_URL})** |"
    )
    return "\n".join(lines)


def render_recognized(boards):
    """Identify-only boards, rendered as one paragraph under the table.

    Empty/absent -> "" (the block is byte-identical to the pre-split output).
    """
    if not boards:
        return ""
    items = ", ".join(
        f"**{b['name']}**" + (f" ({b['reason']})" if b.get("reason") else "")
        for b in boards
    )
    return (
        "\n\n**Recognised, but not drivable yet.** Aether identifies these boards, "
        "names them and draws their layout, but has no verified protocol for them — "
        "lighting and actuation stay switched off and they are not offered as "
        f"selectable options anywhere in the app: {items}."
    )


def build_block():
    with open(BOARDS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    boards = data.get("boards", [])
    recognized = data.get("recognized", [])
    return f"{START}\n{render_table(boards)}{render_recognized(recognized)}\n{END}"


def splice(readme_text, block):
    if START not in readme_text or END not in readme_text:
        raise SystemExit(
            f"README is missing the {START} / {END} markers — add them around the table first."
        )
    pre = readme_text.split(START, 1)[0]
    post = readme_text.split(END, 1)[1]
    return pre + block + post


def main(argv):
    mode = argv[0] if argv else "--check"
    if mode not in ("--write", "--check"):
        print("usage: gen_boards_table.py [--write|--check]", file=sys.stderr)
        return 2

    block = build_block()
    with open(README_PATH, encoding="utf-8") as f:
        readme = f.read()
    updated = splice(readme, block)

    if mode == "--write":
        if updated != readme:
            with open(README_PATH, "w", encoding="utf-8") as f:
                f.write(updated)
            print("README boards table updated.")
        else:
            print("README boards table already up to date.")
        return 0

    # --check (read-only)
    if updated != readme:
        print(
            "ERROR: README boards table is out of sync with data/boards.json.\n"
            "Run:  python tools/gen_boards_table.py --write",
            file=sys.stderr,
        )
        return 1
    print("OK: README boards table is in sync with data/boards.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
