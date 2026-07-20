# Restoration Quality Report

Baseline sample: `NIPS-2017-attention-is-all-you-need-Paper.pdf`.

**Release `v1.0.0-mvp` (2026-07-20)** — full 11-page CLI E2E with LibreOffice visual loop.  
**Stakeholder summary:** [DELIVERY_REPORT.md](DELIVERY_REPORT.md)

| Mode | Job | Pages | mean MAD | Overall |
| --- | --- | ---: | ---: | --- |
| **`editable`** | `workspace/archive/v1.0.0-mvp/` | **11 → 11** | **0.0726** | **PASS** (CER 0.0; visual warn) |
| **`positioned`** | `workspace/archive/v1.0.0-mvp/` | **11 → 11** | **0.0493** | **PASS** (≤0.055) |
| **`hybrid`** | `workspace/jobs/release-v1/hybrid/` | **11 → 11** | **0.0198** | **PASS** |
| **`fidelity`** | `workspace/jobs/release-v1/fidelity/` | **11 → 11** | **0.0194** | **PASS** |

Release archive: `workspace/archive/v1.0.0-mvp/` (`docx/`, `validation/`, `logs/`).  
Unit tests: **42 OK** (1 skipped). GUI smoke archive: `workspace/archive/gui-smoke-20260720/`.

Phase 4 / historical regression rows below are retained for audit.

## Verified

- Native text-layer extraction still works.
- Tightened PDF word-gap reconstruction keeps positioned inter-word spaces as separate editable runs for the baseline sample.
- Canonical IR now includes typed elements, runs, page regions, and dedicated payload slots.
- IR schema `1.4` preserves separator graphics, underline state, four OOXML font slots, source font names, run colors, source line breaks and normalized `line_bboxes`, image source dimensions, table geometry, merge placeholders/spans, per-cell border evidence, and an optional source-page snapshot path.
- The baseline page produced:
  - 1 heading
  - 43 paragraphs
  - 1 footer
- DOCX output can write detected footer text into the Word section footer.
- Each input page now gets an independent Word section so page-specific footer text is not overwritten by the last page.
- Synthetic renderer test covers:
  - header rendering
  - footer rendering
  - real Word table rendering
  - mixed-font text runs
- The full 11-page sample converts successfully with the native fallback and renders to an 11-page DOCX PDF in the current packed editable flow.
- The full 11-page sample in `fidelity` mode renders to exactly 11 pages under LibreOffice; each page is backed by its source-page snapshot, including the table-heavy page 9.
- The page 3 embedded image is extracted from its PDF image stream at `1520 x 2239` pixels instead of only using a page crop.
- The page 9 table is recovered as 8 rows x 13 columns with fixed column widths, row heights, and inferred cell borders.
- Page 9 multiline numeric cells retain source line breaks; synthetic merged-cell coverage is represented as `None` placeholders plus `row_span`/`col_span` in the IR.
- `positioned` mode now emits native DrawingML text boxes and image anchors. The page 3 embedded figure remains a replaceable Word picture rather than a VML drawing.
- Source font faces and grayscale text colors are retained on individual IR runs; normalized desktop families remain the current Word fallback policy.
- `validation/preflight.json` records native availability, preferred/selected parser per page, and the clone/import status of MinerU, Docling, and PaddleOCR.
- Post-render `ValidationEngine` writes `validation/validation_report.json` + `.md` for every conversion (disable with `--no-validate`).
- Baseline page 1 and table-heavy page 9: structure/text/table/image layers pass with IR↔DOCX character error rate `0.0` when document order is preserved.
- Full current 11-page editable conversion structure/text/table/image layers pass (CER `0.0`); the page-count gate is now `11 → 11`, with a visual warning only for elevated MAD on page 2.

## Partially Implemented

