from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DocxTableSnapshot:
    row_count: int
    column_count: int
    cells: list[list[str]]


@dataclass
class DocxSnapshot:
    paragraph_count: int = 0
    heading_count: int = 0
    empty_paragraph_count: int = 0
    table_count: int = 0
    image_count: int = 0
    section_count: int = 0
    header_texts: list[str] = field(default_factory=list)
    footer_texts: list[str] = field(default_factory=list)
    has_footer_page_field: bool = False
    tables: list[DocxTableSnapshot] = field(default_factory=list)
    body_text: str = ""
    body_paragraphs: list[str] = field(default_factory=list)


def read_docx_snapshot(path: str | Path) -> DocxSnapshot:
    """Extract structure and text from a DOCX for validation comparisons."""
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise RuntimeError("python-docx is required for DOCX validation") from exc

    document = Document(str(path))
    snapshot = DocxSnapshot(section_count=len(document.sections))
    body_chunks: list[str] = []

    # Walk body children in document order so tables stay interleaved with paragraphs.
    for block in _iter_block_items(document, Paragraph, Table, qn):
        if isinstance(block, Paragraph):
            text = block.text or ""
            style_name = (block.style.name if block.style is not None else "") or ""
            is_heading = style_name.lower().startswith("heading")
            snapshot.paragraph_count += 1
            if is_heading:
                snapshot.heading_count += 1
            if not text.strip():
                snapshot.empty_paragraph_count += 1
                continue
            snapshot.body_paragraphs.append(text)
            body_chunks.append(text)
            continue

        rows: list[list[str]] = []
        max_cols = 0
        for row in block.rows:
            # python-docx repeats cells across horizontal merges; keep first occurrence only
            # would lose data, so retain all values for structural checks.
            cells = [(cell.text or "").strip() for cell in row.cells]
            rows.append(cells)
            max_cols = max(max_cols, len(cells))
        snapshot.tables.append(
            DocxTableSnapshot(row_count=len(rows), column_count=max_cols, cells=rows)
        )
        snapshot.table_count += 1
        for row_obj, row in zip(block.rows, rows):
            # python-docx exposes a horizontally merged cell once per grid
            # slot. Keep the raw row shape for structure checks, but count
            # each underlying XML cell only once in document text, otherwise
            # merged headers inflate CER with duplicate labels.
            seen_cells: set[int] = set()
            for cell_obj, cell_text in zip(row_obj.cells, row):
                cell_key = id(cell_obj._tc)
                if cell_key in seen_cells:
                    continue
                seen_cells.add(cell_key)
                if cell_text:
                    body_chunks.append(cell_text)

    image_count = 0
    for rel in document.part.rels.values():
        reltype = getattr(rel, "reltype", "") or ""
        if "image" in reltype:
            image_count += 1
    blip_tag = qn("a:blip")
    blips = document.element.findall(f".//{blip_tag}")
    if blips:
        image_count = max(image_count, len(blips))
    snapshot.image_count = image_count

    for section in document.sections:
        header_text = "\n".join(p.text for p in section.header.paragraphs if p.text).strip()
        footer_text = "\n".join(p.text for p in section.footer.paragraphs if p.text).strip()
        footer_xml = section.footer._element.xml if section.footer is not None else ""
        if header_text:
            snapshot.header_texts.append(header_text)
        elif "PAGE" in section.header._element.xml:
            snapshot.header_texts.append("{PAGE_FIELD}")
        if footer_text:
            snapshot.footer_texts.append(footer_text)
        if "PAGE" in footer_xml and "fldChar" in footer_xml:
            snapshot.has_footer_page_field = True
            if not footer_text:
                snapshot.footer_texts.append("{PAGE_FIELD}")

    snapshot.body_text = "\n".join(body_chunks)
    return snapshot


def _iter_block_items(document, paragraph_cls, table_cls, qn):
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield paragraph_cls(child, document)
        elif child.tag == qn("w:tbl"):
            yield table_cls(child, document)
