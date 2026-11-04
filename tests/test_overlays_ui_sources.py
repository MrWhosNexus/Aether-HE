"""Phase 6 / Task 7: the Dashboard's "Status on keys" chips show the Pomodoro
phase + countdown (pure helper, run in node when installed)."""
import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "ui", "runtime_src")
NODE = shutil.which("node")

HARNESS = r"""
const fs = require("fs");
global.window = { AetherKeyboard: { KB_ROWS: [], KeyboardPanel() {} } };
global.React = { useState() {}, useEffect() {}, useMemo() {}, createElement() {} };
global.localStorage = { getItem() { return null; }, setItem() {} };
require("vm").runInThisContext(fs.readFileSync(process.argv[2], "utf8"), { filename: process.argv[2] });
const T = window.AetherDashboard.overlayText;
console.log(JSON.stringify([
  T({ id: "cpu", label: "CPU", on: true, value: 0.234 }),
  T({ id: "cpu", label: "CPU", on: false, value: null }),
  T({ id: "gpu", label: "GPU", on: false, available: false, value: null }),
  T({ id: "pomodoro", label: "Pomodoro", on: true, value: 0.4, phase: "work", remaining_s: 754 }),
  T({ id: "pomodoro", label: "Pomodoro", on: true, phase: "break", remaining_s: 59 }),
  T({ id: "pomodoro", label: "Pomodoro", on: false, value: 0.4, phase: "work", remaining_s: 754 }),
  T({ id: "pomodoro", label: "Pomodoro", on: true, value: 0.4 }),
]));
"""


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_chip_uses_the_helper_and_the_helper_is_exported():
    dash = _read("workspaces", "dashboard.jsx")
    assert "{overlayText(o)}" in dash
    assert "overlayView, overlayText," in dash
    assert "const overlayText = (o) => {" in dash


def test_built_dashboard_carries_the_helper():
    assert "overlayText" in _read("build", "ws_dashboard.js")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_chip_text(tmp_path):
    h = tmp_path / "h.cjs"
    h.write_text(HARNESS, encoding="utf-8")
    out = subprocess.run([NODE, str(h), os.path.join(SRC, "build", "ws_dashboard.js")],
                         check=True, capture_output=True, text=True, encoding="utf-8")
    assert json.loads(out.stdout) == ["CPU 23%", "CPU", "GPU", "Focus 12:34", "Break 0:59",
                                      "Pomodoro", "Pomodoro"]
