import unittest

from pdf2word.pdf_backends import PdfGraphicObject, PdfImageObject, PdfTableObject, PdfTextObject
from pdf2word.routing import PagePreflight, ParserRouter, PreflightAnalyzer


class ParserRouterTests(unittest.TestCase):
    def test_native_text_low_complexity_routes_to_native(self):
        route = ParserRouter(available_parsers={"native", "docling", "mineru"}).choose_parser(
            PagePreflight(page_no=1, has_text_layer=True, word_count=120, layout_complexity="low")
        )
        self.assertEqual(route, "native")


class PreflightSignalTests(unittest.TestCase):
    class _Backend:
        def page_size(self, page_no):
            return 612.0, 792.0

        def extract_text_objects(self, page_no):
            words = [
                PdfTextObject(
                    text=f"left{index}", x0=80 + index * 8, top=200 + index, x1=120 + index * 8, bottom=210 + index
                )
                for index in range(16)
            ]
            words += [
                PdfTextObject(
                    text=f"right{index}", x0=420 + index * 8, top=240 + index, x1=460 + index * 8, bottom=250 + index
                )
                for index in range(16)
            ]
            words += [
                PdfTextObject(text="header", x0=100, top=10, x1=140, bottom=20),
                PdfTextObject(text="page", x0=100, top=742, x1=130, bottom=752),
                PdfTextObject(text="x^2", x0=200, top=300, x1=220, bottom=310),
                PdfTextObject(text="y=1", x0=200, top=315, x1=220, bottom=325),
                PdfTextObject(text="√x", x0=200, top=330, x1=230, bottom=340),
            ]
            return words

        def extract_images(self, page_no):
            return [PdfImageObject("cover", 0, 0, 612, 400, 612, 400)]

        def extract_tables(self, page_no):
            return [PdfTableObject(80, 400, 530, 600, [["A"]], [[(80, 400, 530, 600)]])]

        def extract_lines(self, page_no):
            return [PdfGraphicObject(80, 400 + i * 5, 530, 401 + i * 5, 450, 1) for i in range(20)]

        def extract_rects(self, page_no):
            return []

    def test_detects_cover_table_formula_columns_and_page_chrome(self):
        result = PreflightAnalyzer().analyze_pages(self._Backend(), [1])[0]

        self.assertGreaterEqual(result.image_coverage, 0.25)
        self.assertEqual(result.table_count, 1)
        self.assertGreaterEqual(result.formula_like_count, 3)
        self.assertEqual(result.column_count, 2)
        self.assertTrue(result.has_header)
        self.assertTrue(result.has_footer)
        self.assertIn("image-heavy", result.signals)
        self.assertIn("formula-like", result.signals)
        self.assertIn("2-column", result.signals)

    def test_no_text_layer_routes_to_mineru(self):
        route = ParserRouter().choose_parser(
            PagePreflight(page_no=1, has_text_layer=False, word_count=0, layout_complexity="unknown")
        )
        self.assertEqual(route, "mineru")

    def test_unavailable_ocr_falls_back_to_native_without_crash(self):
        router = ParserRouter(available_parsers={"native"})
        preflight = PagePreflight(
            page_no=1,
            has_text_layer=False,
            word_count=0,
            layout_complexity="high",
            image_coverage=0.9,
        )
        self.assertEqual(router.choose_parser(preflight), "mineru")
        self.assertEqual(router.choose_available_parser(preflight), "native")
        self.assertTrue(router.is_degraded(preflight))

    def test_formula_or_multicolumn_routes_to_docling(self):
        route = ParserRouter().choose_parser(
            PagePreflight(
                page_no=1,
                has_text_layer=True,
                word_count=400,
                layout_complexity="medium",
                formula_like_count=12,
                column_count=2,
            )
        )
        self.assertEqual(route, "docling")

    def test_unavailable_complex_parser_falls_back_to_native_text(self):
        route = ParserRouter(available_parsers={"native"}).choose_available_parser(
            PagePreflight(
                page_no=1,
                has_text_layer=True,
                word_count=400,
                layout_complexity="medium",
                formula_like_count=12,
                column_count=2,
            )
        )
        self.assertEqual(route, "native")

    def test_detected_table_with_lines_stays_native_for_mvp_table_extraction(self):
        route = ParserRouter().choose_parser(
            PagePreflight(
                page_no=1,
                has_text_layer=True,
                word_count=80,
                layout_complexity="high",
                table_count=1,
                line_count=30,
            )
        )
        self.assertEqual(route, "native")


if __name__ == "__main__":
    unittest.main()
