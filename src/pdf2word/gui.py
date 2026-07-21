from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from pdf2word.cli import parse_page_selection
from pdf2word.pdf_backends import PdfPlumberBackend
from pdf2word.routing import ParserRouter, PreflightAnalyzer
from pdf2word.services import ConversionOptions, ConversionService


def _resolve_pages(pdf_path: Path, selection: str) -> list[int]:
    if selection.strip():
        return parse_page_selection(selection)
    with PdfPlumberBackend(pdf_path) as backend:
        return list(range(1, backend.page_count() + 1))


def launch_gui(on_ready: Callable[[object], None] | None = None) -> int:
    """Launch the optional PySide6 desktop shell around the CLI service."""
    try:
        from PySide6.QtCore import QThread, QUrl, Qt, Signal
        from PySide6.QtGui import QDesktopServices, QPixmap
        from PySide6.QtWidgets import (
            QApplication,
            QDialog,
            QFileDialog,
            QFormLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPlainTextEdit,
            QProgressBar,
            QPushButton,
            QComboBox,
            QScrollArea,
            QSpinBox,
            QSplitter,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 is optional. Install the GUI extra with `python -m pip install -e '.[gui]'`."
        ) from exc

    class PdfDropLineEdit(QLineEdit):
        file_dropped = Signal(str)

        def __init__(self):
            super().__init__()
            self.setAcceptDrops(True)

        def dragEnterEvent(self, event) -> None:
            urls = event.mimeData().urls()
            if any(url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf") for url in urls):
                event.acceptProposedAction()
            else:
                event.ignore()

        def dropEvent(self, event) -> None:
            for url in event.mimeData().urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                    self.file_dropped.emit(url.toLocalFile())
                    event.acceptProposedAction()
                    return
            event.ignore()

    class PreflightWorker(QThread):
        completed = Signal(object)
        failed = Signal(str)

        def __init__(self, pdf_path: Path, pages: list[int]):
            super().__init__()
            self.pdf_path = pdf_path
            self.pages = pages

        def run(self) -> None:
            try:
                with PdfPlumberBackend(self.pdf_path) as backend:
                    findings = PreflightAnalyzer().analyze_pages(backend, self.pages)
                    router = ParserRouter()
                    payload = {
                        "pages": [
                            {
                                **finding.__dict__,
                                "preferred_parser": router.choose_parser(finding),
                                "selected_parser": router.choose_available_parser(finding),
                            }
                            for finding in findings
                        ],
                        "available_parsers": router.availability_report(),
                    }
                self.completed.emit(payload)
            except Exception as exc:  # pragma: no cover - exercised by the GUI runtime
                self.failed.emit(f"{type(exc).__name__}: {exc}")

    class ConvertWorker(QThread):
        completed = Signal(object)
        failed = Signal(str)

        def __init__(self, pdf_path: Path, pages: list[int], output: Path, mode: str):
            super().__init__()
            self.pdf_path = pdf_path
            self.pages = pages
            self.output = output
            self.mode = mode

        def run(self) -> None:
            try:
                result = ConversionService().convert(
                    self.pdf_path,
                    self.output,
                    ConversionOptions(
                        pages=self.pages,
                        mode=self.mode,
                        dump_ir=True,
                        workspace_root=Path("workspace"),
                        validate=True,
                        visual_validate=True,
                    ),
                )
                self.completed.emit(result)
            except Exception as exc:  # pragma: no cover - exercised by the GUI runtime
                self.failed.emit(f"{type(exc).__name__}: {exc}")

    class PreviewPane(QWidget):
        """A page image that fits the pane while remaining scrollable."""

        def __init__(self, title: str):
            super().__init__()
            self._source_pixmap = QPixmap()
            title_label = QLabel(title)
            title_label.setStyleSheet("font-weight: 600; padding: 4px 0;")
            self._image = QLabel("No preview available")
            self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._image.setMinimumSize(240, 320)
            self._image.setStyleSheet(
                "background: #f4f5f7; border: 1px solid #c9cdd3; color: #68707a;"
            )
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scroll.setWidget(self._image)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(title_label)
            layout.addWidget(scroll, 1)
            self._scroll = scroll

        def set_image(self, path: Path | None) -> None:
            self._source_pixmap = QPixmap(str(path)) if path and path.exists() else QPixmap()
            self._refresh_image()

        def _refresh_image(self) -> None:
            if self._source_pixmap.isNull():
                self._image.setPixmap(QPixmap())
                self._image.setText("No preview available")
                return
            self._image.setText("")
            viewport = self._scroll.viewport().size()
            max_width = max(240, viewport.width() - 18)
            max_height = max(320, viewport.height() - 18)
            scaled = self._source_pixmap.scaled(
                max_width,
                max_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._image.setPixmap(scaled)
            self._image.resize(scaled.size())

        def resizeEvent(self, event) -> None:  # pragma: no cover - Qt layout callback
            super().resizeEvent(event)
            self._refresh_image()

    class ComparisonDialog(QDialog):
        """Side-by-side visual comparison of the source PDF and rendered DOCX."""

        def __init__(self, parent, pdf_path: Path, result: object, pages: list[int], mode: str):
            super().__init__(parent)
            self.setWindowTitle(f"PDF / Word 对照预览 — {mode}")
            self.resize(1320, 860)
            self._result = result
            self._pages = pages

            report = getattr(result, "validation_report", None)
            visual = getattr(report, "visual", None)
            visual_metrics = getattr(visual, "metrics", None) or {}
            text = getattr(report, "text", None)
            text_metrics = getattr(text, "metrics", None) or {}
            ir = getattr(result, "document_ir", None)
            element_names = [
                type(element).__name__
                for page in getattr(ir, "pages", [])
                for element in page.elements
            ]
            table_count = element_names.count("TableElement")
            formula_count = element_names.count("FormulaElement")
            image_count = element_names.count("ImageElement")
            editability = {
                "editable": "正文、原生表格可编辑；复杂公式以文字/上下标 fallback 保留",
                "positioned": "原生定位对象可编辑；部分公式使用视觉裁剪图，不能承诺完全可编辑",
                "hybrid": "视觉快照优先；对象层隐藏，仅用于检索/替换，不是主编辑版本",
                "fidelity": "视觉快照优先，不作为主要可编辑版本",
            }.get(mode, "请打开 DOCX 在 Word/WPS/LibreOffice 中检查编辑")
            summary = (
                f"源 PDF：{pdf_path.name}    模式：{mode}    "
                f"页数：{visual_metrics.get('source_page_count', len(pages))} → "
                f"{visual_metrics.get('rendered_page_count', '?')}    "
                f"MAD：{visual_metrics.get('mean_mad', 'n/a')}    "
                f"CER：{text_metrics.get('character_error_rate', 'n/a')}\n"
                f"IR 元素：表格 {table_count} · 公式 {formula_count} · 图片 {image_count}\n"
                f"编辑性：{editability}"
            )
            summary_label = QLabel(summary)
            summary_label.setWordWrap(True)
            summary_label.setStyleSheet(
                "padding: 6px; background: #f4f5f7; border: 1px solid #d5d9df;"
            )

            self._page_spin = QSpinBox()
            self._page_spin.setRange(1, max(1, len(pages)))
            self._page_spin.valueChanged.connect(self._show_page)
            controls = QHBoxLayout()
            controls.addWidget(QLabel("对照页"))
            controls.addWidget(self._page_spin)
            controls.addWidget(QLabel("（左：PDF；右：DOCX 经 LibreOffice 渲染页）"))
            controls.addStretch(1)
            open_button = QPushButton("在默认 Word 应用中打开")
            open_button.clicked.connect(self._open_output)
            close_button = QPushButton("关闭")
            close_button.clicked.connect(self.close)
            controls.addWidget(open_button)
            controls.addWidget(close_button)

            self._source_pane = PreviewPane("源 PDF")
            self._output_pane = PreviewPane("转换后 DOCX")
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._source_pane)
            splitter.addWidget(self._output_pane)
            splitter.setSizes([640, 640])

            layout = QVBoxLayout(self)
            layout.addWidget(summary_label)
            layout.addLayout(controls)
            layout.addWidget(splitter, 1)
            self._show_page(1)

        def _show_page(self, page_index: int) -> None:
            index = max(0, page_index - 1)
            source_page = self._pages[index] if index < len(self._pages) else None
            validation_dir = getattr(getattr(self._result, "workspace", None), "validation_dir", None)
            visual_dir = Path(validation_dir) / "visual" if validation_dir else None
            source_path = (
                visual_dir / "source_pages" / f"page_{source_page:03d}.png"
                if visual_dir and source_page
                else None
            )
            output_path = (
                visual_dir / "docx_pages" / f"page_{index + 1:03d}.png"
                if visual_dir
                else None
            )
            self._source_pane.set_image(source_path)
            self._output_pane.set_image(output_path)

        def _open_output(self) -> None:
            output = getattr(self._result, "output_path", None)
            if output:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(output)))

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("PDF to Word")
            self.resize(980, 680)
            self._worker = None
            self._last_output: Path | None = None
            self._preview_dialog: QDialog | None = None

            source_edit = PdfDropLineEdit()
            source_edit.setPlaceholderText("Select a PDF file")
            source_edit.file_dropped.connect(self._set_source_path)
            source_button = QPushButton("Browse")
            source_button.clicked.connect(self._choose_source)
            source_row = QHBoxLayout()
            source_row.addWidget(source_edit, 1)
            source_row.addWidget(source_button)

            pages_edit = QLineEdit("")
            pages_edit.setPlaceholderText("Blank = all pages; example: 1,3-5")
            mode_combo = QComboBox()
            # Deliverable defaults first; hybrid/fidelity are pixel-proof tools only.
            mode_combo.addItem("positioned — 可编辑交付 (DrawingML)", "positioned")
            mode_combo.addItem("editable — 流式可编辑", "editable")
            mode_combo.addItem("hybrid — 像素校对(非主交付)", "hybrid")
            mode_combo.addItem("fidelity — 像素证明(非主交付)", "fidelity")
            mode_combo.setCurrentIndex(0)
            mode_combo.setToolTip(
                "positioned/editable: native editable objects.\n"
                "hybrid/fidelity: pixel-proof tools (page snapshots), not primary editable deliverables."
            )

            output_edit = QLineEdit()
            output_edit.setPlaceholderText("Optional DOCX path")
            output_button = QPushButton("Browse")
            output_button.clicked.connect(self._choose_output)
            output_row = QHBoxLayout()
            output_row.addWidget(output_edit, 1)
            output_row.addWidget(output_button)

            form = QFormLayout()
            form.addRow("PDF", source_row)
            form.addRow("Pages", pages_edit)
            form.addRow("Mode", mode_combo)
            form.addRow("DOCX", output_row)

            preflight_button = QPushButton("Preflight")
            convert_button = QPushButton("Convert")
            open_button = QPushButton("Open output")
            open_button.setEnabled(False)
            preflight_button.clicked.connect(self._run_preflight)
            convert_button.clicked.connect(self._run_convert)
            open_button.clicked.connect(self._open_output)
            button_row = QHBoxLayout()
            button_row.addWidget(preflight_button)
            button_row.addWidget(convert_button)
            button_row.addStretch(1)
            button_row.addWidget(open_button)

            progress = QProgressBar()
            progress.setRange(0, 1)
            progress.setValue(0)
            status = QLabel("Ready")
            log = QPlainTextEdit()
            log.setReadOnly(True)

            central = QWidget()
            layout = QVBoxLayout(central)
            layout.addLayout(form)
            layout.addLayout(button_row)
            layout.addWidget(progress)
            layout.addWidget(status)
            layout.addWidget(log, 1)
            self.setCentralWidget(central)

            self._source_edit = source_edit
            self._pages_edit = pages_edit
            self._mode_combo = mode_combo
            self._output_edit = output_edit
            self._preflight_button = preflight_button
            self._convert_button = convert_button
            self._open_button = open_button
            self._progress = progress
            self._status = status
            self._log = log

        def _choose_source(self) -> None:
            path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF files (*.pdf)")
            if path:
                self._set_source_path(path)

        def _set_source_path(self, path: str) -> None:
            self._source_edit.setText(path)
            if not self._output_edit.text().strip():
                self._output_edit.setText(str(Path(path).with_suffix(".docx")))

        def _choose_output(self) -> None:
            path, _ = QFileDialog.getSaveFileName(self, "Save DOCX", "", "Word files (*.docx)")
            if path:
                self._output_edit.setText(path)

        def _inputs(self) -> tuple[Path, list[int], Path, str] | None:
            pdf_path = Path(self._source_edit.text().strip()).expanduser()
            if not pdf_path.is_file():
                QMessageBox.warning(self, "Missing input", "Select an existing PDF file first.")
                return None
            try:
                pages = _resolve_pages(pdf_path, self._pages_edit.text())
            except Exception as exc:
                QMessageBox.warning(self, "Invalid pages", str(exc))
                return None
            output_text = self._output_edit.text().strip()
            output = Path(output_text).expanduser() if output_text else pdf_path.with_suffix(".docx")
            mode = self._mode_combo.currentData() or self._mode_combo.currentText()
            if isinstance(mode, str) and "—" in mode:
                mode = mode.split("—", 1)[0].strip()
            return pdf_path, pages, output, str(mode)

        def _set_busy(self, busy: bool, message: str) -> None:
            self._preflight_button.setEnabled(not busy)
            self._convert_button.setEnabled(not busy)
            self._progress.setRange(0, 0 if busy else 1)
            if not busy:
                self._progress.setValue(0)
            self._status.setText(message)

        def _run_preflight(self) -> None:
            inputs = self._inputs()
            if inputs is None:
                return
            pdf_path, pages, _, _ = inputs
            self._set_busy(True, "Running preflight...")
            self._log.appendPlainText(f"PREFLIGHT {pdf_path} pages={pages}")
            self._worker = PreflightWorker(pdf_path, pages)
            self._worker.completed.connect(self._preflight_done)
            self._worker.failed.connect(self._worker_failed)
            self._worker.finished.connect(self._worker.deleteLater)
            self._worker.start()

        def _preflight_done(self, payload: object) -> None:
            self._set_busy(False, "Preflight complete")
            data = payload if isinstance(payload, dict) else {}
            pages = data.get("pages") or []
            no_text = [p.get("page_no") for p in pages if not p.get("has_text_layer")]
            degraded = [
                p for p in pages if p.get("preferred_parser") != p.get("selected_parser")
            ]
            available = data.get("available_parsers") or {}
            external = any(available.get(name) for name in ("mineru", "paddleocr", "docling"))
            if no_text and not external:
                warn = (
                    "WARNING: scanned / no-text-layer page(s) "
                    f"{no_text[:12]} and external OCR parsers are unavailable. "
                    "Convert will fall back to native (limited quality)."
                )
                self._log.appendPlainText(warn)
                QMessageBox.warning(self, "Scanned PDF risk", warn)
            if degraded:
                self._log.appendPlainText(
                    f"WARNING: {len(degraded)} page(s) will use a degraded parser "
                    f"(preferred → selected mismatch)."
                )
            self._log.appendPlainText(json.dumps(data, ensure_ascii=False, indent=2))

        def _run_convert(self) -> None:
            inputs = self._inputs()
            if inputs is None:
                return
            pdf_path, pages, output, mode = inputs
            self._set_busy(True, "Converting...")
            self._log.appendPlainText(f"CONVERT mode={mode} output={output}")
            self._worker = ConvertWorker(pdf_path, pages, output, mode)
            self._worker.completed.connect(self._convert_done)
            self._worker.failed.connect(self._worker_failed)
            self._worker.finished.connect(self._worker.deleteLater)
            self._worker.start()

        def _convert_done(self, result: object) -> None:
            self._set_busy(False, "Conversion complete")
            self._last_output = getattr(result, "output_path", None)
            self._open_button.setEnabled(bool(self._last_output))
            report = getattr(result, "validation_report", None)
            visual = getattr(report, "visual", None)
            visual_metrics = getattr(visual, "metrics", None) or {}
            text = getattr(report, "text", None)
            text_metrics = getattr(text, "metrics", None) or {}
            summary = {
                "docx": str(getattr(result, "output_path", "")),
                "preflight": str(getattr(result, "preflight_path", "")),
                "validation": str(getattr(result, "validation_path", "")),
                "passed": getattr(report, "passed", None),
                "source_pages": visual_metrics.get("source_page_count"),
                "rendered_pages": visual_metrics.get("rendered_page_count"),
                "mean_mad": visual_metrics.get("mean_mad"),
                "cer": text_metrics.get("character_error_rate"),
            }
            self._log.appendPlainText(json.dumps(summary, ensure_ascii=False, indent=2))
            pdf_path = Path(self._source_edit.text().strip()).expanduser()
            pages = [page.page_number for page in getattr(getattr(result, "document_ir", None), "pages", [])]
            mode = self._mode_combo.currentData() or "positioned"
            if self._preview_dialog is not None:
                self._preview_dialog.close()
            self._preview_dialog = ComparisonDialog(self, pdf_path, result, pages, str(mode))
            self._preview_dialog.show()

        def _worker_failed(self, message: str) -> None:
            self._set_busy(False, "Failed")
            self._log.appendPlainText(message)
            QMessageBox.critical(self, "PDF to Word failed", message)

        def _open_output(self) -> None:
            if self._last_output:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output)))

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    if on_ready is not None:
        on_ready(window)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(launch_gui())
