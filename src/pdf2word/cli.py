from __future__ import annotations

import argparse
from pathlib import Path

from pdf2word.services import ConversionOptions, ConversionService


def parse_page_selection(value: str) -> list[int]:
    pages: set[int] = set()
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise argparse.ArgumentTypeError(f"Invalid page range: {chunk}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(chunk))
    if not pages:
        raise argparse.ArgumentTypeError("Page selection cannot be empty")
    if any(page < 1 for page in pages):
        raise argparse.ArgumentTypeError("Pages are 1-based and must be positive")
    return sorted(pages)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdf2word")
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert = subparsers.add_parser("convert", help="Convert selected PDF pages to DOCX")
    convert.add_argument("pdf", type=Path)
    convert.add_argument("--pages", type=parse_page_selection, required=True, help="Page list, for example 1,3-5")
    convert.add_argument("--out", type=Path, default=None, help="DOCX output path")
    convert.add_argument(
        "--mode",
        choices=["editable", "positioned", "fidelity", "hybrid"],
        default="editable",
        help="editable flow | DrawingML positioned | snapshot fidelity | hybrid snapshot+editable",
    )
    convert.add_argument("--workspace", type=Path, default=Path("workspace"))
    convert.add_argument("--dump-ir", action="store_true", help="Write Canonical IR JSON into the job folder")
    convert.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip post-render structure/text/table/image validation",
    )
    convert.add_argument(
        "--no-visual-diff",
        action="store_true",
        help="Skip LibreOffice PDF visual diff even when validation is enabled",
    )

    subparsers.add_parser("gui", help="Launch the optional PySide6 desktop UI")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "convert":
        result = ConversionService().convert(
            args.pdf,
            args.out,
            ConversionOptions(
                pages=args.pages,
                mode=args.mode,
                dump_ir=args.dump_ir,
                workspace_root=args.workspace,
                validate=not args.no_validate,
                visual_validate=not args.no_visual_diff,
            ),
        )
        print(f"DOCX: {result.output_path}")
        if result.ir_path:
            print(f"IR: {result.ir_path}")
        print(f"PREFLIGHT: {result.preflight_path}")
        if result.validation_path and result.validation_report is not None:
            report = result.validation_report
            print(f"VALIDATION: {result.validation_path}")
            print(f"VALIDATION_PASSED: {report.passed}")
            print(
                "VALIDATION_LAYERS: "
                f"structure={report.structure.status} "
                f"text={report.text.status} "
                f"table={report.table.status} "
                f"image={report.image.status} "
                f"visual={report.visual.status}"
            )
            visual_metrics = report.visual.metrics or {}
            if "source_page_count" in visual_metrics or "rendered_page_count" in visual_metrics:
                print(
                    "VISUAL_PAGES: "
                    f"source={visual_metrics.get('source_page_count')} "
                    f"rendered={visual_metrics.get('rendered_page_count')} "
                    f"delta={visual_metrics.get('page_count_delta')} "
                    f"mean_mad={visual_metrics.get('mean_mad')}"
                )
        print(f"JOB: {result.workspace.root}")
    elif args.command == "gui":
        from pdf2word.gui import launch_gui

        raise SystemExit(launch_gui())


if __name__ == "__main__":
    main()
