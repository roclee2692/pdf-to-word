# LibreOffice setup for visual validation

Visual validation converts DOCX → PDF with LibreOffice, renders both the source PDF and that PDF to PNG, then computes page counts and mean absolute difference (MAD).

## Install (macOS)

```bash
brew install --cask libreoffice
```

Binary path:

```text
/Applications/LibreOffice.app/Contents/MacOS/soffice
```

Also linked as `/opt/homebrew/bin/soffice`.

## Environment

```bash
export PDF2WORD_SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"
```

Add the same line to `~/.zshrc` so new shells pick it up.

## Smoke test

```bash
$PDF2WORD_SOFFICE --headless --convert-to pdf --outdir /tmp /path/to/test.docx
```

## Run conversion with visual loop

```bash
export PDF2WORD_SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"
PYTHONPATH=src python -m pdf2word convert input.pdf --pages 1-11 --mode editable --out out.docx
# Look for VALIDATION_PASSED and VISUAL_PAGES lines
```

Artifacts:

- `job/validation/validation_report.json`
- `job/validation/visual/source_pages/`
- `job/validation/visual/docx_pdf/`
- `job/validation/visual/docx_pages/`
