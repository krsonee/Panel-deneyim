#!/usr/bin/env bash
# Cloud Agent install: refresh Python deps for MakroPanel + Mikromail.
# Idempotent — safe to run repeatedly and against cached state.
set -euo pipefail

cd "$(dirname "$0")/.."

# The default image ships python3.12 but not the venv module; add it once.
if ! dpkg -s python3.12-venv >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv
fi

# Keep the virtualenv outside the repo checkout so it survives re-checkout
# when a fresh agent boots from a prebuilt environment.
VENV="$HOME/.venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r requirements.txt

echo "install: MakroPanel/Mikromail dependencies ready in $VENV"
