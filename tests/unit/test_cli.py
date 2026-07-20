import argparse
import unittest

from pdf2word.cli import build_parser, parse_page_selection


class PageSelectionTests(unittest.TestCase):
    def test_single_pages_and_ranges_are_sorted(self):
        self.assertEqual(parse_page_selection("3,1-2"), [1, 2, 3])

    def test_reverse_range_is_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_page_selection("5-3")

    def test_zero_page_is_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_page_selection("0")

    def test_empty_pages_means_all(self):
        self.assertIsNone(parse_page_selection(None))
        self.assertIsNone(parse_page_selection(""))
        self.assertIsNone(parse_page_selection("  "))

    def test_optional_gui_command_is_registered(self):
        args = build_parser().parse_args(["gui"])

        self.assertEqual(args.command, "gui")

    def test_convert_pages_optional_and_default_mode_positioned(self):
        args = build_parser().parse_args(["convert", "sample.pdf"])
        self.assertIsNone(args.pages)
        self.assertEqual(args.mode, "positioned")

    def test_batch_command_is_registered(self):
        args = build_parser().parse_args(
            ["batch", "in_dir", "--out", "out_dir", "--mode", "editable"]
        )
        self.assertEqual(args.command, "batch")
        self.assertEqual(args.mode, "editable")


if __name__ == "__main__":
    unittest.main()
