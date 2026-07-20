from __future__ import annotations

import re
import unicodedata

from pdf2word.domain import DocumentIR
from pdf2word.validation.docx_reader import DocxSnapshot
from pdf2word.validation.models import LayerSummary, ValidationIssue


_WHITESPACE_RE = re.compile(r"\s+")
_DIGIT_RE = re.compile(r"\d")


def normalize_text(value: str) -> str:
    collapsed = _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", value or "")).strip()
    return collapsed


def extract_ir_body_text(document_ir: DocumentIR) -> str:
    chunks: list[str] = []
    for page in document_ir.pages:
        for element in page.ordered_elements():
            if element.type in {"header", "footer", "page_number", "separator", "blank_space"}:
                continue
            if element.type == "table" and element.table is not None:
                for row in element.table.rows:
                    for cell in row:
                        if cell is not None and cell.text:
                            chunks.append(cell.text)
                continue
            if element.type == "formula" and element.formula is not None:
                chunks.append(element.formula.fallback_text or element.text or "")
                continue
            if element.text:
                chunks.append(element.text)
    return "\n".join(chunk for chunk in chunks if chunk)


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein CER. 0.0 is perfect; 1.0+ means worse than empty output."""
    if not reference and not hypothesis:
        return 0.0
    if not reference:
        return 1.0
    distance = _levenshtein(reference, hypothesis)
    return distance / max(1, len(reference))


def digit_error_rate(reference: str, hypothesis: str) -> float:
    ref_digits = "".join(_DIGIT_RE.findall(reference))
    hyp_digits = "".join(_DIGIT_RE.findall(hypothesis))
    if not ref_digits and not hyp_digits:
        return 0.0
    if not ref_digits:
        return 1.0
    return _levenshtein(ref_digits, hyp_digits) / max(1, len(ref_digits))


def validate_text(document_ir: DocumentIR, docx: DocxSnapshot) -> tuple[LayerSummary, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    ir_text = normalize_text(extract_ir_body_text(document_ir))
    docx_text = normalize_text(docx.body_text)
    cer = character_error_rate(ir_text, docx_text)
    der = digit_error_rate(ir_text, docx_text)
    ir_len = len(ir_text)
    docx_len = len(docx_text)
    coverage = (min(ir_len, docx_len) / ir_len) if ir_len else 1.0

    metrics = {
        "ir_char_count": ir_len,
        "docx_char_count": docx_len,
        "character_error_rate": round(cer, 4),
        "digit_error_rate": round(der, 4),
        "length_coverage": round(coverage, 4),
        "ir_preview": ir_text[:160],
        "docx_preview": docx_text[:160],
    }

    if ir_len == 0 and docx_len == 0:
        return LayerSummary(status="pass", issue_count=0, metrics=metrics), issues

    if ir_len > 0 and docx_len == 0:
        issues.append(
            ValidationIssue(
                layer="text",
                severity="error",
                code="docx_text_empty",
                message="IR has body text but DOCX extraction is empty",
                metrics=metrics,
            )
        )
    if cer > 0.35:
        issues.append(
            ValidationIssue(
                layer="text",
                severity="error",
                code="high_character_error_rate",
                message=f"Character error rate {cer:.3f} exceeds 0.35",
                metrics={"character_error_rate": cer},
            )
        )
    elif cer > 0.12:
        issues.append(
            ValidationIssue(
                layer="text",
                severity="warning",
                code="elevated_character_error_rate",
                message=f"Character error rate {cer:.3f} exceeds 0.12",
                metrics={"character_error_rate": cer},
            )
        )
    if der > 0.05:
        issues.append(
            ValidationIssue(
                layer="text",
                severity="warning" if der <= 0.2 else "error",
                code="digit_error_rate",
                message=f"Digit error rate {der:.3f}",
                metrics={"digit_error_rate": der},
            )
        )
    if coverage < 0.7:
        issues.append(
            ValidationIssue(
                layer="text",
                severity="warning",
                code="low_text_coverage",
                message=f"DOCX length coverage against IR is only {coverage:.3f}",
                metrics={"length_coverage": coverage},
            )
        )

    status = "pass"
    if any(issue.severity == "error" for issue in issues):
        status = "fail"
    elif issues:
        status = "warn"
    return LayerSummary(status=status, issue_count=len(issues), metrics=metrics), issues


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    # Banded-friendly classic DP with two rows.
    previous = list(range(len(right) + 1))
    for i, left_ch in enumerate(left, start=1):
        current = [i]
        for j, right_ch in enumerate(right, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if left_ch == right_ch else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]
