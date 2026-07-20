import tempfile
import unittest
from pathlib import Path

from pdf2word.pdf_backends import PdfPlumberBackend


SAMPLE = Path(__file__).resolve().parents[2] / "NIPS-2017-attention-is-all-you-need-Paper.pdf"


@unittest.skipUnless(SAMPLE.exists(), "regression sample is not present")
class PdfPlumberSampleTests(unittest.TestCase):
    def test_embedded_image_stream_and_recovered_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            with PdfPlumberBackend(SAMPLE, image_output_dir=tmp) as backend:
                images = backend.extract_images(3)
                self.assertTrue(images)
                self.assertTrue(images[0].image_path)
                self.assertTrue(Path(images[0].image_path).exists())
                self.assertGreaterEqual(images[0].source_width_px or 0, 1000)
                self.assertGreaterEqual(images[0].source_height_px or 0, 1000)

                tables = backend.extract_tables(9)
                self.assertTrue(tables)
                self.assertEqual(len(tables[0].rows), 8)
                self.assertEqual(max(len(row) for row in tables[0].rows), 13)
                self.assertEqual(len(tables[0].column_widths_pt), 13)
                self.assertTrue(any(tables[0].cell_borders or []))
                self.assertIn("\n", tables[0].rows[2][4])
                self.assertIn("\n", tables[0].rows[4][10])


if __name__ == "__main__":
    unittest.main()
