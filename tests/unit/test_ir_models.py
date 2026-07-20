import unittest

from pdf2word.domain import (
    BoundingBox,
    DocumentElement,
    DocumentIR,
    DocumentMeta,
    PageIR,
    Provenance,
)


class IrModelTests(unittest.TestCase):
    def test_bbox_normalizes_points(self):
        bbox = BoundingBox.from_points(50, 100, 150, 300, page_width=200, page_height=400)
        self.assertEqual(bbox.as_list(), [0.25, 0.25, 0.75, 0.75])

    def test_document_text_uses_reading_order(self):
        page = PageIR(
            id="page_001",
            page_number=1,
            width_pt=100,
            height_pt=100,
            elements=[
                DocumentElement(
                    id="b",
                    type="paragraph",
                    text="second",
                    bbox=BoundingBox(left=0, top=0, right=1, bottom=1),
                    reading_order=2,
                    provenance=Provenance(parser="test", source_page=1),
                ),
                DocumentElement(
                    id="a",
                    type="heading",
                    text="first",
                    bbox=BoundingBox(left=0, top=0, right=1, bottom=1),
                    reading_order=1,
                    provenance=Provenance(parser="test", source_page=1),
                ),
            ],
        )
        ir = DocumentIR(document=DocumentMeta(page_count=1), pages=[page])
        self.assertEqual(ir.text_content(), "first\nsecond")


if __name__ == "__main__":
    unittest.main()

