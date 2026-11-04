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


def test_alias_and_module_getattr_bypasses_are_caught():
    cases = {
        "import os as o\no.system('x')\n": "os.system",
        "import os\ngetattr(os, 'system')('x')\n": "on module os",
        "import os.path as p\nimport os\nos.popen('x')\n": "os.popen",
        "from os import system\n": "only os.path",
        "from os import system as s\n": "only os.path",
        "import sys\nsys.modules['subprocess']\n": "import sys",
        "import asyncio\n": "import asyncio",
        "import io\n": "import io",
        "import pathlib\n": "import pathlib",
        "import struct as s\ngetattr(s, 'pack')\n": "on module s",
        "x = ().__class__.__bases__[0].__subclasses__()\n": "__subclasses__",
        "getattr(obj, '__globals__')\n": "of __globals__",
        "from struct import *\n": "import *",
    }
    for src, needle in cases.items():
        assert _hits(src), (src, needle)


def test_allowed_code_stays_clean():
    src = ("import os\nimport os.path\nfrom os import path\nimport struct as st\n"
           "from .base import BoardDriver\nimport protocol_mini60 as pm\nimport boards\n"
           "p = os.path.join('a', 'b')\nn = getattr(profile, 'slug', None)\n")
    assert _hits(src) == []


def test_reviewed_exemption_is_pinned_to_the_line(tmp_path, monkeypatch):
    # The real mini60 exemption passes; the same finding on another line does not.
    assert scan_contrib.main([]) == 0
    f = tmp_path / "drivers" / "mini60.py"
    f.parent.mkdir()
    f.write_text("x = open('other')\n")
    monkeypatch.setattr(scan_contrib.os.path, "relpath", lambda p, start: "drivers/mini60.py")
    assert scan_contrib.main([str(f)]) == 1


def test_transitive_and_submodule_escapes_are_caught():
    cases = {
        "import os\nos.path.os.system('x')\n": "reaches os",
        "import os.path as p\np.os.system('x')\n": "reaches os",
        "from os.path import os\n": "from os.path import os",
        "import logging.config\n": "import logging.config",
        "import logging\nlogging.config.listen()\n": "reaches config",
        "import logging\nlogging.handlers.SocketHandler('h', 1)\n": "reaches handlers",
        "from logging import config\n": "from logging import config",
        "from logging import handlers as h\n": "from logging import handlers",
        "import threading\nthreading._os\n": "reaches _os",
        "import json\njson.decoder.sys\n": "reaches sys",
        "import json.decoder\n": "import json.decoder",
        "import protocol_x.evil\n": "import protocol_x.evil",
    }
    for src, needle in cases.items():
        assert _hits(src), (src, needle)


def test_ordinary_module_use_stays_clean():
    src = ("import logging\nimport threading\nimport struct\nimport os\n"
           "log = logging.getLogger(__name__)\nt = threading.Thread(target=f)\n"
           "b = struct.pack('<H', 1)\np = os.path.join(os.path.dirname(x), 'y')\n"
           "import drivers.base\nimport protocol_mini60\n")
    assert _hits(src) == []


def test_module_aliases_through_assignment_and_arguments_are_caught():
    for src in ("import os\nm = os\nm.system('x')\n",
                "import os\nx = os.path\nx.os.system('x')\n",
                "import os\nf(os)\n",
                "import os\nd = {'m': os}\n",
                "import os\nfor m in [os]:\n    pass\n",
                "import os\nwith ctx(os) as m:\n    pass\n",
                "import os\nreturn_it = lambda: os\n",
                "import os\ngetattr(os, 'system')\n",
                "import json\njson.decoder\n",
                "import threading\nthreading.Thread._bootstrap\n",
                "import boards\nboards.os.system('x')\n",
                "from struct import _clearcache\n"):
        assert _hits(src), src


def test_allowed_stdlib_attribute_list_is_enforced():
    assert _hits("import time\ntime.sleep(0.1)\nt = time.monotonic()\n") == []
    assert _hits("import struct\nstruct.pack('<H', 1)\nstruct.Struct('<H').pack(1)\n") == []
    assert _hits("import threading\nthreading.Thread(target=f).start()\n") == []
    assert _hits("import time\ntime.tzset()\n")
