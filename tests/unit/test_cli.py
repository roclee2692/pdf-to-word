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

    def test_optional_gui_command_is_registered(self):
        args = build_parser().parse_args(["gui"])

        self.assertEqual(args.command, "gui")


if __name__ == "__main__":
    unittest.main()
