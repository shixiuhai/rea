#!/usr/bin/env bash
# One-command runner. Examples:
#   ./run.sh selftest
#   ./run.sh list --tab store
#   ./run.sh search --query "斗罗大陆"
#   ./run.sh extract-so
#   ./run.sh probe-native
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

if [ ! -d .venv ] && ! python3 -c "import requests" 2>/dev/null; then
  echo "[run] installing dependencies..."
  "$PY" -m pip install -r requirements.txt
fi

exec "$PY" cli.py "$@"
