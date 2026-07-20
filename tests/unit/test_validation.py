import tempfile
import unittest
from pathlib import Path

from pdf2word.domain import (
    BoundingBox,
    DocumentElement,
    DocumentIR,
    DocumentMeta,
    HeaderFooterPayload,
    ImagePayload,
    PageIR,
    Provenance,
    TableCellPayload,
    TablePayload,
    TextRun,
)
from pdf2word.renderers import EditableDocxRenderer
from pdf2word.validation import ValidationEngine, ValidationOptions
from pdf2word.validation.text import character_error_rate, normalize_text


class ValidationEngineTests(unittest.TestCase):
    def _sample_ir(self, *, with_image: bool = False, with_table: bool = True) -> DocumentIR:
        elements = [
            DocumentElement(
                id="heading",
                type="heading",
                text="Attention Is All You Need",
                runs=[TextRun(text="Attention Is All You Need", bold=True, font_size_pt=16)],
                bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.15),
                reading_order=1,
                provenance=Provenance(parser="test", source_page=1),
            ),
            DocumentElement(
                id="para",
                type="paragraph",
                text="The dominant sequence transduction models are based on complex recurrent.",
                runs=[
                    TextRun(
                        text="The dominant sequence transduction models are based on complex recurrent.",
                        font_size_pt=11,
                    )
                ],
                bbox=BoundingBox(left=0.1, top=0.2, right=0.9, bottom=0.3),
                reading_order=2,
                provenance=Provenance(parser="test", source_page=1),
            ),
            DocumentElement(
                id="footer",
                type="footer",
                text="1",
                page_region="footer",
                bbox=BoundingBox(left=0.45, top=0.95, right=0.55, bottom=0.98),
                reading_order=4,
                header_footer=HeaderFooterPayload(kind="footer", text="1"),
                provenance=Provenance(parser="test", source_page=1),
            ),
        ]
        if with_table:
            elements.append(
                DocumentElement(
                    id="table",
                    type="table",
                    text=None,
                    bbox=BoundingBox(left=0.1, top=0.4, right=0.9, bottom=0.6),
                    reading_order=3,
                    table=TablePayload(
                        row_count=2,
                        column_count=2,
                        rows=[
                            [
                                TableCellPayload(text="Layer"),
                                TableCellPayload(text="BLEU"),
                            ],
                            [
                                TableCellPayload(text="Base"),
                                TableCellPayload(text="27.3"),
                            ],
                        ],
                    ),
                    provenance=Provenance(parser="test", source_page=1),
                )
            )
        if with_image:
            elements.append(
                DocumentElement(
                    id="image",
                    type="image",
                    text=None,
                    bbox=BoundingBox(left=0.2, top=0.65, right=0.8, bottom=0.85),
                    reading_order=5,
                    image=ImagePayload(image_path="/tmp/missing-image.png", width_pt=200, height_pt=100),
                    provenance=Provenance(parser="test", source_page=1),
                )
            )
        page = PageIR(id="page_001", page_number=1, width_pt=612, height_pt=792, elements=elements)
        return DocumentIR(document=DocumentMeta(page_count=1), pages=[page])

    def test_character_error_rate_is_zero_for_identical_text(self):
        self.assertEqual(character_error_rate("abc", "abc"), 0.0)
        self.assertEqual(normalize_text("  a\n b  "), "a b")

    def test_structure_and_text_pass_for_renderer_roundtrip(self):
        ir = self._sample_ir()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docx = root / "out.docx"
            EditableDocxRenderer().render(ir, docx)
            report = ValidationEngine().evaluate(
                ir,
                docx,
                root / "validation",
                mode="editable",
                options=ValidationOptions(visual=False, write_report=True),
            )
            self.assertTrue(report.passed)
            self.assertIn(report.structure.status, {"pass", "warn"})
            self.assertEqual(report.text.status, "pass")
            self.assertEqual(report.table.status, "pass")
            self.assertEqual(report.visual.status, "skipped")
            self.assertTrue((root / "validation" / "validation_report.json").exists())
            self.assertTrue((root / "validation" / "validation_report.md").exists())

    def test_missing_image_asset_fails_image_layer(self):
        # Renderer refuses to emit a placeholder image; validate IR against a
        # text-only DOCX so the image layer can still fail closed.
        text_only = self._sample_ir(with_image=False, with_table=False)
        ir = self._sample_ir(with_image=True, with_table=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docx = root / "out.docx"
            EditableDocxRenderer().render(text_only, docx)
            report = ValidationEngine().evaluate(
                ir,
                docx,
                root / "validation",
                mode="editable",
                options=ValidationOptions(visual=False, write_report=False),
            )
            self.assertFalse(report.passed)
            self.assertEqual(report.image.status, "fail")
            codes = {issue.code for issue in report.issues}
            self.assertTrue({"image_file_missing", "images_not_in_docx"} & codes)


if __name__ == "__main__":
    unittest.main()
