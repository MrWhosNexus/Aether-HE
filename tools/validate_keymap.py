#!/usr/bin/env python3
"""validate_keymap.py — strict, fail-closed validation for board keymap files.

Every keymap.json that ships comes from an untrusted submitter (a GitHub issue /
PR). GitHub authenticates *who* sent it, not *what's inside*. This module treats a
keymap as hostile data and validates it against a strict schema with hard bounds,
so malformed or malicious input is rejected *before* it ever reaches the device
bridge or the WebView UI.

Two entry points:
  * validate_keymap(data)  -> list[str] of human-readable errors ("" = valid).
                              Pure, side-effect free; reused by device_state and CI.
  * load_keymap(path)      -> dict, raising KeymapValidationError on any problem
                              (also enforces a file-size cap before parsing).

CLI:
    python tools/validate_keymap.py ui/keymap.json    # exit 0 = ok, 1 = invalid
    python tools/validate_keymap.py a.json b.json      # validate several
"""
import json
import os
import sys

# ---- Hard bounds (fail-closed). Tune as new, larger boards are added. --------
MAX_FILE_BYTES = 256 * 1024     # a keymap is small text; reject anything huge
MAX_KEYS = 512                  # full-size is ~104 keys; 512 is generous headroom
MAX_INDEX = 1023                # firmware matrix index ceiling
MAX_HID = 0xFF                  # HID usage IDs are a single byte
MAX_NAME_LEN = 16               # key labels are short ("Back", "L-Shift", "1!")
MAX_CODE_LEN = 32               # browser event-codes ("BracketLeft", "ControlLeft")
MAX_COORD = 10000               # pixel positions / sizes
# NOTE on label safety: we deliberately do NOT char-filter labels. Real keycaps
# legitimately contain '<', '>', '"', '&', '\\' etc. (the ',<' and '.>' keys!),
# so blocking those would reject valid boards. XSS is prevented at the correct
# layer instead: output encoding (React escapes {label} as text) PLUS a CI guard
# that forbids innerHTML/dangerouslySetInnerHTML. Here we only bound length and
# reject control characters (which have no place in a printable label).


class KeymapValidationError(ValueError):
    """Raised when a keymap fails validation. Message lists every problem."""


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _coerce_int(v):
    """Accept an int or a decimal string; reject anything else. Returns (ok, val)."""
    if isinstance(v, bool):
        return False, None
    if isinstance(v, int):
        return True, v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return True, int(v.strip())
    return False, None


def _coerce_hid(v):
    """HID code: int, decimal string, or hex string ('29', '0x29'). -> (ok, val)."""
    if isinstance(v, bool):
        return False, None
    if isinstance(v, int):
        return True, v
    if isinstance(v, str):
        s = v.strip()
        try:
            return True, int(s, 16) if not s.lstrip("-").isdigit() else int(s)
        except ValueError:
            try:
                return True, int(s, 16)
            except ValueError:
                return False, None
    return False, None


def _coerce_coord(v):
    if _is_number(v):
        return True, float(v)
    if isinstance(v, str):
        try:
            return True, float(v.strip())
        except ValueError:
            return False, None
    return False, None


