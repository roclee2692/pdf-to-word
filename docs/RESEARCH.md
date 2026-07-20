# PDF-to-Word Engineering Research

Research date: 2026-07-20

This document records external evidence used for implementation decisions. It is intentionally separate from the quality report so the project can update the evidence without rewriting acceptance criteria.

## Repeated failure modes

- PDF is fixed-position content while Word reconstructs semantic objects and flowing paragraphs. Microsoft documents that tables in a PDF may be only a set of lines with no relationship to cell content, so table reconstruction must be explicit rather than text-only.
- Font substitution is a first-order layout risk. Adobe documents that unavailable fonts are substituted during reuse/export, which can change line widths and downstream pagination.
- Table extraction engines can lose structure even when OCR text is available. Docling issue #1922 reports nested-table text loss and a mismatch between complete raw cell text and incomplete structural metadata.
- PaddleOCR separates layout detection from table recognition, and its issue tracker includes cases where table structure, empty cells, or table-vs-figure classification are incorrect. The adapter must preserve raw regions and confidence instead of trusting one HTML/table result.
- `pdfplumber` exposes line-based and text-based table strategies and recommends cropping when a region contains competing layout signals. The backend therefore keeps raw lines/rects and table cell bboxes in IR.
- LibreOffice interoperability is itself a validation variable: current release notes and bug reports include DOCX formula-centering and table/header layout fixes. Render validation must use the target office engine, not only OOXML inspection.
- Office Math is a native OOXML object, not ordinary run text. The Microsoft Open XML specification places `m:oMath` inside a Word paragraph and defines structures such as `m:f`, `m:sSup`, `m:sSub`, and `m:rad`; the implementation therefore emits OMML only for conservative, recognized patterns and keeps a fallback for everything else.

## Decisions applied

1. Keep a typed IR between parsers and renderers. It prevents optional parser output from being mistaken for a Word paragraph and makes loss/confidence measurable.
2. Store both semantic geometry and raw evidence. Text runs, cell bboxes, image source dimensions, line/rect evidence, and parser provenance must survive normalization.
3. Prefer native Word objects, but fail loudly when a required source asset cannot be materialized. A placeholder image would violate the acceptance contract.
4. Treat table structure as uncertain. A `pdfplumber` table result can be refined with row rules and text x-anchors; the result remains traceable so a later Docling/MinerU/PaddleOCR adapter can replace it.
5. Separate preferred parser from executable parser. Optional adapters are only selectable when a real local adapter exists; otherwise text-bearing pages use a documented native fallback and scanned pages remain blocked.
6. Run structural checks and render checks. A DOCX can contain a real table while still being visually wrong, so both XML-level and PNG-level evidence are required.
7. Keep model downloads explicit. A parser repository can be cloned and its Python entry point importable while its model artifacts remain unavailable; the route must record both states and fall back without silently reaching the network.

## 2026-07-20 industry pain points (re-checked)

Commercial and community reports continue to cluster on the same failures the blueprint targets:

- Garbled/misaligned text, missing word spaces after copy, wrong or substituted fonts.
- Tables and multi-column layouts that break into plain paragraphs or wrong cell grids.
- Images that disappear, shift, or become non-editable placeholders.
- Extra line/page breaks after conversion that destroy pagination.
- Borderless or sparsely ruled tables that `lines`-only extractors miss; `pdfplumber` documents `text` / `explicit` strategies for those cases.

Decision impact for this iteration: validation must measure **document-order** IR↔DOCX text (not “all paragraphs then all tables”), table geometry separately from text CER, and visual MAD only when an office renderer is present. A high CER with equal character counts is a strong signal of block reordering rather than missing content.

## Sources

- Microsoft Support, [Opening PDFs in Word](https://support.microsoft.com/en-US/Word/opening-pdfs-in-word)
- Adobe Help, [Reusing PDF content](https://helpx.adobe.com/acrobat/using/reusing-pdf-content.html)
- pdfplumber repository, [table extraction strategies](https://github.com/jsvine/pdfplumber)
- Smallpdf, [common PDF-to-Word formatting issues](https://smallpdf.com/blog/common-issues-in-pdf-to-word-conversion-and-how-to-fix-them)
- Docling, [nested table extraction issue #1922](https://github.com/docling-project/docling/issues/1922)
- PaddleOCR, [table structure issue #11892](https://github.com/PaddlePaddle/PaddleOCR/issues/11892)
- PaddleOCR, [layout analysis documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/ppstructure/layout/README.md)
- MinerU repository, [features and installation](https://github.com/opendatalab/MinerU)
- LibreOffice, [25.2.2 release notes](https://whatsnew.libreoffice.org/25.2.2/)
- Microsoft Learn, [Office Open XML `oMath`](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/f5d23e19-a38f-4089-9c1e-efa6c284b86c)
- Microsoft Learn, [Office Math elements and arguments](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/621fc70c-9d6e-4502-bdac-015453605f66)
