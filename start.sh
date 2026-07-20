#!/usr/bin/env bash
# Load .env and run pdf2word (convert | gui | test | python -m …).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Sensible macOS default if still unset
if [ -z "${PDF2WORD_SOFFICE:-}" ]; then
  for cand in \
    "/Applications/LibreOffice.app/Contents/MacOS/soffice" \
    "/opt/homebrew/bin/soffice" \
    "/usr/local/bin/soffice"; do
    if [ -x "$cand" ]; then
      export PDF2WORD_SOFFICE="$cand"
      break
    fi
  done
fi

if [ ! -x .venv/bin/python ]; then
  echo "error: .venv missing. Run: ./scripts/setup.sh" >&2
  exit 1
fi

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
PY=".venv/bin/python"

usage() {
  cat <<'EOF'
Usage:
  ./start.sh gui
  ./start.sh test
  ./start.sh convert <pdf> [pdf2word convert args...]
  ./start.sh python  <args...>     # raw .venv python
  ./start.sh help

Environment (from .env or shell):
  PDF2WORD_SOFFICE   LibreOffice binary for visual validation
  PDF2WORD_ENABLE_EXTERNAL_PARSERS=1  enable optional third_party parsers
EOF
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  help|-h|--help)
    usage
    ;;
  gui)
    exec "$PY" -m pdf2word gui "$@"
    ;;
  test|tests)
    exec "$PY" -m unittest discover -s tests -q "$@"
    ;;
  convert)
    if [ "$#" -lt 1 ]; then
      echo "error: convert requires a PDF path" >&2
      usage >&2
      exit 1
    fi
    exec "$PY" -m pdf2word convert "$@"
    ;;
  python)
    exec "$PY" "$@"
    ;;
  *)
    echo "error: unknown command: $cmd" >&2
    usage >&2
    exit 1
    ;;
esac
