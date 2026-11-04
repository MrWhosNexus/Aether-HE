"""Security gate for board-support code (docs/security/2026-11-04-submissions-plan.md, rule 2).

Protocol modules (protocol*.py) and drivers (drivers/**/*.py) only build
packets and talk to the keyboard through the device object they are handed.
They must never reach the network, start programs, load native code,
deserialize objects, touch files, or run text as code.

This is an ALLOWLIST scan of the AST (nothing is imported or run):
  * only the modules in ALLOWED_MODULES / ALLOWED_LOCAL may be imported
    (any alias is tracked); `os` only as `os.path`;
  * no eval/exec/compile/__import__/open/... builtins;
  * no getattr/setattr/hasattr/delattr on an imported module, and none with
    a computed attribute name anywhere;
  * no dunder escape hatches (__subclasses__, __globals__, __builtins__, ...).
The local modules allowed here (boards, device_state, aula_device, protocol*,
drivers.*) are owner-reviewed core files (.github/CODEOWNERS).

    python tools/scan_contrib.py            # scan the repo's protocol/driver files
    python tools/scan_contrib.py a.py b.py  # scan given files
Exit 1 with one line per finding.
"""
import ast
import glob
import hashlib
import os
import sys

ALLOWED_MODULES = {
    "struct", "json", "logging", "threading", "time", "math", "enum", "typing",
    "dataclasses", "collections", "itertools", "functools", "re", "binascii",
    "hid",            # the HID library itself (device access is the job)
}
ALLOWED_LOCAL = {"boards", "device_state", "aula_device", "protocol", "drivers"}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "open", "input",
                   "breakpoint", "globals", "vars", "locals"}
ATTR_CALLS = {"getattr", "setattr", "hasattr", "delattr"}
DUNDER_ESCAPES = {"__subclasses__", "__globals__", "__builtins__", "__code__",
                  "__dict__", "__class__", "__bases__", "__mro__", "__loader__",
                  "__spec__", "__import__", "__getattribute__", "__reduce__",
                  "__reduce_ex__", "f_globals", "f_locals", "gi_frame", "tb_frame"}
# Reviewed exceptions: (repo-relative path with "/", finding text without the
# line number, sha256 of the stripped source line, first 12 hex). The hash
# pins the exemption to that exact line: editing it re-raises the finding.
REVIEWED = {
    # reads data/board_registry.json (read-only) for the dongle's frameLen
    ("drivers/mini60.py", "call open()", "c844db07de5e"),
}


def _root(name):
    return (name or "").split(".")[0]


def _module_allowed(name):
    r = _root(name)
    return r in ALLOWED_MODULES or r in ALLOWED_LOCAL or r.startswith("protocol")


def scan_source(src, path="<src>"):
    """Findings (strings) for one module's source text."""
    try:
        tree = ast.parse(src, path)
    except SyntaxError as e:
        return [f"{path}:{e.lineno}: does not parse ({e.msg})"]
    out = []
    module_names = set()      # every local name bound to an imported module
    os_names = set()          # names bound to the os module itself
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for a in node.names:
                bound = a.asname or _root(a.name)
                if a.name in ("os", "os.path"):
                    if a.name == "os" or a.asname is None:
                        os_names.add(bound)
                    module_names.add(bound)
                    continue
                if not _module_allowed(a.name):
                    out.append(f"{path}:{line}: import {a.name} (not allowed)")
                module_names.add(bound)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:            # relative import inside drivers/
                continue
            for a in node.names:
                if a.name == "*":
                    out.append(f"{path}:{line}: from {mod} import *")
            if mod == "os":
                for a in node.names:
                    if a.name != "path":
                        out.append(f"{path}:{line}: from os import {a.name} (only os.path)")
                    module_names.add(a.asname or a.name)
            elif mod == "os.path":
                pass
            elif not _module_allowed(mod):
                out.append(f"{path}:{line}: from {mod} import ... (not allowed)")
            else:
                for a in node.names:
                    module_names.add(a.asname or a.name)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            if fn in FORBIDDEN_CALLS:
                out.append(f"{path}:{line}: call {fn}()")
            if fn in ATTR_CALLS:
                tgt = node.args[0] if node.args else None
                name = node.args[1] if len(node.args) >= 2 else None
                if isinstance(tgt, ast.Name) and tgt.id in module_names:
                    out.append(f"{path}:{line}: {fn}() on module {tgt.id}")
                elif not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
                    out.append(f"{path}:{line}: {fn}() with a computed attribute name")
                elif name.value.startswith("__"):
                    out.append(f"{path}:{line}: {fn}() of {name.value}")
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in os_names \
                    and node.attr != "path":
                out.append(f"{path}:{line}: os.{node.attr} (only os.path)")
            if node.attr in DUNDER_ESCAPES:
                out.append(f"{path}:{line}: .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in ("__builtins__", "__loader__", "__spec__"):
            out.append(f"{path}:{line}: {node.id}")
    return sorted(set(out), key=lambda s: (int(s.split(":")[1]) if s.split(":")[1].isdigit() else 0, s))


def _line_hash(src_lines, lineno):
    text = src_lines[lineno - 1].strip() if 0 < lineno <= len(src_lines) else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def default_targets(root):
    files = sorted(glob.glob(os.path.join(root, "protocol*.py")))
    files += sorted(glob.glob(os.path.join(root, "drivers", "**", "*.py"), recursive=True))
    return files


def main(argv):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = argv or default_targets(here)
    findings = []
    for p in files:
        rel = os.path.relpath(p, here).replace(os.sep, "/")
        with open(p, encoding="utf-8") as fh:
            src = fh.read()
        lines = src.splitlines()
        for f in scan_source(src, rel):
            parts = f.split(": ", 1)
            lineno = int(parts[0].rsplit(":", 1)[1]) if parts[0].rsplit(":", 1)[1].isdigit() else 0
            if (rel, parts[1], _line_hash(lines, lineno)) not in REVIEWED:
                findings.append(f)
    for f in findings:
        print(f)
    print(f"scanned {len(files)} file(s): {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
