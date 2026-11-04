"""Security gate for board-support code (docs/security/2026-11-04-submissions-plan.md, rule 2).

Protocol modules (protocol*.py) and drivers (drivers/**/*.py) only build
packets and talk to the keyboard through the device object they are handed.
They must never reach the network, start programs, load native code,
deserialize objects, touch files, or run text as code.

This is an ALLOWLIST scan of the AST (nothing is imported or run):
  * imports: only the exact module names in ALLOWED_ATTRS / ALLOWED_LOCAL
    (plus protocol_<x>, drivers.<x>); `os` only for `os.path`;
  * standard-library modules: only the attributes listed per module in
    ALLOWED_ATTRS (None = any public name of a pure module), and the same
    for `from <module> import <name>`;
  * an imported module may only be used as `module.attribute`: assigning it,
    passing it, returning it or storing it anywhere is refused, so no alias
    can hide it from these rules;
  * local (owner-reviewed, .github/CODEOWNERS) modules: public attributes
    only, and no segment leading back out to os/sys/... ;
  * no eval/exec/compile/__import__/open/... builtins; no getattr & co. with
    a computed name or on a module; no dunder escape hatches.

    python tools/scan_contrib.py            # scan the repo's protocol/driver files
    python tools/scan_contrib.py a.py b.py  # scan given files
Exit 1 with one line per finding.
"""
import ast
import glob
import hashlib
import os
import re
import sys

# module -> attributes board code may use (exact module names).
ALLOWED_ATTRS = {
    "struct": {"pack", "unpack", "unpack_from", "pack_into", "calcsize", "iter_unpack",
               "Struct", "error"},
    "json": {"load", "loads", "dumps", "JSONDecodeError"},
    "logging": {"getLogger", "Logger", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"},
    "threading": {"Lock", "RLock", "Event", "Thread", "Condition", "Semaphore",
                  "BoundedSemaphore", "Timer", "current_thread", "get_ident"},
    "time": {"sleep", "time", "monotonic", "perf_counter", "time_ns", "monotonic_ns",
             "perf_counter_ns"},
    "math": {"floor", "ceil", "sqrt", "pow", "log", "log2", "log10", "exp", "sin", "cos",
             "tan", "atan2", "hypot", "pi", "e", "inf", "isfinite", "isnan", "isinf",
             "fabs", "fmod", "copysign", "trunc", "gcd", "isclose", "radians", "degrees"},
    "enum": {"Enum", "IntEnum", "Flag", "IntFlag", "auto", "unique"},
    "typing": {"Any", "Optional", "Union", "List", "Dict", "Tuple", "Set", "FrozenSet",
               "Iterable", "Iterator", "Sequence", "Mapping", "Callable", "Literal",
               "NamedTuple", "TypedDict", "ClassVar", "Final", "TYPE_CHECKING"},
    "dataclasses": {"dataclass", "field", "fields", "asdict", "astuple", "replace"},
    "collections": {"namedtuple", "deque", "OrderedDict", "defaultdict", "Counter"},
    "itertools": {"chain", "islice", "count", "cycle", "repeat", "product", "zip_longest",
                  "groupby", "accumulate", "pairwise", "combinations", "permutations"},
    "functools": {"partial", "lru_cache", "cache", "reduce", "wraps", "cached_property",
                  "total_ordering"},
    "re": {"compile", "match", "search", "fullmatch", "sub", "subn", "split", "findall",
           "finditer", "escape", "error", "Pattern", "Match", "I", "IGNORECASE", "M",
           "MULTILINE", "S", "DOTALL", "X", "VERBOSE", "A", "ASCII"},
    "binascii": {"hexlify", "unhexlify", "crc32", "b2a_hex", "a2b_hex"},
    "hid": {"device", "Device", "enumerate"},       # the HID library: device access is the job
    "os": {"path"},
    "os.path": {"join", "dirname", "basename", "abspath", "normpath", "split",
                "splitext", "exists", "isfile", "isdir", "sep"},
}
ALLOWED_LOCAL = {"boards", "device_state", "aula_device", "protocol", "drivers"}
_LOCAL_RE = re.compile(r"^(protocol_[a-z0-9_]+|drivers\.[a-z0-9_]+)$")
# Local modules are owner-reviewed, but no chain through them may lead back
# out to these (boards.os.system, device_state.threading._os, ...).
FORBIDDEN_SEGMENTS = {"os", "sys", "subprocess", "socket", "builtins", "importlib",
                      "config", "handlers", "ctypes", "shutil", "pickle", "marshal",
                      "codecs", "io", "pathlib", "urllib", "http", "signal", "pty",
                      "system", "popen", "spawn", "exec", "loader", "modules", "json",
                      "threading", "logging", "time", "struct", "hid", "re"}
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
    # lazy `import hid` in connected_profiles() so tests run without hidapi
    ("drivers/__init__.py", "import not at module top level", "27416581434e"),
}


def _is_local(name):
    return name in ALLOWED_LOCAL or bool(_LOCAL_RE.match(name or ""))


def _module_allowed(name):
    return name in ALLOWED_ATTRS or _is_local(name)


def _attr_ok(module, attr):
    """May `module.attr` be used? (module: exact dotted module name).
    stdlib modules: only the names on their explicit list (so typing.sys,
    json.decoder, os.path.os are out). Local modules: public names that are
    not FORBIDDEN_SEGMENTS (no route back out to os/sys/the stdlib)."""
    if attr.startswith("_"):
        return False
    if module in ALLOWED_ATTRS:
        return attr in ALLOWED_ATTRS[module]
    return _is_local(module) and attr not in FORBIDDEN_SEGMENTS


