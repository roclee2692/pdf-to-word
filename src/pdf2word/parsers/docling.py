from __future__ import annotations

from pathlib import Path

from pdf2word.domain import (
    BoundingBox,
    Confidence,
    DocumentElement,
    DocumentIR,
    DocumentMeta,
    FormulaPayload,
    ImagePayload,
    PageIR,
    Provenance,
    TableCellPayload,
    TablePayload,
    TextRun,
)
from pdf2word.parsers.native_parser import NativeTextParser
from pdf2word.pdf_backends import PdfBackend


class DoclingParser:
    """Normalize Docling's typed document tree into the project IR."""

    name = "docling"

    def parse(self, backend: PdfBackend, pages: list[int]) -> DocumentIR:
        source_path = getattr(backend, "pdf_path", None)
        if source_path is None:
            raise RuntimeError("Docling requires a backend exposing the source PDF path")
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(
            str(source_path),
            raises_on_error=True,
            page_range=(min(pages), max(pages)),
        )
        if result.document is None:
            raise RuntimeError("Docling returned no document")
        return self._to_ir(result.document, backend, pages)

    def _to_ir(self, document, backend: PdfBackend, pages: list[int]) -> DocumentIR:
        page_map = {
            page_no: PageIR(
                id=f"page_{page_no:03d}",
                page_number=page_no,
                width_pt=backend.page_size(page_no)[0],
                height_pt=backend.page_size(page_no)[1],
                elements=[],
            )
            for page_no in pages
        }
        native_helpers = NativeTextParser()
        order_by_page = {page_no: 0 for page_no in pages}
        for item, _ in document.iterate_items(traverse_pictures=True):
            provenance = self._first_provenance(item)
            if provenance is None or provenance.page_no not in page_map:
                continue
            page_no = provenance.page_no
            page_width, page_height = backend.page_size(page_no)
            bbox = self._bbox(provenance.bbox, page_height, page_width)
            order_by_page[page_no] += 1
            element = self._item_to_element(
                item,
                document,
                bbox,
                page_no,
                order_by_page[page_no],
                native_helpers,
                page_width,
                page_height,
                getattr(backend, "image_output_dir", None),
            )
            if element is not None:
                page_map[page_no].elements.append(element)
        return DocumentIR(
            document=DocumentMeta(
                page_count=backend.page_count(),
                language=["unknown"],
                document_type="docling_pdf",
            ),
            pages=[page_map[page_no] for page_no in pages],
        )

    def _item_to_element(
        self,
        item,
        document,
        bbox: BoundingBox,
        page_no: int,
        reading_order: int,
        native_helpers: NativeTextParser,
        page_width: float,
        page_height: float,
        image_output_dir,
    ) -> DocumentElement | None:
        label = self._label(item)
        item_id = str(getattr(item, "self_ref", f"item_{reading_order}"))
        text = str(getattr(item, "text", "") or "").strip()
        if hasattr(item, "data") and hasattr(item.data, "grid"):
            return self._table_element(item, bbox, page_no, reading_order, document, page_width, page_height)
        if label in {"picture", "chart"}:
            return self._picture_element(item, document, bbox, page_no, reading_order, image_output_dir)
        if not text:
            return None
        if label == "formula":
            omml = native_helpers._formula_to_omml(text)
            return DocumentElement(
                id=f"p{page_no:03d}_docling_{item_id}",
                type="formula",
                text=text,
                bbox=bbox,
                reading_order=reading_order,
                formula=FormulaPayload(
                    latex=text,
                    fallback_text=text,
                    omml_xml=omml,
                    source_type="vector" if omml else "unknown",
                ),
                confidence=Confidence(text=0.9, role=0.9, geometry=0.9),
                provenance=Provenance(parser=self.name, source_page=page_no, source="docling"),
            )
        element_type = "heading" if label in {"title", "section_header"} else "paragraph"
        if label == "page_header":
            element_type = "header"
        elif label == "page_footer":
            element_type = "footer"
        return DocumentElement(
            id=f"p{page_no:03d}_docling_{item_id}",
            type=element_type,
            text=text,
            runs=[TextRun(text=text)],
            page_region="header" if element_type == "header" else "footer" if element_type == "footer" else "body",
            bbox=bbox,
            reading_order=reading_order,
            confidence=Confidence(text=0.9, role=0.85, geometry=0.9),
            provenance=Provenance(parser=self.name, source_page=page_no, source="docling"),
        )

    def _table_element(self, item, bbox, page_no, reading_order, document, page_width, page_height):
        grid = item.data.grid
        rows: list[list[TableCellPayload]] = []
        for row in grid:
            payload_row: list[TableCellPayload] = []
            for cell in row:
                cell_bbox = None
                if cell.bbox is not None:
                    cell_bbox = BoundingBox.from_points(
                        *cell.bbox.to_top_left_origin(page_height).as_tuple(),
                        page_width=page_width,
                        page_height=page_height,
                    )
                payload_row.append(
                    TableCellPayload(
                        text=str(cell._get_text(doc=document) or ""),
                        bbox=cell_bbox,
                        row_span=max(1, int(cell.row_span)),
                        col_span=max(1, int(cell.col_span)),
                        alignment="center" if cell.column_header else "left",
                    )
                )
            rows.append(payload_row)
        return DocumentElement(
            id=f"p{page_no:03d}_docling_table_{reading_order:04d}",
            type="table",
            role="table",
            text="\n".join("\t".join(cell.text for cell in row) for row in rows),
            bbox=bbox,
            reading_order=reading_order,
            table=TablePayload(
                row_count=int(item.data.num_rows),
                column_count=int(item.data.num_cols),
                rows=rows,
                has_borders=True,
            ),
            confidence=Confidence(text=0.9, role=0.9, geometry=0.9),
            provenance=Provenance(parser=self.name, source_page=page_no, source="docling"),
        )

    def _picture_element(self, item, document, bbox, page_no, reading_order, image_output_dir):
        image = item.get_image(document)
        if image is None:
            return None
        output_dir = Path(image_output_dir or Path.cwd())
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"page_{page_no:03d}_docling_picture_{reading_order:04d}.png"
        image.save(output)
        width_pt = max(1.0, bbox.right - bbox.left)
        height_pt = max(1.0, bbox.bottom - bbox.top)
        return DocumentElement(
            id=f"p{page_no:03d}_docling_picture_{reading_order:04d}",
            type="image",
            role="embedded_image",
            bbox=bbox,
            reading_order=reading_order,
            image=ImagePayload(
                image_path=str(output.resolve()),
                width_pt=width_pt,
                height_pt=height_pt,
                source_width_px=image.width,
                source_height_px=image.height,
            ),
            confidence=Confidence(text=0.0, role=0.9, geometry=0.9),
            provenance=Provenance(parser=self.name, source_page=page_no, source="docling"),
        )

    def _first_provenance(self, item):
        provenance = getattr(item, "prov", None) or []
        return provenance[0] if provenance else None

    def _label(self, item) -> str:
        label = getattr(item, "label", "")
        return str(getattr(label, "value", label)).lower().split(".")[-1]

    def _bbox(self, bbox, page_height: float, page_width: float) -> BoundingBox:
        if getattr(bbox, "coord_origin", None) is not None:
            bbox = bbox.to_top_left_origin(page_height)
        return BoundingBox.from_points(*bbox.as_tuple(), page_width=page_width, page_height=page_height)
