# v1.0.0-mvp release archive

Date: 2026-07-20  
Sample: `NIPS-2017-attention-is-all-you-need-Paper.pdf` pages 1–11  
Environment: project `.venv`, LibreOffice via `PDF2WORD_SOFFICE`, macOS

## Metrics

| Mode | Pages | mean MAD | VALIDATION_PASSED |
| --- | ---: | ---: | --- |
| editable | 11 → 11 | 0.0726 | true (visual warn; CER 0.0) |
| positioned | 11 → 11 | 0.0493 | true |
| hybrid | 11 → 11 | 0.0198 | true |
| fidelity | 11 → 11 | 0.0194 | true |

## Layout

```text
docx/{editable,positioned,hybrid,fidelity}.docx
validation/{mode}.validation_report.{json,md}
validation/preflight.json
logs/{mode}.cli.log
RELEASE_METRICS.json
```

## Reproduce

```bash
export PDF2WORD_SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"
PYTHONPATH=src .venv/bin/python -m pdf2word convert \
  NIPS-2017-attention-is-all-you-need-Paper.pdf \
  --pages 1-11 --mode positioned \
  --out workspace/jobs/demo/result.docx --dump-ir
```
