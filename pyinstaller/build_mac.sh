#!/bin/sh
# Build the macOS directory bundle, using the project .venv if present.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
else
    PYTHON=python3
fi

echo "Using Python: $PYTHON"
"$PYTHON" -m pip install pyinstaller
"$PYTHON" pyinstaller/build_exe.py "$@"
