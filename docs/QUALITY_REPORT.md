# Restoration Quality Report

Baseline sample: `NIPS-2017-attention-is-all-you-need-Paper.pdf`.

**Current release `v1.0.2-mode-specific-rendering` (2026-07-20)** — full 11-page CLI E2E with LibreOffice visual loop, formula fallback verification, and full table-grid verification.
**Stakeholder summary:** [DELIVERY_REPORT.md](DELIVERY_REPORT.md)

| Mode | Job | Pages | mean MAD | Overall |
| --- | --- | ---: | ---: | --- |
| **`editable`** | `workspace/archive/v1.0.2-mode-specific-rendering/` | **11 → 11** | **0.0737** | **PASS** (CER 0.0022; visual warn) |
| **`positioned`** | `workspace/archive/v1.0.2-mode-specific-rendering/` | **11 → 11** | **0.0495** | **PASS** (≤0.055) |
| **`hybrid`** | `workspace/archive/v1.0.2-mode-specific-rendering/` | **11 → 11** | **0.0203** | **PASS** |
| **`fidelity`** | `workspace/archive/v1.0.2-mode-specific-rendering/` | **11 → 11** | **0.0197** | **PASS** |

Release archive: `workspace/archive/v1.0.2-mode-specific-rendering/` (`docx/`, `validation/`, `validation_report.json`, `preflight/`, `ir/`).
Unit tests: **46 OK** (1 skipped). GUI smoke archive: `workspace/archive/gui-smoke-20260720/`.

## Current Mode Contract

| Mode | Primary contract | Formula policy | Table policy |
| --- | --- | --- | --- |
| `editable` | Text and object editing | Editable runs with superscript/subscript; simple OMML plus hidden text fallback; complex formulas remain text | Native editable Word table with full horizontal and vertical borders; repeatable header and no row splitting |
| `positioned` | PDF-like placement with native objects | Source-coordinate formula crop plus hidden searchable text | Floating native Word table with fixed column geometry and full grid borders |
| `hybrid` | Snapshot proof plus retained structure | Snapshot paints the formula; hidden editable layer remains in the DOCX | Native table grid remains visible over the snapshot |
| `fidelity` | Snapshot proof | Snapshot paints formula/font/image/color | Snapshot keeps source horizontal rules; precise vertical DrawingML separators improve column readability without adding blank table rows |

The four outputs are intentionally different. `editable` is the one to modify, `positioned` is the one to inspect and replace objects in place, `hybrid` is the compromise for visual review, and `fidelity` is the visual archive.

Phase 4 / historical regression rows below are retained for audit.

## Verified

- Native text-layer extraction still works.
- Tightened PDF word-gap reconstruction keeps positioned inter-word spaces as separate editable runs for the baseline sample.
- Canonical IR now includes typed elements, runs, page regions, and dedicated payload slots.
- IR schema `1.5` preserves separator graphics, underline state, four OOXML font slots, source font names, run colors, source line breaks, source word-gap flags and normalized `line_bboxes`, image source dimensions, table geometry, merge placeholders/spans, per-cell border evidence, and an optional source-page snapshot path.
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
- Table 2 is recovered as 12 rows x 5 columns with merged two-level headers, scientific-notation cell grouping, fixed widths, and inferred borders; Table 3 is recovered as 8 rows x 13 columns with multiline numeric cells and merged label coverage.
- Page 9 multiline numeric cells retain source line breaks; synthetic merged-cell coverage is represented as `None` placeholders plus `row_span`/`col_span` in the IR.
- `positioned` mode now emits native DrawingML text boxes and image anchors. The page 3 embedded figure remains a replaceable Word picture rather than a VML drawing.
- Source font faces and grayscale text colors are retained on individual IR runs; normalized desktop families remain the current Word fallback policy.
- `validation/preflight.json` records native availability, preferred/selected parser per page, and the clone/import status of MinerU, Docling, and PaddleOCR.
- Post-render `ValidationEngine` writes `validation/validation_report.json` + `.md` for every conversion (disable with `--no-validate`).
- Baseline page 1 and table-heavy pages: structure/text/table/image layers pass with document-order IR↔DOCX character error rate below `0.001`.
- Current 11-page editable conversion structure/text/table/image layers pass (CER `0.0022`, digit error rate `0.0`); the page-count gate is `11 → 11`, with visual warnings on pages 2, 6, and 8.
- Display formulas on the Attention sample retain source-coordinate raster crops in `positioned`, `hybrid`, and `fidelity`; the learning-rate formula on page 7 was visually verified. `editable` renders its formula run stream with superscript/subscript styling and keeps a hidden plain-text fallback for structured OMML.
- Table 2 and Table 3 in all four delivered outputs have readable column separation: native modes use full cell grids, while `fidelity` overlays only precise vertical separators over the source snapshot.

## Partially Implemented

- Font preservation now stores run-level font name and size, and writes Word `ascii`, `hAnsi`, `eastAsia`, and `cs` font slots. It does not yet map PDF embedded font names to clean installed system font families.
- Tables are extracted through `pdfplumber.find_tables()` and refined with row-rule and text-anchor recovery when a PDF exposes only a frame. Per-cell border width/color and fixed geometry are preserved, but merged header spans in the paper table still need stronger inference.
- Images are represented in IR. `PdfPlumberBackend` first decodes the embedded stream into a job-local PNG and falls back to a page crop only when the stream cannot be decoded. Floating placement and rotation are still limited by the inline Word renderer.
- PDF horizontal rules below text can become native Word underline properties only when their width matches the text; long rules beneath short labels are retained as cover/form guide-line separators and rendered as native rule geometry.
- Formula detection is heuristic. High-confidence fractions, superscripts, subscripts, and radicals emit structured OMML; other formula-like lines retain an editable token-stream representation in the IR and use the source-coordinate text fallback in the positioned renderer until a full math recognizer is available. Nested math trees, equation numbering, and raster/scanned formulas still need a dedicated recognizer.
- The final `x_tolerance=0.5` extraction recovers the paper's encoded English word gaps (`As side benefit`, `self-attention could yield...`) while preserving compact math fragments; it still cannot infer spaces that are absent from both the PDF text stream and character geometry.
- **Editable geometry packing (2026-07-20):** each PDF page contributes to a continuous Word flow with matching `612×792` page geometry; margins are derived from body bbox extents; vertical gaps and horizontal insets come from IR bboxes; default Word paragraph gaps are zeroed; same-paragraph line merge is slightly more aggressive. Current baseline structure/text/table/image layers pass and LibreOffice page count is `11/11`.

