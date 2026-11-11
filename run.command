#!/usr/bin/env bash
# Launch the AETHER HE Keyboard Hub on macOS from a source checkout.
# Double-clickable in Finder (that is what .command buys over run.sh).
# For the packaged app use AetherHE.app instead — see AetherHE-macos.spec.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x venv-web/bin/python ]; then
  echo "No venv-web found. Creating one..."
  python3 -m venv venv-web
  venv-web/bin/pip install --upgrade pip
  venv-web/bin/pip install -r requirements.txt
fi

exec venv-web/bin/python app_web.py "$@"
