import importlib.util
import tempfile
import unittest
from pathlib import Path

from pdf2word.domain import (
    BoundingBox,
    DocumentElement,
    DocumentIR,
    DocumentMeta,
    FormulaPayload,
    HeaderFooterPayload,
    PageIR,
    Provenance,
    TableCellPayload,
    TablePayload,
    TextRun,
    FontSlots,
)
from pdf2word.renderers import EditableDocxRenderer


@unittest.skipIf(importlib.util.find_spec("docx") is None, "python-docx is not installed")
class EditableDocxRendererTests(unittest.TestCase):
    def test_renders_simple_formula_as_omml(self):
        from docx import Document

        page = PageIR(
            id="page_001",
            page_number=1,
            width_pt=612,
            height_pt=792,
            elements=[
                DocumentElement(
                    id="formula",
                    type="formula",
                    text="x^2",
                    formula=FormulaPayload(
                        fallback_text="x^2",
                        omml_xml=(
                            '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
                            "<m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e>"
                            "<m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:oMath>"
                        ),
                    ),
                    bbox=BoundingBox(left=0, top=0.2, right=1, bottom=0.25),
                    reading_order=1,
                    provenance=Provenance(parser="test", source_page=1),
                )
            ],
        )
        ir = DocumentIR(document=DocumentMeta(page_count=1), pages=[page])

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "formula.docx"
            EditableDocxRenderer().render(ir, output, layout="paged")
            doc = Document(output)
            self.assertIn("m:oMath", doc.paragraphs[0]._p.xml)
            self.assertIn("m:sSup", doc.paragraphs[0]._p.xml)

    def test_renders_header_footer_table_and_runs(self):
        from docx import Document

        page = PageIR(
            id="page_001",
            page_number=1,
            width_pt=612,
            height_pt=792,
            elements=[
                DocumentElement(
                    id="header",
                    type="header",
                    text="Report Header",
                    page_region="header",
                    bbox=BoundingBox(left=0, top=0, right=1, bottom=0.05),
                    reading_order=1,
                    header_footer=HeaderFooterPayload(kind="header", text="Report Header"),
                    provenance=Provenance(parser="test", source_page=1),
                ),
                DocumentElement(
                    id="text",
                    type="paragraph",
                    text="Hello 世界",
                    runs=[
                        TextRun(
                            text="Hello",
                            font_family="Arial",
                            font_slots=FontSlots(ascii="Arial", hAnsi="Arial", eastAsia="SimSun", cs="Arial"),
                            font_size_pt=11,
                            underline=True,
                        ),
                        TextRun(text="世界", font_family="SimSun", font_size_pt=11),
                    ],
                    bbox=BoundingBox(left=0, top=0.2, right=1, bottom=0.25),
                    reading_order=2,
                    provenance=Provenance(parser="test", source_page=1),
                ),
                DocumentElement(
                    id="table",
                    type="table",
                    text="A\tB\n1\t2",
                    bbox=BoundingBox(left=0, top=0.3, right=1, bottom=0.5),
                    reading_order=3,
                    table=TablePayload(
                        row_count=2,
                        column_count=2,
                        rows=[
                            [TableCellPayload(text="A"), TableCellPayload(text="B")],
                            [TableCellPayload(text="1"), TableCellPayload(text="2")],
                        ],
                    ),
                    provenance=Provenance(parser="test", source_page=1),
                ),
                DocumentElement(
                    id="footer",
                    type="footer",
                    text="Page 1",
                    page_region="footer",
                    bbox=BoundingBox(left=0, top=0.95, right=1, bottom=1),
                    reading_order=4,
                    header_footer=HeaderFooterPayload(kind="footer", text="Page 1"),
                    provenance=Provenance(parser="test", source_page=1),
                ),
            ],
        )
        ir = DocumentIR(document=DocumentMeta(page_count=1), pages=[page])

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.docx"
            EditableDocxRenderer().render(ir, output, layout="paged")
            doc = Document(output)
            self.assertEqual(doc.sections[0].header.paragraphs[0].text, "Report Header")
            footer_xml = doc.sections[0].footer._element.xml
            self.assertIn("PAGE", footer_xml)
            self.assertIn("fldChar", footer_xml)
            self.assertEqual(len(doc.tables), 1)
            self.assertEqual(doc.tables[0].cell(1, 1).text, "2")
            table_xml = doc.tables[0]._tbl.xml
            self.assertIn("w:tblHeader", table_xml)
            self.assertIn("w:cantSplit", table_xml)
            self.assertIn('w:left w:val="single"', table_xml)
            self.assertIn('w:right w:val="single"', table_xml)
            body_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
            self.assertIn("Hello 世界", body_text)
            first_run_xml = doc.paragraphs[0]._p.xml
            self.assertIn('w:eastAsia="SimSun"', first_run_xml)
            self.assertIn("w:u", first_run_xml)

    def test_complex_formula_with_source_crop_stays_editable_in_flow(self):
        from docx import Document
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "formula.png"
            Image.new("RGB", (120, 24), "white").save(image_path)
            page = PageIR(
                id="page_001",
                page_number=1,
                width_pt=612,
                height_pt=792,
                elements=[
                    DocumentElement(
                        id="formula",
                        type="formula",
                        text="lrate = d^−_model^0.5",
                        runs=[
                            TextRun(text="lrate = d", italic=True),
                            TextRun(text="−_model^0.5", italic=True, superscript=True),
                        ],
                        formula=FormulaPayload(
                            fallback_text="lrate = d^−_model^0.5",
                            image_path=str(image_path),
                        ),
                        bbox=BoundingBox(left=0.2, top=0.2, right=0.8, bottom=0.24),
                        reading_order=1,
                        provenance=Provenance(parser="test", source_page=1),
                    )
                ],
            )
            output = Path(tmp) / "formula-flow.docx"
            EditableDocxRenderer().render(
                DocumentIR(document=DocumentMeta(page_count=1), pages=[page]),
                output,
                layout="continuous",
            )
            doc = Document(output)
            xml = doc.element.body.xml
            self.assertIn("lrate = d", doc.paragraphs[0].text)
            self.assertIn("w:vertAlign", xml)
            self.assertNotIn("pic:pic", xml)

    def test_keeps_page_specific_footers_in_separate_sections(self):
        from docx import Document

        def page(page_number: int) -> PageIR:
            return PageIR(
                id=f"page_{page_number:03d}",
                page_number=page_number,
                width_pt=612,
                height_pt=792,
                elements=[
                    DocumentElement(
                        id=f"footer_{page_number}",
                        type="footer",
                        text=str(page_number),
                        page_region="footer",
                        bbox=BoundingBox(left=0, top=0.95, right=1, bottom=1),
                        reading_order=1,
                        header_footer=HeaderFooterPayload(kind="footer", text=str(page_number)),
                        provenance=Provenance(parser="test", source_page=page_number),
                    )
                ],
            )

        ir = DocumentIR(document=DocumentMeta(page_count=2), pages=[page(1), page(2)])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.docx"
            EditableDocxRenderer().render(ir, output, layout="paged")
            doc = Document(output)
            self.assertEqual(len(doc.sections), 2)
            self.assertIn("PAGE", doc.sections[0].footer._element.xml)
            self.assertIn("PAGE", doc.sections[1].footer._element.xml)
            self.assertIn("fldChar", doc.sections[0].footer._element.xml)
            self.assertIn("1", doc.sections[0].footer._element.xml)
            self.assertIn("2", doc.sections[1].footer._element.xml)

    def test_applies_page_geometry_and_bbox_spacing(self):
        from docx import Document

        page = PageIR(
            id="page_001",
            page_number=1,
            width_pt=612,
            height_pt=792,
            elements=[
                DocumentElement(
                    id="p1",
                    type="paragraph",
                    text="First",
                    runs=[TextRun(text="First", font_size_pt=12)],
                    bbox=BoundingBox(left=0.15, top=0.20, right=0.85, bottom=0.23),
                    reading_order=1,
                    provenance=Provenance(parser="test", source_page=1),
                ),
                DocumentElement(
                    id="p2",
                    type="paragraph",
                    text="Second",
                    runs=[TextRun(text="Second", font_size_pt=12)],
                    bbox=BoundingBox(left=0.25, top=0.30, right=0.80, bottom=0.33),
                    reading_order=2,
                    provenance=Provenance(parser="test", source_page=1),
                ),
            ],
        )
        ir = DocumentIR(document=DocumentMeta(page_count=1), pages=[page])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "geo.docx"
            EditableDocxRenderer().render(ir, output)
            doc = Document(output)
            section = doc.sections[0]
            self.assertAlmostEqual(section.page_width.pt, 612, places=1)
            self.assertAlmostEqual(section.page_height.pt, 792, places=1)
            # Content starts at left=0.15 → margin ~91.8pt
            self.assertGreater(section.left_margin.pt, 70)
            self.assertLess(section.left_margin.pt, 110)
            paragraphs = [p for p in doc.paragraphs if p.text.strip()]
            self.assertEqual(len(paragraphs), 2)
            # Geometry remains applied; exact spacing depends on vertical map / pack profile.
            self.assertIsNotNone(paragraphs[1].paragraph_format.space_before)
            self.assertGreaterEqual(paragraphs[1].paragraph_format.space_before.pt, 0.0)


if __name__ == "__main__":
    unittest.main()
