import unittest
from pathlib import Path

from pdf2word.parsers.adapter_registry import resource_report


class OpenSourceResourceTests(unittest.TestCase):
    def test_pinned_repositories_are_complete_local_clones(self):
        report = resource_report()

        self.assertEqual(set(report), {"docling", "mineru", "paddleocr"})
        for status in report.values():
            self.assertTrue(status["cloned"])
            self.assertTrue(status["full_clone"])
            self.assertRegex(status["commit"], r"^[0-9a-f]{40}$")
            self.assertTrue(Path(status["repository"]).exists())


if __name__ == "__main__":
    unittest.main()
