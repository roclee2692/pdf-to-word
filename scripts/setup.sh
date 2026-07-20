#!/usr/bin/env bash
# Create .venv and install pinned dependencies for v1.0.0-mvp.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: python3 not found" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> creating .venv"
  "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> upgrading pip"
python -m pip install -U pip setuptools wheel

echo "==> installing pinned core deps"
python -m pip install -r requirements.txt

if [ "${SKIP_GUI:-0}" != "1" ]; then
  echo "==> installing GUI deps"
  python -m pip install -r requirements-gui.txt
else
  echo "==> skipping GUI (SKIP_GUI=1)"
fi

echo "==> editable install of pdf2word"
python -m pip install -e .

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "==> wrote .env from .env.example (edit PDF2WORD_SOFFICE if needed)"
fi

echo
echo "Setup complete."
echo "  GUI:  ./start.sh gui"
echo "  Test: ./start.sh test"
echo "  Conv: ./start.sh convert input.pdf --pages 1 --mode editable --out out.docx"
