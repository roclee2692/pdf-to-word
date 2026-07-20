from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PdfTextObject:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    font_name: str | None = None
    font_size: float | None = None
    color: object | None = None


@dataclass(frozen=True)
class PdfGraphicObject:
    x0: float
    top: float
    x1: float
    bottom: float
    width: float
    height: float
    stroke_width: float | None = None
    stroke_color: object | None = None
    fill_color: object | None = None


@dataclass(frozen=True)
class PdfBorderObject:
    visible: bool = True
    width_pt: float = 0.5
    color: object | None = None
    style: str = "single"


@dataclass(frozen=True)
class PdfImageObject:
    id: str
    x0: float
    top: float
    x1: float
    bottom: float
    width: float
    height: float
    name: str | None = None
    image_path: str | None = None
    source_width_px: int | None = None
    source_height_px: int | None = None
    rotation_deg: float = 0.0


@dataclass(frozen=True)
class PdfTableObject:
    x0: float
    top: float
    x1: float
    bottom: float
    rows: list[list[str]]
    cell_bboxes: list[list[tuple[float, float, float, float] | None]]
    cell_borders: list[list[dict[str, PdfBorderObject]]] | None = None
    column_widths_pt: list[float] | None = None
    row_heights_pt: list[float] | None = None


class PdfBackend(Protocol):
    def page_count(self) -> int:
        ...

    def page_size(self, page_no: int) -> tuple[float, float]:
        ...

    def extract_text_objects(self, page_no: int) -> list[PdfTextObject]:
        ...

    def extract_images(self, page_no: int) -> list[PdfImageObject]:
        ...

    def extract_lines(self, page_no: int) -> list[PdfGraphicObject]:
        ...

    def extract_rects(self, page_no: int) -> list[PdfGraphicObject]:
        ...

    def extract_tables(self, page_no: int) -> list[PdfTableObject]:
        ...

    def inspect_metadata(self) -> dict[str, object]:
        ...

    def render_crop(
        self,
        page_no: int,
        bbox: tuple[float, float, float, float],
        output_path: str,
        *,
        padding_pt: float = 2.0,
    ) -> str:
        ...
