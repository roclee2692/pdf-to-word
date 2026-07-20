from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pdf2word.domain import DocumentIR
from pdf2word.validation.docx_reader import read_docx_snapshot
from pdf2word.validation.models import LayerSummary, ValidationReport
from pdf2word.validation.structure import validate_images, validate_structure, validate_tables
from pdf2word.validation.text import validate_text
from pdf2word.validation.visual import validate_visual


@dataclass(frozen=True)
class ValidationOptions:
    visual: bool = True
    write_report: bool = True


class ValidationEngine:
    """Run structure/text/table/image/visual checks after DOCX rendering."""

    def evaluate(
        self,
        document_ir: DocumentIR,
        docx_path: str | Path,
        report_dir: str | Path,
        *,
        mode: str,
        source_pdf: str | Path | None = None,
        options: ValidationOptions | None = None,
    ) -> ValidationReport:
        opts = options or ValidationOptions()
        docx_path = Path(docx_path)
        report_dir = Path(report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)

        docx = read_docx_snapshot(docx_path)
        non_flow_layout = mode in {"fidelity", "positioned", "hybrid"} or (
            all(bool(page.background_image_path) for page in document_ir.pages) and bool(document_ir.pages)
        )

        structure_summary, structure_issues = validate_structure(document_ir, docx)
        if non_flow_layout:
            # Snapshot and positioned layouts keep the edit surface inside
            # drawing objects; python-docx's body iterator cannot inspect it.
            text_summary = LayerSummary(
                status="skipped",
                issue_count=0,
                metrics={"reason": f"{mode}_layout_mode"},
                reason=f"{mode} layout keeps text in native positioned drawing objects",
            )
            text_issues = []
            table_summary = LayerSummary(
                status="skipped",
                issue_count=0,
                metrics={"reason": f"{mode}_layout_mode"},
                reason=f"{mode} layout keeps tables inside positioned drawing objects",
            )
            table_issues = []
            # Footer/header warnings are noise when the snapshot carries page chrome.
            structure_issues = [
                issue
                for issue in structure_issues
                if issue.code not in {"header_not_in_docx", "footer_not_in_docx"}
            ]
            structure_summary = structure_summary.model_copy(
                update={
                    "issue_count": len(structure_issues),
                    "status": "pass"
                    if not structure_issues
                    else (
                        "fail"
                        if any(i.severity == "error" for i in structure_issues)
                        else "warn"
                    ),
                }
            )
        else:
            text_summary, text_issues = validate_text(document_ir, docx)
            table_summary, table_issues = validate_tables(document_ir, docx)

        image_summary, image_issues = validate_images(document_ir, docx)
        # Continuous editable flow targets ≈ source page count (tolerance 1).
        # Fidelity requires exact page alignment.
        page_tol = 0 if non_flow_layout else 1
        visual_summary, visual_issues = validate_visual(
            document_ir,
            docx_path,
            report_dir / "visual",
            source_pdf=Path(source_pdf) if source_pdf else None,
            enabled=opts.visual,
            expect_page_count_match=True,
            page_count_tolerance=page_tol,
        )

        issues = structure_issues + text_issues + table_issues + image_issues + visual_issues
        # Visual skip must not fail the job; only hard errors fail.
        hard_fail_layers = {
            issue.layer
            for issue in issues
            if issue.severity == "error" and issue.layer != "visual"
        }
        # Visual errors only fail when visual layer actually ran.
        if visual_summary.status == "fail":
            hard_fail_layers.add("visual")

        report = ValidationReport(
            mode=mode,
            passed=not hard_fail_layers,
            structure=structure_summary,
            text=text_summary,
            table=table_summary,
            image=image_summary,
            visual=visual_summary,
            issues=issues,
        )

        if opts.write_report:
            path = report_dir / "validation_report.json"
            path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            self._write_markdown_summary(report, report_dir / "validation_report.md")
        return report

    def _write_markdown_summary(self, report: ValidationReport, path: Path) -> None:
        lines = [
            "# Validation Report",
            "",
            f"- mode: `{report.mode}`",
            f"- passed: **{report.passed}**",
            f"- issues: {len(report.issues)}",
            "",
            "| Layer | Status | Issues |",
            "| --- | --- | ---: |",
        ]
        for name in ("structure", "text", "table", "image", "visual"):
            layer: LayerSummary = getattr(report, name)
            note = f" ({layer.reason})" if layer.reason else ""
            lines.append(f"| {name} | {layer.status}{note} | {layer.issue_count} |")
        visual_metrics = report.visual.metrics or {}
        if visual_metrics:
            lines.extend(
                [
                    "",
                    "## Visual metrics",
                    "",
                    f"- source pages: `{visual_metrics.get('source_page_count')}`",
                    f"- rendered pages: `{visual_metrics.get('rendered_page_count')}`",
                    f"- page delta: `{visual_metrics.get('page_count_delta')}`",
                    f"- mean MAD: `{visual_metrics.get('mean_mad')}`",
                    f"- pairing: `{visual_metrics.get('mad_pairing')}`",
                ]
            )
        if report.issues:
            lines.extend(["", "## Issues", ""])
            for issue in report.issues:
                page = f" page={issue.page}" if issue.page is not None else ""
                lines.append(f"- **{issue.severity}** `{issue.layer}/{issue.code}`{page}: {issue.message}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
