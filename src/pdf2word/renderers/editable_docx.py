from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from pdf2word.domain import DocumentElement, DocumentIR, PageIR


@dataclass(frozen=True)
class _PageMargins:
    left: float
    right: float
    top: float
    bottom: float


@dataclass(frozen=True)
class _FlowGeometry:
    space_before_pt: float
    left_indent_pt: float
    right_indent_pt: float
    line_spacing: float | None


@dataclass(frozen=True)
class _PackProfile:
    # Balanced defaults: readable academic layout while keeping ≈ source page count.
    font_scale: float = 0.96
    space_scale: float = 0.48
    image_max_height_frac: float = 0.40


@dataclass(frozen=True)
class _VerticalMap:
    """Maps source page Y coordinates into the Word content frame."""

    source_top: float
    source_span: float
    target_top: float
    target_span: float

    def map_y(self, source_y: float) -> float:
        if self.source_span <= 1e-6:
            return self.target_top
        rel = (source_y - self.source_top) / self.source_span
        rel = max(0.0, min(1.0, rel))
        return self.target_top + rel * self.target_span


class EditableDocxRenderer:
    """Render the Canonical IR as editable Word paragraphs with geometry-aware flow.

    layout:
      - continuous (default): one flowing section; minimizes LibreOffice page inflation
        caused by hard section breaks that cannot reclaim overflow space.
      - paged: one Word section per PDF page (page-specific headers/footers; more pages).
    """

    name = "editable_docx"

    def render(
        self,
        document_ir: DocumentIR,
        output_path: str | Path,
        *,
        layout: str = "continuous",
    ) -> Path:
        try:
            from docx import Document
            from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
            from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
            from docx.enum.section import WD_SECTION_START
            from docx.shared import Pt, Twips
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
        except ImportError as exc:
            raise RuntimeError("python-docx is required to render DOCX output") from exc

        if layout not in {"continuous", "paged"}:
            raise ValueError(f"Unsupported editable layout: {layout}")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        doc = Document()
        self._tighten_default_styles(doc, Pt)
        if layout == "continuous":
            self._render_continuous(
                doc,
                document_ir,
                WD_TABLE_ALIGNMENT,
                WD_CELL_VERTICAL_ALIGNMENT,
                WD_ALIGN_PARAGRAPH,
                WD_LINE_SPACING,
                Pt,
                Twips,
                OxmlElement,
                qn,
            )
        else:
            self._render_paged(
                doc,
                document_ir,
                WD_SECTION_START,
                WD_TABLE_ALIGNMENT,
                WD_CELL_VERTICAL_ALIGNMENT,
                WD_ALIGN_PARAGRAPH,
                WD_LINE_SPACING,
                Pt,
                Twips,
                OxmlElement,
                qn,
            )

        doc.save(output)
        return output

    def _render_continuous(
        self,
        doc,
        document_ir: DocumentIR,
        table_alignment,
        cell_vertical_alignment,
        alignment_enum,
        line_spacing_enum,
        point_factory,
        twips_factory,
        oxml_element,
        qn,
    ) -> None:
        if not document_ir.pages:
            return
        # Use the first page as the section canvas; body content from all pages flows.
        base_page = document_ir.pages[0]
        margins = self._compute_document_margins(document_ir.pages)
        section = doc.sections[0]
        self._apply_section_geometry(section, base_page, margins, point_factory, twips_factory)
        self._render_continuous_header_footer(section, document_ir.pages)
        for page_index, page in enumerate(document_ir.pages):
            pack = self._pack_profile(page)
            column_count, column_splits = self._detect_columns(page)
            # Map source Y into the Word frame so soft-broken pages do not leave
            # a huge empty band under short body content.
            vmap = self._vertical_map(page, margins, pack, multi_column=column_count > 1)
            need_page_break = page_index > 0
            prev_bottom_pt: float | None = None
            prev_column: int | None = None
            body_elements = [
                element
                for element in page.ordered_elements()
                if element.type not in {"header", "footer"} and not self._skip_separator(page, element)
            ]
            index = 0
            while index < len(body_elements):
                element = body_elements[index]
                pair = None
                if (
                    element.type == "image"
                    and index + 1 < len(body_elements)
                    and body_elements[index + 1].type == "image"
                    and self._images_side_by_side(element, body_elements[index + 1])
                ):
                    pair = body_elements[index + 1]
                column_index = self._column_index(element, column_splits)
                geometry = self._flow_geometry(
                    page,
                    element,
                    prev_bottom_pt,
                    margins,
                    pack,
                    multi_column=column_count > 1,
                    column_changed=prev_column is not None and column_index != prev_column,
                    vertical_map=vmap,
                )
                if pair is not None:
                    self._render_image_pair(
                        doc,
                        page,
                        element,
                        pair,
                        geometry,
                        margins,
                        point_factory,
                        pack,
                        page_break_before=need_page_break,
                    )
                    index += 2
                    need_page_break = False
                    bottom_src = page.height_pt * max(element.bbox.bottom, pair.bbox.bottom)
                    prev_bottom_pt = vmap.map_y(bottom_src) if vmap else bottom_src
                    prev_column = column_index
                    continue
                self._render_body_element(
                    doc,
                    page,
                    element,
                    geometry,
                    margins,
                    table_alignment,
                    cell_vertical_alignment,
                    alignment_enum,
                    line_spacing_enum,
                    point_factory,
                    oxml_element,
                    qn,
                    pack,
                    page_break_before=need_page_break,
                    absolute_frame=False,
                )
                need_page_break = False
                bottom_src = page.height_pt * element.bbox.bottom
                prev_bottom_pt = vmap.map_y(bottom_src) if vmap else bottom_src
                prev_column = column_index
                index += 1

    def _render_paged(
        self,
        doc,
        document_ir: DocumentIR,
        section_start,
        table_alignment,
        cell_vertical_alignment,
        alignment_enum,
        line_spacing_enum,
        point_factory,
        twips_factory,
        oxml_element,
        qn,
    ) -> None:
        for page_index, page in enumerate(document_ir.pages):
            section = doc.sections[0] if page_index == 0 else doc.add_section(section_start.NEW_PAGE)
            margins = self._compute_margins(page)
            self._apply_section_geometry(section, page, margins, point_factory, twips_factory)
            self._render_page_header_footer(section, page)
            pack = self._pack_profile(page)
            vmap = self._vertical_map(page, margins, pack, multi_column=False)
            prev_bottom_pt: float | None = None
            for element in page.ordered_elements():
                if element.type in {"header", "footer"}:
                    continue
                if self._skip_separator(page, element):
                    continue
                geometry = self._flow_geometry(
                    page, element, prev_bottom_pt, margins, pack, vertical_map=vmap
                )
                self._render_body_element(
                    doc,
                    page,
                    element,
                    geometry,
                    margins,
                    table_alignment,
                    cell_vertical_alignment,
                    alignment_enum,
                    line_spacing_enum,
                    point_factory,
                    oxml_element,
                    qn,
                    pack,
                )
                bottom_src = page.height_pt * element.bbox.bottom
                prev_bottom_pt = vmap.map_y(bottom_src) if vmap else bottom_src

    def _pack_profile(self, page: PageIR) -> _PackProfile:
        body = [
            element
            for element in page.elements
            if element.page_region == "body" and element.type not in {"separator", "blank_space"}
        ]
        formulas = sum(1 for element in body if element.type == "formula")
        images = sum(1 for element in body if element.type == "image")
        tables = sum(1 for element in body if element.type == "table")
        short = sum(1 for element in body if element.text and len(element.text) < 40)
        column_count, _ = self._detect_columns(page)
        table_height = 0.0
        for element in body:
            if element.type == "table" and element.table is not None:
                if element.table.row_heights_pt:
                    table_height += sum(element.table.row_heights_pt)
                else:
                    table_height += element.table.row_count * 14.0
        if tables and table_height >= page.height_pt * 0.28:
            profile = _PackProfile(font_scale=0.90, space_scale=0.28, image_max_height_frac=0.26)
        elif column_count > 1 or len(body) >= 28 or formulas >= 3 or images >= 2 or short >= 12:
            profile = _PackProfile(font_scale=0.92, space_scale=0.34, image_max_height_frac=0.30)
        elif len(body) >= 20 or formulas >= 2 or short >= 10:
            profile = _PackProfile(font_scale=0.94, space_scale=0.42, image_max_height_frac=0.36)
        else:
            profile = _PackProfile(font_scale=0.97, space_scale=0.55, image_max_height_frac=0.44)
        return self._fit_pack_profile(page, profile)

    def _detect_columns(self, page: PageIR) -> tuple[int, list[float]]:
        body = [
            element
            for element in page.elements
            if element.page_region == "body" and element.type in {"paragraph", "heading", "formula", "caption"}
        ]
        centers = sorted((element.bbox.left + element.bbox.right) / 2 for element in body)
        if len(centers) < 16:
            return 1, [1.0]
        gaps = [(centers[i + 1] - centers[i], i) for i in range(len(centers) - 1)]
        candidates = [item for item in gaps if item[0] >= 0.10]
        if not candidates:
            return 1, [1.0]
        _, index = max(candidates, key=lambda item: item[0])
        left_cluster = centers[: index + 1]
        right_cluster = centers[index + 1 :]
        if len(left_cluster) < max(6, len(centers) * 0.18) or len(right_cluster) < max(6, len(centers) * 0.18):
            return 1, [1.0]
        split = (centers[index] + centers[index + 1]) / 2
        return 2, [split]

    def _skip_separator(self, page: PageIR, element: DocumentElement) -> bool:
        """Drop decorative rules that become junk boxes next to tables/figures."""
        if element.type != "separator":
            return False
        height_pt = page.height_pt * max(0.0, element.bbox.bottom - element.bbox.top)
        width_frac = max(0.0, element.bbox.right - element.bbox.left)
        # Keep only substantial full-width horizontal rules (e.g. under titles).
        if height_pt < 3.0:
            return True
        if width_frac < 0.35:
            return True
        if element.separator and element.separator.orientation == "vertical":
            return True
        return False

    def _images_side_by_side(self, left: DocumentElement, right: DocumentElement) -> bool:
        """True when two figures share a horizontal band (Attention page-4 diagrams)."""
        if left.type != "image" or right.type != "image":
            return False
        a0, a1 = left.bbox.top, left.bbox.bottom
        b0, b1 = right.bbox.top, right.bbox.bottom
        overlap = min(a1, b1) - max(a0, b0)
        min_h = max(1e-6, min(a1 - a0, b1 - b0))
        if overlap < 0.35 * min_h:
            return False
        mid_a = (left.bbox.left + left.bbox.right) / 2
        mid_b = (right.bbox.left + right.bbox.right) / 2
        return abs(mid_a - mid_b) >= 0.12

    def _column_index(self, element: DocumentElement, splits: list[float]) -> int:
        mid = (element.bbox.left + element.bbox.right) / 2
        for index, edge in enumerate(splits):
            if mid < edge:
                return index
        return max(0, len(splits) - 1)

    def _fit_pack_profile(self, page: PageIR, profile: _PackProfile) -> _PackProfile:
        """Mild overflow protection only — never crush text into unreadable density."""
        margins = self._compute_margins(page)
        usable = max(120.0, page.height_pt - margins.top - margins.bottom)
        font_scale = profile.font_scale
        space_scale = profile.space_scale
        image_frac = profile.image_max_height_frac
        column_count, _ = self._detect_columns(page)
        multi = column_count > 1
        # Keep ≈1 Word page per PDF page without returning to 0.80× crushed text.
        target = 0.93 if multi else 0.96
        min_font = 0.86 if multi else 0.88
        for _ in range(12):
            estimated = self._estimate_body_height_pt(
                page, margins, font_scale, space_scale, image_frac, multi_column=multi
            )
            if estimated <= usable * target:
                break
            ratio = max(0.82, (usable * (target - 0.03)) / max(estimated, 1.0))
            font_scale = max(min_font, font_scale * ratio)
            space_scale = max(0.22 if multi else 0.28, space_scale * ratio)
            image_frac = max(0.18, image_frac * ratio)

        estimated = self._estimate_body_height_pt(
            page, margins, font_scale, space_scale, image_frac, multi_column=multi
        )
        # Mild open on under-filled simple pages (reduces huge bottom white).
        if not multi and estimated > 0 and estimated < usable * 0.78:
            space_scale = min(0.68, max(space_scale, 0.48))
            font_scale = min(1.0, max(font_scale, 0.94))
        return _PackProfile(
            font_scale=font_scale,
            space_scale=space_scale,
            image_max_height_frac=image_frac,
        )

    def _estimates_fit_one_page(
        self,
        page: PageIR,
        margins: _PageMargins,
        pack: _PackProfile,
        *,
        multi_column: bool,
    ) -> bool:
        usable = max(120.0, page.height_pt - margins.top - margins.bottom)
        estimated = self._estimate_body_height_pt(
            page,
            margins,
            pack.font_scale,
            pack.space_scale,
            pack.image_max_height_frac,
            multi_column=multi_column,
        )
        return estimated <= usable * 0.98

    def _estimate_body_height_pt(
        self,
        page: PageIR,
        margins: _PageMargins,
        font_scale: float,
        space_scale: float,
        image_frac: float,
        *,
        multi_column: bool = False,
    ) -> float:
        body = [
            element
            for element in page.ordered_elements()
            if element.page_region == "body" and element.type not in {"header", "footer"}
        ]
        if not body:
            return 0.0
        content_width = max(120.0, page.width_pt - margins.left - margins.right)
        # Full-measure single-column reflow after multi-column collapse.
        avg_glyph = (5.6 if multi_column else 6.0) * font_scale
        chars_per_line = max(30.0, content_width / max(avg_glyph, 1.0))
        total = 0.0
        prev_bottom: float | None = None
        prev_col: int | None = None
        _, splits = self._detect_columns(page)
        for element in body:
            top = page.height_pt * element.bbox.top
            bottom = page.height_pt * element.bbox.bottom
            col = self._column_index(element, splits)
            if prev_bottom is not None:
                if multi_column and prev_col is not None and col != prev_col:
                    total += 3.0 * space_scale
                else:
                    gap = max(0.0, top - prev_bottom)
                    if gap >= 5.0:
                        total += min(10.0, gap * space_scale)
            if element.type == "image" and element.image is not None:
                max_h = max(48.0, (page.height_pt - margins.top - margins.bottom - 36.0) * image_frac)
                height = min(element.image.height_pt, max_h)
                width = min(element.image.width_pt, content_width)
                if element.image.width_pt > 0 and width < element.image.width_pt:
                    height *= width / element.image.width_pt
                total += height
            elif element.type == "table" and element.table is not None:
                if element.table.row_heights_pt:
                    total += min(page.height_pt * 0.34, sum(element.table.row_heights_pt) * font_scale)
                else:
                    total += max(18.0, element.table.row_count * 12.0 * font_scale)
            elif element.type == "separator":
                continue
            else:
                font = (element.style.font_size_pt or 10.0) * font_scale
                text_len = len(element.text or "")
                lines = max(1.0, text_len / chars_per_line)
                total += lines * font * (1.0 if multi_column else 1.05)
            prev_bottom = bottom
            prev_col = col
        return total

    def _render_body_element(
        self,
        doc,
        page,
        element: DocumentElement,
        geometry: _FlowGeometry,
        margins: _PageMargins,
        table_alignment,
        cell_vertical_alignment,
        alignment_enum,
        line_spacing_enum,
        point_factory,
        oxml_element,
        qn,
        pack: _PackProfile | None = None,
        *,
        page_break_before: bool = False,
        absolute_frame: bool = False,
    ) -> None:
        pack = pack or _PackProfile()
        if page_break_before and element.type not in {"table", "image"}:
            pass
        elif page_break_before:
            breaker = doc.add_paragraph()
            breaker.paragraph_format.page_break_before = True
            breaker.paragraph_format.space_before = point_factory(0)
            breaker.paragraph_format.space_after = point_factory(0)
            page_break_before = False
        if element.type == "table":
            self._render_table(
                doc,
                page,
                element,
                geometry,
                table_alignment,
                cell_vertical_alignment,
                oxml_element,
                qn,
                point_factory,
                pack,
            )
        elif element.type == "image":
            self._render_image(
                doc,
                page,
                element,
                geometry,
                margins,
                point_factory,
                pack,
                page_break_before=page_break_before,
                absolute_frame=absolute_frame,
            )
        elif element.type == "formula":
            self._render_formula(
                doc,
                element,
                geometry,
                alignment_enum,
                line_spacing_enum,
                point_factory,
                qn,
                page_break_before=page_break_before,
                absolute_frame=absolute_frame,
                page=page,
            )
        elif element.type == "separator":
            self._render_separator(
                doc, page, element, geometry, point_factory, oxml_element, qn, page_break_before=page_break_before
            )
        elif element.text:
            self._render_text_element(
                doc,
                element,
                geometry,
                alignment_enum,
                line_spacing_enum,
                point_factory,
                qn,
                pack,
                page_break_before=page_break_before,
                absolute_frame=absolute_frame,
                page=page,
            )

    def _compute_document_margins(self, pages: list[PageIR]) -> _PageMargins:
        margins = [self._compute_margins(page) for page in pages]
        if not margins:
            return _PageMargins(left=72.0, right=72.0, top=72.0, bottom=72.0)

        # Prefer the tightest common content frame so soft-broken pages share one section
        # geometry without clipping dense STEM pages.
        return _PageMargins(
            left=min(item.left for item in margins),
            right=min(item.right for item in margins),
            top=min(item.top for item in margins),
            bottom=min(item.bottom for item in margins),
        )

    def apply_centered_page_number_footer(
        self,
        section,
        *,
        page_hint: int = 1,
        font_size_pt: float = 10.0,
        clear_header: bool = False,
    ) -> None:
        """Centered PAGE field for every page including page 1 (never hide first page)."""
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        section.header.is_linked_to_previous = False
        section.footer.is_linked_to_previous = False
        try:
            section.different_first_page_header_footer = False
        except Exception:
            pass
        if clear_header:
            section.header.paragraphs[0].text = ""
        footer = section.footer.paragraphs[0]
        footer.text = ""
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.paragraph_format.space_before = self._pt(0)
        footer.paragraph_format.space_after = self._pt(0)
        run = footer.add_run()
        try:
            run.font.name = "Times New Roman"
            run.font.size = self._pt(font_size_pt)
            # Soft gray so numbers stay quiet next to body text / page pictures.
            from docx.shared import RGBColor

            run.font.color.rgb = RGBColor(0x40, 0x40, 0x40)
        except Exception:
            pass
        fld_char_begin = OxmlElement("w:fldChar")
        fld_char_begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        instr.text = " PAGE "
        fld_char_separate = OxmlElement("w:fldChar")
        fld_char_separate.set(qn("w:fldCharType"), "separate")
        result = OxmlElement("w:t")
        result.text = str(max(1, int(page_hint)))
        fld_char_end = OxmlElement("w:fldChar")
        fld_char_end.set(qn("w:fldCharType"), "end")
        run._r.append(fld_char_begin)
        run._r.append(instr)
        run._r.append(fld_char_separate)
        run._r.append(result)
        run._r.append(fld_char_end)
        try:
            section.footer_distance = self._pt(18)
        except Exception:
            pass

    def _render_continuous_header_footer(self, section, pages: list[PageIR]) -> None:
        header_texts: list[str] = []
        for page in pages:
            for element in page.elements:
                if not element.header_footer or element.header_footer.kind != "header":
                    continue
                text = (element.header_footer.text or "").strip()
                if text and text not in header_texts:
                    header_texts.append(text)
        section.header.is_linked_to_previous = False
        section.header.paragraphs[0].text = " ".join(header_texts[:2])
        # Unified sequential page numbers for the whole document (including page 1).
        self.apply_centered_page_number_footer(section, page_hint=1, font_size_pt=10.0)

    def _tighten_default_styles(self, doc, point_factory) -> None:
        """Remove Word's generous default paragraph gaps so bbox spacing can dominate."""
        for style_name in ("Normal", "Heading 1", "Heading 2", "Heading 3"):
            try:
                style = doc.styles[style_name]
            except KeyError:
                continue
            fmt = style.paragraph_format
            fmt.space_before = point_factory(0)
            fmt.space_after = point_factory(0)
            fmt.line_spacing = 1.0

    def _compute_margins(self, page: PageIR) -> _PageMargins:
        body = [
            element
            for element in page.elements
            if element.page_region == "body" and element.type not in {"separator", "blank_space"}
        ]
        if not body:
            return _PageMargins(left=72.0, right=72.0, top=72.0, bottom=72.0)

        left = min(element.bbox.left for element in body) * page.width_pt
        right = (1.0 - max(element.bbox.right for element in body)) * page.width_pt
        top = min(element.bbox.top for element in body) * page.height_pt
        bottom = (1.0 - max(element.bbox.bottom for element in body)) * page.height_pt

        footer = [element for element in page.elements if element.type == "footer" or element.page_region == "footer"]
        if footer:
            footer_top = min(element.bbox.top for element in footer) * page.height_pt
            bottom = max(bottom, page.height_pt - footer_top)

        # Mild pull-in for glyph-width slack while staying close to the source frame.
        left = min(max(18.0, left * 0.94), page.width_pt * 0.30)
        right = min(max(18.0, right * 0.94), page.width_pt * 0.30)
        top = min(max(18.0, top * 0.92), page.height_pt * 0.22)
        bottom = min(max(22.0, bottom * 0.80), page.height_pt * 0.16)
        if left + right >= page.width_pt - 72:
            left = right = 48.0
        if top + bottom >= page.height_pt - 72:
            top = bottom = 48.0
        return _PageMargins(left=left, right=right, top=top, bottom=bottom)

    def _apply_section_geometry(self, section, page: PageIR, margins: _PageMargins, point_factory, twips_factory) -> None:
        from docx.oxml.ns import qn

        section.page_width = point_factory(page.width_pt)
        section.page_height = point_factory(page.height_pt)
        section.left_margin = point_factory(margins.left)
        section.right_margin = point_factory(margins.right)
        section.top_margin = point_factory(margins.top)
        section.bottom_margin = point_factory(margins.bottom)
        section.header_distance = point_factory(max(12.0, min(margins.top * 0.45, 36.0)))
        section.footer_distance = point_factory(max(12.0, min(margins.bottom * 0.45, 36.0)))
        # Explicit page size on sectPr for engines that ignore high-level props.
        sect_pr = section._sectPr
        pg_sz = sect_pr.find(qn("w:pgSz"))
        if pg_sz is not None:
            pg_sz.set(qn("w:w"), str(int(round(page.width_pt * 20))))
            pg_sz.set(qn("w:h"), str(int(round(page.height_pt * 20))))
        _ = twips_factory

    def _vertical_map(
        self,
        page: PageIR,
        margins: _PageMargins,
        pack: _PackProfile,
        *,
        multi_column: bool,
    ) -> _VerticalMap | None:
        body = [
            element
            for element in page.elements
            if element.page_region == "body" and element.type not in {"separator", "blank_space"}
        ]
        if not body:
            return None
        source_top = min(page.height_pt * element.bbox.top for element in body)
        source_bottom = max(page.height_pt * element.bbox.bottom for element in body)
        source_span = max(1.0, source_bottom - source_top)
        target_top = margins.top
        usable = max(120.0, page.height_pt - margins.top - margins.bottom)
        # Fill most of the content frame so soft page breaks do not leave a
        # giant empty band under sparse body blocks.
        dense = len(body) >= 28 or multi_column
        target_span = usable * (0.94 if dense else 0.97)
        if pack.font_scale < 0.90:
            target_span *= 0.97
        return _VerticalMap(
            source_top=source_top,
            source_span=source_span,
            target_top=target_top,
            target_span=target_span,
        )

    def _flow_geometry(
        self,
        page: PageIR,
        element: DocumentElement,
        prev_bottom_pt: float | None,
        margins: _PageMargins,
        pack: _PackProfile | None = None,
        *,
        multi_column: bool = False,
        column_changed: bool = False,
        vertical_map: _VerticalMap | None = None,
    ) -> _FlowGeometry:
        pack = pack or _PackProfile()
        top_pt = page.height_pt * element.bbox.top
        bottom_pt = page.height_pt * element.bbox.bottom
        left_pt = page.width_pt * element.bbox.left
        right_pt = page.width_pt * element.bbox.right

        if element.style.space_before_pt is not None:
            space_before = element.style.space_before_pt
        elif vertical_map is not None:
            target_top = vertical_map.map_y(top_pt)
            if prev_bottom_pt is None:
                space_before = max(0.0, target_top - margins.top)
            elif multi_column and column_changed:
                space_before = max(3.0, min(10.0, target_top - prev_bottom_pt))
            else:
                space_before = max(0.0, target_top - prev_bottom_pt)
        elif prev_bottom_pt is None:
            space_before = max(0.0, top_pt - margins.top)
            space_before = min(space_before, 36.0)
        elif multi_column and column_changed:
            space_before = 6.0 * max(0.35, pack.space_scale)
        else:
            space_before = max(0.0, top_pt - prev_bottom_pt)
            if space_before < 1.2:
                space_before = 0.0
            else:
                # Keep more of the source leading so academic pages stay open.
                space_before *= max(0.70, pack.space_scale)

        if element.type == "formula":
            space_before = min(space_before, 14.0)
        elif element.type == "heading":
            space_before = min(max(space_before, 6.0), 22.0)
        elif element.type == "image":
            space_before = min(max(space_before, 8.0), 28.0)
        space_before = min(space_before, 42.0)

        if multi_column:
            # Collapse multi-column gutters into full-measure single-column text.
            left_indent = 0.0
            right_indent = 0.0
        elif element.style.left_indent_pt is not None:
            left_indent = element.style.left_indent_pt
            right_indent = element.style.right_indent_pt or 0.0
        else:
            left_indent = max(0.0, left_pt - margins.left)
            right_indent = max(0.0, (page.width_pt - margins.right) - right_pt)
        # Large side indents shrink the measure and force extra wraps/pages.
        left_indent = min(left_indent, page.width_pt * 0.12)
        right_indent = min(right_indent, page.width_pt * 0.08)

        # Prefer slightly open AT_LEAST leading (negative pt convention) so text
        # does not look stacked/crowded relative to the academic PDF.
        font_size = (element.style.font_size_pt or 10.0) * pack.font_scale
        height_pt = max(0.0, bottom_pt - top_pt)
        if element.style.line_spacing is not None and element.style.line_spacing >= 1.0:
            line_spacing = -(font_size * min(1.28, max(1.08, element.style.line_spacing)))
        elif height_pt > 0 and font_size:
            estimated_lines = max(1.0, height_pt / max(font_size * 1.18, 1.0))
            if estimated_lines <= 1.4:
                line_spacing = -(font_size * 1.12)
            else:
                per_line = height_pt / estimated_lines
                line_spacing = -max(font_size * 1.08, min(font_size * 1.28, per_line * 1.02))
        else:
            line_spacing = -(font_size * 1.12)
        if element.type == "formula":
            line_spacing = -(font_size * 1.10)
        if element.type == "heading":
            line_spacing = -(font_size * 1.16)

        return _FlowGeometry(
            space_before_pt=space_before,
            left_indent_pt=left_indent if left_indent >= 1.0 else 0.0,
            right_indent_pt=right_indent if right_indent >= 1.0 else 0.0,
            line_spacing=line_spacing,
        )

    def _render_text_element(
        self,
        doc,
        element: DocumentElement,
        geometry: _FlowGeometry,
        alignment_enum,
        line_spacing_enum,
        point_factory,
        qn,
        pack: _PackProfile | None = None,
        *,
        page_break_before: bool = False,
        absolute_frame: bool = False,
        page: PageIR | None = None,
    ) -> None:
        pack = pack or _PackProfile()
        # Keep headings as Normal + bold runs. Heading styles still inflate metrics in LO/Word.
        paragraph = doc.add_paragraph()
        if page_break_before:
            paragraph.paragraph_format.page_break_before = True
        if absolute_frame and page is not None:
            self._apply_absolute_frame(paragraph, page, element, qn)
            # Frame owns geometry; suppress flow indents/gaps that fight absolute coords.
            geometry = _FlowGeometry(
                space_before_pt=0.0,
                left_indent_pt=0.0,
                right_indent_pt=0.0,
                line_spacing=geometry.line_spacing,
            )
        self._apply_paragraph_style(paragraph, element, geometry, alignment_enum, line_spacing_enum, point_factory)
        if element.type == "heading":
            self._set_outline_level(paragraph, 0, qn)
        # Near-source font size for framed layout (better MAD).
        font_scale = 1.0 if absolute_frame else pack.font_scale
        if element.runs:
            for index, run_payload in enumerate(element.runs):
                run = paragraph.add_run(run_payload.text)
                if run_payload.space_after and index < len(element.runs) - 1:
                    run.add_text(" ")
                self._apply_run_style(run, element, run_payload, point_factory, qn, font_scale)
        else:
            run = paragraph.add_run(element.text or "")
            self._apply_run_style(run, element, None, point_factory, qn, font_scale)

    def _apply_absolute_frame(self, paragraph, page: PageIR, element: DocumentElement, qn) -> None:
        """Absolute framing is intentionally disabled.

        Historical ``w:framePr`` anchors collapsed page counts under LibreOffice.
        Coordinate placement for non-flow layouts belongs in DrawingML
        (``FidelityDocxRenderer`` / ``positioned`` mode), not framePr.
        """
        return

    def _render_formula_fallback(
        self,
        doc,
        element: DocumentElement,
        geometry: _FlowGeometry,
        alignment_enum,
        line_spacing_enum,
        point_factory,
        qn,
        *,
        page_break_before: bool = False,
        absolute_frame: bool = False,
        page: PageIR | None = None,
    ) -> None:
        paragraph = doc.add_paragraph()
        if page_break_before:
            paragraph.paragraph_format.page_break_before = True
        if absolute_frame and page is not None:
            self._apply_absolute_frame(paragraph, page, element, qn)
            geometry = _FlowGeometry(0.0, 0.0, 0.0, geometry.line_spacing)
        self._apply_paragraph_style(paragraph, element, geometry, alignment_enum, line_spacing_enum, point_factory)
        payloads = list(element.runs)
        if not payloads:
            payloads = [None]
        for index, payload in enumerate(payloads):
            text = (
                payload.text
                if payload is not None
                else (element.formula.fallback_text if element.formula else element.text or "")
            )
            run = paragraph.add_run(text)
            if payload is None:
                run.italic = True
            self._apply_run_style(run, element, payload, point_factory, qn, 1.0 if absolute_frame else 0.96)
            if payload is not None and payload.space_after and index < len(payloads) - 1:
                run.add_text(" ")

    def _render_formula(
        self,
        doc,
        element: DocumentElement,
        geometry: _FlowGeometry,
        alignment_enum,
        line_spacing_enum,
        point_factory,
        qn,
        *,
        page_break_before: bool = False,
        absolute_frame: bool = False,
        page: PageIR | None = None,
    ) -> None:
        # Editable mode deliberately uses the extracted run stream. The
        # source crop is reserved for positioned/fidelity modes; inserting it
        # here would make the formula look right but turn it into a picture.
        # Prefer compact italic text in editable flow. OMML display math expands line
        # boxes and is a major source of page inflation on STEM pages.
        if (
            element.formula
            and element.formula.omml_xml
            and self._has_structured_omml(element.formula.omml_xml)
            and len(element.text or "") <= 24
            and not absolute_frame
        ):
            from docx.oxml import parse_xml

            paragraph = doc.add_paragraph()
            if page_break_before:
                paragraph.paragraph_format.page_break_before = True
            self._apply_paragraph_style(paragraph, element, geometry, alignment_enum, line_spacing_enum, point_factory)
            try:
                paragraph._p.append(parse_xml(element.formula.omml_xml))
                fallback_text = (element.formula.fallback_text or element.text or "").strip()
                if fallback_text:
                    # Keep a searchable/copyable plain-text representation in
                    # the same paragraph without painting it twice.
                    fallback_run = paragraph.add_run(fallback_text)
                    fallback_run.font.hidden = True
                return
            except (ValueError, TypeError):
                pass
        self._render_formula_fallback(
            doc,
            element,
            geometry,
            alignment_enum,
            line_spacing_enum,
            point_factory,
            qn,
            page_break_before=page_break_before,
            absolute_frame=absolute_frame,
            page=page,
        )

    def _has_structured_omml(self, omml_xml: str | None) -> bool:
        """Allow only stable OMML objects into the compact flow layout."""
        if not omml_xml:
            return False
        return any(f"<m:{tag}" in omml_xml for tag in ("f", "sSup", "sSub", "sSubSup", "rad"))

    def _render_separator(
        self,
        doc,
        page,
        element: DocumentElement,
        geometry: _FlowGeometry,
        point_factory,
        oxml_element,
        qn,
        *,
        page_break_before: bool = False,
    ) -> None:
        if element.separator is None:
            return
        paragraph = doc.add_paragraph()
        if page_break_before:
            paragraph.paragraph_format.page_break_before = True
        paragraph.paragraph_format.space_before = point_factory(geometry.space_before_pt)
        paragraph.paragraph_format.space_after = point_factory(0)
        height_pt = max(1.0, page.height_pt * (element.bbox.bottom - element.bbox.top))
        paragraph.paragraph_format.line_spacing = point_factory(height_pt)
        if geometry.left_indent_pt:
            paragraph.paragraph_format.left_indent = point_factory(geometry.left_indent_pt)
        p_pr = paragraph._p.get_or_add_pPr()
        borders = p_pr.first_child_found_in("w:pBdr")
        if borders is None:
            borders = oxml_element("w:pBdr")
            p_pr.append(borders)
        orientation = element.separator.orientation
        edges = (
            ("bottom",)
            if orientation == "horizontal"
            else ("left",) if orientation == "vertical" else ("top", "right", "bottom", "left")
        )
        for edge in edges:
            border = borders.find(qn(f"w:{edge}"))
            if border is None:
                border = oxml_element(f"w:{edge}")
                borders.append(border)
            border.set(qn("w:val"), "single")
            border.set(qn("w:sz"), str(max(2, int(round(element.separator.stroke_width_pt * 8)))))
            border.set(qn("w:space"), "0")
            border.set(qn("w:color"), element.separator.stroke_color or "808080")
        if element.separator.fill_color:
            shading = oxml_element("w:shd")
            shading.set(qn("w:fill"), element.separator.fill_color)
            p_pr.append(shading)

    def _render_table(
        self,
        doc,
        page,
        element: DocumentElement,
        geometry: _FlowGeometry,
        table_alignment,
        cell_vertical_alignment,
        oxml_element,
        qn,
        point_factory,
        pack: _PackProfile | None = None,
    ) -> None:
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
        from docx.enum.table import WD_ROW_HEIGHT_RULE

        pack = pack or _PackProfile()
        if element.table is None or element.table.row_count == 0 or element.table.column_count == 0:
            return
        # Absorb vertical gap as a spacing paragraph before the table.
        if geometry.space_before_pt > 1.0:
            spacer = doc.add_paragraph()
            spacer.paragraph_format.space_before = point_factory(0)
            spacer.paragraph_format.space_after = point_factory(0)
            spacer.paragraph_format.line_spacing = point_factory(max(1.0, min(10.0, geometry.space_before_pt)))

        table = doc.add_table(rows=element.table.row_count, cols=element.table.column_count)
        table.alignment = table_alignment.LEFT
        table.autofit = False
        # Avoid "Table Grid" + invented cell borders (double lines / junk boxes on
        # Attention tables 2–3). Start borderless; apply only evidenced edges.
        try:
            table.style = "Table Normal"
        except KeyError:
            pass
        column_widths = self._table_column_widths(page, element)
        self._set_table_geometry(table, column_widths, element, page, geometry, oxml_element, qn)
        self._set_table_default_borders(table, element, oxml_element, qn)
        repeat_header_rows = min(element.table.row_count, element.table.repeat_header_row_count)
        for row_index, row in enumerate(table.rows):
            row_properties = row._tr.get_or_add_trPr()
            cant_split = oxml_element("w:cantSplit")
            row_properties.append(cant_split)
            if row_index < repeat_header_rows:
                header = oxml_element("w:tblHeader")
                header.set(qn("w:val"), "true")
                row_properties.append(header)
        raw_heights = list(element.table.row_heights_pt)
        if raw_heights:
            total_h = sum(raw_heights)
            max_table_h = max(160.0, page.height_pt * 0.48)
            height_scale = min(1.0, max_table_h / max(total_h, 1.0)) * max(0.88, pack.font_scale)
        else:
            height_scale = max(0.88, pack.font_scale)
        cell_font_scale = max(0.88, pack.font_scale * 0.96)
        cell_font_size = max(8.5, 10.0 * min(1.0, max(0.90, pack.font_scale)))
        occupied: set[tuple[int, int]] = set()
        for row_index, row_payload in enumerate(element.table.rows):
            for column_index in range(element.table.column_count):
                if (row_index, column_index) in occupied:
                    continue
                cell = table.cell(row_index, column_index)
                payload = row_payload[column_index] if column_index < len(row_payload) else None
                if payload is None:
                    continue
                if payload.row_span > 1 or payload.col_span > 1:
                    end_row = min(element.table.row_count - 1, row_index + payload.row_span - 1)
                    end_column = min(element.table.column_count - 1, column_index + payload.col_span - 1)
                    cell = cell.merge(table.cell(end_row, end_column))
                    for merge_row in range(row_index, end_row + 1):
                        for merge_column in range(column_index, end_column + 1):
                            if (merge_row, merge_column) != (row_index, column_index):
                                occupied.add((merge_row, merge_column))
                cell.vertical_alignment = {
                    "top": cell_vertical_alignment.TOP,
                    "center": cell_vertical_alignment.CENTER,
                    "bottom": cell_vertical_alignment.BOTTOM,
                }[payload.vertical_alignment]
                cell.width = point_factory(column_widths[column_index])
                cell.text = ""
                paragraph = cell.paragraphs[0]
                paragraph.alignment = {
                    "left": WD_ALIGN_PARAGRAPH.LEFT,
                    "center": WD_ALIGN_PARAGRAPH.CENTER,
                    "right": WD_ALIGN_PARAGRAPH.RIGHT,
                }[payload.alignment]
                paragraph.paragraph_format.space_before = point_factory(0)
                paragraph.paragraph_format.space_after = point_factory(0)
                paragraph.paragraph_format.line_spacing = point_factory(max(8.0, cell_font_size * 1.02))
                paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
                run = paragraph.add_run(payload.text)
                self._apply_run_style(run, element, None, point_factory, qn, cell_font_scale)
                run.font.size = point_factory(cell_font_size)
                self._set_cell_borders(cell, payload, oxml_element, qn)
                self._set_cell_margins(cell, oxml_element, qn, compact=False)
            if row_index < len(raw_heights):
                row = table.rows[row_index]
                row.height = point_factory(max(8.0, raw_heights[row_index] * height_scale))
                # Multiline PDF cells need room for every preserved source line.
                # An exact row height clips those lines in LibreOffice/Word.
                row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST

    def _table_column_widths(self, page, element: DocumentElement) -> list[float]:
        assert element.table is not None
        widths = list(element.table.column_widths_pt)
        table_width = page.width_pt * max(0.0, element.bbox.right - element.bbox.left)
        if len(widths) != element.table.column_count or sum(widths) <= 0:
            return [table_width / element.table.column_count] * element.table.column_count
        scale = table_width / sum(widths) if table_width > 0 else 1.0
        return [max(1.0, width * scale) for width in widths]

    def _set_table_geometry(self, table, column_widths, element, page, geometry: _FlowGeometry, oxml_element, qn) -> None:
        tbl_pr = table._tbl.tblPr
        tbl_width = int(round(sum(column_widths) * 20))
        tbl_w = tbl_pr.first_child_found_in("w:tblW")
        if tbl_w is None:
            tbl_w = oxml_element("w:tblW")
            tbl_pr.append(tbl_w)
        tbl_w.set(qn("w:type"), "dxa")
        tbl_w.set(qn("w:w"), str(tbl_width))
        if geometry.left_indent_pt > 0:
            tbl_ind = tbl_pr.first_child_found_in("w:tblInd")
            if tbl_ind is None:
                tbl_ind = oxml_element("w:tblInd")
                tbl_pr.append(tbl_ind)
            tbl_ind.set(qn("w:w"), str(int(round(geometry.left_indent_pt * 20))))
            tbl_ind.set(qn("w:type"), "dxa")
        layout = tbl_pr.first_child_found_in("w:tblLayout")
        if layout is None:
            layout = oxml_element("w:tblLayout")
            tbl_pr.append(layout)
        layout.set(qn("w:type"), "fixed")
        grid = table._tbl.tblGrid
        for child in list(grid):
            grid.remove(child)
        for width in column_widths:
            grid_column = oxml_element("w:gridCol")
            grid_column.set(qn("w:w"), str(int(round(width * 20))))
            grid.append(grid_column)
        for row in table.rows:
            for index, cell in enumerate(row.cells):
                if index >= len(column_widths):
                    continue
                tc_pr = cell._tc.get_or_add_tcPr()
                tc_w = tc_pr.first_child_found_in("w:tcW")
                if tc_w is None:
                    tc_w = oxml_element("w:tcW")
                    tc_pr.append(tc_w)
                tc_w.set(qn("w:type"), "dxa")
                tc_w.set(qn("w:w"), str(int(round(column_widths[index] * 20))))

    def _set_table_default_borders(self, table, element: DocumentElement, oxml_element, qn) -> None:
        """Apply a single clean grid from table-level borders (no junk boxes)."""
        if element.table is None:
            return
        # Count evidenced edges; if sparse, still draw a light full grid for STEM tables.
        evidenced = 0
        total = 0
        for row in element.table.rows:
            for cell in row:
                if cell is None:
                    continue
                for edge in (cell.top_border, cell.right_border, cell.bottom_border, cell.left_border):
                    total += 1
                    if edge is not None:
                        evidenced += 1
        density = evidenced / max(total, 1)
        # Always prefer one tblBorders definition over per-cell invented singles.
        tbl_pr = table._tbl.tblPr
        borders = tbl_pr.first_child_found_in("w:tblBorders")
        if borders is None:
            borders = oxml_element("w:tblBorders")
            tbl_pr.append(borders)
        # Attention-style tables: light gray grid matching paper rules.
        sz = "8" if density >= 0.35 else "6"
        color = "404040" if density >= 0.35 else "606060"
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            edge_element = borders.find(qn(f"w:{edge}"))
            if edge_element is None:
                edge_element = oxml_element(f"w:{edge}")
                borders.append(edge_element)
            edge_element.set(qn("w:val"), "single")
            edge_element.set(qn("w:sz"), sz)
            edge_element.set(qn("w:space"), "0")
            edge_element.set(qn("w:color"), color)

    def _set_cell_borders(self, cell, payload, oxml_element, qn) -> None:
        """Only override edges that have explicit IR evidence; never invent singles."""
        border_values = {
            "top": payload.top_border,
            "right": payload.right_border,
            "bottom": payload.bottom_border,
            "left": payload.left_border,
        }
        if all(border is None for border in border_values.values()):
            return
        tc_pr = cell._tc.get_or_add_tcPr()
        borders = tc_pr.first_child_found_in("w:tcBorders")
        if borders is None:
            borders = oxml_element("w:tcBorders")
            tc_pr.append(borders)
        for edge, border in border_values.items():
            if border is None:
                continue
            edge_element = borders.find(qn(f"w:{edge}"))
            if edge_element is None:
                edge_element = oxml_element(f"w:{edge}")
                borders.append(edge_element)
            edge_element.set(qn("w:val"), border.val if border.val != "nil" else "single")
            edge_element.set(qn("w:sz"), str(max(4, int(round(border.width_pt * 8)))))
            edge_element.set(qn("w:space"), "0")
            edge_element.set(qn("w:color"), border.color or "404040")

    def _set_cell_margins(self, cell, oxml_element, qn, *, compact: bool = False) -> None:
        tc_pr = cell._tc.get_or_add_tcPr()
        margins = tc_pr.first_child_found_in("w:tcMar")
        if margins is None:
            margins = oxml_element("w:tcMar")
            tc_pr.append(margins)
        # Compact STEM tables use near-zero cell padding to reclaim vertical space.
        pad_tb = "20" if compact else "40"
        pad_lr = "30" if compact else "60"
        for edge in ("top", "left", "bottom", "right"):
            margin = margins.find(qn(f"w:{edge}"))
            if margin is None:
                margin = oxml_element(f"w:{edge}")
                margins.append(margin)
            margin.set(qn("w:w"), pad_tb if edge in {"top", "bottom"} else pad_lr)
            margin.set(qn("w:type"), "dxa")

    def _render_image_pair(
        self,
        doc,
        page: PageIR,
        left: DocumentElement,
        right: DocumentElement,
        geometry: _FlowGeometry,
        margins: _PageMargins,
        point_factory,
        pack: _PackProfile | None = None,
        *,
        page_break_before: bool = False,
    ) -> None:
        """Place two horizontally adjacent figures in one borderless 1×2 table."""
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        pack = pack or _PackProfile()
        # Order left-to-right by source X.
        a, b = (left, right) if left.bbox.left <= right.bbox.left else (right, left)
        paths: list[Path] = []
        for element in (a, b):
            path = self._materialize_image(element)
            if not path or not path.exists():
                raise RuntimeError(f"Image element {element.id} has no materialized source")
            paths.append(path)
        content_width = page.width_pt - margins.left - margins.right
        max_h = max(64.0, (page.height_pt - margins.top - margins.bottom) * pack.image_max_height_frac)
        cell_w = content_width * 0.46
        sizes: list[tuple[float, float]] = []
        for element, _path in zip((a, b), paths):
            assert element.image is not None
            w = min(element.image.width_pt, cell_w)
            h = element.image.height_pt
            if element.image.width_pt > 0 and w < element.image.width_pt:
                h *= w / element.image.width_pt
            if h > max_h and h > 0:
                scale = max_h / h
                h = max_h
                w *= scale
            sizes.append((w, h))
        # Match heights for a tidy pair.
        target_h = min(sizes[0][1], sizes[1][1])
        final_sizes: list[tuple[float, float]] = []
        for (w, h), element in zip(sizes, (a, b)):
            if h > 0 and abs(h - target_h) > 0.5:
                w *= target_h / h
                h = target_h
            final_sizes.append((w, h))

        if page_break_before:
            breaker = doc.add_paragraph()
            breaker.paragraph_format.page_break_before = True
            breaker.paragraph_format.space_before = point_factory(0)
            breaker.paragraph_format.space_after = point_factory(0)
        # One centered paragraph with two pictures side-by-side (no extra Word table,
        # which would pollute validation and look like a junk 1×2 grid).
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = point_factory(
            max(6.0, min(geometry.space_before_pt, 16.0))
        )
        paragraph.paragraph_format.space_after = point_factory(8.0)
        for index, ((w, h), path) in enumerate(zip(final_sizes, paths)):
            run = paragraph.add_run()
            run.add_picture(str(path), width=point_factory(w), height=point_factory(h))
            if index == 0:
                # Thin spacer between the pair.
                gap = paragraph.add_run("  ")

    def _render_image(
        self,
        doc,
        page,
        element: DocumentElement,
        geometry: _FlowGeometry,
        margins: _PageMargins,
        point_factory,
        pack: _PackProfile | None = None,
        *,
        page_break_before: bool = False,
        absolute_frame: bool = False,
    ) -> None:
        pack = pack or _PackProfile()
        if element.image is None:
            return
        image_path = self._materialize_image(element)
        if not image_path or not image_path.exists():
            raise RuntimeError(f"Image element {element.id} has no materialized source")
        if absolute_frame:
            width_pt = max(24.0, page.width_pt * (element.bbox.right - element.bbox.left))
            height_pt = max(24.0, page.height_pt * (element.bbox.bottom - element.bbox.top))
        else:
            from docx.enum.text import WD_ALIGN_PARAGRAPH

            content_width = page.width_pt - margins.left - margins.right
            max_height = max(
                72.0,
                (page.height_pt - margins.top - margins.bottom - 36.0) * pack.image_max_height_frac,
            )
            # Keep figures on a common centered measure (fixes page-4 stacked diagrams).
            target_width = min(element.image.width_pt, max(120.0, content_width * 0.88))
            width_pt = target_width
            height_pt = element.image.height_pt
            if element.image.width_pt > 0 and width_pt < element.image.width_pt:
                height_pt = element.image.height_pt * (width_pt / element.image.width_pt)
            if height_pt > max_height and height_pt > 0:
                scale = max_height / height_pt
                height_pt = max_height
                width_pt *= scale
        paragraph = doc.add_paragraph()
        if page_break_before:
            paragraph.paragraph_format.page_break_before = True
        if absolute_frame:
            from docx.oxml.ns import qn as _qn

            self._apply_absolute_frame(paragraph, page, element, _qn)
            paragraph.paragraph_format.space_before = point_factory(0)
            paragraph.paragraph_format.space_after = point_factory(0)
        else:
            from docx.enum.text import WD_ALIGN_PARAGRAPH

            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = point_factory(
                max(6.0, min(geometry.space_before_pt, 18.0))
            )
            paragraph.paragraph_format.space_after = point_factory(8.0)
            paragraph.paragraph_format.left_indent = point_factory(0)
            paragraph.paragraph_format.right_indent = point_factory(0)
        run = paragraph.add_run()
        run.add_picture(str(image_path), width=point_factory(width_pt), height=point_factory(height_pt))

    def _render_page_header_footer(self, section, page) -> None:
        header_texts = [
            element.header_footer.text
            for element in page.elements
            if element.header_footer and element.header_footer.kind == "header"
        ]
        section.header.is_linked_to_previous = False
        section.header.paragraphs[0].text = " ".join(dict.fromkeys(header_texts))
        for paragraph in section.header.paragraphs:
            paragraph.paragraph_format.space_before = self._pt(0)
            paragraph.paragraph_format.space_after = self._pt(0)
        # Prefer live PAGE field over static PDF footer digits so numbering is
        # sequential and page 1 is never blank.
        self.apply_centered_page_number_footer(
            section,
            page_hint=getattr(page, "page_number", 1) or 1,
            font_size_pt=10.0,
        )

    def _apply_paragraph_style(
        self,
        paragraph,
        element: DocumentElement,
        geometry: _FlowGeometry,
        alignment_enum,
        line_spacing_enum,
        point_factory,
    ) -> None:
        alignment = element.style.alignment
        if alignment == "center":
            paragraph.alignment = alignment_enum.CENTER
        elif alignment == "right":
            paragraph.alignment = alignment_enum.RIGHT
        elif alignment == "justify":
            paragraph.alignment = alignment_enum.JUSTIFY
        else:
            paragraph.alignment = alignment_enum.LEFT
        paragraph_format = paragraph.paragraph_format
        space_before = (
            element.style.space_before_pt
            if element.style.space_before_pt is not None
            else geometry.space_before_pt
        )
        space_after = element.style.space_after_pt if element.style.space_after_pt is not None else 0.0
        paragraph_format.space_before = point_factory(max(0.0, space_before))
        paragraph_format.space_after = point_factory(max(0.0, space_after))
        # Negative line_spacing means leading in points (see _flow_geometry).
        # AT_LEAST avoids clipping and reduces stacked/cramped look vs EXACTLY.
        if geometry.line_spacing is not None and geometry.line_spacing < 0:
            paragraph_format.line_spacing = point_factory(abs(geometry.line_spacing))
            paragraph_format.line_spacing_rule = line_spacing_enum.AT_LEAST
        elif geometry.line_spacing is not None:
            paragraph_format.line_spacing = geometry.line_spacing
            paragraph_format.line_spacing_rule = line_spacing_enum.MULTIPLE
        elif element.style.line_spacing:
            paragraph_format.line_spacing = element.style.line_spacing
            paragraph_format.line_spacing_rule = line_spacing_enum.MULTIPLE
        else:
            font_size = element.style.font_size_pt or 10.0
            paragraph_format.line_spacing = point_factory(font_size * 1.2)
            paragraph_format.line_spacing_rule = line_spacing_enum.AT_LEAST
        if element.style.first_line_indent_pt is not None:
            paragraph_format.first_line_indent = point_factory(element.style.first_line_indent_pt)
        left_indent = (
            element.style.left_indent_pt if element.style.left_indent_pt is not None else geometry.left_indent_pt
        )
        right_indent = (
            element.style.right_indent_pt if element.style.right_indent_pt is not None else geometry.right_indent_pt
        )
        if left_indent:
            paragraph_format.left_indent = point_factory(left_indent)
        if right_indent:
            paragraph_format.right_indent = point_factory(right_indent)

    def _set_outline_level(self, paragraph, level: int, qn) -> None:
        p_pr = paragraph._p.get_or_add_pPr()
        outline = p_pr.first_child_found_in("w:outlineLvl")
        if outline is None:
            from docx.oxml import OxmlElement

            outline = OxmlElement("w:outlineLvl")
            p_pr.append(outline)
        outline.set(qn("w:val"), str(level))

    def _apply_run_style(
        self,
        run,
        element: DocumentElement,
        run_payload,
        point_factory,
        qn,
        font_scale: float = 0.96,
    ) -> None:
        font_family = (run_payload.font_family if run_payload else None) or element.style.font_family
        font_size = (run_payload.font_size_pt if run_payload else None) or element.style.font_size_pt
        # Mild optical scale: prefer near-source size when pack allows it.
        if font_size:
            font_size = font_size * max(0.94, min(1.0, font_scale))
        # Normalize noisy PDF face names to a crisp desktop serif for body text.
        normalized = self._normalize_font_family(font_family)
        if normalized:
            font_family = normalized
            run.font.name = font_family
            rpr = run._element.get_or_add_rPr()
            rfonts = rpr.rFonts
            if rfonts is None:
                rfonts = rpr._add_rFonts()
            slots = (run_payload.font_slots if run_payload else None) or element.style.font_slots
            values = {
                "ascii": slots.ascii if slots and slots.ascii else font_family,
                "hAnsi": slots.hAnsi if slots and slots.hAnsi else font_family,
                "eastAsia": slots.eastAsia if slots and slots.eastAsia else font_family,
                "cs": slots.cs if slots and slots.cs else font_family,
            }
            # Prefer normalized desktop faces for latin slots (clearer on LO/Pages).
            for slot in ("ascii", "hAnsi", "cs"):
                values[slot] = font_family
            for slot, value in values.items():
                rfonts.set(qn(f"w:{slot}"), value)
        if font_size:
            run.font.size = point_factory(font_size)
        run.font.bold = (run_payload.bold if run_payload else False) or element.style.bold or element.type == "heading"
        run.font.italic = (run_payload.italic if run_payload else False) or element.style.italic
        if (run_payload.underline if run_payload else False) or element.style.underline:
            run.font.underline = True
        color = (run_payload.color if run_payload else None) or element.style.color
        if color:
            from docx.shared import RGBColor

            try:
                run.font.color.rgb = RGBColor.from_string(color)
            except ValueError:
                pass
        if run_payload:
            run.font.superscript = run_payload.superscript
            run.font.subscript = run_payload.subscript
        # Slight positive character spacing eases "字距太密" without exploding measure.
        if not (run_payload and (run_payload.superscript or run_payload.subscript)):
            from docx.oxml import OxmlElement

            r_pr = run._element.get_or_add_rPr()
            spacing = r_pr.find(qn("w:spacing"))
            if spacing is None:
                spacing = OxmlElement("w:spacing")
                r_pr.append(spacing)
            spacing.set(qn("w:val"), "8")  # 8 twips ≈ 0.4pt — ease crowding without wrap blow-up

    def _normalize_font_family(self, font_family: str | None) -> str | None:
        if not font_family:
            return "Times New Roman"
        key = font_family.lower().replace(" ", "")
        if any(token in key for token in ("times", "nimbusrom", "liberation serif", "stix", "cmr", "computer modern")):
            return "Times New Roman"
        if any(token in key for token in ("arial", "helvetica", "nimbus san", "liberation san", "dejavu")):
            return "Arial"
        if any(token in key for token in ("courier", "mono", "consolas")):
            return "Courier New"
        return font_family

    def _pt(self, value: float):
        from docx.shared import Pt

        return Pt(value)

    def _materialize_image(self, element: DocumentElement) -> Path | None:
        if element.image is None:
            return None
        if element.image.image_path:
            return Path(element.image.image_path)
        if element.image.base64_data:
            raw = base64.b64decode(element.image.base64_data)
            suffix = ".png"
            tmp = NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(raw)
            tmp.close()
            return Path(tmp.name)
        return None
