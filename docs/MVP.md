# MVP Build Notes

The first implementation deliberately avoids Agent repair.

**Release:** `v1.0.0-mvp` (2026-07-20)  
**Full delivery write-up:** [DELIVERY_REPORT.md](DELIVERY_REPORT.md)

## Implemented

- `PdfBackend` protocol and `PdfPlumberBackend` (text, image streams, lines, rectangles, tables).
- `NativeTextParser` → ordered paragraph/run elements with page-region and graphic evidence.
- Canonical Document IR (schema **1.4**): image, table, formula, header/footer, separator, border, font slots, `line_bboxes`.
- `EditableDocxRenderer`: continuous packing, multi-column collapse, inline images, STEM table compression, real tables, footer + PAGE field.
- `FidelityDocxRenderer` DrawingML family: `positioned` / `hybrid` / `fidelity`.
- Capability-aware preflight + router; optional adapters fall back to native.
- `ValidationEngine`: structure / text (CER) / table / image / visual (LibreOffice MAD + page count).
- CLI: `pdf2word convert` with four modes; optional `pdf2word gui` (PySide6).
- Local job workspace + release archive under `workspace/archive/v1.0.0-mvp/`.

## Acceptance snapshot (Attention, 11 pages)

| Mode | Pages | mean MAD | Notes |
| --- | ---: | ---: | --- |
| `editable` | 11 → 11 | 0.0724 | CER 0.0; visual warn on residual pages |
| `positioned` | 11 → 11 | 0.0492 | ≤ 0.055 gate |
| `hybrid` | 11 → 11 | 0.0198 | snapshot behind + vanish layer |
| `fidelity` | 11 → 11 | 0.0194 | snapshot proof |

Unit tests: **38 OK** (1 skipped). GUI smoke: preflight + four modes + Open output on macOS Cocoa.

## Next Engineering Steps

1. Shave pure-`positioned` page-2 residual (~0.064) via font-metric / kerning.
2. Stronger table merge inference and true cross-page table continuation.
3. Pin Docling models; install MinerU / PaddleOCR runtimes behind `DocumentParser`.
4. OCR + formula-region recognition for scanned / math-heavy pages.
5. IR patch/revision storage, then optional Agent repair loop.
6. Cross-platform desktop packaging beyond the validated macOS shell.
