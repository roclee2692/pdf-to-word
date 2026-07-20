from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdf2word.services import ConversionOptions, ConversionService


def parse_page_selection(value: str | None) -> list[int] | None:
    """Parse page list. Empty / None means all pages (resolved later)."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    pages: set[int] = set()
    for chunk in text.split(","):
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
        return None
    if any(page < 1 for page in pages):
        raise argparse.ArgumentTypeError("Pages are 1-based and must be positive")
    return sorted(pages)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdf2word")
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert = subparsers.add_parser("convert", help="Convert PDF pages to DOCX")
    convert.add_argument("pdf", type=Path)
    convert.add_argument(
        "--pages",
        type=parse_page_selection,
        default=None,
        help="Page list (e.g. 1,3-5). Default: all pages",
    )
    convert.add_argument("--out", type=Path, default=None, help="DOCX output path")
    convert.add_argument(
        "--mode",
        choices=["editable", "positioned", "fidelity", "hybrid"],
        default="positioned",
        help=(
            "positioned=native DrawingML (default deliverable) | "
            "editable=flow | "
            "hybrid/fidelity=pixel-proof tools (not primary editable deliverables)"
        ),
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
    convert.add_argument(
        "--strict-visual",
        action="store_true",
        help="Stricter gates: drawing-text checks + visual warnings fail the job",
    )

    batch = subparsers.add_parser("batch", help="Convert all PDFs in a directory")
    batch.add_argument("input_dir", type=Path, help="Directory containing PDF files")
    batch.add_argument("--out", type=Path, required=True, help="Output directory for DOCX files")
    batch.add_argument(
        "--mode",
        choices=["editable", "positioned", "fidelity", "hybrid"],
        default="positioned",
    )
    batch.add_argument(
        "--pages",
        type=parse_page_selection,
        default=None,
        help="Optional page list applied to every PDF; default all pages",
    )
    batch.add_argument("--workspace", type=Path, default=Path("workspace"))
    batch.add_argument("--no-validate", action="store_true")
    batch.add_argument("--no-visual-diff", action="store_true")
    batch.add_argument("--strict-visual", action="store_true")
    batch.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep converting remaining files after a failure",
    )

    subparsers.add_parser("gui", help="Launch the optional PySide6 desktop UI")

    return parser


def _print_result(result) -> None:
    for warning in getattr(result, "warnings", ()) or ():
        print(f"WARNING: {warning}", file=sys.stderr)
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
                strict_visual=args.strict_visual,
            ),
        )
        _print_result(result)
    elif args.command == "batch":
        input_dir = Path(args.input_dir)
        out_dir = Path(args.out)
        if not input_dir.is_dir():
            raise SystemExit(f"Input directory not found: {input_dir}")
        out_dir.mkdir(parents=True, exist_ok=True)
        pdfs = sorted(input_dir.glob("*.pdf")) + sorted(input_dir.glob("*.PDF"))
        # de-dupe case-insensitive fs
        seen: set[Path] = set()
        unique: list[Path] = []
        for pdf in pdfs:
            key = pdf.resolve()
            if key in seen:
                continue
            seen.add(key)
            unique.append(pdf)
        if not unique:
            raise SystemExit(f"No PDF files found in {input_dir}")
        failures = 0
        for pdf in unique:
            target = out_dir / f"{pdf.stem}.docx"
            print(f"=== batch: {pdf.name} -> {target.name} ===")
            try:
                result = ConversionService().convert(
                    pdf,
                    target,
                    ConversionOptions(
                        pages=args.pages,
                        mode=args.mode,
                        dump_ir=False,
                        workspace_root=args.workspace,
                        validate=not args.no_validate,
                        visual_validate=not args.no_visual_diff,
                        strict_visual=args.strict_visual,
                    ),
                )
                _print_result(result)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"ERROR: {pdf}: {type(exc).__name__}: {exc}", file=sys.stderr)
                if not args.continue_on_error:
                    raise SystemExit(1) from exc
        if failures:
            raise SystemExit(f"Batch finished with {failures} failure(s)")
        print(f"BATCH_OK: {len(unique)} file(s)")
    elif args.command == "gui":
        from pdf2word.gui import launch_gui

        raise SystemExit(launch_gui())


if __name__ == "__main__":
    main()
