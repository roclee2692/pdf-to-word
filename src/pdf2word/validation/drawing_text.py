from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from pdf2word.domain import DocumentIR
from pdf2word.validation.models import LayerSummary, ValidationIssue
from pdf2word.validation.text import extract_ir_body_text, normalize_text

_W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def extract_docx_all_text(path: str | Path) -> str:
    """Collect all ``w:t`` text from document.xml, including DrawingML text boxes."""
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        try:
            xml = archive.read("word/document.xml")
        except KeyError:
            return ""
    root = ET.fromstring(xml)
    parts: list[str] = []
    for node in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
        if node.text:
            parts.append(node.text)
    return normalize_text("".join(parts))


def validate_drawing_text(
    document_ir: DocumentIR,
    docx_path: str | Path,
    *,
    mode: str,
) -> tuple[LayerSummary, list[ValidationIssue]]:
    """Ensure positioned/hybrid DrawingML packages still carry body text."""
    issues: list[ValidationIssue] = []
    ir_text = normalize_text(extract_ir_body_text(document_ir))
    docx_text = extract_docx_all_text(docx_path)
    ir_len = len(ir_text)
    docx_len = len(docx_text)
    metrics = {
        "mode": mode,
        "ir_char_count": ir_len,
        "docx_xml_char_count": docx_len,
        "coverage": (docx_len / ir_len) if ir_len else 1.0,
    }

    if ir_len >= 40 and docx_len == 0:
        issues.append(
            ValidationIssue(
                layer="text",
                severity="error",
                code="drawing_text_empty",
                message=(
                    f"{mode} DOCX has no extractable w:t text while IR body has {ir_len} characters"
                ),
            )
        )
    elif ir_len >= 80 and docx_len < max(20, int(ir_len * 0.15)):
        issues.append(
            ValidationIssue(
                layer="text",
                severity="error" if mode == "positioned" else "warning",
                code="drawing_text_sparse",
                message=(
                    f"{mode} DOCX text coverage is low: IR={ir_len} chars, "
                    f"DOCX w:t={docx_len} chars (ratio={metrics['coverage']:.3f})"
                ),
            )
        )

    # hybrid may vanish text for paint but OOXML should still store it
    if mode == "hybrid" and ir_len >= 40 and docx_len == 0:
        issues.append(
            ValidationIssue(
                layer="text",
                severity="error",
                code="hybrid_vanish_layer_missing",
                message="hybrid mode snapshot present but editable vanish text layer is empty",
            )
        )

    if any(i.severity == "error" for i in issues):
        status = "fail"
    elif issues:
        status = "warn"
    else:
        status = "pass"
    return LayerSummary(status=status, issue_count=len(issues), metrics=metrics), issues


def docx_contains_frame_pr(path: str | Path) -> bool:
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    return bool(re.search(r"w:framePr\b", xml))
