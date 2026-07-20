#!/bin/bash
# One-click GUI launcher for PDF-to-Word (macOS / Linux).
cd "$(dirname "$0")"

# Load machine-local env (PDF2WORD_SOFFICE, etc.)
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PDF2WORD_SOFFICE="${PDF2WORD_SOFFICE:-/Applications/LibreOffice.app/Contents/MacOS/soffice}"

LOG_DIR="./logs"
LOG_FILE="$LOG_DIR/start.log"
mkdir -p "$LOG_DIR"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE" >&2
}

if [ ! -x .venv/bin/python ]; then
  msg="未找到 .venv，请先执行: ./scripts/setup.sh"
  log "ERROR: $msg"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"$msg\" buttons {\"OK\"} default button 1 with icon stop with title \"PDF-to-Word\"" >/dev/null 2>&1 || true
  fi
  exit 1
fi

export PYTHONPATH=src
{
  echo "==== $(date '+%Y-%m-%d %H:%M:%S') start.sh ===="
  echo "PWD=$(pwd)"
  echo "PDF2WORD_SOFFICE=${PDF2WORD_SOFFICE:-}"
  echo "PDF2WORD_ENABLE_EXTERNAL_PARSERS=${PDF2WORD_ENABLE_EXTERNAL_PARSERS:-0}"
} >>"$LOG_FILE"

# Keep Qt free of a stdout pipe; append stderr to the log for crash diagnosis.
if ! .venv/bin/python -m pdf2word gui 2>>"$LOG_FILE"; then
  status=$?
  log "ERROR: GUI exited with status $status (see $LOG_FILE)"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"PDF-to-Word 启动失败，详见 logs/start.log\" buttons {\"OK\"} default button 1 with icon stop with title \"PDF-to-Word\"" >/dev/null 2>&1 || true
  fi
  exit "$status"
fi
