#!/bin/bash
# CLI helper: ./scripts/cli.sh convert input.pdf --pages 1-11 --mode positioned --out out.docx
cd "$(dirname "$0")/.."
export PDF2WORD_SOFFICE="${PDF2WORD_SOFFICE:-/Applications/LibreOffice.app/Contents/MacOS/soffice}"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
if [ ! -x .venv/bin/python ]; then
  echo "未找到 .venv，请先执行: ./scripts/setup.sh" >&2
  exit 1
fi
export PYTHONPATH=src
exec .venv/bin/python -m pdf2word "$@"