## Visual loop (LibreOffice) — 2026-07-20

LibreOffice is installed at `/Applications/LibreOffice.app/Contents/MacOS/soffice` and wired via `PDF2WORD_SOFFICE`.

### Current final acceptance rerun (`v1.0.2-mode-specific-rendering`)

| Mode | Final job | Source pages | Rendered pages | Delta | mean MAD | Text/structure gate |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `editable` | `workspace/jobs/20260720_133328_6ffb325e/` | 11 | **11** | 0 | **0.0737** | PASS; CER `0.0022`, table/image pass |
| `positioned` | `workspace/jobs/20260720_131939_574c2975/` | 11 | **11** | 0 | **0.0495** | PASS |
| `hybrid` | `workspace/jobs/20260720_131943_8c79e1f5/` | 11 | **11** | 0 | **0.0203** | PASS |
| `fidelity` | `workspace/jobs/20260720_132545_5b279657/` | 11 | **11** | 0 | **0.0197** | PASS; vertical separator overlay |

The reproducible copy of this current DOCX set and its reports is `workspace/archive/v1.0.2-mode-specific-rendering/`.

### Historical final acceptance rerun

| Mode | Final job | Source pages | Rendered pages | Delta | mean MAD | Text/structure gate |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `editable` | `workspace/jobs/20260720_123400_1511dfeb/` | 11 | **11** | 0 | **0.0734** | PASS; CER `0.0002`, table/image pass |
| `positioned` | `workspace/jobs/20260720_123410_2a1f0c10/` | 11 | **11** | 0 | **0.0492** | PASS |
| `hybrid` | `workspace/jobs/20260720_123421_bdab846e/` | 11 | **11** | 0 | **0.0200** | PASS |
| `fidelity` | `workspace/jobs/20260720_123432_b17b8bf4/` | 11 | **11** | 0 | **0.0194** | PASS |

The reproducible copy of these DOCX files and reports is `workspace/archive/v1.0.0-mvp-final/`.

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

**Historical v1.0.0-mvp archive:** `workspace/archive/v1.0.0-mvp/`.
**Final acceptance archive:** `workspace/archive/v1.0.0-mvp-final/` — four DOCX, per-mode validation JSON/MD, `validation_report.json`, IR, and preflight records.

GUI smoke archive (earlier same day): `workspace/archive/gui-smoke-20260720/` (PySide6 `6.11.1`, four modes, all `passed=true`, 11/11 pages).

### DrawingML workstream (MAD path)

Delivered modes:

1. **`positioned`** — `wp:anchor` + `wps:txbx` **per-source-line** text boxes, floating tables (`tblpPr`), anchored images and full native table grids. Final mean MAD **0.0495** (≤0.055). IR `1.5` stores `line_bboxes` and source word-gap flags for pixel anchoring.
2. **`hybrid`** — full-page snapshot with `behindDoc=1` + DrawingML editable layer using `w:vanish`; native table borders remain painted. Final mean MAD **0.0203**.
3. **`fidelity`** — snapshot paint via the same behind-doc anchor plus precise vertical table separator DrawingML. Final mean MAD **0.0197**.

Positioned MAD path (0.061 → 0.048):

- Split multi-line IR blocks into one DrawingML textbox per source line.
- Persist normalized `line_bboxes` and source word-gap flags on IR elements (schema 1.5).
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
| `editable` | Flow paragraphs + real tables | Reflow paint | **0.0737** |
| `positioned` | DrawingML objects + real tables | DrawingML paint | **0.0495** |
| `hybrid` | DrawingML (vanished) | Snapshot behind + visible table grid | **0.0203** |
| `fidelity` | Snapshot + separator lines | Snapshot + vertical table separators | **0.0197** |

## Not Yet Implemented

- Pure `positioned` page-2 residual (~0.064) still trails hybrid; further gains need font-metric matching / kerning.
- Making hybrid text visible while keeping snapshot MAD (would double-paint unless text is transparent or selectively hidden).
- `positioned` is not yet a pixel-accurate editable renderer: the latest line-fit guard reduces long-text wrapping/clipping risk, but font-metric and kerning residuals remain. The page 9 native floating table retains logical rows, marks the first row as a repeating header, and prevents row splitting; header/cell metric matching and cross-editor checks remain. The native image anchor path is verified, but rotation/cropping needs cross-editor checks.
- Cross-page table continuation.
- OCR-based scanned page recovery.
- PySide6 `6.11.1` is installed. GUI smoke (Qt offscreen + native macOS Cocoa) completed without crash; `v1.0.0-mvp` freezes the CLI four-mode metrics above. Cross-platform desktop packaging remains a follow-up.
- Native fallback is intentionally marked as degraded for formula-heavy or scanned pages until executable optional runtimes and model artifacts are available; the current project `.venv` probes record Docling blocked by `docling_core`, MinerU dependency-gated, and PaddleOCR blocked by `paddlex`.
