from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from pdf2word.domain import DocumentIR
from pdf2word.validation.models import LayerSummary, ValidationIssue


def find_soffice() -> Path | None:
    configured = os.environ.get("PDF2WORD_SOFFICE") or os.environ.get("SOFFICE_PATH")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    which = shutil.which("soffice") or shutil.which("libreoffice")
    if which:
        candidates.append(Path(which))
    candidates.extend(
        [
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            Path("/usr/bin/soffice"),
            Path("/usr/bin/libreoffice"),
            Path("/usr/local/bin/soffice"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def mean_absolute_difference(left_path: Path, right_path: Path) -> float:
    from PIL import Image

    left = Image.open(left_path).convert("L")
    right = Image.open(right_path).convert("L")
    if left.size != right.size:
        right = right.resize(left.size)
    left_px = list(left.getdata())
    right_px = list(right.getdata())
    if not left_px:
        return 0.0
    total = sum(abs(a - b) for a, b in zip(left_px, right_px))
    return total / (len(left_px) * 255.0)


def render_pdf_pages(pdf_path: Path, output_dir: Path, dpi: int = 120) -> list[Path]:
    """Render each PDF page to PNG via pypdfium2."""
    import pypdfium2 as pdfium

    output_dir.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(pdf_path))
    scale = dpi / 72.0
    paths: list[Path] = []
    try:
        for index in range(len(document)):
            page = document[index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            path = output_dir / f"page_{index + 1:03d}.png"
            image.save(path)
            paths.append(path)
            page.close()
    finally:
        document.close()
    return paths


def convert_docx_to_pdf(docx_path: Path, output_dir: Path, soffice: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_root = "/private/tmp" if Path("/private/tmp").is_dir() else None
    with tempfile.TemporaryDirectory(prefix="pdf2word_soffice_profile_", dir=profile_root) as profile:
        env = os.environ.copy()
        env["HOME"] = profile
        env["XDG_CONFIG_HOME"] = str(Path(profile) / "xdg_config")
        env["XDG_CACHE_HOME"] = str(Path(profile) / "xdg_cache")
        Path(env["XDG_CONFIG_HOME"]).mkdir(parents=True, exist_ok=True)
        Path(env["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)
        command = [
            str(soffice),
            f"-env:UserInstallation=file://{profile}",
            "--headless",
            "--nologo",
            "--nolockcheck",
            "--nodefault",
            "--norestore",
            "--nofirststartwizard",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(docx_path),
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
    pdf_path = output_dir / f"{docx_path.stem}.pdf"
    if completed.returncode != 0 or not pdf_path.exists():
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"LibreOffice conversion failed: {detail[:400]}")
    return pdf_path


def validate_visual(
    document_ir: DocumentIR,
    docx_path: Path,
    work_dir: Path,
    *,
    source_pdf: Path | None = None,
    enabled: bool = True,
    mad_warn: float = 0.08,
    mad_fail: float = 0.20,
    expect_page_count_match: bool = True,
    page_count_tolerance: int = 0,
) -> tuple[LayerSummary, list[ValidationIssue]]:
    """Compare source PDF pages against LibreOffice-rendered DOCX pages when possible."""
    issues: list[ValidationIssue] = []
    metrics: dict[str, object] = {
        "enabled": enabled,
        "page_count": len(document_ir.pages),
        "expect_page_count_match": expect_page_count_match,
        "page_count_tolerance": page_count_tolerance,
    }

    if not enabled:
        return (
            LayerSummary(status="skipped", issue_count=0, metrics=metrics, reason="visual validation disabled"),
            issues,
        )

    soffice = find_soffice()
    if soffice is None:
        return (
            LayerSummary(
                status="skipped",
                issue_count=0,
                metrics=metrics,
                reason="LibreOffice soffice not found; install it or set PDF2WORD_SOFFICE",
            ),
            issues,
        )
    metrics["soffice"] = str(soffice)

    if source_pdf is None or not Path(source_pdf).exists():
        # Fall back to IR background snapshots when present (fidelity mode).
        snapshot_paths = [
            Path(page.background_image_path)
            for page in document_ir.pages
            if page.background_image_path
        ]
        if not snapshot_paths or any(not path.exists() for path in snapshot_paths):
            return (
                LayerSummary(
                    status="skipped",
                    issue_count=0,
                    metrics=metrics,
                    reason="source PDF unavailable and no IR page snapshots present",
                ),
                issues,
            )
        source_pages = snapshot_paths
        metrics["source"] = "ir_page_snapshots"
    else:
        source_dir = work_dir / "source_pages"
        source_pages = render_pdf_pages(Path(source_pdf), source_dir)
        # Restrict to the converted IR pages by page_number order.
        page_numbers = [page.page_number for page in document_ir.pages]
        source_pages = [source_dir / f"page_{number:03d}.png" for number in page_numbers]
        metrics["source"] = str(source_pdf)

    try:
        rendered_pdf = convert_docx_to_pdf(Path(docx_path), work_dir / "docx_pdf", soffice)
        rendered_pages = render_pdf_pages(rendered_pdf, work_dir / "docx_pages")
    except Exception as exc:  # noqa: BLE001 - surface tool failures as skipped/fail metrics
        issues.append(
            ValidationIssue(
                layer="visual",
                severity="warning",
                code="visual_render_failed",
                message=str(exc),
            )
        )
        return LayerSummary(status="warn", issue_count=len(issues), metrics=metrics, reason=str(exc)), issues

    metrics["source_page_count"] = len(source_pages)
    metrics["rendered_page_count"] = len(rendered_pages)
    metrics["page_count_delta"] = len(rendered_pages) - len(source_pages)

    delta = abs(len(rendered_pages) - len(source_pages))
    page_counts_match = delta == 0
    page_counts_ok = delta <= max(0, page_count_tolerance)
    if not page_counts_ok:
        issues.append(
            ValidationIssue(
                layer="visual",
                severity="error" if expect_page_count_match else "warning",
                code="page_count_mismatch",
                message=(
                    f"Source visual pages={len(source_pages)} "
                    f"DOCX-rendered pages={len(rendered_pages)} "
                    f"(delta={len(rendered_pages) - len(source_pages)}, "
                    f"tolerance={page_count_tolerance})"
                ),
                metrics={
                    "source_page_count": len(source_pages),
                    "rendered_page_count": len(rendered_pages),
                    "page_count_delta": len(rendered_pages) - len(source_pages),
                    "page_count_tolerance": page_count_tolerance,
                },
            )
        )
    elif not page_counts_match:
        issues.append(
            ValidationIssue(
                layer="visual",
                severity="warning",
                code="page_count_near_match",
                message=(
                    f"Source visual pages={len(source_pages)} "
                    f"DOCX-rendered pages={len(rendered_pages)} "
                    f"(within tolerance {page_count_tolerance})"
                ),
                metrics={
                    "source_page_count": len(source_pages),
                    "rendered_page_count": len(rendered_pages),
                    "page_count_delta": len(rendered_pages) - len(source_pages),
                },
            )
        )

    page_scores: list[dict[str, object]] = []
    # Only pair 1:1 MAD when page counts match; otherwise prefix pairing is misleading
    # for overflow pages and is recorded only as a diagnostic under partial_pairing.
    if page_counts_match:
        metrics["mad_pairing"] = "aligned"
        pair_count = len(source_pages)
    else:
        metrics["mad_pairing"] = "prefix_diagnostic_only"
        pair_count = min(len(source_pages), len(rendered_pages))

    for index in range(pair_count):
        left = source_pages[index]
        right = rendered_pages[index]
        if not left.exists() or not right.exists():
            issues.append(
                ValidationIssue(
                    layer="visual",
                    severity="warning",
                    code="missing_render_artifact",
                    message=f"Missing render artifact for page pair {index + 1}",
                    page=document_ir.pages[index].page_number if index < len(document_ir.pages) else None,
                )
            )
            continue
        mad = mean_absolute_difference(left, right)
        page_no = document_ir.pages[index].page_number if index < len(document_ir.pages) else index + 1
        page_scores.append({"page": page_no, "mean_absolute_difference": round(mad, 4)})
        # MAD thresholds only enforce hard fail when pages are aligned 1:1.
        if not page_counts_match:
            continue
        if mad >= mad_fail:
            issues.append(
                ValidationIssue(
                    layer="visual",
                    severity="error",
                    code="high_visual_difference",
                    message=f"Page {page_no} MAD {mad:.3f} exceeds fail threshold {mad_fail}",
                    page=page_no,
                    metrics={"mean_absolute_difference": mad},
                )
            )
        elif mad >= mad_warn:
            issues.append(
                ValidationIssue(
                    layer="visual",
                    severity="warning",
                    code="elevated_visual_difference",
                    message=f"Page {page_no} MAD {mad:.3f} exceeds warn threshold {mad_warn}",
                    page=page_no,
                    metrics={"mean_absolute_difference": mad},
                )
            )

    metrics["pages"] = page_scores
    if page_scores:
        metrics["mean_mad"] = round(
            sum(float(item["mean_absolute_difference"]) for item in page_scores) / len(page_scores),
            4,
        )

    status = "pass"
    if any(issue.severity == "error" for issue in issues):
        status = "fail"
    elif issues:
        status = "warn"
    return LayerSummary(status=status, issue_count=len(issues), metrics=metrics), issues
