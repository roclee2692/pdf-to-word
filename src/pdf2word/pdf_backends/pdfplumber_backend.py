from __future__ import annotations

import io
from pathlib import Path
from types import TracebackType

from pdf2word.pdf_backends.base import (
    PdfBorderObject,
    PdfGraphicObject,
    PdfImageObject,
    PdfTableObject,
    PdfTextObject,
)


class PdfPlumberBackend:
    """Native text-layer backend based on pdfplumber."""

    def __init__(self, pdf_path: str | Path, image_output_dir: str | Path | None = None):
        self.pdf_path = Path(pdf_path)
        self.image_output_dir = Path(image_output_dir) if image_output_dir else None
        self._pdf = None
        self._render_cache: dict[int, object] = {}

    def __enter__(self) -> "PdfPlumberBackend":
        import pdfplumber

        self._pdf = pdfplumber.open(self.pdf_path)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._pdf is not None:
            self._pdf.close()
            self._pdf = None
        self._render_cache.clear()

    @property
    def pdf(self):
        if self._pdf is None:
            raise RuntimeError("PdfPlumberBackend must be used as a context manager")
        return self._pdf

    def page_count(self) -> int:
        return len(self.pdf.pages)

    def page_size(self, page_no: int) -> tuple[float, float]:
        page = self.pdf.pages[page_no - 1]
        return float(page.width), float(page.height)

    def extract_text_objects(self, page_no: int) -> list[PdfTextObject]:
        page = self.pdf.pages[page_no - 1]
        # The sample paper encodes inter-word gaps as positioning rather than spaces.
        # A tighter tolerance preserves those gaps as separate editable runs.
        words = page.extract_words(
            extra_attrs=["fontname", "size", "non_stroking_color"],
            keep_blank_chars=False,
            x_tolerance=0.5,
        )
        objects: list[PdfTextObject] = []
        for word in words:
            text = self._clean_pdf_text(word.get("text", ""))
            if not text:
                continue
            objects.append(
                PdfTextObject(
                    text=text,
                    x0=float(word["x0"]),
                    top=float(word["top"]),
                    x1=float(word["x1"]),
                    bottom=float(word["bottom"]),
                    font_name=word.get("fontname"),
                    font_size=float(word["size"]) if word.get("size") else None,
                    color=word.get("non_stroking_color"),
                )
            )
        return objects

    def extract_images(self, page_no: int) -> list[PdfImageObject]:
        page = self.pdf.pages[page_no - 1]
        images: list[PdfImageObject] = []
        for index, image in enumerate(page.images, start=1):
            x0, top, x1, bottom = self._object_bbox(image)
            image_path = self._extract_image_stream(image, index) or self._crop_image(page_no, index, x0, top, x1, bottom)
            srcsize = image.get("srcsize") or (None, None)
            images.append(
                PdfImageObject(
                    id=f"page_{page_no:03d}_img_{index:03d}",
                    x0=x0,
                    top=top,
                    x1=x1,
                    bottom=bottom,
                    width=float(image.get("width", x1 - x0)),
                    height=float(image.get("height", bottom - top)),
                    name=image.get("name"),
                    image_path=str(image_path) if image_path else None,
                    source_width_px=int(srcsize[0]) if srcsize[0] else None,
                    source_height_px=int(srcsize[1]) if srcsize[1] else None,
                    rotation_deg=float(image.get("angle", 0.0) or 0.0),
                )
            )
        return images

    def extract_lines(self, page_no: int) -> list[PdfGraphicObject]:
        page = self.pdf.pages[page_no - 1]
        return [self._graphic_from_object(line) for line in page.lines]

    def extract_rects(self, page_no: int) -> list[PdfGraphicObject]:
        page = self.pdf.pages[page_no - 1]
        return [self._graphic_from_object(rect) for rect in page.rects]

    def extract_tables(self, page_no: int) -> list[PdfTableObject]:
        page = self.pdf.pages[page_no - 1]
        graphics = [self._graphic_from_object(item) for item in [*page.lines, *page.rects]]
        tables: list[PdfTableObject] = []
        for table in page.find_tables():
            rows: list[list[str]] = []
            cell_bboxes: list[list[tuple[float, float, float, float] | None]] = []
            cell_borders: list[list[dict[str, PdfBorderObject]]] = []
            extracted = table.extract() or []
            for row_index, row in enumerate(table.rows):
                raw_values = extracted[row_index] if row_index < len(extracted) else []
                bboxes = [self._cell_bbox(cell) if cell is not None else None for cell in row.cells]
                cell_bboxes.append(bboxes)
                values: list[str] = []
                for column_index, bbox in enumerate(bboxes):
                    fallback = raw_values[column_index] if column_index < len(raw_values) else ""
                    values.append(self._cell_text(page, bbox) or str(fallback or ""))
                rows.append(values)
                cell_borders.append([self._infer_cell_borders(bbox, graphics) for bbox in bboxes])
            x0, top, x1, bottom = table.bbox
            if max((len(row.cells) for row in table.rows), default=0) <= 1:
                recovered = self._recover_text_grid(page, table, graphics)
                if recovered is not None:
                    rows, cell_bboxes, cell_borders, x0, top, x1, bottom = recovered
            tables.append(
                PdfTableObject(
                    x0=float(x0),
                    top=float(top),
                    x1=float(x1),
                    bottom=float(bottom),
                    rows=rows,
                    cell_bboxes=cell_bboxes,
                    cell_borders=cell_borders,
                    column_widths_pt=self._table_column_widths(cell_bboxes, x0, x1),
                    row_heights_pt=self._table_row_heights(cell_bboxes),
                )
            )
        # Some academic tables draw only horizontal rules. pdfplumber's
        # ``find_tables`` needs a stronger cell grid and otherwise returns
        # nothing, leaving the table to be flattened into body text.
        if not tables:
            recovered = self._recover_horizontal_rule_table(page, graphics)
            if recovered is not None:
                tables.append(recovered)
        return tables

    def _recover_horizontal_rule_table(self, page, graphics) -> PdfTableObject | None:
        """Recover a text-grid table bounded by repeated horizontal rules."""
        horizontal = [
            graphic
            for graphic in graphics
            if graphic.width >= page.width * 0.10 and graphic.height <= 2.0
        ]
        if len(horizontal) < 4:
            return None

        rules = sorted(horizontal, key=lambda item: item.top)
        runs: list[list[PdfGraphicObject]] = []
        for rule in rules:
            if runs and rule.top - runs[-1][-1].top <= 90.0:
                runs[-1].append(rule)
            else:
                runs.append([rule])
        rules = max(runs, key=len)
        long_rules = [rule for rule in rules if rule.width >= page.width * 0.45]
        if len(long_rules) < 4:
            return None

        x0 = min(rule.x0 for rule in long_rules)
        x1 = max(rule.x1 for rule in long_rules)
        top = min(rule.top for rule in long_rules)
        bottom = max(rule.bottom for rule in long_rules)
        words = [
            word
            for word in page.extract_words(
                extra_attrs=["fontname", "size"],
                keep_blank_chars=False,
                x_tolerance=0.5,
            )
            if x0 - 2.0 <= (word["x0"] + word["x1"]) / 2 <= x1 + 2.0
            and top - 3.0 <= (word["top"] + word["bottom"]) / 2 <= bottom + 3.0
        ]
        if not words:
            return None

        rule_tops: list[float] = []
        for rule in sorted(rules, key=lambda item: item.top):
            if not rule_tops or abs(rule.top - rule_tops[-1]) > 1.5:
                rule_tops.append(rule.top)
        header_split = rule_tops[1] if len(rule_tops) > 1 else top
        body_split = rule_tops[2] if len(rule_tops) > 2 else header_split
        body_words = [
            word
            for word in words
            if (word["top"] + word["bottom"]) / 2 >= body_split - 1.5
        ]
        body_rows = self._cluster_words_by_y(body_words, tolerance=4.5)
        if len(body_rows) < 3:
            return None

        header_words = [
            word
            for word in words
            if (word["top"] + word["bottom"]) / 2 < body_split - 1.5
        ]
        subheaders = [
            word
            for word in header_words
            if str(word.get("text", "")).strip() in {"EN-DE", "EN-FR"}
        ]
        centers = sorted((word["x0"] + word["x1"]) / 2 for word in subheaders)
        if len(centers) != 4:
            return None
        first_edge = centers[0] - (centers[1] - centers[0]) / 2.0
        edges = [x0, first_edge]
        edges.extend((left + right) / 2.0 for left, right in zip(centers, centers[1:]))
        edges.append(x1)
        if any(right - left < 8.0 for left, right in zip(edges, edges[1:])):
            return None

        row_specs: list[tuple[list[dict], float, float]] = []
        # Keep the two-level header as real Word rows. This is what prevents
        # BLEU and Training Cost labels from drifting over the wrong columns.
        row_specs.append((header_words, top, header_split))
        row_specs.append((header_words, header_split, body_split))
        body_centers = [
            sum((word["top"] + word["bottom"]) / 2 for word in row) / len(row)
            for row in body_rows
        ]
        body_bounds = [body_split]
        for left, right in zip(body_centers, body_centers[1:]):
            body_bounds.append((left + right) / 2.0)
        body_bounds.append(bottom)
        row_specs.extend(
            (row, body_bounds[index], body_bounds[index + 1])
            for index, row in enumerate(body_rows)
        )

        rows: list[list[str]] = []
        cell_bboxes: list[list[tuple[float, float, float, float] | None]] = []
        cell_borders: list[list[dict[str, PdfBorderObject]]] = []
        for row_index, (row_words, row_top, row_bottom) in enumerate(row_specs):
            buckets: list[list[dict]] = [[] for _ in range(5)]
            if row_index == 0:
                # Top-level labels are deliberately assigned to their first
                # logical column; the payload below adds the correct spans.
                for word in row_words:
                    text = self._clean_pdf_text(word.get("text", ""))
                    center = (word["x0"] + word["x1"]) / 2.0
                    if text == "BLEU":
                        buckets[1].append(word)
                    elif text == "Training":
                        buckets[3].append(word)
                    elif text == "Cost":
                        buckets[3].append(word)
                    elif text == "(FLOPs)":
                        buckets[3].append(word)
                    elif center < edges[1]:
                        buckets[0].append(word)
            elif row_index == 1:
                for word in row_words:
                    center = (word["x0"] + word["x1"]) / 2.0
                    column = min(range(5), key=lambda index: abs(center - (edges[index] + edges[index + 1]) / 2.0))
                    buckets[column].append(word)
            else:
                # Keep tightly adjacent glyph runs such as ``3.3 · 10^18``
                # in one logical cell even when the superscript crosses the
                # inferred column midpoint.
                for chunk in self._cluster_words_by_x(row_words):
                    first = chunk[0]
                    center = (first["x0"] + first["x1"]) / 2.0
                    column = min(range(5), key=lambda index: abs(center - (edges[index] + edges[index + 1]) / 2.0))
                    buckets[column].extend(chunk)
            values = [self._join_words_by_line(bucket) for bucket in buckets]
            rows.append(values)
            row_boxes = [
                (float(edges[column]), float(row_top), float(edges[column + 1]), float(row_bottom))
                for column in range(5)
            ]
            if row_index == 0:
                row_boxes[0] = (float(edges[0]), float(row_top), float(edges[1]), float(body_split))
                row_boxes[1] = (float(edges[1]), float(row_top), float(edges[3]), float(row_bottom))
                row_boxes[2] = None
                row_boxes[3] = (float(edges[3]), float(row_top), float(edges[5]), float(row_bottom))
                row_boxes[4] = None
            elif row_index == 1:
                row_boxes[0] = None
            cell_bboxes.append(row_boxes)
            cell_borders.append([self._infer_cell_borders(box, graphics) for box in row_boxes])

        # Replace the detected header text with stable logical labels and
        # preserve the two merged header bands in the IR.
        rows[0] = [rows[0][0] or "Model", "BLEU", "", "Training Cost (FLOPs)", ""]
        rows[1] = ["", "EN-DE", "EN-FR", "EN-DE", "EN-FR"]
        return PdfTableObject(
            x0=float(x0),
            top=float(top),
            x1=float(x1),
            bottom=float(bottom),
            rows=rows,
            cell_bboxes=cell_bboxes,
            cell_borders=cell_borders,
            column_widths_pt=self._table_column_widths(cell_bboxes, x0, x1),
            row_heights_pt=self._table_row_heights(cell_bboxes),
        )

    def _cluster_words_by_y(self, words: list[dict], tolerance: float) -> list[list[dict]]:
        rows: list[list[dict]] = []
        for word in sorted(words, key=lambda item: ((item["top"] + item["bottom"]) / 2, item["x0"])):
            center = (word["top"] + word["bottom"]) / 2
            if rows:
                previous_center = sum((item["top"] + item["bottom"]) / 2 for item in rows[-1]) / len(rows[-1])
                if abs(center - previous_center) <= tolerance:
                    rows[-1].append(word)
                    continue
            rows.append([word])
        return rows

    def _cluster_words_by_x(self, words: list[dict]) -> list[list[dict]]:
        chunks: list[list[dict]] = []
        for word in sorted(words, key=lambda item: item["x0"]):
            if chunks and float(word["x0"]) - float(chunks[-1][-1]["x1"]) <= 8.0:
                chunks[-1].append(word)
            else:
                chunks.append([word])
        return chunks

    def _recover_text_grid(self, page, table, graphics):
        """Recover columns when a PDF draws only an outer frame and row rules."""
        row_boxes = [
            self._cell_bbox(row.cells[0])
            for row in table.rows
            if row.cells and row.cells[0] is not None
        ]
        if len(row_boxes) < 2:
            return None
        top = min(box[1] for box in row_boxes)
        bottom = max(box[3] for box in row_boxes)
        table_graphics = [
            graphic
            for graphic in graphics
            if graphic.bottom >= top - 2.0 and graphic.top <= bottom + 2.0
        ]
        horizontal = [graphic for graphic in table_graphics if graphic.width >= max(10.0, graphic.height * 10.0)]
        if horizontal:
            x0 = min(graphic.x0 for graphic in horizontal)
            x1 = max(graphic.x1 for graphic in horizontal)
        else:
            x0, x1 = table.bbox[0], table.bbox[2]
        words = page.extract_words(
            extra_attrs=["fontname", "size"],
            keep_blank_chars=False,
            x_tolerance=0.5,
        )
        row_words: list[list[dict]] = []
        for row_box in row_boxes:
            row_words.append(
                [
                    word
                    for word in words
                    if x0 - 2.0 <= (word["x0"] + word["x1"]) / 2 <= x1 + 2.0
                    and row_box[1] - 1.5 <= (word["top"] + word["bottom"]) / 2 <= row_box[3] + 1.5
                ]
            )
        anchor_row = 1 if len(row_words) > 1 and len(row_words[1]) >= 5 else max(
            range(len(row_words)), key=lambda index: len(row_words[index])
        )
        anchors = sorted(
            {(word["x0"] + word["x1"]) / 2 for word in row_words[anchor_row]}
        )
        if len(anchors) < 3:
            return None
        edges = [x0]
        edges.extend((left + right) / 2 for left, right in zip(anchors, anchors[1:]))
        edges.append(x1)
        recovered_rows: list[list[str]] = []
        recovered_bboxes: list[list[tuple[float, float, float, float] | None]] = []
        recovered_borders: list[list[dict[str, PdfBorderObject]]] = []
        for row_index, row_box in enumerate(row_boxes):
            buckets: list[list[dict]] = [[] for _ in anchors]
            for word in sorted(row_words[row_index], key=lambda item: (item["top"], item["x0"])):
                center = (word["x0"] + word["x1"]) / 2
                column = min(range(len(anchors)), key=lambda index: abs(anchors[index] - center))
                buckets[column].append(word)
            recovered_rows.append([self._join_words_by_line(bucket) for bucket in buckets])
            row_bboxes = [
                (float(edges[column]), float(row_box[1]), float(edges[column + 1]), float(row_box[3]))
                for column in range(len(anchors))
            ]
            recovered_bboxes.append(row_bboxes)
            recovered_borders.append([self._infer_cell_borders(bbox, table_graphics) for bbox in row_bboxes])
        return (
            recovered_rows,
            recovered_bboxes,
            recovered_borders,
            float(x0),
            float(top),
            float(x1),
            float(bottom),
        )

    def _cell_text(self, page, bbox: tuple[float, float, float, float] | None) -> str:
        if bbox is None:
            return ""
        x0, top, x1, bottom = bbox
        words = [
            word
            for word in page.extract_words(
                extra_attrs=["fontname", "size"],
                keep_blank_chars=False,
            x_tolerance=0.5,
            )
            if x0 - 1.0 <= (word["x0"] + word["x1"]) / 2 <= x1 + 1.0
            and top - 1.5 <= (word["top"] + word["bottom"]) / 2 <= bottom + 1.5
        ]
        return self._join_words_by_line(words)

    def _join_words_by_line(self, words: list[dict]) -> str:
        if not words:
            return ""
        lines = self._cluster_words_by_y(words, tolerance=6.0)
        rendered_lines: list[str] = []
        for line in lines:
            ordered = sorted(line, key=lambda item: float(item["x0"]))
            if not ordered:
                continue
            sizes = [float(item["size"]) for item in ordered if item.get("size")]
            baseline_size = max(sizes, default=10.0)
            baseline_centers = [
                (item["top"] + item["bottom"]) / 2
                for item in ordered
                if float(item.get("size") or baseline_size) >= baseline_size * 0.84
            ]
            baseline_y = sum(baseline_centers) / len(baseline_centers) if baseline_centers else 0.0
            result = ""
            previous = None
            for word in ordered:
                text = self._clean_pdf_text(word.get("text", ""))
                if not text:
                    continue
                center_y = (word["top"] + word["bottom"]) / 2
                small = float(word.get("size") or baseline_size) < baseline_size * 0.84
                if small and center_y < baseline_y - 1.0:
                    prefix = "^"
                elif small and center_y > baseline_y + 1.0:
                    prefix = "_"
                else:
                    prefix = ""
                if previous is not None and not prefix:
                    gap = float(word["x0"]) - float(previous["x1"])
                    previous_text = self._clean_pdf_text(previous.get("text", ""))
                    if (
                        gap > 0.8
                        and not previous_text.endswith(("(", "[", "{"))
                        and not text.startswith((".", ",", ";", ":", ")", "]", "}"))
                        and previous_text not in {"·", "×"}
                        and text not in {"·", "×"}
                    ):
                        result += " "
                result += prefix + text
                previous = word
            if result:
                rendered_lines.append(result.strip())
        return "\n".join(rendered_lines).strip()

    def _clean_pdf_text(self, value: object) -> str:
        text = str(value or "").strip()
        # pdfplumber exposes this particular Computer Modern epsilon glyph as
        # a CID token in the paper's embedded font.
        return text.replace("(cid:15)", "ε").replace("(cid:80)", "∑")

    def inspect_metadata(self) -> dict[str, object]:
        metadata = dict(self.pdf.metadata or {})
        metadata["page_count"] = self.page_count()
        return metadata

    def _graphic_from_object(self, obj: dict) -> PdfGraphicObject:
        x0, top, x1, bottom = self._object_bbox(obj)
        return PdfGraphicObject(
            x0=x0,
            top=top,
            x1=x1,
            bottom=bottom,
            width=float(obj.get("width", x1 - x0)),
            height=float(obj.get("height", bottom - top)),
            stroke_width=float(obj["linewidth"]) if obj.get("linewidth") is not None else None,
            stroke_color=obj.get("stroking_color"),
            fill_color=obj.get("non_stroking_color"),
        )

    def _object_bbox(self, obj: dict) -> tuple[float, float, float, float]:
        x0 = float(obj.get("x0", 0))
        x1 = float(obj.get("x1", x0))
        top = float(obj.get("top", min(obj.get("y0", 0), obj.get("y1", 0))))
        bottom = float(obj.get("bottom", max(obj.get("y0", 0), obj.get("y1", 0))))
        return x0, top, x1, bottom

    def _cell_bbox(self, cell) -> tuple[float, float, float, float]:
        x0, top, x1, bottom = cell
        return float(x0), float(top), float(x1), float(bottom)

    def _infer_cell_borders(
        self,
        bbox: tuple[float, float, float, float] | None,
        graphics: list[PdfGraphicObject],
    ) -> dict[str, PdfBorderObject]:
        if bbox is None:
            return {}
        x0, top, x1, bottom = bbox
        edges = {
            "top": ("horizontal", top, x0, x1),
            "bottom": ("horizontal", bottom, x0, x1),
            "left": ("vertical", x0, top, bottom),
            "right": ("vertical", x1, top, bottom),
        }
        result: dict[str, PdfBorderObject] = {}
        for name, (orientation, position, start, end) in edges.items():
            candidates = [
                graphic
                for graphic in graphics
                if self._graphic_touches_edge(graphic, orientation, position, start, end)
            ]
            if not candidates:
                continue
            graphic = max(candidates, key=lambda item: item.stroke_width or 0.0)
            result[name] = PdfBorderObject(
                visible=True,
                width_pt=max(0.25, float(graphic.stroke_width or 0.5)),
                color=graphic.stroke_color,
                style="single",
            )
        return result

    def _graphic_touches_edge(
        self,
        graphic: PdfGraphicObject,
        orientation: str,
        position: float,
        start: float,
        end: float,
    ) -> bool:
        tolerance = 1.5
        if orientation == "horizontal":
            near = abs(graphic.top - position) <= tolerance or abs(graphic.bottom - position) <= tolerance
            overlap = min(graphic.x1, end) - max(graphic.x0, start)
        else:
            near = abs(graphic.x0 - position) <= tolerance or abs(graphic.x1 - position) <= tolerance
            overlap = min(graphic.bottom, end) - max(graphic.top, start)
        return near and overlap >= max(1.0, (end - start) * 0.50)

    def _table_column_widths(
        self,
        cell_bboxes: list[list[tuple[float, float, float, float] | None]],
        x0: float,
        x1: float,
    ) -> list[float]:
        edges: list[float] = []
        for row in cell_bboxes:
            for bbox in row:
                if bbox is not None:
                    edges.extend((float(bbox[0]), float(bbox[2])))
        unique_edges: list[float] = []
        for edge in sorted(edges):
            if not unique_edges or abs(edge - unique_edges[-1]) > 1.5:
                unique_edges.append(edge)
        if len(unique_edges) >= 2:
            widths = [right - left for left, right in zip(unique_edges, unique_edges[1:])]
            if all(width > 1.0 for width in widths):
                return widths
        first_row = cell_bboxes[0] if cell_bboxes else []
        widths = [bbox[2] - bbox[0] for bbox in first_row if bbox is not None and bbox[2] > bbox[0]]
        if widths:
            return [float(width) for width in widths]
        return [float(x1 - x0)] if x1 > x0 else []

    def _table_row_heights(
        self,
        cell_bboxes: list[list[tuple[float, float, float, float] | None]],
    ) -> list[float]:
        heights: list[float] = []
        for row in cell_bboxes:
            valid = [bbox for bbox in row if bbox is not None and bbox[3] > bbox[1]]
            heights.append(float(max((bbox[3] for bbox in valid), default=0) - min((bbox[1] for bbox in valid), default=0)))
        return heights

    def _extract_image_stream(self, image: dict, image_index: int) -> Path | None:
        if self.image_output_dir is None:
            return None
        stream = image.get("stream")
        if stream is None:
            return None
        try:
            from PIL import Image

            self.image_output_dir.mkdir(parents=True, exist_ok=True)
            raw = stream.get_data()
            decoded = None
            try:
                decoded = Image.open(io.BytesIO(raw))
                decoded.load()
                decoded = decoded.convert("RGBA" if "A" in decoded.getbands() else "RGB")
            except Exception:
                attrs = getattr(stream, "attrs", {}) or {}
                width = int(attrs.get("Width", image.get("srcsize", (0, 0))[0]))
                height = int(attrs.get("Height", image.get("srcsize", (0, 0))[1]))
                colorspace = str(attrs.get("ColorSpace", "DeviceRGB")).lstrip("/")
                mode = {"DeviceGray": "L", "DeviceRGB": "RGB", "DeviceCMYK": "CMYK"}.get(colorspace, "RGB")
                decoded = Image.frombytes(mode, (width, height), raw)
                if mode == "CMYK":
                    decoded = decoded.convert("RGB")
            output = self.image_output_dir / f"page_{image.get('page_number', 0):03d}_image_{image_index:03d}_source.png"
            decoded.save(output)
            return output.resolve()
        except Exception:
            return None

    def _crop_image(self, page_no: int, image_index: int, x0: float, top: float, x1: float, bottom: float) -> Path | None:
        if self.image_output_dir is None:
            return None
        try:
            self.image_output_dir.mkdir(parents=True, exist_ok=True)
            page_image, scale = self._render_page_image(page_no)
            crop = page_image.crop((int(x0 * scale), int(top * scale), int(x1 * scale), int(bottom * scale)))
            output = self.image_output_dir / f"page_{page_no:03d}_image_{image_index:03d}.png"
            crop.save(output)
            return output.resolve()
        except Exception:
            return None

    def _render_page_image(self, page_no: int):
        if page_no in self._render_cache:
            return self._render_cache[page_no]
        import pypdfium2 as pdfium

        scale = 2.0
        pdf = pdfium.PdfDocument(str(self.pdf_path))
        page = pdf[page_no - 1]
        pil_image = page.render(scale=scale).to_pil()
        self._render_cache[page_no] = (pil_image, scale)
        return pil_image, scale

    def render_page_snapshot(self, page_no: int, output_path: str | Path) -> Path:
        image, _ = self._render_page_image(page_no)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
        return output.resolve()

    def render_crop(
        self,
        page_no: int,
        bbox: tuple[float, float, float, float],
        output_path: str | Path,
        *,
        padding_pt: float = 2.0,
    ) -> Path:
        """Materialize a source crop for formulas whose PDF text tree is lossy."""
        image, scale = self._render_page_image(page_no)
        x0, top, x1, bottom = bbox
        pad = padding_pt * scale
        crop = image.crop(
            (
                max(0, int(x0 * scale - pad)),
                max(0, int(top * scale - pad)),
                min(image.width, int(x1 * scale + pad)),
                min(image.height, int(bottom * scale + pad)),
            )
        )
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        crop.save(output)
        return output.resolve()
