#!/bin/bash
# One-click GUI launcher for PDF-to-Word (macOS / Linux).
cd "$(dirname "$0")"

export PDF2WORD_SOFFICE="${PDF2WORD_SOFFICE:-/Applications/LibreOffice.app/Contents/MacOS/soffice}"

if [ ! -x .venv/bin/python ]; then
  echo "未找到 .venv，请先执行: ./scripts/setup.sh" >&2
  exit 1
fi

export PYTHONPATH=src
exec .venv/bin/python -m pdf2word gui
