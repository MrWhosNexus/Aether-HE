"""Guards for the hand-edited JSX sources and their built output: an
unterminated block comment silently swallows the code after it (the Settings
workspace once threw "BackupWidget is not defined" at load)."""
import glob
import os
import re

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")
FILES = sorted(glob.glob(os.path.join(SRC, "src", "*.jsx"))
               + glob.glob(os.path.join(SRC, "workspaces", "*.jsx")))


def _unterminated_comments(text):
    """Line numbers of block comments that never close before the next one
    opens (their body contains another '/*') or before end of file. A stray
    '*/' outside a comment (e.g. inside a regex literal) is ignored."""
    bad, pos = [], 0
    while True:
        i = text.find("/*", pos)
        if i < 0:
            return bad
        j = text.find("*/", i + 2)
        line = text.count("\n", 0, i) + 1
        if j < 0 or "/*" in text[i + 2:j]:
            bad.append(line)
            pos = i + 2
        else:
            pos = j + 2


def test_unterminated_comment_detector_catches_the_swallow_bug():
    src = "/* a */\n/* open\nfunction F() {}\n/* b */\nx"
    assert _unterminated_comments(src) == [2]
    assert _unterminated_comments("/* a */ code /* b */") == []
    assert _unterminated_comments(r"s.replace(/\s*/g, ' ') /* ok */") == []


@pytest.mark.parametrize("path", FILES, ids=[os.path.basename(p) for p in FILES])
def test_jsx_block_comments_are_terminated(path):
    with open(path, encoding="utf-8") as fh:
        assert _unterminated_comments(fh.read()) == [], path


def test_built_settings_workspace_defines_backup_widget():
    with open(os.path.join(SRC, "build", "ws_settings.js"), encoding="utf-8") as fh:
        code = re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)
    assert "function BackupWidget" in code
    assert "render: BackupWidget" in code
