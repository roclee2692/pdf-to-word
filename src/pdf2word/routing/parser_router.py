from __future__ import annotations

from pdf2word.parsers.adapter_registry import available_adapter_names, resource_report
from pdf2word.routing.preflight import PagePreflight


class ParserRouter:
    """Choose a parser policy and keep unavailable adapters out of execution."""

    def __init__(self, available_parsers: set[str] | None = None):
        self._available_parsers = available_parsers

    def choose_parser(self, preflight: PagePreflight) -> str:
        """Return the ideal parser according to document signals."""
        if preflight.table_count and (preflight.line_count + preflight.rect_count) > 20:
            return "native"
        if preflight.image_coverage > 0.65 and not preflight.has_text_layer:
            return "mineru"
        if preflight.formula_like_count > 8 or preflight.column_count > 1:
            return "docling"
        if preflight.has_text_layer and preflight.layout_complexity in {"low", "medium"}:
            return "native"
        if preflight.has_text_layer:
            return "docling"
        return "mineru"

    def choose_available_parser(self, preflight: PagePreflight) -> str:
        """Return an executable parser.

        Always prefers the ideal parser when it is installed and enabled.
        If the preferred engine is unavailable, degrade to ``native`` so the
        convert path never crashes on scanned/complex pages (quality may be low).
        """
        preferred = self.choose_parser(preflight)
        available = self.available_parsers()
        if preferred in available:
            return preferred
        if "native" in available:
            return "native"
        if available:
            return sorted(available)[0]
        return preferred

    def is_degraded(self, preflight: PagePreflight) -> bool:
        return self.choose_parser(preflight) != self.choose_available_parser(preflight)

    def available_parsers(self) -> set[str]:
        if self._available_parsers is not None:
            return set(self._available_parsers)
        return {"native", *available_adapter_names()}

    def availability_report(self) -> dict[str, bool]:
        available = self.available_parsers()
        return {
            "native": "native" in available,
            **{name: name in available for name in ("docling", "mineru", "paddleocr")},
        }

    def resource_report(self) -> dict[str, dict[str, object]]:
        return resource_report()

    def external_ocr_available(self) -> bool:
        available = self.available_parsers()
        return bool(available & {"mineru", "paddleocr", "docling"})
