# PDF-to-Word Final Acceptance Archive

Baseline: `NIPS-2017-attention-is-all-you-need-Paper.pdf` (11 pages)

The four DOCX outputs were generated after the formula/table/text fixes and
validated through the current native parser, IR schema 1.5, and LibreOffice
visual loop. `positioned` is the primary editable delivery; `editable` is the
flow/reflow delivery; `hybrid` and `fidelity` are pixel-proof variants.

The PySide6 GUI smoke also passed on macOS with preflight, all four modes,
validation summary fields, and the Open output action exercised.

Contents:

- `docx/`: final outputs for all four modes.
- `validation/`: per-mode `validation_report.json` and Markdown summaries.
- `validation_report.json`: primary `positioned` validation report.
- `preflight/`: parser capability and open-source runtime probes.
- `ir/`: dumped Canonical IR for each mode.
- `RELEASE_METRICS.json`: machine-readable acceptance summary.
