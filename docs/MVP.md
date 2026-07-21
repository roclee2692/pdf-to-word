# MVP Build Notes

The first implementation deliberately avoids Agent repair.

**Release:** `v1.0.2-mode-specific-rendering` (2026-07-20)
**Full delivery write-up:** [DELIVERY_REPORT.md](DELIVERY_REPORT.md)

## Implemented

- `PdfBackend` protocol and `PdfPlumberBackend` (text, image streams, lines, rectangles, tables).
- `NativeTextParser` → ordered paragraph/run elements with page-region and graphic evidence.
- Canonical Document IR (schema **1.5**): image, table, formula, header/footer, separator, border, font slots, `line_bboxes`, source word-gap flags.
- `EditableDocxRenderer`: continuous packing, multi-column collapse, inline images, STEM table compression, real tables, footer + PAGE field.
- `FidelityDocxRenderer` DrawingML family: `positioned` / `hybrid` / `fidelity`.
- Capability-aware preflight + router; optional adapters fall back to native.
- `ValidationEngine`: structure / text (CER) / table / image / visual (LibreOffice MAD + page count).
- CLI: `pdf2word convert` with four modes; optional `pdf2word gui` (PySide6).
- Local job workspace + final release archive under `workspace/archive/v1.0.2-mode-specific-rendering/`.

## Acceptance snapshot (Attention, 11 pages)

| Mode | Pages | mean MAD | Notes |
| --- | ---: | ---: | --- |
| `editable` | 11 → 11 | 0.0737 | CER 0.0022; native full-grid tables; visual warn on residual pages |
| `positioned` | 11 → 11 | 0.0495 | ≤ 0.055 gate; native full-grid tables |
| `hybrid` | 11 → 11 | 0.0203 | snapshot behind + hidden layer + visible table grid |
| `fidelity` | 11 → 11 | 0.0197 | snapshot proof + vertical table separators |

Unit tests: **46 OK** (1 skipped). GUI smoke: preflight + four modes + Open output on macOS Cocoa.

GUI 对照预览已接入：转换完成后自动显示源 PDF 与 LibreOffice 渲染后的 DOCX 页面，可逐页切换并查看页数、MAD、CER 和 IR 元素摘要；实际编辑仍通过默认 Word/WPS/LibreOffice 打开生成的 DOCX。

The mode contract is intentional: `editable` is the text-editing output, `positioned` is the native-object layout output, `hybrid` is the visual-review compromise, and `fidelity` is the snapshot archive. Table 2 and Table 3 use full native grids in the editable modes; fidelity adds only precise vertical separator lines over the source page snapshot.

## Next Engineering Steps

1. Shave pure-`positioned` page-2 residual (~0.064) via font-metric / kerning.
2. Stronger table merge inference and true cross-page table continuation.
3. Pin Docling models; install MinerU / PaddleOCR runtimes behind `DocumentParser`.
4. OCR + formula-region recognition for scanned / math-heavy pages.
5. IR patch/revision storage, then optional Agent repair loop.
6. Cross-platform desktop packaging beyond the validated macOS shell.
