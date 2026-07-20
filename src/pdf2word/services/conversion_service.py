from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from pdf2word.domain import DocumentIR
from pdf2word.parsers import DoclingParser, NativeTextParser
from pdf2word.pdf_backends import PdfPlumberBackend
from pdf2word.renderers import EditableDocxRenderer, FidelityDocxRenderer
from pdf2word.routing import ParserRouter, PreflightAnalyzer
from pdf2word.storage import JobWorkspace, WorkspaceStore
from pdf2word.validation import ValidationEngine, ValidationOptions, ValidationReport


@dataclass(frozen=True)
class ConversionOptions:
    pages: list[int] | None = None  # None or [] => all pages
    mode: str = "positioned"
    dump_ir: bool = False
    workspace_root: Path = Path("workspace")
    validate: bool = True
    visual_validate: bool = True
    strict_visual: bool = False


@dataclass(frozen=True)
class ConversionResult:
    output_path: Path
    ir_path: Path | None
    preflight_path: Path
    validation_path: Path | None
    validation_report: ValidationReport | None
    workspace: JobWorkspace
    document_ir: DocumentIR
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ConversionService:
    def convert(
        self,
        pdf_path: str | Path,
        output_path: str | Path | None,
        options: ConversionOptions,
    ) -> ConversionResult:
        if options.mode not in {"editable", "positioned", "fidelity", "hybrid"}:
            raise ValueError(f"Unsupported rendering mode: {options.mode}")

        pdf_path = Path(pdf_path)
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        store = WorkspaceStore(options.workspace_root)
        workspace = store.create_job()
        native_parser = NativeTextParser()
        if options.mode == "editable":
            renderer = EditableDocxRenderer()
            render_layout = "continuous"
        else:
            renderer = FidelityDocxRenderer()
            render_layout = options.mode  # positioned | fidelity | hybrid

        convert_warnings: list[str] = []

        with PdfPlumberBackend(pdf_path, image_output_dir=workspace.parser_outputs_dir / "images") as backend:
            page_count = backend.page_count()
            pages = self._resolve_pages(options.pages, page_count)
            preflight = PreflightAnalyzer().analyze_pages(backend, pages)
            router = ParserRouter()
            preflight_path = workspace.validation_dir / "preflight.json"
            available = router.available_parsers()

            page_routes: list[dict] = []
            for page in preflight:
                preferred = router.choose_parser(page)
                selected = router.choose_available_parser(page)
                degraded = preferred != selected
                route = {
                    **page.__dict__,
                    "preferred_parser": preferred,
                    "selected_parser": selected,
                    "degraded": degraded,
                }
                if degraded:
                    reason = (
                        f"page {page.page_no}: preferred '{preferred}' unavailable; "
                        f"using '{selected}' (quality may be limited)"
                    )
                    route["degraded_reason"] = reason
                    convert_warnings.append(reason)
                page_routes.append(route)

            no_text_pages = [p.page_no for p in preflight if not p.has_text_layer]
            if no_text_pages and not router.external_ocr_available():
                msg = (
                    "page(s) without a text layer detected "
                    f"({no_text_pages[:12]}{'…' if len(no_text_pages) > 12 else ''}) and "
                    "external OCR parsers (MinerU/PaddleOCR/Docling) are unavailable. "
                    "Falling back to native parser — output quality will be limited for scanned pages. "
                    "Install OCR runtimes and set PDF2WORD_ENABLE_EXTERNAL_PARSERS=1 for better results."
                )
                convert_warnings.append(msg)
                # Single surface path: CLI prints convert_warnings; avoid triple-spam.

            parser_names = {page["selected_parser"] for page in page_routes}
            executable = {name for name in parser_names if name in available}
            if not executable:
                if "native" in available:
                    executable = {"native"}
                    parser_names = {"native"}
                    convert_warnings.append(
                        "No selected parser was executable; forced native fallback."
                    )
                else:
                    raise ValueError(
                        "No available parser. Install dependencies or use a text-based PDF. "
                        f"See {preflight_path}"
                    )

            # Prefer a single executable engine for the job.
            if "docling" in executable and "docling" in parser_names:
                try:
                    document_ir = DoclingParser().parse(backend, pages)
                    execution: dict = {"parser": "docling", "fallback": False}
                except Exception as exc:  # noqa: BLE001 - degrade to native
                    document_ir = native_parser.parse(backend, pages)
                    execution = {
                        "parser": "native",
                        "fallback": True,
                        "fallback_reason": f"{type(exc).__name__}: {exc}",
                    }
                    convert_warnings.append(
                        f"Docling parse failed; fell back to native: {type(exc).__name__}: {exc}"
                    )
            else:
                # native, or preferred OCR engine not actually wired as a full parser yet
                if parser_names - {"native"}:
                    convert_warnings.append(
                        f"Selected non-native parser(s) {sorted(parser_names - {'native'})} "
                        "are not executable in this build; using native."
                    )
                document_ir = native_parser.parse(backend, pages)
                execution = {
                    "parser": "native",
                    "fallback": bool(convert_warnings),
                    "fallback_reason": convert_warnings[0] if convert_warnings else None,
                }

            if options.mode in {"fidelity", "hybrid"} and hasattr(backend, "render_page_snapshot"):
                snapshot_dir = workspace.parser_outputs_dir / "page_snapshots"
                pages_with_snapshots = []
                for page in document_ir.pages:
                    snapshot = backend.render_page_snapshot(
                        page.page_number,
                        snapshot_dir / f"page_{page.page_number:03d}.png",
                    )
                    pages_with_snapshots.append(
                        page.model_copy(update={"background_image_path": str(snapshot)})
                    )
                document_ir = document_ir.model_copy(update={"pages": pages_with_snapshots})

            preflight_path.write_text(
                json.dumps(
                    {
                        "available_parsers": router.availability_report(),
                        "open_source_resources": router.resource_report(),
                        "execution": execution,
                        "warnings": convert_warnings,
                        "pages": page_routes,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        ir_path = workspace.ir_dir / "original.json" if options.dump_ir else None
        if ir_path:
            ir_path.write_text(
                json.dumps(document_ir.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        docx_path = Path(output_path) if output_path else workspace.output_dir / "result.docx"
        if options.mode == "editable":
            renderer.render(document_ir, docx_path)
        else:
            renderer.render(document_ir, docx_path, layout=render_layout)

        validation_report: ValidationReport | None = None
        validation_path: Path | None = None
        if options.validate:
            validation_report = ValidationEngine().evaluate(
                document_ir,
                docx_path,
                workspace.validation_dir,
                mode=options.mode,
                source_pdf=pdf_path,
                options=ValidationOptions(
                    visual=options.visual_validate,
                    write_report=True,
                    strict=options.strict_visual,
                ),
            )
            validation_path = workspace.validation_dir / "validation_report.json"

        return ConversionResult(
            output_path=docx_path,
            ir_path=ir_path,
            preflight_path=preflight_path,
            validation_path=validation_path,
            validation_report=validation_report,
            workspace=workspace,
            document_ir=document_ir,
            warnings=tuple(convert_warnings),
        )

    def _resolve_pages(self, pages: list[int] | None, page_count: int) -> list[int]:
        if not pages:
            if page_count < 1:
                raise ValueError("PDF has no pages")
            return list(range(1, page_count + 1))
        invalid = [page for page in pages if page < 1 or page > page_count]
        if invalid:
            raise ValueError(
                f"Page selection out of range: {invalid}; document has {page_count} pages"
            )
        return list(pages)
