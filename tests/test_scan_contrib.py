"""tools/scan_contrib.py: the CI gate for board-support code."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import scan_contrib  # noqa: E402


def _hits(src):
    return scan_contrib.scan_source(src, "p.py")


def test_repo_board_code_is_clean():
    assert scan_contrib.main([]) == 0


def test_plain_packet_code_passes():
    assert _hits("import struct\nimport os.path\nX = getattr(o, 'slug', None)\n"
                 "def build(a):\n    return bytes([1, a & 0xFF])\n") == []


def test_flags_network_process_native_and_eval():
    src = ("import subprocess\nimport urllib.request\nfrom socket import socket\n"
           "import ctypes\nimport pickle\nimport base64\n"
           "eval('1')\nexec('x=1')\n__import__('os')\nopen('f')\n"
           "import os\nos.system('x')\nos.remove('f')\n"
           "getattr(o, name)\n().__class__.__subclasses__\n")
    found = " ".join(_hits(src))
    for needle in ("import subprocess", "import urllib.request", "from socket", "import ctypes",
                   "import pickle", "import base64", "call eval", "call exec", "call __import__",
                   "call open", "os.system", "os.remove", "computed attribute", "__subclasses__"):
        assert needle in found, needle


def test_unparseable_code_fails():
    assert "does not parse" in _hits("def (:\n")[0]
