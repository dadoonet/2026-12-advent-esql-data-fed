#!/bin/sh
# Single public entry point; implementation lives in scripts/demo.py.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'ERROR: Install Python 3.10–3.14 and run ./demo.sh again.' >&2
  exit 1
fi
# Help and cleanup do not need Python packages or network access.
case "${1:-}" in
  help|-h|--help|down|reset) exec python3 scripts/demo.py "$@" ;;
esac
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import boto3, pyarrow; assert pyarrow.__version__ == "23.0.1"; assert boto3.__version__ == "1.40.70"' >/dev/null 2>&1; then
  echo '[prepare] Installing pinned Python dependencies into .venv'
  .venv/bin/python -m pip --disable-pip-version-check install -r requirements.txt
fi
exec .venv/bin/python scripts/demo.py "$@"