- Font preservation now stores run-level font name and size, and writes Word `ascii`, `hAnsi`, `eastAsia`, and `cs` font slots. It does not yet map PDF embedded font names to clean installed system font families.
- Tables are extracted through `pdfplumber.find_tables()` and refined with row-rule and text-anchor recovery when a PDF exposes only a frame. Per-cell border width/color and fixed geometry are preserved, but merged header spans in the paper table still need stronger inference.
- Images are represented in IR. `PdfPlumberBackend` first decodes the embedded stream into a job-local PNG and falls back to a page crop only when the stream cannot be decoded. Floating placement and rotation are still limited by the inline Word renderer.
- PDF horizontal rules below text can become native Word underline properties only when their width matches the text; long rules beneath short labels are retained as cover/form guide-line separators and rendered as native rule geometry.
- Formula detection is heuristic. High-confidence fractions, superscripts, subscripts, and radicals emit structured OMML; other formula-like lines retain an editable token-stream representation in the IR and use the source-coordinate text fallback in the positioned renderer until a full math recognizer is available. Nested math trees, equation numbering, and raster/scanned formulas still need a dedicated recognizer.
- The tighter `x_tolerance=2.0` extraction recovers many positioned English word gaps, but it cannot infer spaces that are absent from both the PDF text stream and character geometry.
- **Editable geometry packing (2026-07-20):** each PDF page contributes to a continuous Word flow with matching `612×792` page geometry; margins are derived from body bbox extents; vertical gaps and horizontal insets come from IR bboxes; default Word paragraph gaps are zeroed; same-paragraph line merge is slightly more aggressive. Current baseline structure/text/table/image layers pass and LibreOffice page count is `11/11`.

## Visual loop (LibreOffice) — 2026-07-20

LibreOffice is installed at `/Applications/LibreOffice.app/Contents/MacOS/soffice` and wired via `PDF2WORD_SOFFICE`.

| Mode | Job | Source pages | Rendered pages | Δ | mean MAD | Overall |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `editable` baseline (pre-pack) | `workspace/jobs/visual-editable-full11/` | 11 | **21** | **+10** | 0.064 | **FAIL** |
| `editable` pack-v1 | `workspace/jobs/pack-v1/` | 11 | **13** | +2 | 0.070 | FAIL |
| `editable` pack-v9 | `workspace/jobs/pack-v9/` | 11 | **12** | +1 | 0.069 | PASS (tol≤1) |
| `editable` pack-v14 | `workspace/jobs/pack-v14/` | 11 | **11** | 0 | **0.0692** | PASS (CER 0.0; structure footer warn) |
| `editable` mad-v10 (historical) | `workspace/jobs/mad-v10/` | 11 | **11** | **0** | 0.0724 | PASS (structure pass + CER 0.0; visual warn p2/p6) |
| `editable` IR 1.4 rerun | `workspace/jobs/phase3-editable4/` | 11 | **11** | 0 | 0.0738 | PASS |
| **`editable` Phase 4 formula rerun** | `workspace/jobs/phase4-editable1/` | 11 | **11** | 0 | **0.0726** | **PASS** (CER 0.0; visual warn) |
| `fidelity` (legacy inline snapshot) | phase3 / visual-fidelity-full11 | 11 | 11 | 0 | ~0.055 | PASS |
| **`fidelity` DrawingML behind-doc** | `workspace/jobs/dml-fid1/` | 11 | **11** | 0 | **0.0194** | **PASS** |
| `positioned` DrawingML (pre-line-split) | `workspace/jobs/dml-pos2/` | 11 | 11 | 0 | 0.0612 | PASS (warn p2) |
| `positioned` DrawingML (previous baseline) | `workspace/jobs/phase4-formula7/` | 11 | 11 | 0 | 0.0483 | PASS (≤0.055 target) |
| `positioned` DrawingML (GUI smoke) | `workspace/archive/gui-smoke-20260720/` | 11 | **11** | 0 | 0.0493 | PASS (≤0.055) |
| **`positioned` DrawingML (v1.0.0-mvp release)** | `workspace/archive/v1.0.0-mvp/` | 11 | **11** | 0 | **0.0493** | **PASS** (≤0.055) |
| **`hybrid` snapshot+DrawingML** | `workspace/jobs/dml-hybrid1/` / release-v1 | 11 | **11** | 0 | **0.0198** | **PASS** |
| **`hybrid` Phase 4 rerun** | `workspace/jobs/phase4-hybrid1/` | 11 | **11** | 0 | **0.0198** | **PASS** |
| **`editable` v1.0.0-mvp release** | `workspace/archive/v1.0.0-mvp/` | 11 | **11** | 0 | **0.0726** | **PASS** (CER 0.0) |
| **`fidelity` v1.0.0-mvp release** | `workspace/jobs/release-v1/fidelity/` | 11 | **11** | 0 | **0.0194** | **PASS** |

**v1.0.0-mvp release archive:** `workspace/archive/v1.0.0-mvp/` — four DOCX, validation JSON/MD, CLI logs, `preflight.json`.

GUI smoke archive (earlier same day): `workspace/archive/gui-smoke-20260720/` (PySide6 `6.11.1`, four modes, all `passed=true`, 11/11 pages).

