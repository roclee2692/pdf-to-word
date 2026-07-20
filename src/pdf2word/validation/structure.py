from __future__ import annotations

from collections import Counter

from pdf2word.domain import DocumentIR
from pdf2word.validation.docx_reader import DocxSnapshot
from pdf2word.validation.models import LayerSummary, ValidationIssue


def validate_structure(document_ir: DocumentIR, docx: DocxSnapshot) -> tuple[LayerSummary, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    ir_pages = len(document_ir.pages)
    ir_headings = 0
    ir_paragraphs = 0
    ir_tables = 0
    ir_images = 0
    ir_headers = 0
    ir_footers = 0
    missing_image_assets = 0
    empty_text_elements = 0
    reading_order_issues = 0

    for page in document_ir.pages:
        orders = [element.reading_order for element in page.elements]
        if orders and (sorted(orders) != list(range(min(orders), min(orders) + len(orders))) or len(set(orders)) != len(orders)):
            reading_order_issues += 1
            issues.append(
                ValidationIssue(
                    layer="structure",
                    severity="warning",
                    code="reading_order_gap_or_duplicate",
                    message=f"Page {page.page_number} has gaps or duplicates in reading_order",
                    page=page.page_number,
                    metrics={"orders": orders},
                )
            )
        for element in page.elements:
            if element.type == "heading":
                ir_headings += 1
            elif element.type == "paragraph":
                ir_paragraphs += 1
            elif element.type == "table":
                ir_tables += 1
            elif element.type == "image":
                ir_images += 1
                if element.image is None or not element.image.image_path:
                    missing_image_assets += 1
                    issues.append(
                        ValidationIssue(
                            layer="image",
                            severity="error",
                            code="missing_image_asset",
                            message="Image element has no materializable image_path",
                            page=page.page_number,
                            element_id=element.id,
                        )
                    )
            elif element.type == "header":
                ir_headers += 1
            elif element.type == "footer":
                ir_footers += 1

            if element.type in {"paragraph", "heading", "caption"} and not (element.text or "").strip():
                empty_text_elements += 1

    if ir_pages == 0:
        issues.append(
            ValidationIssue(
                layer="structure",
                severity="error",
                code="empty_document",
                message="IR contains no pages",
            )
        )

    # Continuous editable layout intentionally uses one flowing section.
    if 1 < docx.section_count < ir_pages:
        issues.append(
            ValidationIssue(
                layer="structure",
                severity="warning",
                code="section_count_below_page_count",
                message=(
                    f"DOCX has {docx.section_count} section(s) for {ir_pages} IR page(s); "
                    "page-specific headers/footers may be collapsed"
                ),
                metrics={"docx_sections": docx.section_count, "ir_pages": ir_pages},
            )
        )

    if empty_text_elements > max(5, ir_paragraphs // 2):
        issues.append(
            ValidationIssue(
                layer="structure",
                severity="warning",
                code="empty_paragraph_explosion",
                message=f"IR has {empty_text_elements} empty text elements",
                metrics={"empty_text_elements": empty_text_elements},
            )
        )

    if ir_headers and not docx.header_texts:
        issues.append(
            ValidationIssue(
                layer="structure",
                severity="warning",
                code="header_not_in_docx",
                message=f"IR has {ir_headers} header element(s) but DOCX headers are empty",
            )
        )
    if ir_footers and not docx.footer_texts and not getattr(docx, "has_footer_page_field", False):
        issues.append(
            ValidationIssue(
                layer="structure",
                severity="warning",
                code="footer_not_in_docx",
                message=f"IR has {ir_footers} footer element(s) but DOCX footers are empty",
            )
        )

    type_counts = Counter(
        element.type for page in document_ir.pages for element in page.elements
    )
    metrics = {
        "ir_pages": ir_pages,
        "ir_headings": ir_headings,
        "ir_paragraphs": ir_paragraphs,
        "ir_tables": ir_tables,
        "ir_images": ir_images,
        "ir_headers": ir_headers,
        "ir_footers": ir_footers,
        "docx_paragraphs": docx.paragraph_count,
        "docx_headings": docx.heading_count,
        "docx_tables": docx.table_count,
        "docx_images": docx.image_count,
        "docx_sections": docx.section_count,
        "empty_text_elements": empty_text_elements,
        "reading_order_issues": reading_order_issues,
        "missing_image_assets": missing_image_assets,
        "element_type_counts": dict(type_counts),
    }
    structure_issues = [issue for issue in issues if issue.layer == "structure"]
    status = _status_from_issues(structure_issues)
    return LayerSummary(status=status, issue_count=len(structure_issues), metrics=metrics), issues


def validate_tables(document_ir: DocumentIR, docx: DocxSnapshot) -> tuple[LayerSummary, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    ir_tables = [
        element
        for page in document_ir.pages
        for element in page.elements
        if element.type == "table" and element.table is not None
    ]
    metrics: dict[str, object] = {
        "ir_table_count": len(ir_tables),
        "docx_table_count": docx.table_count,
        "row_mismatches": 0,
        "column_mismatches": 0,
    }

    if len(ir_tables) != docx.table_count:
        issues.append(
            ValidationIssue(
                layer="table",
                severity="warning" if ir_tables and docx.table_count else "error",
                code="table_count_mismatch",
                message=f"IR tables={len(ir_tables)} DOCX tables={docx.table_count}",
                metrics={"ir": len(ir_tables), "docx": docx.table_count},
            )
        )

    for index, element in enumerate(ir_tables):
        assert element.table is not None
        if index >= len(docx.tables):
            break
        rendered = docx.tables[index]
        if element.table.row_count and element.table.row_count != rendered.row_count:
            metrics["row_mismatches"] = int(metrics["row_mismatches"]) + 1
            issues.append(
                ValidationIssue(
                    layer="table",
                    severity="warning",
                    code="table_row_count_mismatch",
                    message=(
                        f"Table {index + 1} rows IR={element.table.row_count} "
                        f"DOCX={rendered.row_count}"
                    ),
                    element_id=element.id,
                    page=element.provenance.source_page,
                )
            )
        if element.table.column_count and element.table.column_count != rendered.column_count:
            metrics["column_mismatches"] = int(metrics["column_mismatches"]) + 1
            issues.append(
                ValidationIssue(
                    layer="table",
                    severity="warning",
                    code="table_column_count_mismatch",
                    message=(
                        f"Table {index + 1} columns IR={element.table.column_count} "
                        f"DOCX={rendered.column_count}"
                    ),
                    element_id=element.id,
                    page=element.provenance.source_page,
                )
            )

    status = _status_from_issues(issues) if ir_tables or docx.table_count else "pass"
    if not ir_tables and not docx.table_count:
        status = "pass"
    return LayerSummary(status=status, issue_count=len(issues), metrics=metrics), issues


def validate_images(document_ir: DocumentIR, docx: DocxSnapshot) -> tuple[LayerSummary, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    ir_images = [
        element
        for page in document_ir.pages
        for element in page.elements
        if element.type == "image"
    ]
    for element in ir_images:
        if element.image is None or not element.image.image_path:
            issues.append(
                ValidationIssue(
                    layer="image",
                    severity="error",
                    code="missing_image_asset",
                    message="Image element has no materializable image_path",
                    page=element.provenance.source_page,
                    element_id=element.id,
                )
            )
        elif element.image.image_path:
            from pathlib import Path

            if not Path(element.image.image_path).exists():
                issues.append(
                    ValidationIssue(
                        layer="image",
                        severity="error",
                        code="image_file_missing",
                        message=f"Image path does not exist: {element.image.image_path}",
                        page=element.provenance.source_page,
                        element_id=element.id,
                    )
                )

    if ir_images and docx.image_count == 0:
        issues.append(
            ValidationIssue(
                layer="image",
                severity="error",
                code="images_not_in_docx",
                message=f"IR has {len(ir_images)} image(s) but DOCX contains none",
            )
        )
    elif ir_images and docx.image_count < len(ir_images):
        issues.append(
            ValidationIssue(
                layer="image",
                severity="warning",
                code="image_count_below_ir",
                message=f"IR images={len(ir_images)} DOCX images={docx.image_count}",
            )
        )

    metrics = {
        "ir_image_count": len(ir_images),
        "docx_image_count": docx.image_count,
    }
    status = _status_from_issues(issues) if ir_images or docx.image_count else "pass"
    return LayerSummary(status=status, issue_count=len(issues), metrics=metrics), issues


def _status_from_issues(issues: list[ValidationIssue]) -> str:
    if any(issue.severity == "error" for issue in issues):
        return "fail"
    if any(issue.severity == "warning" for issue in issues):
        return "warn"
    return "pass"
