import json, os, subprocess, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_bot as b, minimax_client as m, board_submission as bs
body = json.loads(subprocess.run(["gh","issue","view","9","-R","MrWhosNexus/Aether-HE","--json","body"],
                                  capture_output=True, text=True).stdout)["body"]
sub = b.extract_json_block(body)
print("1) submission parsed:", bool(sub))
print("2) submission valid:", bs.validate_submission(sub) or "OK")
try:
    raw = m.complete(b.build_prompt(sub, b._read_prompt()))
    print("3) complete OK, chars:", len(raw))
except Exception as e:
    print("3) complete RAISED:", type(e).__name__, str(e)[:400]); sys.exit()
art = b.parse_model_output(raw)
print("4) parsed -> registry:", bool(art["registry"]), "layout:", bool(art["layout"]),
      "adapter chars:", len(art["adapter"]), "notes chars:", len(art["notes"]))
if art["registry"] is None:
    print("   registry block was present but did NOT parse as JSON (model wrapped it?)")
    import re
    mm = re.search(r"=== FILE: registry_entry.json ===\n(.*?)(?=\n=== FILE:|\Z)", re.sub(r"<think>.*?</think>","",raw,flags=re.S), re.S)
    print("   raw registry block first 300:", (mm.group(1)[:300] if mm else "NOT FOUND"))
existing = set()
try: existing = {x.get("slug") for x in json.load(open("data/board_registry.json")).get("boards",[])}
except Exception: pass
print("5) sanity_check problems:", b.sanity_check(art, existing) or "NONE (would open PR)")