### DrawingML workstream (MAD path)

Delivered modes:

1. **`positioned`** — `wp:anchor` + `wps:txbx` **per-source-line** text boxes, floating tables (`tblpPr`), anchored images. Release mean MAD **0.0493** (≤0.055). IR `1.4` stores `line_bboxes` for pixel anchoring.
2. **`hybrid`** — full-page snapshot with `behindDoc=1` + DrawingML editable layer using `w:vanish`. Mean MAD **0.0198**.
3. **`fidelity`** — snapshot-only paint via the same behind-doc anchor; mean MAD **0.0194**.

Positioned MAD path (0.061 → 0.048):

- Split multi-line IR blocks into one DrawingML textbox per source line.
- Persist normalized `line_bboxes` on IR elements (schema 1.4).
- LO-stable font mapping (Times/Helvetica → installed faces).
- Tighter `bodyPr` (`wrap=none`, overflow, zero insets) + slight width pad for wrap safety.

Notes:

- Abandoned `w:framePr` for LO (collapses pages). DrawingML anchors are the supported path.
- Hybrid remains best when page bitmaps are acceptable.
- Pure positioned is the path when the file must not embed page bitmaps **and** mean MAD ≤ 0.055.
- Phase 4 formula regression keeps complex formula-like lines editable as source-coordinate text while storing a bounded OMML token representation in IR. Direct OMML painting is restricted to stable structured objects because flat OMML token streams change LibreOffice font metrics and can overlap nearby text.

### Editable page-pack workstream

What reduced **21 → 11**:

1. **Aggressive line/paragraph merge** in `NativeTextParser` (including short formula fragments; formula false-positives reduced).
2. **Exact line spacing** + compressed bbox gaps; skip thin separators.
3. **Font family normalization** (Times/Helvetica → desktop faces) and density-aware optical shrink.
4. **Layout change:** default `continuous` flow with soft page breaks between source pages (not hard sections). Hard per-page sections could not reclaim overflow and caused the original 21-page blow-up.
5. **Per-page auto-fit pack profile** estimating body height from IR and tightening font/space/image caps until the estimate fits one canvas.
6. Compact formula rendering (prefer italic text over tall OMML in editable).
7. **Multi-column detection** (column-major reading order + gutter collapse to full-measure single-column flow).
8. **Inline embedded images** (no floating wrap) with density-based height caps.
9. **STEM table compression** on page 9-style grids: compact row constraints, cell padding, and font scale (page 9 alone was the last 12→11 overflow source).

Acceptance now:

- editable LibreOffice page count **= 11** on Attention baseline
- text CER **0.0**
- structure **pass** (continuous footer emits IR text + PAGE field with cached result)
- mean MAD **≈ 0.072** for flow `editable` (semantic path)
- **hybrid/fidelity DrawingML path mean MAD ≈ 0.020** (pixel path, target 0.055 exceeded)

### Mode roles

| Mode | Edit surface | Pixel authority | Typical MAD |
| --- | --- | --- | ---: |
| `editable` | Flow paragraphs | Reflow paint | ~0.07 |
| `positioned` | DrawingML objects | DrawingML paint | **0.0493** |
| `hybrid` | DrawingML (vanished) | Snapshot behind | **0.0198** |
| `fidelity` | None / snapshot only | Snapshot | **0.0194** |

## Not Yet Implemented

- Pure `positioned` page-2 residual (~0.064) still trails hybrid; further gains need font-metric matching / kerning.
- Making hybrid text visible while keeping snapshot MAD (would double-paint unless text is transparent or selectively hidden).
- `positioned` is not yet a pixel-accurate editable renderer: the latest line-fit guard reduces long-text wrapping/clipping risk, but font-metric and kerning residuals remain. The page 9 native floating table retains logical rows, marks the first row as a repeating header, and prevents row splitting; header/cell metric matching and cross-editor checks remain. The native image anchor path is verified, but rotation/cropping needs cross-editor checks.
- Cross-page table continuation.
- OCR-based scanned page recovery.
- PySide6 `6.11.1` is installed. GUI smoke (Qt offscreen + native macOS Cocoa) completed without crash; `v1.0.0-mvp` freezes the CLI four-mode metrics above. Cross-platform desktop packaging remains a follow-up.
- Native fallback is intentionally marked as degraded for formula-heavy or scanned pages until executable optional runtimes and model artifacts are available; the current project `.venv` probes record Docling blocked by `docling_core`, MinerU dependency-gated, and PaddleOCR blocked by `paddlex`.
