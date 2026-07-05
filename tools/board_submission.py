"""Schema + validator for aether-board-submission/1 — the A<->B contract.
Hand-rolled (no jsonschema dep); mirrors tools/validate_keymap.py. Never raises."""
import re
import time

SCHEMA_ID = "aether-board-submission/1"
_SIZES = {"60", "65", "75", "tkl"}
_HEX = re.compile(r"^[0-9a-fA-F]*$")


def new_submission_skeleton(app_version):
    return {
        "schema": SCHEMA_ID,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "app_version": str(app_version),
        "device": {"vid": "", "pid": "", "manufacturer": "", "product": "",
                   "usage_page": "", "hid_descriptor_b64": "", "interfaces": []},
        "meta": {"brand": "", "model": "", "switch_type": "", "form_factor": "", "size": ""},
        "size_template": "",
        "input_capture": {"duration_ms": 0, "report_len": 0, "reports": [], "keys_seen": 0},
        "output_pcap": {"attached": False, "filename": None},
        "notes": "",
    }


def validate_submission(obj):
    """Return a list of human-readable error strings. [] == valid. Never raises."""
    e = []
    try:
        if not isinstance(obj, dict):
            return ["top-level value must be a JSON object"]
        if obj.get("schema") != SCHEMA_ID:
            e.append(f'schema must be "{SCHEMA_ID}"')
        dev = obj.get("device")
        if not isinstance(dev, dict):
            e.append('"device" must be an object')
        else:
            for f in ("vid", "pid"):
                if not isinstance(dev.get(f), str) or not dev.get(f):
                    e.append(f'device.{f} is required (non-empty string)')
        meta = obj.get("meta")
        if not isinstance(meta, dict):
            e.append('"meta" must be an object')
        else:
            for f in ("brand", "model"):
                if not isinstance(meta.get(f), str) or not meta.get(f):
                    e.append(f'meta.{f} is required')
            if meta.get("size") not in _SIZES:
                e.append(f'meta.size must be one of {sorted(_SIZES)}')
        cap = obj.get("input_capture")
        if not isinstance(cap, dict):
            e.append('"input_capture" must be an object')
        else:
            reps = cap.get("reports")
            if not isinstance(reps, list):
                e.append('input_capture.reports must be an array')
            else:
                for i, r in enumerate(reps):
                    if not isinstance(r, dict) or not _HEX.match(str(r.get("hex", "x"))):
                        e.append(f'input_capture.reports[{i}].hex must be hex')
                        break
    except Exception as ex:  # never raise
        return [f"validator error: {ex}"]
    return e
