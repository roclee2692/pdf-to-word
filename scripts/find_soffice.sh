#!/usr/bin/env bash
# Print LibreOffice soffice path if found (macOS / Linux / Windows Git-Bash / WSL).
set -euo pipefail

if [ -n "${PDF2WORD_SOFFICE:-}" ] && [ -x "${PDF2WORD_SOFFICE}" ]; then
  echo "$PDF2WORD_SOFFICE"
  exit 0
fi

if command -v soffice >/dev/null 2>&1; then
  command -v soffice
  exit 0
fi
if command -v libreoffice >/dev/null 2>&1; then
  command -v libreoffice
  exit 0
fi

candidates=(
  "/Applications/LibreOffice.app/Contents/MacOS/soffice"
  "/usr/bin/soffice"
  "/usr/bin/libreoffice"
  "/usr/local/bin/soffice"
  "/snap/bin/libreoffice"
  "/opt/libreoffice*/program/soffice"
  "/mnt/c/Program Files/LibreOffice/program/soffice.exe"
  "/mnt/c/Program Files (x86)/LibreOffice/program/soffice.exe"
)

for pattern in "${candidates[@]}"; do
  # shellcheck disable=SC2086
  for path in $pattern; do
    if [ -x "$path" ] || [ -f "$path" ]; then
      echo "$path"
      exit 0
    fi
  done
done

exit 1
