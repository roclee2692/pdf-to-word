import importlib.util
import tempfile
import unittest
from pathlib import Path

from pdf2word.domain import (
    BoundingBox,
    DocumentElement,
    DocumentIR,
    DocumentMeta,
    ElementStyle,
    ImagePayload,
    PageIR,
    Provenance,
    TableCellPayload,
    TablePayload,
)
from pdf2word.renderers import FidelityDocxRenderer


@unittest.skipIf(importlib.util.find_spec("docx") is None, "python-docx is not installed")
class FidelityDocxRendererTests(unittest.TestCase):
    def _page(self, background_image_path: str | None = None) -> PageIR:
        return PageIR(
            id="page_001",
            page_number=1,
            width_pt=612,
            height_pt=792,
            background_image_path=background_image_path,
            elements=[
                DocumentElement(
                    id="text_001",
                    type="paragraph",
                    text="Editable fallback text",
                    bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.15),
                    reading_order=1,
                    provenance=Provenance(parser="test", source_page=1),
                )
            ],
        )

    def test_snapshot_mode_keeps_the_visual_layer_as_page_anchor_picture(self):
        from PIL import Image
        from docx import Document

        with tempfile.TemporaryDirectory() as tmp:
            background = Path(tmp) / "page.png"
            Image.new("RGB", (612, 792), "white").save(background)
            output = Path(tmp) / "snapshot.docx"
            FidelityDocxRenderer().render(
                DocumentIR(document=DocumentMeta(page_count=1), pages=[self._page(str(background))]),
                output,
                layout="fidelity",
            )
            doc = Document(output)
            xml = doc.element.body.xml
            self.assertIn("wp:anchor", xml)
            self.assertIn('behindDoc="1"', xml)
            self.assertNotIn("Editable fallback text", xml)

    def test_hybrid_mode_keeps_snapshot_and_vanished_editable_text(self):
        from PIL import Image
        from docx import Document

        with tempfile.TemporaryDirectory() as tmp:
            background = Path(tmp) / "page.png"
            Image.new("RGB", (612, 792), "white").save(background)
            output = Path(tmp) / "hybrid.docx"
            FidelityDocxRenderer().render(
                DocumentIR(document=DocumentMeta(page_count=1), pages=[self._page(str(background))]),
                output,
                layout="hybrid",
            )
            xml = Document(output).element.body.xml
            self.assertIn('behindDoc="1"', xml)
            self.assertIn("wps:txbx", xml)
            self.assertIn("Editable fallback text", xml)
            self.assertIn("w:vanish", xml)

    def test_no_snapshot_fallback_emits_editable_drawingml_textbox(self):
        from docx import Document

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "fallback.docx"
            FidelityDocxRenderer().render(
                DocumentIR(document=DocumentMeta(page_count=1), pages=[self._page()]),
                output,
            )
            doc = Document(output)
            xml = doc.element.body.xml
            self.assertIn("wps:wsp", xml)
            self.assertIn("wps:txbx", xml)
            self.assertIn("wp:anchor", xml)
            self.assertIn("Editable fallback text", xml)

    def test_long_positioned_line_gets_font_fit_scale(self):
        from docx import Document

        page = self._page()
        page.elements[0] = page.elements[0].model_copy(
            update={
                "text": "long text " * 40,
                "bbox": BoundingBox(left=0.1, top=0.1, right=0.3, bottom=0.15),
                "style": ElementStyle(font_size_pt=10),
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "long-line.docx"
            FidelityDocxRenderer().render(
                DocumentIR(document=DocumentMeta(page_count=1), pages=[page]),
                output,
            )
            xml = Document(output).element.body.xml
            self.assertIn("w:sz", xml)
            self.assertNotIn('w:sz w:val="20"', xml)

    def test_no_snapshot_images_use_editable_drawingml_anchor(self):
        from PIL import Image
        from docx import Document

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "figure.png"
            Image.new("RGB", (80, 40), "red").save(image_path)
            page = self._page()
            page.elements.append(
                DocumentElement(
                    id="image_001",
                    type="image",
                    bbox=BoundingBox(left=0.2, top=0.3, right=0.5, bottom=0.4),
                    reading_order=2,
                    image=ImagePayload(
                        image_path=str(image_path),
                        width_pt=180,
                        height_pt=60,
                        wrap="floating",
                        rotation_deg=2.0,
                    ),
                    provenance=Provenance(parser="test", source_page=1),
                )
            )
            output = Path(tmp) / "image-anchor.docx"
            FidelityDocxRenderer().render(
                DocumentIR(document=DocumentMeta(page_count=1), pages=[page]),
                output,
            )
            xml = Document(output).element.body.xml
            self.assertIn("wp:anchor", xml)
            self.assertIn("pic:pic", xml)
            self.assertIn('rot="120000"', xml)
            self.assertNotIn("w:pict", xml)

    def test_no_snapshot_tables_use_native_floating_table_position(self):
        from docx import Document

        page = PageIR(
            id="page_001",
            page_number=1,
            width_pt=612,
            height_pt=792,
            elements=[
                DocumentElement(
                    id="table_001",
                    type="table",
                    bbox=BoundingBox(left=0.2, top=0.3, right=0.8, bottom=0.5),
                    reading_order=1,
                    table=TablePayload(
                        row_count=2,
                        column_count=2,
                        rows=[
                            [TableCellPayload(text="A"), TableCellPayload(text="B")],
                            [TableCellPayload(text="1"), TableCellPayload(text="2")],
                        ],
                        column_widths_pt=[100, 100],
                        row_heights_pt=[20, 20],
                    ),
                    provenance=Provenance(parser="test", source_page=1),
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "floating-table.docx"
            FidelityDocxRenderer().render(
                DocumentIR(document=DocumentMeta(page_count=1), pages=[page]),
                output,
            )
            doc = Document(output)
            self.assertEqual(len(doc.tables), 1)
            table_xml = doc.tables[0]._tbl.xml
            self.assertIn("w:tblpPr", table_xml)
            self.assertIn('w:horzAnchor="page"', table_xml)
            self.assertIn('w:vertAnchor="page"', table_xml)
            self.assertIn("w:tblHeader", table_xml)
            self.assertIn("w:cantSplit", table_xml)
            self.assertNotIn("wps:txbx", table_xml)


if __name__ == "__main__":
    unittest.main()