def validate_keymap(data):
    """Return a list of error strings. Empty list == valid. Never raises."""
    errors = []

    if not isinstance(data, dict):
        return ["top-level value must be a JSON object"]
    if "keys" not in data:
        return ['missing required "keys" array']
    keys = data["keys"]
    if not isinstance(keys, list):
        return ['"keys" must be an array']
    if not keys:
        return ['"keys" is empty — at least one key is required']
    if len(keys) > MAX_KEYS:
        errors.append(f'too many keys: {len(keys)} (max {MAX_KEYS})')

    if "type" in data and not isinstance(data["type"], str):
        errors.append('"type" must be a string if present')

    seen_index = {}
    for i, k in enumerate(keys):
        where = f"keys[{i}]"
        if not isinstance(k, dict):
            errors.append(f"{where}: must be an object")
            continue

        # index — required, integer, in range, unique
        if "index" not in k:
            errors.append(f"{where}: missing required 'index'")
        else:
            ok, idx = _coerce_int(k["index"])
            if not ok:
                errors.append(f"{where}: 'index' must be an integer, got {k['index']!r}")
            elif not (0 <= idx <= MAX_INDEX):
                errors.append(f"{where}: 'index' {idx} out of range 0..{MAX_INDEX}")
            elif idx in seen_index:
                errors.append(f"{where}: duplicate 'index' {idx} (also {seen_index[idx]})")
            else:
                seen_index[idx] = where

        # name — required, length- and charset-limited
        if "name" not in k:
            errors.append(f"{where}: missing required 'name'")
        elif not isinstance(k["name"], str):
            errors.append(f"{where}: 'name' must be a string")
        else:
            name = k["name"]
            if not (1 <= len(name) <= MAX_NAME_LEN):
                errors.append(f"{where}: 'name' length {len(name)} out of 1..{MAX_NAME_LEN}")
            if any(ord(c) < 32 or ord(c) == 127 for c in name):
                errors.append(f"{where}: 'name' contains control characters")

        # code — required, strict identifier charset
        if "code" not in k:
            errors.append(f"{where}: missing required 'code'")
        elif not isinstance(k["code"], str):
            errors.append(f"{where}: 'code' must be a string")
        else:
            code = k["code"]
            if not (1 <= len(code) <= MAX_CODE_LEN):
                errors.append(f"{where}: 'code' length {len(code)} out of 1..{MAX_CODE_LEN}")
            if not code.isascii() or not code.isalnum():
                errors.append(f"{where}: 'code' must be ASCII alphanumeric, got {code!r}")

        # hidCode — required, single byte
        if "hidCode" not in k:
            errors.append(f"{where}: missing required 'hidCode'")
        else:
            ok, hid = _coerce_hid(k["hidCode"])
            if not ok:
                errors.append(f"{where}: 'hidCode' must be hex/int, got {k['hidCode']!r}")
            elif not (0 <= hid <= MAX_HID):
                errors.append(f"{where}: 'hidCode' {hid:#x} out of range 0..{MAX_HID:#x}")

        # x / y — required coordinates
        for axis in ("x", "y"):
            if axis not in k:
                errors.append(f"{where}: missing required '{axis}'")
            else:
                ok, val = _coerce_coord(k[axis])
                if not ok:
                    errors.append(f"{where}: '{axis}' must be numeric, got {k[axis]!r}")
                elif not (0 <= val <= MAX_COORD):
                    errors.append(f"{where}: '{axis}' {val} out of range 0..{MAX_COORD}")

        # width / height — optional, but bounded if present
        for dim in ("width", "height"):
            if dim in k:
                ok, val = _coerce_coord(k[dim])
                if not ok:
                    errors.append(f"{where}: '{dim}' must be numeric, got {k[dim]!r}")
                elif not (1 <= val <= MAX_COORD):
                    errors.append(f"{where}: '{dim}' {val} out of range 1..{MAX_COORD}")

    return errors


def load_keymap(path):
    """Read, size-check, parse, and validate a keymap file. Returns the dict.

    Raises KeymapValidationError on oversized files, JSON syntax errors, or any
    schema violation. Callers should treat that as 'no board' (fail closed).
    """
    try:
        size = os.path.getsize(path)
    except OSError as e:
        raise KeymapValidationError(f"cannot stat {path}: {e}") from e
    if size > MAX_FILE_BYTES:
        raise KeymapValidationError(
            f"{path}: file is {size} bytes (max {MAX_FILE_BYTES}) — refusing to parse")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise KeymapValidationError(f"{path}: cannot parse JSON: {e}") from e

    errors = validate_keymap(data)
    if errors:
        joined = "\n  - ".join(errors)
        raise KeymapValidationError(f"{path}: invalid keymap:\n  - {joined}")
    return data


def main(argv):
    if not argv:
        print("usage: validate_keymap.py <keymap.json> [more.json ...]", file=sys.stderr)
        return 2
    failed = False
    for path in argv:
        try:
            data = load_keymap(path)
            print(f"OK: {path} ({len(data['keys'])} keys)")
        except KeymapValidationError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
