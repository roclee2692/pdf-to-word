from __future__ import annotations

import json
from dataclasses import dataclass
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
    pages: list[int]
    mode: str = "editable"
    dump_ir: bool = False
    workspace_root: Path = Path("workspace")
    validate: bool = True
    visual_validate: bool = True


@dataclass(frozen=True)
class ConversionResult:
    output_path: Path
    ir_path: Path | None
    preflight_path: Path
    validation_path: Path | None
    validation_report: ValidationReport | None
    workspace: JobWorkspace
    document_ir: DocumentIR


class ConversionService:
    def convert(self, pdf_path: str | Path, output_path: str | Path | None, options: ConversionOptions) -> ConversionResult:
        if options.mode not in {"editable", "positioned", "fidelity", "hybrid"}:
            raise ValueError(f"Unsupported rendering mode: {options.mode}")

        pdf_path = Path(pdf_path)
        store = WorkspaceStore(options.workspace_root)
        workspace = store.create_job()
        parser = NativeTextParser()
        if options.mode == "editable":
            renderer = EditableDocxRenderer()
            render_layout = "continuous"
        else:
            renderer = FidelityDocxRenderer()
            render_layout = options.mode  # positioned | fidelity | hybrid

        with PdfPlumberBackend(pdf_path, image_output_dir=workspace.parser_outputs_dir / "images") as backend:
            self._validate_pages(options.pages, backend.page_count())
            preflight = PreflightAnalyzer().analyze_pages(backend, options.pages)
            router = ParserRouter()
            preflight_path = workspace.validation_dir / "preflight.json"
            page_routes = [
                {
                    **page.__dict__,
                    "preferred_parser": router.choose_parser(page),
                    "selected_parser": router.choose_available_parser(page),
                }
                for page in preflight
            ]
            parser_names = {page["selected_parser"] for page in page_routes}
            if parser_names != {"native"}:
                if "docling" not in parser_names:
                    raise ValueError(
                        "No executable parser is available for the selected pages; "
                        f"router selected {sorted(parser_names)}. See {preflight_path}"
                    )
                try:
                    document_ir = DoclingParser().parse(backend, options.pages)
                    execution = {"parser": "docling", "fallback": False}
                except Exception as exc:
                    document_ir = parser.parse(backend, options.pages)
                    execution = {
                        "parser": "native",
                        "fallback": True,
                        "fallback_reason": f"{type(exc).__name__}: {exc}",
                    }
            else:
                document_ir = parser.parse(backend, options.pages)
                execution = {"parser": "native", "fallback": False}
            if options.mode in {"fidelity", "hybrid"} and hasattr(backend, "render_page_snapshot"):
                snapshot_dir = workspace.parser_outputs_dir / "page_snapshots"
                pages_with_snapshots = []
                for page in document_ir.pages:
                    snapshot = backend.render_page_snapshot(
                        page.page_number,
                        snapshot_dir / f"page_{page.page_number:03d}.png",
                    )
                    pages_with_snapshots.append(page.model_copy(update={"background_image_path": str(snapshot)}))
                document_ir = document_ir.model_copy(update={"pages": pages_with_snapshots})
            preflight_path.write_text(
                json.dumps(
                    {
                        "available_parsers": router.availability_report(),
                        "open_source_resources": router.resource_report(),
                        "execution": execution,
                        "pages": page_routes,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        ir_path = workspace.ir_dir / "original.json" if options.dump_ir else None
        if ir_path:
            ir_path.write_text(json.dumps(document_ir.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

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
                options=ValidationOptions(visual=options.visual_validate, write_report=True),
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
        )

    def _validate_pages(self, pages: list[int], page_count: int) -> None:
        if not pages:
            raise ValueError("At least one page must be selected")
        invalid = [page for page in pages if page < 1 or page > page_count]
        if invalid:
            raise ValueError(f"Page selection out of range: {invalid}; document has {page_count} pages")
