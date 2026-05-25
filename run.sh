#!/usr/bin/env bash
# Launch the AETHER HE Keyboard Hub (exact Claude Design rendered in a webview).
cd "$(dirname "$0")"
exec venv-web/bin/python app_web.py
