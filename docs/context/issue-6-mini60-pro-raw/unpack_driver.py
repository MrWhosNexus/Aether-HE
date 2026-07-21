"""unpack_driver.py - split the scraped Aula Hub bundles into individual .js/.css files.

The scrape (Playwright + in-page fetch of every asset the WebHID driver loads) lands as
one JSON blob per batch: {filename: source}. This explodes it into driver_src/ so the
chunks are greppable and diffable, the same way driver_src/decoded/ works for the Win60.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "driver_src"


def unpack(blob_path):
    data = json.loads(Path(blob_path).read_text(encoding="utf-8"))
    # the evaluate() result is a JSON *string*, so the saved file is double-encoded
    if isinstance(data, str):
        data = json.loads(data)
    files = data.get("files", data)  # batch 2 wraps in {fetched, files}
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, src in files.items():
        if not isinstance(src, str) or src.startswith(("HTTP ", "ERROR ")):
            print("  skip %s -> %s" % (name, src))
            continue
        (OUT / name).write_text(src, encoding="utf-8")
        print("  %-52s %8d bytes" % (name, len(src)))
        written += 1
    return written


if __name__ == "__main__":
    total = 0
    for p in sys.argv[1:]:
        print("unpacking %s" % p)
        total += unpack(p)
    print("wrote %d files to %s" % (total, OUT))