def _chain(node):
    """(root name, [attr, ...]) of a dotted chain like a.b.c, else (None, [])."""
    attrs = []
    while isinstance(node, ast.Attribute):
        attrs.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return node.id, list(reversed(attrs))
    return None, []


def scan_source(src, path="<src>"):
    """Findings (strings) for one module's source text."""
    try:
        tree = ast.parse(src, path)
    except SyntaxError as e:
        return [f"{path}:{e.lineno}: does not parse ({e.msg})"]
    out = []
    mods = {}                 # local name -> exact module it is bound to
    values = {}               # local name -> "module.attr" a from-import bound
    top = set(id(n) for n in tree.body)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, (ast.Import, ast.ImportFrom)) and id(node) not in top:
            # inside a class/function/if/try: its binding could escape the
            # name tracking below (class C: import os -> C.os.system)
            out.append(f"{path}:{line}: import not at module top level")
            continue
        if isinstance(node, ast.Import):
            for a in node.names:
                if not _module_allowed(a.name):
                    out.append(f"{path}:{line}: import {a.name} (not allowed)")
                    continue
                if a.asname and not _is_local(a.name):
                    # a renamed stdlib module could be re-exported under an
                    # innocent name (protocol_a: import os as h; b: protocol_a.h)
                    out.append(f"{path}:{line}: import {a.name} as {a.asname} "
                               "(stdlib modules may not be renamed)")
                    continue
                if a.asname:
                    mods[a.asname] = a.name
                else:                      # `import os.path` binds `os`
                    mods[a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level:                 # relative import inside drivers/
                for a in node.names:
                    values[a.asname or a.name] = "drivers"
                continue
            mod = node.module or ""
            if not _module_allowed(mod):
                out.append(f"{path}:{line}: from {mod} import ... (not allowed)")
                continue
            for a in node.names:
                if a.name == "*":
                    out.append(f"{path}:{line}: from {mod} import *")
                elif not _attr_ok(mod, a.name):
                    out.append(f"{path}:{line}: from {mod} import {a.name} (not allowed)")
                elif f"{mod}.{a.name}" in ALLOWED_ATTRS:     # from os import path
                    if a.asname and a.asname != a.name:
                        out.append(f"{path}:{line}: from {mod} import {a.name} as "
                                   f"{a.asname} (modules may not be renamed)")
                    else:
                        mods[a.name] = f"{mod}.{a.name}"
                else:
                    values[a.asname or a.name] = f"{mod}.{a.name}"
    parent = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            parent[c] = p
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            if fn in FORBIDDEN_CALLS:
                out.append(f"{path}:{line}: call {fn}()")
            if fn in ATTR_CALLS:
                name = node.args[1] if len(node.args) >= 2 else None
                if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
                    out.append(f"{path}:{line}: {fn}() with a computed attribute name")
                elif name.value.startswith("__"):
                    out.append(f"{path}:{line}: {fn}() of {name.value}")
        elif isinstance(node, ast.Name) and node.id in mods:
            up = parent.get(node)
            if not (isinstance(up, ast.Attribute) and up.value is node):
                # bare module value: an alias, an argument, a stored reference
                out.append(f"{path}:{line}: module {node.id} used as a value "
                           f"(only {node.id}.<attribute> is allowed)")
        elif isinstance(node, ast.Attribute):
            if node.attr in DUNDER_ESCAPES:
                out.append(f"{path}:{line}: .{node.attr}")
            if isinstance(parent.get(node), ast.Attribute) and parent[node].value is node:
                continue                   # check each chain once, from its outermost node
            root, attrs = _chain(node)
            if root in values and root not in mods:
                bad = [s for s in attrs if s.startswith("_") or s in FORBIDDEN_SEGMENTS]
                if bad:
                    out.append(f"{path}:{line}: {root}.{'.'.join(attrs)} (reaches {bad[0]})")
                continue
            if root not in mods:
                continue
            module = mods[root]
            for i, seg in enumerate(attrs):
                if not _attr_ok(module, seg):
                    out.append(f"{path}:{line}: {root}.{'.'.join(attrs[:i + 1])} (not allowed)")
                    break
                nxt = f"{module}.{seg}"
                if nxt in ALLOWED_ATTRS or _is_local(nxt):
                    module = nxt           # os -> os.path
                    if i == len(attrs) - 1:
                        # the whole chain IS a module (x = os.path): same rule
                        # as a bare module name
                        out.append(f"{path}:{line}: module {root}.{'.'.join(attrs)} "
                                   "used as a value")
                elif _is_local(module):
                    continue               # local module members: keep checking segments
                else:
                    # a value from an allowed stdlib module: later segments are
                    # ordinary method/attribute access, but never private
                    rest = attrs[i + 1:]
                    bad = [s for s in rest if s.startswith("_") or s in FORBIDDEN_SEGMENTS]
                    if bad:
                        out.append(f"{path}:{line}: {root}.{'.'.join(attrs)} (reaches {bad[0]})")
                    break
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
            tail = parts[0].rsplit(":", 1)[1]
            lineno = int(tail) if tail.isdigit() else 0
            if (rel, parts[1], _line_hash(lines, lineno)) not in REVIEWED:
                findings.append(f)
    for f in findings:
        print(f)
    print(f"scanned {len(files)} file(s): {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
