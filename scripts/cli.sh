#!/bin/bash
# CLI helper: ./scripts/cli.sh convert input.pdf --pages 1-11 --mode positioned --out out.docx
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
if [ -z "${PDF2WORD_SOFFICE:-}" ] || [ ! -x "${PDF2WORD_SOFFICE}" ]; then
  if SOFFICE_FOUND="$(./scripts/find_soffice.sh 2>/dev/null)"; then
    export PDF2WORD_SOFFICE="$SOFFICE_FOUND"
  fi
fi
if [ ! -x .venv/bin/python ]; then
  # Windows venv layout when using Git Bash
  if [ -x .venv/Scripts/python.exe ]; then
    PY=".venv/Scripts/python.exe"
  else
    echo "未找到 .venv，请先执行: ./scripts/setup.sh" >&2
    exit 1
  fi
else
  PY=".venv/bin/python"
fi
export PYTHONPATH=src
exec "$PY" -m pdf2word "$@"
