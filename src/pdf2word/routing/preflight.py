from __future__ import annotations

from dataclasses import dataclass
import re

from pdf2word.pdf_backends import PdfBackend


@dataclass(frozen=True)
class PagePreflight:
    page_no: int
    has_text_layer: bool
    word_count: int
    layout_complexity: str
    image_coverage: float = 0.0
    table_count: int = 0
    line_count: int = 0
    rect_count: int = 0
    formula_like_count: int = 0
    column_count: int = 1
    has_header: bool = False
    has_footer: bool = False
    header_word_count: int = 0
    footer_word_count: int = 0
    page_number_like: bool = False
    signals: tuple[str, ...] = ()


class PreflightAnalyzer:
    def analyze_pages(self, backend: PdfBackend, pages: list[int]) -> list[PagePreflight]:
        results: list[PagePreflight] = []
        for page_no in pages:
            width, height = backend.page_size(page_no)
            words = backend.extract_text_objects(page_no)
            images = backend.extract_images(page_no)
            tables = backend.extract_tables(page_no)
            lines = backend.extract_lines(page_no)
            rects = backend.extract_rects(page_no)
            word_count = len(words)
            header_words = [word for word in words if word.bottom <= height * 0.10]
            footer_words = [word for word in words if word.top >= height * 0.92]
            image_coverage = self._image_coverage(images, width, height)
            formula_like_count = self._formula_like_count(words)
            column_count = self._estimate_column_count(words, width, height)
            signals = self._signals(
                image_coverage=image_coverage,
                table_count=len(tables),
                line_count=len(lines),
                rect_count=len(rects),
                formula_like_count=formula_like_count,
                column_count=column_count,
                has_header=bool(header_words),
                has_footer=bool(footer_words),
            )
            results.append(
                PagePreflight(
                    page_no=page_no,
                    has_text_layer=word_count > 0,
                    word_count=word_count,
                    layout_complexity=self._estimate_layout_complexity(words, images, tables, lines, rects),
                    image_coverage=image_coverage,
                    table_count=len(tables),
                    line_count=len(lines),
                    rect_count=len(rects),
                    formula_like_count=formula_like_count,
                    column_count=column_count,
                    has_header=bool(header_words),
                    has_footer=bool(footer_words),
                    header_word_count=len(header_words),
                    footer_word_count=len(footer_words),
                    page_number_like=self._page_number_like(footer_words),
                    signals=signals,
                )
            )
        return results

    def _estimate_layout_complexity(self, words, images, tables, lines, rects) -> str:
        if not words:
            return "unknown"
        line_keys = {round(word.top / 3) for word in words}
        density = len(words) / max(len(line_keys), 1)
        structure_score = len(tables) * 4 + len(images) * 2 + (len(lines) + len(rects)) / 20
        if len(line_keys) > 70 or density > 16 or structure_score >= 8:
            return "high"
        if len(line_keys) > 35 or density > 10 or structure_score >= 3:
            return "medium"
        return "low"

    def _image_coverage(self, images, page_width: float, page_height: float) -> float:
        page_area = page_width * page_height
        if page_area <= 0:
            return 0.0
        image_area = self._union_area(
            [
                (image.x0, image.top, image.x1, image.bottom)
                for image in images
                if image.x1 > image.x0 and image.bottom > image.top
            ]
        )
        return min(1.0, image_area / page_area)

    def _formula_like_count(self, words) -> int:
        marker_pattern = re.compile(r"(?:=|<=|>=|!=|\\[A-Za-z]+|[∑∫√≤≥≠→αβγλ]|[A-Za-z][_^][A-Za-z0-9])")
        return sum(1 for word in words if marker_pattern.search(word.text))

    def _estimate_column_count(self, words, page_width: float, page_height: float) -> int:
        body_words = [word for word in words if page_height * 0.10 < word.top and word.bottom < page_height * 0.90]
        if len(body_words) < 24 or page_width <= 0:
            return 1
        centers = sorted((word.x0 + word.x1) / 2 for word in body_words)
        gaps = [right - left for left, right in zip(centers, centers[1:])]
        split_points = [index for index, gap in enumerate(gaps) if gap >= page_width * 0.08]
        if not split_points:
            return 1

        clusters: list[list[float]] = []
        start = 0
        for split_index in split_points:
            cluster = centers[start : split_index + 1]
            if len(cluster) >= max(8, len(centers) * 0.12):
                clusters.append(cluster)
                start = split_index + 1
        tail = centers[start:]
        if len(tail) >= max(8, len(centers) * 0.12):
            clusters.append(tail)
        return min(3, max(1, len(clusters)))

    def _page_number_like(self, footer_words) -> bool:
        text = " ".join(word.text for word in footer_words).strip()
        if not text:
            return False
        return bool(re.fullmatch(r"(?:page\s*)?\d+(?:\s*(?:/|of)\s*\d+)?", text, flags=re.IGNORECASE))

    def _signals(
        self,
        *,
        image_coverage: float,
        table_count: int,
        line_count: int,
        rect_count: int,
        formula_like_count: int,
        column_count: int,
        has_header: bool,
        has_footer: bool,
    ) -> tuple[str, ...]:
        signals: list[str] = []
        if image_coverage >= 0.25:
            signals.append("image-heavy")
        if table_count or line_count + rect_count >= 12:
            signals.append("table-or-rules")
        if formula_like_count >= 3:
            signals.append("formula-like")
        if column_count > 1:
            signals.append(f"{column_count}-column")
        if has_header:
            signals.append("header")
        if has_footer:
            signals.append("footer")
        return tuple(signals)

    def _union_area(self, boxes: list[tuple[float, float, float, float]]) -> float:
        if not boxes:
            return 0.0
        x_edges = sorted({edge for box in boxes for edge in (box[0], box[2])})
        area = 0.0
        for left, right in zip(x_edges, x_edges[1:]):
            if right <= left:
                continue
            intervals = sorted(
                (box[1], box[3])
                for box in boxes
                if box[0] < right and box[2] > left
            )
            covered_height = 0.0
            current_top = current_bottom = None
            for top, bottom in intervals:
                if current_top is None:
                    current_top, current_bottom = top, bottom
                elif top <= current_bottom:
                    current_bottom = max(current_bottom, bottom)
                else:
                    covered_height += current_bottom - current_top
                    current_top, current_bottom = top, bottom
            if current_top is not None:
                covered_height += current_bottom - current_top
            area += (right - left) * covered_height
        return area
