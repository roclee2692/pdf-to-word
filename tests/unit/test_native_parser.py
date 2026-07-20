import unittest
from pathlib import Path

from pdf2word.parsers.native_parser import NativeTextParser
from pdf2word.pdf_backends import PdfGraphicObject, PdfTableObject, PdfTextObject


class NativeParserGraphicTests(unittest.TestCase):
    def test_attention_math_and_horizontal_rule_table_are_structured(self):
        from pdf2word.parsers.native_parser import NativeTextParser
        from pdf2word.pdf_backends import PdfPlumberBackend

        pdf = Path(__file__).parents[2] / "NIPS-2017-attention-is-all-you-need-Paper.pdf"
        with PdfPlumberBackend(pdf) as backend:
            ir = NativeTextParser().parse(backend, [7, 8])

        formula = next(element for element in ir.pages[0].elements if element.type == "formula")
        self.assertIn("d^", formula.text)
        self.assertIn("model", formula.text)
        self.assertTrue(any(run.superscript for run in formula.runs))
        self.assertTrue(any(run.subscript for run in formula.runs))
        table = next(element for element in ir.pages[1].elements if element.type == "table")
        self.assertEqual((table.table.row_count, table.table.column_count), (12, 5))
        self.assertEqual(table.table.rows[0][1].col_span, 2)
        self.assertIn("3.3", table.table.rows[-2][3].text)
        self.assertIn("10^18", table.table.rows[-2][3].text)

    def test_builds_omml_for_simple_superscript(self):
        omml = NativeTextParser()._formula_to_omml("x^2")

        self.assertIsNotNone(omml)
        self.assertIn("m:sSup", omml)
        self.assertIn("<m:t>2</m:t>", omml)

    def test_builds_editable_omml_token_stream_for_complex_formula(self):
        omml = NativeTextParser()._formula_to_omml(
            "Attention( Q,K,V ) = softmax( Q ) V (1)"
        )

        self.assertIsNotNone(omml)
        self.assertIn("m:oMath", omml)
        self.assertIn("<m:t>Attention</m:t>", omml)
        self.assertIn("<m:t>=</m:t>", omml)
        self.assertIn("<m:t>softmax</m:t>", omml)

    def test_builds_subscript_and_superscript_object(self):
        omml = NativeTextParser()._formula_to_omml("x_i^2")

        self.assertIsNotNone(omml)
        self.assertIn("m:sSubSup", omml)

    def test_keeps_source_font_and_text_color_on_runs(self):
        run = NativeTextParser()._word_to_run(
            PdfTextObject(
                text="A",
                x0=0,
                top=0,
                x1=5,
                bottom=8,
                font_name="ABC+NimbusRomNo9L-Medi",
                font_size=10,
                color=(0.5,),
            )
        )

        self.assertEqual(run.source_font_family, "ABC+NimbusRomNo9L-Medi")
        self.assertEqual(run.font_family, "Times New Roman")
        self.assertEqual(run.color, "808080")

    def test_does_not_center_full_width_body_lines(self):
        parser = NativeTextParser()

        self.assertEqual(parser._guess_alignment(108, 506, 612), "left")
        self.assertEqual(parser._guess_alignment(220, 392, 612), "center")

    def test_promotes_rule_below_heading_to_underlined_run(self):
        parser = NativeTextParser()
        elements = parser._page_to_elements(
            words=[
                PdfTextObject(
                    text="TITLE",
                    x0=72,
                    top=100,
                    x1=180,
                    bottom=120,
                    font_name="Helvetica-Bold",
                    font_size=18,
                )
            ],
            tables=[],
            images=[],
            lines=[
                PdfGraphicObject(
                    x0=72,
                    top=122,
                    x1=180,
                    bottom=122.5,
                    width=108,
                    height=0.5,
                )
            ],
            rects=[],
            page_no=1,
            page_width=612,
            page_height=792,
        )

        self.assertEqual(len(elements), 1)
        self.assertTrue(elements[0].style.underline)
        self.assertTrue(elements[0].runs[0].underline)

    def test_keeps_long_cover_guide_line_as_separator(self):
        parser = NativeTextParser()
        elements = parser._page_to_elements(
            words=[
                PdfTextObject(
                    text="Name",
                    x0=72,
                    top=100,
                    x1=110,
                    bottom=112,
                    font_name="Helvetica",
                    font_size=10,
                )
            ],
            tables=[],
            images=[],
            lines=[
                PdfGraphicObject(
                    x0=72,
                    top=114,
                    x1=260,
                    bottom=114.5,
                    width=188,
                    height=0.5,
                )
            ],
            rects=[],
            page_no=1,
            page_width=612,
            page_height=792,
        )

        self.assertEqual([element.type for element in elements], ["paragraph", "separator"])

    def test_keeps_non_text_rule_as_separator(self):
        parser = NativeTextParser()
        elements = parser._page_to_elements(
            words=[],
            tables=[],
            images=[],
            lines=[
                PdfGraphicObject(
                    x0=300,
                    top=100,
                    x1=301,
                    bottom=200,
                    width=1,
                    height=100,
                )
            ],
            rects=[],
            page_no=1,
            page_width=612,
            page_height=792,
        )

        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0].type, "separator")
        self.assertEqual(elements[0].separator.orientation, "vertical")

    def test_preserves_pdf_table_row_and_column_spans(self):
        table = PdfTableObject(
            x0=0,
            top=0,
            x1=200,
            bottom=40,
            rows=[["Merged", ""], ["", "C"]],
            cell_bboxes=[
                [(0, 0, 200, 20), None],
                [None, (100, 20, 200, 40)],
            ],
        )
        element = NativeTextParser()._table_to_element(table, 1, 200, 40, 1, 1)

        self.assertEqual(element.table.rows[0][0].col_span, 2)
        self.assertIsNone(element.table.rows[0][1])
        self.assertIsNone(element.table.rows[1][0])
        self.assertEqual(element.table.rows[1][1].text, "C")


if __name__ == "__main__":
    unittest.main()
