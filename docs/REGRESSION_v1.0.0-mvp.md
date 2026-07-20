# Regression Report — v1.0.0-mvp

**Tag:** `v1.0.0-mvp` → commit `16d3844`  
**Date:** 2026-07-20  
**Host:** local macOS · LibreOffice optional (cases below used `--no-visual-diff` for speed)

## Unit tests

```text
Ran 42 tests · OK (skipped=1)
```

## Scenario matrix

| Case | Input | Mode | Result |
| --- | --- | --- | --- |
| Text + layout | Attention p1–3 | positioned | PASS · DOCX written · validation true |
| Flow editable | Attention p1 | editable | PASS · CER path active |
| Table-heavy | Attention p9 | positioned | PASS |
| Formula-ish | Attention p5–6 | positioned | PASS · degraded warning (docling unavailable → native) |
| **Scanned / no text layer** | synthetic image-only PDF · word_count=0 | positioned | **PASS no crash** · WARNING degraded mineru→native |
| **Batch** | dir with scanned + attention | positioned p1 | **BATCH_OK: 2 files** · both DOCX present |

Artifacts (local, gitignored under `workspace/jobs/`):

```text
workspace/jobs/mvp-regression/
  fixtures/scanned_no_text.pdf
  fixtures/attention_text_tables_formulas.pdf
  out/*.docx
  batch-out/{a_scanned,b_attention}.docx
  logs/*.log
```

## P0 / P1 / P2 checklist

| Item | Status at tag |
| --- | --- |
| Scanned no-OCR no crash + warning | Done |
| `start.sh` `.env` + `logs/start.log` + macOS dialog | Done |
| `framePr` no-op | Done |
| Default mode `positioned`; hybrid/fidelity labeled | Done |
| DrawingML non-empty text + `--strict-visual` | Done |
| `--pages` optional (default all) | Done |
| `pdf2word batch` | Done |
| README modes / scan / formula / batch | Done |

## Remote

Push when `origin` exists:

```bash
git push -u origin main
git push origin v1.0.0-mvp
```
