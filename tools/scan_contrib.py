"""Security gate for board-support code (docs/security/2026-11-04-submissions-plan.md, rule 2).

Protocol modules (protocol*.py) and drivers (drivers/*.py) only build packets
and talk to the keyboard through the device object they are handed. They must
never reach the network, start programs, load native code, deserialize
objects, touch files, or run text as code. This scans them with the AST (never
imports or runs them) and fails on anything outside that.

    python tools/scan_contrib.py            # scan the repo's protocol/driver files
    python tools/scan_contrib.py a.py b.py  # scan given files
Exit 1 with one line per finding.
"""
import ast
import glob
import os
import sys

FORBIDDEN_MODULES = {
    "subprocess", "socket", "ssl", "urllib", "http", "requests", "httpx",
    "aiohttp", "ftplib", "smtplib", "telnetlib", "xmlrpc", "webbrowser",
    "ctypes", "cffi", "pickle", "marshal", "shelve", "dill", "importlib",
    "runpy", "code", "codeop", "pty", "multiprocessing", "shutil", "tempfile",
    "winreg", "_winapi", "msvcrt", "base64", "zipimport", "builtins",
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "open", "input",
                   "breakpoint", "globals", "vars"}
# Attribute access by a name computed at runtime can reach anything; a fixed
# string literal (getattr(obj, "slug", None)) is ordinary code.
DYNAMIC_ATTR_CALLS = {"getattr", "setattr", "delattr", "hasattr"}
# Reviewed exceptions: (repo-relative path with "/", finding text without the
# line). Adding one needs a maintainer review (CODEOWNERS covers tools/).
REVIEWED = {
    # reads data/board_registry.json (read-only) for the dongle's frameLen
    ("drivers/mini60.py", "call open()"),
}
# os is allowed for os.path only; these attributes are not.
FORBIDDEN_OS = {"system", "popen", "spawnl", "spawnv", "spawnve", "spawnlp",
                "execv", "execve", "execl", "execlp", "execvp", "startfile",
                "remove", "unlink", "rmdir", "removedirs", "rename", "replace",
                "makedirs", "mkdir", "chmod", "kill", "fork", "environ", "putenv",
                "getenv", "open", "fdopen", "write", "listdir", "scandir", "walk"}


def _root(name):
    return (name or "").split(".")[0]


def scan_source(src, path="<src>"):
    """Findings (strings) for one module's source text."""
    try:
        tree = ast.parse(src, path)
    except SyntaxError as e:
        return [f"{path}:{e.lineno}: does not parse ({e.msg})"]
    out = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for a in node.names:
                if _root(a.name) in FORBIDDEN_MODULES:
                    out.append(f"{path}:{line}: import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and _root(node.module) in FORBIDDEN_MODULES:
                out.append(f"{path}:{line}: from {node.module} import ...")
            if node.level == 0 and _root(node.module) == "os":
                for a in node.names:
                    if a.name in FORBIDDEN_OS or a.name == "*":
                        out.append(f"{path}:{line}: from os import {a.name}")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in FORBIDDEN_CALLS:
                out.append(f"{path}:{line}: call {f.id}()")
            if (isinstance(f, ast.Name) and f.id in DYNAMIC_ATTR_CALLS
                    and not (len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                             and isinstance(node.args[1].value, str))):
                out.append(f"{path}:{line}: {f.id}() with a computed attribute name")
        elif isinstance(node, ast.Attribute):
            v = node.value
            if isinstance(v, ast.Name) and v.id == "os" and node.attr in FORBIDDEN_OS:
                out.append(f"{path}:{line}: os.{node.attr}")
            if node.attr in ("__subclasses__", "__globals__", "__builtins__", "__code__"):
                out.append(f"{path}:{line}: .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in ("__builtins__",):
            out.append(f"{path}:{line}: {node.id}")
    return out


def default_targets(root):
    files = sorted(glob.glob(os.path.join(root, "protocol*.py")))
    files += sorted(glob.glob(os.path.join(root, "drivers", "*.py")))
    return files


def main(argv):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = argv or default_targets(here)
    findings = []
    for p in files:
        rel = os.path.relpath(p, here).replace(os.sep, "/")
        with open(p, encoding="utf-8") as fh:
            for f in scan_source(fh.read(), rel):
                if (rel, f.split(": ", 1)[1]) not in REVIEWED:
                    findings.append(f)
    for f in findings:
        print(f)
    print(f"scanned {len(files)} file(s): {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
