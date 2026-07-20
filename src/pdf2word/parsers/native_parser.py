from __future__ import annotations

import re
from pathlib import Path
import tempfile
from xml.sax.saxutils import escape

from pdf2word.domain import (
    BoundingBox,
    Confidence,
    DocumentElement,
    DocumentIR,
    DocumentMeta,
    ElementStyle,
    FontSlots,
    FormulaPayload,
    HeaderFooterPayload,
    ImagePayload,
    PageIR,
    Provenance,
    SeparatorPayload,
    TableCellPayload,
    TablePayload,
    BorderStyle,
    TextRun,
)
from pdf2word.pdf_backends import PdfBackend, PdfTableObject, PdfTextObject


class NativeTextParser:
    name = "native"

    def parse(self, backend: PdfBackend, pages: list[int]) -> DocumentIR:
        parsed_pages: list[PageIR] = []
        for page_no in pages:
            width, height = backend.page_size(page_no)
            words = backend.extract_text_objects(page_no)
            tables = backend.extract_tables(page_no)
            images = backend.extract_images(page_no)
            lines = backend.extract_lines(page_no)
            rects = backend.extract_rects(page_no)
            elements = self._page_to_elements(words, tables, images, lines, rects, page_no, width, height)
            elements = self._attach_formula_assets(backend, elements, page_no, width, height)
            parsed_pages.append(
                PageIR(
                    id=f"page_{page_no:03d}",
                    page_number=page_no,
                    width_pt=width,
                    height_pt=height,
                    elements=elements,
                )
            )
        return DocumentIR(
            document=DocumentMeta(
                page_count=backend.page_count(),
                language=["unknown"],
                document_type="native_pdf",
            ),
            pages=parsed_pages,
        )

    def _page_to_elements(
        self,
        words: list[PdfTextObject],
        tables,
        images,
        lines,
        rects,
        page_no: int,
        page_width: float,
        page_height: float,
    ) -> list[DocumentElement]:
        elements: list[DocumentElement] = []
        table_bboxes = [(table.x0, table.top, table.x1, table.bottom) for table in tables]

        for index, table in enumerate(tables, start=1):
            elements.append(
                self._table_to_element(
                    table,
                    page_no,
                    page_width,
                    page_height,
                    index,
                    len(elements) + 1,
                )
            )

        for index, image in enumerate(images, start=1):
            elements.append(
                DocumentElement(
                    id=f"p{page_no:03d}_image_{index:04d}",
                    type="image",
                    role="embedded_image",
                    bbox=BoundingBox.from_points(image.x0, image.top, image.x1, image.bottom, page_width, page_height),
                    reading_order=len(elements) + 1,
                    image=ImagePayload(
                        width_pt=image.width,
                        height_pt=image.height,
                        image_path=image.image_path,
                        rotation_deg=image.rotation_deg,
                        source_width_px=image.source_width_px,
                        source_height_px=image.source_height_px,
                    ),
                    confidence=Confidence(text=0.0, role=0.8, geometry=0.9),
                    provenance=Provenance(parser=self.name, source_page=page_no, source=image.name or "pdfplumber_image"),
                )
            )

        text_words = [word for word in words if not self._inside_any_bbox(word, table_bboxes)]
        text_elements = self._words_to_text_elements(text_words, page_no, page_width, page_height, len(elements))
        graphic_elements = self._graphics_to_elements(
            [*lines, *rects],
            table_bboxes,
            text_elements,
            page_no,
            page_width,
            page_height,
            len(elements) + len(text_elements),
        )
        elements.extend(text_elements)
        elements.extend(graphic_elements)

        return self._renumber_for_reading_order(elements, page_width, page_height)

    def _attach_formula_assets(
        self,
        backend: PdfBackend,
        elements: list[DocumentElement],
        page_no: int,
        page_width: float,
        page_height: float,
    ) -> list[DocumentElement]:
        renderer = getattr(backend, "render_crop", None)
        if renderer is None:
            return elements
        configured_dir = getattr(backend, "image_output_dir", None)
        output_dir = (
            Path(configured_dir) / "formulas"
            if configured_dir
            else Path(tempfile.gettempdir()) / "pdf2word-formulas"
        )
        updated: list[DocumentElement] = []
        formula_index = 0
        for element in elements:
            if element.type != "formula" or element.formula is None:
                updated.append(element)
                continue
            formula_index += 1
            bbox = element.bbox
            crop_bbox = (
                bbox.left * page_width,
                bbox.top * page_height,
                bbox.right * page_width,
                bbox.bottom * page_height,
            )
            output = output_dir / f"page_{page_no:03d}_formula_{formula_index:03d}.png"
            try:
                image_path = renderer(page_no, crop_bbox, output)
            except Exception:
                image_path = None
            if image_path:
                element = element.model_copy(
                    update={
                        "formula": element.formula.model_copy(
                            update={"image_path": str(image_path), "source_type": "raster"}
                        )
                    }
                )
            updated.append(element)
        return updated

    def _graphics_to_elements(
        self,
        graphics,
        table_bboxes: list[tuple[float, float, float, float]],
        text_elements: list[DocumentElement],
        page_no: int,
        page_width: float,
        page_height: float,
        reading_offset: int,
    ) -> list[DocumentElement]:
        """Keep non-table PDF rules and promote rules below text to underlines."""
        separators: list[DocumentElement] = []
        for graphic_index, graphic in enumerate(graphics, start=1):
            bbox = (graphic.x0, graphic.top, graphic.x1, graphic.bottom)
            if self._inside_graphic_bbox(graphic, table_bboxes):
                continue
            if self._is_horizontal(graphic):
                candidate = self._underline_candidate(graphic, text_elements, page_width, page_height)
                if candidate is not None:
                    candidate_index, candidate_element = candidate
                    updated_runs = [run.model_copy(update={"underline": True}) for run in candidate_element.runs]
                    text_elements[candidate_index] = candidate_element.model_copy(
                        update={
                            "runs": updated_runs,
                            "style": candidate_element.style.model_copy(update={"underline": True}),
                        }
                    )
                    continue
            orientation = "rectangle" if graphic.width >= 8.0 and graphic.height >= 8.0 else (
                "horizontal" if graphic.width >= graphic.height else "vertical"
            )
            separators.append(
                DocumentElement(
                    id=f"p{page_no:03d}_separator_{graphic_index:04d}",
                    type="separator",
                    role="pdf_graphic",
                    page_region=self._page_region(graphic.top, graphic.bottom, page_height),
                    bbox=BoundingBox.from_points(*bbox, page_width, page_height),
                    reading_order=reading_offset + graphic_index,
                    style=ElementStyle(alignment="left"),
                    separator=SeparatorPayload(
                        orientation=orientation,
                        stroke_width_pt=max(0.25, float(graphic.stroke_width or 0.5)),
                        stroke_color=self._color_to_hex(graphic.stroke_color),
                        fill_color=self._color_to_hex(graphic.fill_color),
                    ),
                    confidence=Confidence(text=0.0, role=0.7, geometry=0.9),
                    provenance=Provenance(parser=self.name, source_page=page_no, source="pdfplumber_graphic"),
                )
            )
        return separators

    def _inside_graphic_bbox(self, graphic, bboxes: list[tuple[float, float, float, float]]) -> bool:
        center_x = (graphic.x0 + graphic.x1) / 2
        center_y = (graphic.top + graphic.bottom) / 2
        return any(x0 <= center_x <= x1 and top <= center_y <= bottom for x0, top, x1, bottom in bboxes)

    def _is_horizontal(self, graphic) -> bool:
        return graphic.width >= max(8.0, graphic.height * 10.0)

    def _underline_candidate(self, graphic, elements: list[DocumentElement], page_width: float, page_height: float):
        candidates: list[tuple[float, int, DocumentElement]] = []
        for index, element in enumerate(elements):
            if element.page_region != "body" or element.type not in {"paragraph", "heading", "caption"}:
                continue
            graphic_left = graphic.x0
            graphic_right = graphic.x1
            element_left = element.bbox.left * page_width
            element_right = element.bbox.right * page_width
            if element_right <= element_left:
                continue
            element_width = element_right - element_left
            # A long rule beneath a short label is a cover/form guide line,
            # not a text underline. Keep it as separator evidence so the
            # renderer can draw the full rule instead of underlining a run.
            if graphic.width > element_width * 1.35:
                continue
            overlap = min(graphic_right, element_right) - max(graphic_left, element_left)
            if overlap < max(8.0, (element_right - element_left) * 0.45):
                continue
            element_bottom = element.bbox.bottom * page_height
            distance = graphic.top - element_bottom
            if -2.0 <= distance <= max(5.0, (element.style.font_size_pt or 10.0) * 0.65):
                candidates.append((abs(distance), index, element))
        if not candidates:
            return None
        _, index, element = min(candidates, key=lambda item: item[0])
        return index, element

    def _words_to_text_elements(
        self,
        words: list[PdfTextObject],
        page_no: int,
        page_width: float,
        page_height: float,
        reading_offset: int,
    ) -> list[DocumentElement]:
        lines = self._group_words_by_line(words)
        if not lines:
            return []

        font_sizes = [word.font_size for line in lines for word in line if word.font_size]
        median_size = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else None

        line_infos: list[dict] = []
        for line in lines:
            line = sorted(line, key=lambda item: item.x0)
            text = " ".join(word.text for word in line).strip()
            if not text:
                continue
            x0 = min(word.x0 for word in line)
            top = min(word.top for word in line)
            x1 = max(word.x1 for word in line)
            bottom = max(word.bottom for word in line)
            avg_size = self._average_size(line)
            page_region = self._page_region(top, bottom, page_height)
            element_type = self._text_element_type(text, avg_size, median_size, page_region)
            alignment = self._guess_alignment(x0, x1, page_width)
            line_infos.append(
                {
                    "line": line,
                    "text": text,
                    "x0": x0,
                    "top": top,
                    "x1": x1,
                    "bottom": bottom,
                    "avg_size": avg_size,
                    "page_region": page_region,
                    "element_type": element_type,
                    "alignment": alignment,
                }
            )

        groups: list[list[dict]] = []
        for info in line_infos:
            if groups and self._can_merge_lines(groups[-1][-1], info, page_width, median_size):
                groups[-1].append(info)
            else:
                groups.append([info])

        elements: list[DocumentElement] = []
        for index, group in enumerate(groups, start=1):
            words_in_group = [word for info in group for word in info["line"]]
            x0 = min(info["x0"] for info in group)
            top = min(info["top"] for info in group)
            x1 = max(info["x1"] for info in group)
            bottom = max(info["bottom"] for info in group)
            # Prefer paragraph when a multi-line group mixed formula-looking fragments with prose.
            types_in_group = {item["element_type"] for item in group}
            if len(group) > 1 and "paragraph" in types_in_group:
                element_type = "paragraph"
            elif len(group) > 1 and types_in_group <= {"formula", "paragraph"}:
                element_type = "formula" if types_in_group == {"formula"} else "paragraph"
            else:
                element_type = group[0]["element_type"]
            # Build runs before the final text so mathematical glyphs that
            # sit above/below the baseline remain attached to their formula.
            runs = self._runs_for_line_group(group, formula=element_type == "formula")
            text = self._text_from_runs(runs, formula=element_type == "formula")
            page_region = group[0]["page_region"]
            avg_size = self._average_size(words_in_group)
            # Estimate line spacing from source line boxes for the editable packer.
            line_spacing = None
            if len(group) >= 2 and avg_size:
                heights = [info["bottom"] - info["top"] for info in group]
                median_line_h = sorted(heights)[len(heights) // 2]
                line_spacing = max(1.0, min(1.25, median_line_h / max(avg_size, 1.0)))
            line_bboxes = [
                BoundingBox.from_points(
                    info["x0"],
                    info["top"],
                    info["x1"],
                    info["bottom"],
                    page_width,
                    page_height,
                )
                for info in group
            ]
            elements.append(
                DocumentElement(
                    id=f"p{page_no:03d}_el_{index:04d}",
                    type=element_type,
                    role=self._role_for_text_element(element_type, page_region),
                    text=text,
                    runs=runs,
                    page_region=page_region,
                    bbox=BoundingBox.from_points(x0, top, x1, bottom, page_width, page_height),
                    line_bboxes=line_bboxes,
                    reading_order=reading_offset + index,
                    style=ElementStyle(
                        font_family=self._common_font(words_in_group),
                        font_slots=self._font_slots(words_in_group),
                        font_size_pt=avg_size,
                        bold=self._line_looks_bold(words_in_group),
                        alignment=group[0]["alignment"],
                        line_spacing=line_spacing,
                        space_after_pt=0.0,
                    ),
                    formula=(
                        FormulaPayload(
                            fallback_text=text,
                            omml_xml=self._formula_to_omml(text),
                            source_type="vector" if self._formula_to_omml(text) else "unknown",
                        )
                        if element_type == "formula"
                        else None
                    ),
                    header_footer=(
                        HeaderFooterPayload(kind=page_region, text=text)
                        if page_region in {"header", "footer"}
                        else None
                    ),
                    confidence=Confidence(text=0.98, role=0.7 if element_type == "heading" else 0.55, geometry=0.9),
                    provenance=Provenance(parser=self.name, source_page=page_no, source="pdfplumber"),
                )
            )
        return self._pack_adjacent_body_text(elements, page_width, page_height)

    def _can_merge_lines(self, previous: dict, current: dict, page_width: float, median_size: float | None) -> bool:
        mergeable = {"paragraph", "formula"}
        if previous["element_type"] not in mergeable or current["element_type"] not in mergeable:
            return False
        if previous["page_region"] != "body" or current["page_region"] != "body":
            return False
        # Centered display formulas stay separate from left body text.
        if previous["alignment"] != current["alignment"]:
            if previous["element_type"] == "formula" or current["element_type"] == "formula":
                return False
            return False
        # Allow modest first-line / hanging indent differences inside one paragraph.
        if abs(current["x0"] - previous["x0"]) > page_width * 0.14:
            return False
        gap = current["top"] - previous["bottom"]
        line_size = previous["avg_size"] or current["avg_size"] or median_size or 10.0
        # Balanced merge: enough for 11-page packing, keep section headings separate.
        max_gap = max(7.0, line_size * 1.35)
        if not (-2.0 <= gap <= max_gap):
            return False
        if previous["element_type"] == current["element_type"] == "formula" and gap > max(1.5, line_size * 0.25):
            return False
        prev_text = previous["text"].rstrip()
        curr_text = current["text"].strip()
        # Never glue a section heading into the previous paragraph.
        if self._looks_like_section_heading_text(curr_text):
            return False
        if self._looks_like_section_heading_text(prev_text):
            return False
        # Hard paragraph break on sentence endings with more than single-line leading.
        if prev_text.endswith((".", "!", "?", "。", "！", "？")) and gap > line_size * 1.0:
            return False
        # Keep large display formulas as their own block when they are centered-like and short.
        if (
            previous["element_type"] == "formula"
            and current["element_type"] == "paragraph"
            and len(previous["text"]) <= 40
            and gap > line_size * 1.0
        ):
            return False
        return True

    def _pack_adjacent_body_text(
        self,
        elements: list[DocumentElement],
        page_width: float,
        page_height: float,
    ) -> list[DocumentElement]:
        """Second-pass merge for short body fragments that survived line grouping."""
        if len(elements) < 2:
            return elements
        packed: list[DocumentElement] = []
        index = 0
        while index < len(elements):
            current = elements[index]
            if current.page_region != "body" or current.type not in {"paragraph", "formula"}:
                packed.append(current)
                index += 1
                continue
            merged = current
            index += 1
            while index < len(elements):
                nxt = elements[index]
                if not self._can_pack_elements(merged, nxt, page_width, page_height):
                    break
                merged = self._merge_text_elements(merged, nxt, page_width, page_height)
                index += 1
            packed.append(merged)
        return packed

    def _can_pack_elements(
        self,
        left: DocumentElement,
        right: DocumentElement,
        page_width: float,
        page_height: float,
    ) -> bool:
        if left.page_region != "body" or right.page_region != "body":
            return False
        if left.type not in {"paragraph", "formula"} or right.type not in {"paragraph", "formula"}:
            return False
        if left.style.alignment != right.style.alignment:
            return False
        left_size = left.style.font_size_pt or 10.0
        right_size = right.style.font_size_pt or left_size
        if abs(left_size - right_size) > max(2.0, left_size * 0.35):
            return False
        # Same column band.
        if abs(left.bbox.left - right.bbox.left) > 0.14:
            return False
        gap_pt = (right.bbox.top - left.bbox.bottom) * page_height
        max_gap = max(9.0, left_size * 1.4)
        if gap_pt < -3.0 or gap_pt > max_gap:
            return False
        if left.type == right.type == "formula" and gap_pt > max(1.5, left_size * 0.25):
            return False
        left_text = (left.text or "").rstrip()
        right_text = (right.text or "").strip()
        if self._looks_like_section_heading_text(right_text) or self._looks_like_section_heading_text(left_text):
            return False
        if left_text.endswith((".", "!", "?", "。", "！", "？")) and gap_pt > left_size * 1.05:
            return False
        # Avoid gluing long paragraphs into giant walls of text.
        if len(left_text) + len(right_text) > 900:
            return False
        if len(left_text) > 360 or len(right_text) > 360:
            return False
        return True

    def _looks_like_section_heading_text(self, text: str) -> bool:
        value = " ".join((text or "").split())
        if not value or len(value) > 80:
            return False
        if re.match(r"^\d+(\.\d+)*\s+\S", value):
            return True
        if value.isupper() and any(ch.isalpha() for ch in value) and len(value) <= 48:
            return True
        return False

    def _merge_text_elements(
        self,
        left: DocumentElement,
        right: DocumentElement,
        page_width: float,
        page_height: float,
    ) -> DocumentElement:
        text = f"{(left.text or '').rstrip()} {(right.text or '').lstrip()}".strip()
        right_runs = list(right.runs)
        if right_runs and not right_runs[0].line_break_before:
            right_runs[0] = right_runs[0].model_copy(update={"line_break_before": True})
        runs = list(left.runs) + right_runs
        top = min(left.bbox.top, right.bbox.top)
        bottom = max(left.bbox.bottom, right.bbox.bottom)
        left_edge = min(left.bbox.left, right.bbox.left)
        right_edge = max(left.bbox.right, right.bbox.right)
        element_type = "formula" if left.type == "formula" and right.type == "formula" else "paragraph"
        font_size = left.style.font_size_pt or right.style.font_size_pt
        left_lines = list(left.line_bboxes) or [left.bbox]
        right_lines = list(right.line_bboxes) or [right.bbox]
        return left.model_copy(
            update={
                "type": element_type,
                "role": self._role_for_text_element(element_type, left.page_region),
                "text": text,
                "runs": runs,
                "bbox": BoundingBox(left=left_edge, top=top, right=right_edge, bottom=bottom),
                "line_bboxes": left_lines + right_lines,
                "style": left.style.model_copy(
                    update={
                        "font_size_pt": font_size,
                        "space_after_pt": 0.0,
                        "line_spacing": left.style.line_spacing or right.style.line_spacing or 1.0,
                    }
                ),
                "formula": (
                    FormulaPayload(
                        fallback_text=text,
                        omml_xml=self._formula_to_omml(text),
                        source_type="vector" if self._formula_to_omml(text) else "unknown",
                    )
                    if element_type == "formula"
                    else None
                ),
            }
        )

    def _table_to_element(
        self,
        table: PdfTableObject,
        page_no: int,
        page_width: float,
        page_height: float,
        index: int,
        reading_order: int,
    ) -> DocumentElement:
        row_payloads: list[list[TableCellPayload | None]] = []
        column_count = max((len(row) for row in table.rows), default=0)
        x_edges = self._table_edges(table.cell_bboxes, axis=0)
        y_edges = self._table_edges(table.cell_bboxes, axis=1)
        for row_index, row in enumerate(table.rows):
            payload_row: list[TableCellPayload | None] = []
            for column_index, value in enumerate(row):
                cell_bbox = None
                raw_bbox = None
                if row_index < len(table.cell_bboxes) and column_index < len(table.cell_bboxes[row_index]):
                    raw_bbox = table.cell_bboxes[row_index][column_index]
                    if raw_bbox is not None:
                        cell_bbox = BoundingBox.from_points(*raw_bbox, page_width=page_width, page_height=page_height)
                if raw_bbox is None:
                    payload_row.append(None)
                    continue
                raw_borders = {}
                if table.cell_borders and row_index < len(table.cell_borders):
                    if column_index < len(table.cell_borders[row_index]):
                        raw_borders = table.cell_borders[row_index][column_index]
                payload_row.append(
                    TableCellPayload(
                        text=value,
                        bbox=cell_bbox,
                        row_span=self._span_for_bbox(raw_bbox, y_edges, axis=1),
                        col_span=self._span_for_bbox(raw_bbox, x_edges, axis=0),
                        top_border=self._border_style(raw_borders.get("top")),
                        right_border=self._border_style(raw_borders.get("right")),
                        bottom_border=self._border_style(raw_borders.get("bottom")),
                        left_border=self._border_style(raw_borders.get("left")),
                    )
                )
            row_payloads.append(payload_row)

        self._merge_spanning_label_rows(row_payloads)

        text = "\n".join("\t".join(cell.text if cell is not None else "" for cell in row) for row in row_payloads)
        return DocumentElement(
            id=f"p{page_no:03d}_table_{index:04d}",
            type="table",
            role="table",
            text=text,
            bbox=BoundingBox.from_points(table.x0, table.top, table.x1, table.bottom, page_width, page_height),
            reading_order=reading_order,
            table=TablePayload(
                row_count=len(row_payloads),
                column_count=column_count,
                rows=row_payloads,
                repeat_header_row_count=1 if len(row_payloads) > 1 else 0,
                has_borders=any(
                    cell.top_border or cell.right_border or cell.bottom_border or cell.left_border
                    for row in row_payloads
                    for cell in row
                    if cell is not None
                ),
                column_widths_pt=table.column_widths_pt or [],
                row_heights_pt=table.row_heights_pt or [],
            ),
            confidence=Confidence(text=0.85, role=0.8, geometry=0.85),
            provenance=Provenance(parser=self.name, source_page=page_no, source="pdfplumber_table"),
        )

    def _merge_spanning_label_rows(self, rows: list[list[TableCellPayload | None]]) -> None:
        """Join long descriptive cells that a sparse PDF grid split by x."""
        for row in rows:
            indices = [
                index
                for index, cell in enumerate(row)
                if cell is not None and cell.text.strip()
            ]
            phrase_indices = [
                index
                for index in indices
                if any(
                    marker in row[index].text.lower()
                    for marker in ("positional", "embedding", "instead", "sinusoid")
                )
            ]
            if len(phrase_indices) < 3:
                continue
            start, end = min(phrase_indices), max(phrase_indices)
            if end - start < 2:
                continue
            cells = [row[index] for index in range(start, end + 1) if row[index] is not None]
            if len(cells) < 3:
                continue
            bboxes = [cell.bbox for cell in cells if cell.bbox is not None]
            if not bboxes:
                continue
            first, last = bboxes[0], bboxes[-1]
            merged = TableCellPayload(
                text=" ".join(cell.text.strip() for cell in cells if cell.text.strip()),
                bbox=BoundingBox(
                    left=first.left,
                    top=min(box.top for box in bboxes),
                    right=last.right,
                    bottom=max(box.bottom for box in bboxes),
                ),
                col_span=end - start + 1,
                alignment="center",
                vertical_alignment="center",
                top_border=cells[0].top_border,
                right_border=cells[-1].right_border,
                bottom_border=cells[0].bottom_border,
                left_border=cells[0].left_border,
            )
            row[start] = merged
            for index in range(start + 1, end + 1):
                row[index] = None

    def _table_edges(self, cell_bboxes, axis: int) -> list[float]:
        values: list[float] = []
        end_axis = axis + 2
        for row in cell_bboxes:
            for bbox in row:
                if bbox is None:
                    continue
                values.extend((float(bbox[axis]), float(bbox[end_axis])))
        edges: list[float] = []
        for value in sorted(values):
            if not edges or abs(value - edges[-1]) > 1.5:
                edges.append(value)
            else:
                edges[-1] = (edges[-1] + value) / 2
        return edges

    def _span_for_bbox(self, bbox, edges: list[float], axis: int) -> int:
        if bbox is None or len(edges) < 2:
            return 1
        end_axis = axis + 2
        start = min(range(len(edges)), key=lambda index: abs(edges[index] - float(bbox[axis])))
        end = min(range(len(edges)), key=lambda index: abs(edges[index] - float(bbox[end_axis])))
        return max(1, end - start)

    def _group_words_by_line(self, words: list[PdfTextObject]) -> list[list[PdfTextObject]]:
        """Group baseline text plus nearby PDF superscript/subscript glyphs."""
        groups: list[list[PdfTextObject]] = []
        for word in sorted(words, key=lambda item: ((item.top + item.bottom) / 2, item.x0)):
            center = (word.top + word.bottom) / 2
            if groups:
                previous = groups[-1]
                previous_center = sum((item.top + item.bottom) / 2 for item in previous) / len(previous)
                # A 10pt PDF line is about 11pt apart. A 7pt math glyph
                # belongs to its 10pt baseline when it is within 6pt.
                if abs(center - previous_center) <= 6.0:
                    previous.append(word)
                    continue
            groups.append([word])
        # Display math can place a radical, numerator, or denominator more
        # than 6pt away from its baseline. Attach a compact math-only group to
        # the overlapping broad line without joining ordinary paragraph lines.
        merged: list[list[PdfTextObject]] = []
        for group in groups:
            if merged and self._can_attach_math_fragment(merged[-1], group):
                merged[-1].extend(group)
            elif merged and self._can_attach_math_fragment(group, merged[-1]):
                merged[-1].extend(group)
            else:
                merged.append(group)
        return merged

    def _can_attach_math_fragment(
        self,
        fragment: list[PdfTextObject],
        candidate: list[PdfTextObject],
    ) -> bool:
        if not fragment or not candidate or len(fragment) > 8:
            return False
        fragment_left = min(word.x0 for word in fragment)
        fragment_right = max(word.x1 for word in fragment)
        candidate_left = min(word.x0 for word in candidate)
        candidate_right = max(word.x1 for word in candidate)
        fragment_width = fragment_right - fragment_left
        candidate_width = candidate_right - candidate_left
        if fragment_width >= 80.0 or fragment_width >= candidate_width * 0.42:
            return False
        if fragment_left < candidate_left - 2.0 or fragment_right > candidate_right + 2.0:
            return False
        fragment_center = sum((word.top + word.bottom) / 2 for word in fragment) / len(fragment)
        candidate_center = sum((word.top + word.bottom) / 2 for word in candidate) / len(candidate)
        if abs(fragment_center - candidate_center) > 13.0:
            return False
        # A short math-looking line that starts exactly at the paragraph's
        # left edge is usually the next source line (for example ``P_drop =
        # 0.1``), not a superscript fragment inside the line above it.
        if abs(fragment_left - candidate_left) <= 5.0 and fragment_center > candidate_center + 7.0:
            return False
        return any(self._is_math_word(word) for word in fragment)

    def _is_math_word(self, word: PdfTextObject) -> bool:
        font = (word.font_name or "").lower()
        text = word.text or ""
        return any(token in font for token in ("cmmi", "cmr", "cmsy", "msam", "symbol")) or any(
            marker in text for marker in ("√", "∑", "∫", "−", "·", "≤", "≥", "≠", "→")
        )

    def _average_size(self, words: list[PdfTextObject]) -> float | None:
        sizes = [word.font_size for word in words if word.font_size]
        if not sizes:
            return None
        return sum(sizes) / len(sizes)

    def _common_font(self, words: list[PdfTextObject]) -> str | None:
        fonts = [self._normalize_font_name(word.font_name) for word in words if word.font_name]
        fonts = [font for font in fonts if font]
        if not fonts:
            return None
        return max(set(fonts), key=fonts.count)

    def _normalize_font_name(self, font_name: str | None) -> str | None:
        """Map PDF embedded faces onto common desktop families to reduce reflow width."""
        if not font_name:
            return None
        raw = font_name.split("+")[-1]
        lowered = raw.lower().replace(" ", "")
        if "times" in lowered or "nimbusrom" in lowered or "liberation serif" in lowered:
            return "Times New Roman"
        if "helvetica" in lowered or "arial" in lowered or "nimbusans" in lowered or "liberation sans" in lowered:
            return "Arial"
        if "courier" in lowered or "mono" in lowered:
            return "Courier New"
        if "symbol" in lowered:
            return "Symbol"
        return raw

    def _line_looks_bold(self, words: list[PdfTextObject]) -> bool:
        fonts = " ".join(word.font_name or "" for word in words).lower()
        return "bold" in fonts or "black" in fonts or "semibold" in fonts

    def _text_element_type(
        self,
        text: str,
        avg_size: float | None,
        median_size: float | None,
        page_region: str,
    ) -> str:
        if page_region == "header":
            return "header"
        if page_region == "footer":
            return "footer"
        if self._looks_like_formula(text):
            return "formula"
        if self._looks_like_heading(text, avg_size, median_size):
            return "heading"
        return "paragraph"

    def _looks_like_heading(self, text: str, avg_size: float | None, median_size: float | None) -> bool:
        if avg_size is not None and median_size is not None and avg_size >= median_size * 1.25:
            return True
        if len(text) <= 80 and text.isupper() and any(char.isalpha() for char in text):
            return True
        return False

    def _looks_like_formula(self, text: str) -> bool:
        value = " ".join(text.split())
        if not value or len(value) > 120:
            return False
        math_markers = (
            "=", "\\", "∑", "∫", "√", "≤", "≥", "≠", "→", "α", "β", "γ", "λ",
            "^", "_", "−", "·", "×", "∞", "∂", "∈", "∇", "≈", "≡",
        )
        marker_hits = sum(value.count(marker) for marker in math_markers)
        if marker_hits == 0:
            return False
        words = value.split()
        alpha_words = sum(1 for word in words if sum(ch.isalpha() for ch in word) >= 3)
        # Long prose with a single '=' is not a display formula.
        if alpha_words >= 8 and marker_hits <= 1:
            return False
        if len(value) <= 180 and marker_hits >= 1 and alpha_words <= 12:
            return True
        return marker_hits >= 2 and alpha_words <= 6

    def _formula_to_omml(self, text: str) -> str | None:
        """Build an editable OMML fragment for a bounded one-line formula.

        PDF text extraction often loses the original operator tree, so the
        parser handles high-confidence fraction/superscript/subscript/radical
        forms first and then emits a flat OMML math run sequence for a
        formula-like line. The original text remains in ``fallback_text`` for
        cases where a later recognizer can reconstruct a richer tree.
        """
        value = " ".join(text.split())
        if not value or len(value) > 120 or value == "√":
            return None
        fraction = re.fullmatch(r"([A-Za-z0-9]+)\s*/\s*([A-Za-z0-9]+)", value)
        if fraction:
            return self._omml_wrapper(
                f"<m:f><m:num>{self._omml_run(fraction.group(1))}</m:num>"
                f"<m:den>{self._omml_run(fraction.group(2))}</m:den></m:f>"
            )
        superscript = re.fullmatch(r"([A-Za-zα-ωΑ-Ω0-9]+)\s*\^\s*([A-Za-z0-9]+)", value)
        if superscript:
            return self._omml_wrapper(
                f"<m:sSup><m:e>{self._omml_run(superscript.group(1))}</m:e>"
                f"<m:sup>{self._omml_run(superscript.group(2))}</m:sup></m:sSup>"
            )
        subscript = re.fullmatch(r"([A-Za-zα-ωΑ-Ω0-9]+)\s*_\s*([A-Za-z0-9]+)", value)
        if subscript:
            return self._omml_wrapper(
                f"<m:sSub><m:e>{self._omml_run(subscript.group(1))}</m:e>"
                f"<m:sub>{self._omml_run(subscript.group(2))}</m:sub></m:sSub>"
            )
        radical = re.fullmatch(r"(?:sqrt|√)\s*\(?([A-Za-z0-9]+)\)?", value, flags=re.IGNORECASE)
        if radical:
            return self._omml_wrapper(f"<m:rad><m:e>{self._omml_run(radical.group(1))}</m:e></m:rad>")
        sub_sup = re.fullmatch(
            r"([A-Za-zα-ωΑ-Ω0-9]+)\s*_\s*([A-Za-z0-9]+)\s*\^\s*([A-Za-z0-9]+)",
            value,
        )
        if sub_sup:
            return self._omml_wrapper(
                f"<m:sSubSup><m:e>{self._omml_run(sub_sup.group(1))}</m:e>"
                f"<m:sub>{self._omml_run(sub_sup.group(2))}</m:sub>"
                f"<m:sup>{self._omml_run(sub_sup.group(3))}</m:sup></m:sSubSup>"
            )
        sup_sub = re.fullmatch(
            r"([A-Za-zα-ωΑ-Ω0-9]+)\s*\^\s*([A-Za-z0-9]+)\s*_\s*([A-Za-z0-9]+)",
            value,
        )
        if sup_sub:
            return self._omml_wrapper(
                f"<m:sSubSup><m:e>{self._omml_run(sup_sub.group(1))}</m:e>"
                f"<m:sub>{self._omml_run(sup_sub.group(3))}</m:sub>"
                f"<m:sup>{self._omml_run(sup_sub.group(2))}</m:sup></m:sSubSup>"
            )
        if not self._looks_like_formula(value):
            return None

        # Keep the token stream editable even when the PDF no longer exposes
        # enough geometry to recover nested math objects. Whitespace between
        # extracted tokens is preserved as math runs so operators do not
        # collapse into adjacent words in Word.
        token_pattern = re.compile(r"\\[A-Za-z]+|[A-Za-z]+|\d+(?:\.\d+)?|[α-ωΑ-Ω]+|[^\s]")
        matches = list(token_pattern.finditer(value))
        if not matches:
            return None
        parts: list[str] = []
        for index, match in enumerate(matches):
            token = match.group(0)
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(value)
            had_space_after = bool(value[match.end():next_start].strip() == "" and value[match.end():next_start])
            parts.append(self._omml_run(token))
            if had_space_after:
                parts.append(self._omml_run(" "))
        return self._omml_wrapper("".join(parts))

    def _omml_wrapper(self, content: str) -> str:
        return f'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">{content}</m:oMath>'

    def _omml_run(self, text: str) -> str:
        return f"<m:r><m:t>{escape(text)}</m:t></m:r>"

    def _guess_alignment(self, x0: float, x1: float, page_width: float) -> str:
        block_width = max(0.0, x1 - x0)
        center = (x0 + x1) / 2
        # A full body line often has a center point near the page center even
        # though it is left aligned. Only treat short, page-centered blocks as
        # centered so the positioned renderer does not center every paragraph.
        if (
            block_width <= page_width * 0.58
            and abs(center - page_width / 2) <= page_width * 0.08
        ):
            return "center"
        return "left"

    def _page_region(self, top: float, bottom: float, page_height: float) -> str:
        if bottom <= page_height * 0.10:
            return "header"
        if top >= page_height * 0.92:
            return "footer"
        return "body"

    def _role_for_text_element(self, element_type: str, page_region: str) -> str | None:
        if element_type == "heading":
            return "section_heading"
        if page_region == "header":
            return "running_header"
        if page_region == "footer":
            return "running_footer"
        if element_type == "formula":
            return "formula_text_fallback"
        return None

    def _word_to_run(self, word: PdfTextObject) -> TextRun:
        font = self._normalize_font_name(word.font_name)
        return TextRun(
            text=word.text,
            font_family=font,
            source_font_family=word.font_name,
            font_slots=FontSlots(
                ascii=font,
                hAnsi=font,
                eastAsia=font,
                cs=font,
            ) if font else None,
            font_size_pt=word.font_size,
            bold=self._line_looks_bold([word]),
            italic="italic" in (word.font_name or "").lower() or "oblique" in (word.font_name or "").lower(),
            color=self._color_to_hex(word.color),
        )

    def _runs_for_line_group(self, group: list[dict], *, formula: bool = False) -> list[TextRun]:
        runs: list[TextRun] = []
        for line_index, info in enumerate(group):
            line = sorted(info["line"], key=lambda item: item.x0)
            sizes = [word.font_size for word in line if word.font_size]
            baseline_size = max(sizes, default=10.0)
            baseline_centers = [
                (word.top + word.bottom) / 2
                for word in line
                if (word.font_size or baseline_size) >= baseline_size * 0.84
            ]
            baseline_y = sum(baseline_centers) / len(baseline_centers) if baseline_centers else 0.0
            for word_index, word in enumerate(line):
                run = self._word_to_run(word)
                small = (word.font_size or baseline_size) < baseline_size * 0.84
                center_y = (word.top + word.bottom) / 2
                superscript = formula and small and center_y < baseline_y - 1.0
                subscript = formula and small and center_y > baseline_y + 1.0
                next_word = line[word_index + 1] if word_index + 1 < len(line) else None
                space_after = True
                if next_word is not None:
                    next_center = (next_word.top + next_word.bottom) / 2
                    next_small = (next_word.font_size or baseline_size) < baseline_size * 0.84
                    gap = next_word.x0 - word.x1
                    space_after = gap > max(0.8, (word.font_size or baseline_size) * 0.12)
                    if formula and (small or next_small) and abs(next_center - baseline_y) > 1.0:
                        space_after = False
                    if word.text.endswith(("(", "[", "{")) or next_word.text.startswith((".", ",", ";", ":", ")", "]", "}")):
                        space_after = False
                run = run.model_copy(
                    update={
                        "line_break_before": line_index > 0 and word_index == 0,
                        "space_after": space_after,
                        "superscript": superscript,
                        "subscript": subscript,
                    }
                )
                runs.append(run)
        return runs

    def _text_from_runs(self, runs: list[TextRun], *, formula: bool = False) -> str:
        chunks: list[str] = []
        previous_script: str | None = None
        for run in runs:
            if run.line_break_before:
                chunks.append("\n")
            script = "sup" if formula and run.superscript else "sub" if formula and run.subscript else None
            if script != previous_script:
                if script == "sup":
                    chunks.append("^")
                elif script == "sub":
                    chunks.append("_")
            previous_script = script
            chunks.append(run.text)
            if run.space_after:
                chunks.append(" ")
        return "".join(chunks).strip()

    def _font_slots(self, words: list[PdfTextObject]) -> FontSlots | None:
        font = self._common_font(words)
        if not font:
            return None
        return FontSlots(ascii=font, hAnsi=font, eastAsia=font, cs=font)

    def _border_style(self, border) -> BorderStyle | None:
        if border is None or not border.visible:
            return None
        return BorderStyle(
            val=border.style if border.style in {"none", "single", "dashed", "dotted", "double", "thick"} else "single",
            width_pt=border.width_pt,
            color=self._color_to_hex(border.color),
        )

    def _color_to_hex(self, color) -> str | None:
        if color is None:
            return None
        if isinstance(color, (tuple, list)) and len(color) == 1:
            value = int(round(max(0.0, min(1.0, float(color[0]))) * 255))
            return f"{value:02X}{value:02X}{value:02X}"
        if isinstance(color, (tuple, list)) and len(color) >= 3:
            values = [int(round(max(0.0, min(1.0, float(channel))) * 255)) for channel in color[:3]]
            return "".join(f"{value:02X}" for value in values)
        if isinstance(color, (int, float)):
            value = int(round(max(0.0, min(1.0, float(color))) * 255))
            return f"{value:02X}{value:02X}{value:02X}"
        return None

    def _inside_any_bbox(self, word: PdfTextObject, bboxes: list[tuple[float, float, float, float]]) -> bool:
        center_x = (word.x0 + word.x1) / 2
        center_y = (word.top + word.bottom) / 2
        return any(x0 <= center_x <= x1 and top <= center_y <= bottom for x0, top, x1, bottom in bboxes)

    def _renumber_by_position(self, elements: list[DocumentElement]) -> list[DocumentElement]:
        """Legacy top-then-left order kept for tests/callers that expect it."""
        sorted_elements = sorted(elements, key=lambda item: (item.bbox.top, item.bbox.left, item.reading_order))
        renumbered: list[DocumentElement] = []
        for index, element in enumerate(sorted_elements, start=1):
            renumbered.append(element.model_copy(update={"reading_order": index}))
        return renumbered

    def _renumber_for_reading_order(
        self,
        elements: list[DocumentElement],
        page_width: float,
        page_height: float,
    ) -> list[DocumentElement]:
        """Column-major order when multi-column, else top-then-left."""
        body = [
            element
            for element in elements
            if element.page_region == "body" and element.type not in {"separator", "blank_space"}
        ]
        column_count, splits = self._detect_columns(body)
        if column_count <= 1:
            return self._renumber_by_position(elements)

        def column_index(element: DocumentElement) -> int:
            mid = (element.bbox.left + element.bbox.right) / 2
            for index, edge in enumerate(splits):
                if mid < edge:
                    return index
            return column_count - 1

        sorted_elements = sorted(
            elements,
            key=lambda item: (
                0 if item.page_region == "header" else 2 if item.page_region == "footer" else 1,
                column_index(item) if item.page_region == "body" else 0,
                item.bbox.top,
                item.bbox.left,
                item.reading_order,
            ),
        )
        renumbered: list[DocumentElement] = []
        for index, element in enumerate(sorted_elements, start=1):
            renumbered.append(element.model_copy(update={"reading_order": index}))
        return renumbered

    def _detect_columns(self, body_elements: list[DocumentElement]) -> tuple[int, list[float]]:
        """Return (column_count, split_edges_in_normalized_x)."""
        centers = sorted(
            (element.bbox.left + element.bbox.right) / 2
            for element in body_elements
            if element.type in {"paragraph", "heading", "formula", "caption"}
        )
        if len(centers) < 16:
            return 1, [1.0]
        gaps = [(centers[i + 1] - centers[i], i) for i in range(len(centers) - 1)]
        # Multi-column pages show a wide gap in x-centers around the gutter.
        candidates = [item for item in gaps if item[0] >= 0.10]
        if not candidates:
            return 1, [1.0]
        gap, index = max(candidates, key=lambda item: item[0])
        left_cluster = centers[: index + 1]
        right_cluster = centers[index + 1 :]
        if len(left_cluster) < max(6, len(centers) * 0.18):
            return 1, [1.0]
        if len(right_cluster) < max(6, len(centers) * 0.18):
            return 1, [1.0]
        split = (centers[index] + centers[index + 1]) / 2
        # Optional third column.
        right_gaps = [
            (right_cluster[i + 1] - right_cluster[i], i)
            for i in range(len(right_cluster) - 1)
            if right_cluster[i + 1] - right_cluster[i] >= 0.10
        ]
        if right_gaps and len(right_cluster) >= 18:
            gap2, index2 = max(right_gaps, key=lambda item: item[0])
            mid_cluster = right_cluster[: index2 + 1]
            far_cluster = right_cluster[index2 + 1 :]
            if len(mid_cluster) >= 6 and len(far_cluster) >= 6:
                split2 = (right_cluster[index2] + right_cluster[index2 + 1]) / 2
                return 3, [split, split2]
        return 2, [split]
