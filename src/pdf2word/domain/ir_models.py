from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ElementType = Literal[
    "heading",
    "paragraph",
    "list",
    "table",
    "image",
    "caption",
    "formula",
    "header",
    "footer",
    "page_number",
    "text_box",
    "separator",
    "blank_space",
]


class BoundingBox(BaseModel):
    """Normalized page coordinates in left, top, right, bottom order."""

    left: float = Field(ge=0.0, le=1.0)
    top: float = Field(ge=0.0, le=1.0)
    right: float = Field(ge=0.0, le=1.0)
    bottom: float = Field(ge=0.0, le=1.0)

    @field_validator("right")
    @classmethod
    def right_must_follow_left(cls, value: float, info: Any) -> float:
        left = info.data.get("left")
        if left is not None and value < left:
            raise ValueError("right must be greater than or equal to left")
        return value

    @field_validator("bottom")
    @classmethod
    def bottom_must_follow_top(cls, value: float, info: Any) -> float:
        top = info.data.get("top")
        if top is not None and value < top:
            raise ValueError("bottom must be greater than or equal to top")
        return value

    @classmethod
    def from_points(
        cls,
        x0: float,
        top: float,
        x1: float,
        bottom: float,
        page_width: float,
        page_height: float,
    ) -> "BoundingBox":
        if page_width <= 0 or page_height <= 0:
            raise ValueError("page dimensions must be positive")
        return cls(
            left=max(0.0, min(1.0, x0 / page_width)),
            top=max(0.0, min(1.0, top / page_height)),
            right=max(0.0, min(1.0, x1 / page_width)),
            bottom=max(0.0, min(1.0, bottom / page_height)),
        )

    def as_list(self) -> list[float]:
        return [self.left, self.top, self.right, self.bottom]


class FontSlots(BaseModel):
    """The four OOXML font slots Word uses for mixed-script text."""

    ascii: str | None = None
    hAnsi: str | None = None
    eastAsia: str | None = None
    cs: str | None = None


class ElementStyle(BaseModel):
    font_family: str | None = None
    font_slots: FontSlots | None = None
    font_size_pt: float | None = Field(default=None, gt=0)
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None
    alignment: Literal["left", "center", "right", "justify"] = "left"
    line_spacing: float | None = Field(default=None, gt=0)
    space_before_pt: float | None = Field(default=None, ge=0)
    space_after_pt: float | None = Field(default=None, ge=0)
    first_line_indent_pt: float | None = None
    left_indent_pt: float | None = Field(default=None, ge=0)
    right_indent_pt: float | None = Field(default=None, ge=0)


class TextRun(BaseModel):
    text: str
    line_break_before: bool = False
    # Preserve the source word gap instead of making renderers guess one.
    space_after: bool = True
    font_family: str | None = None
    source_font_family: str | None = None
    font_slots: FontSlots | None = None
    font_size_pt: float | None = Field(default=None, gt=0)
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None
    superscript: bool = False
    subscript: bool = False


class BorderStyle(BaseModel):
    val: Literal["none", "single", "dashed", "dotted", "double", "thick"] = "single"
    width_pt: float = Field(default=0.5, ge=0)
    color: str | None = None


class TableCellPayload(BaseModel):
    text: str = ""
    bbox: BoundingBox | None = None
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    alignment: Literal["left", "center", "right"] = "left"
    vertical_alignment: Literal["top", "center", "bottom"] = "center"
    top_border: BorderStyle | None = None
    right_border: BorderStyle | None = None
    bottom_border: BorderStyle | None = None
    left_border: BorderStyle | None = None


class TablePayload(BaseModel):
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    rows: list[list[TableCellPayload | None]] = Field(default_factory=list)
    repeat_header_row_count: int = Field(default=1, ge=0)
    has_borders: bool = True
    column_widths_pt: list[float] = Field(default_factory=list)
    row_heights_pt: list[float] = Field(default_factory=list)


class ImagePayload(BaseModel):
    image_path: str | None = None
    base64_data: str | None = None
    width_pt: float = Field(gt=0)
    height_pt: float = Field(gt=0)
    wrap: Literal["inline", "floating"] = "inline"
    rotation_deg: float = 0.0
    source_width_px: int | None = Field(default=None, ge=1)
    source_height_px: int | None = Field(default=None, ge=1)
    z_index: int = 0


class FormulaPayload(BaseModel):
    latex: str | None = None
    image_path: str | None = None
    fallback_text: str | None = None
    source_type: Literal["vector", "raster", "unknown"] = "unknown"
    omml_xml: str | None = None


class SeparatorPayload(BaseModel):
    """Raw PDF line/rectangle evidence retained for layout rendering."""

    orientation: Literal["horizontal", "vertical", "rectangle"]
    stroke_width_pt: float = Field(default=0.5, ge=0)
    stroke_color: str | None = None
    fill_color: str | None = None


class HeaderFooterPayload(BaseModel):
    kind: Literal["header", "footer"]
    text: str
    page_number_format: str | None = None


class Confidence(BaseModel):
    text: float = Field(default=1.0, ge=0.0, le=1.0)
    role: float = Field(default=0.6, ge=0.0, le=1.0)
    geometry: float = Field(default=0.8, ge=0.0, le=1.0)


class Provenance(BaseModel):
    parser: str
    source_page: int = Field(ge=1)
    source: str | None = None


class DocumentElement(BaseModel):
    id: str
    type: ElementType
    text: str | None = None
    runs: list[TextRun] = Field(default_factory=list)
    role: str | None = None
    page_region: Literal["header", "body", "footer"] = "body"
    bbox: BoundingBox
    # Optional per-source-line boxes (normalized) for positioned DrawingML paint.
    line_bboxes: list[BoundingBox] = Field(default_factory=list)
    reading_order: int = Field(ge=1)
    style: ElementStyle = Field(default_factory=ElementStyle)
    table: TablePayload | None = None
    image: ImagePayload | None = None
    formula: FormulaPayload | None = None
    separator: SeparatorPayload | None = None
    header_footer: HeaderFooterPayload | None = None
    confidence: Confidence = Field(default_factory=Confidence)
    provenance: Provenance


class PageIR(BaseModel):
    id: str
    page_number: int = Field(ge=1)
    width_pt: float = Field(gt=0)
    height_pt: float = Field(gt=0)
    background_image_path: str | None = None
    elements: list[DocumentElement] = Field(default_factory=list)

    def ordered_elements(self) -> list[DocumentElement]:
        return sorted(self.elements, key=lambda item: item.reading_order)


class DocumentMeta(BaseModel):
    page_count: int = Field(ge=0)
    language: list[str] = Field(default_factory=list)
    document_type: str = "unknown"


class DocumentIR(BaseModel):
    schema_version: str = "1.5"
    document: DocumentMeta
    pages: list[PageIR] = Field(default_factory=list)

    def text_content(self) -> str:
        chunks: list[str] = []
        for page in self.pages:
            for element in page.ordered_elements():
                if element.text:
                    chunks.append(element.text)
        return "\n".join(chunks)
