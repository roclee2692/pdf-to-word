import os
import unittest
from pathlib import Path


@unittest.skipUnless(os.environ.get("PDF2WORD_GUI_SMOKE") == "1", "set PDF2WORD_GUI_SMOKE=1 for the desktop smoke test")
class GuiSmokeTests(unittest.TestCase):
    def test_preflight_and_all_render_modes_through_gui(self):
        os.environ.setdefault(
            "PDF2WORD_SOFFICE",
            "/Users/raelon/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice",
        )
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from pdf2word.gui import launch_gui

        root = Path(__file__).resolve().parents[2]
        pdf_path = root / "NIPS-2017-attention-is-all-you-need-Paper.pdf"
        output_dir = root / "workspace" / "jobs" / "gui-smoke"
        modes = ["editable", "positioned", "hybrid", "fidelity"]
        results: dict[str, object] = {}
        errors: list[str] = []

        def fail(message: str) -> None:
            errors.append(message)
            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(0, app.quit)

        def start_modes(window, index: int = 0) -> None:
            if errors:
                return
            if index >= len(modes):
                log_text = window._log.toPlainText()
                if '"source_pages"' not in log_text or '"mean_mad"' not in log_text or '"cer"' not in log_text:
                    fail("GUI validation summary is missing pages/MAD/CER fields")
                    return
                window._open_button.click()
                QTimer.singleShot(50, QApplication.instance().quit)
                return
            mode = modes[index]
            mode_index = window._mode_combo.findData(mode)
            if mode_index < 0:
                # Fallback for plain-text combo items
                mode_index = window._mode_combo.findText(mode)
            window._mode_combo.setCurrentIndex(max(0, mode_index))
            output = output_dir / f"{mode}.docx"
            window._output_edit.setText(str(output))
            window._convert_button.click()
            worker = window._worker

            def completed(result, current_mode=mode, next_index=index + 1):
                report = getattr(result, "validation_report", None)
                if report is None or not report.passed:
                    fail(f"{current_mode}: validation did not pass")
                    return
                output_path = Path(result.output_path)
                if not output_path.is_file():
                    fail(f"{current_mode}: output DOCX missing")
                    return
                metrics = report.visual.metrics or {}
                if metrics.get("rendered_page_count") != 11:
                    fail(f"{current_mode}: rendered page count is {metrics.get('rendered_page_count')}")
                    return
                visual_metrics = getattr(report.visual, "metrics", None) or {}
                text_metrics = getattr(report.text, "metrics", None) or {}
                if visual_metrics.get("source_page_count") != 11:
                    fail(f"{current_mode}: source page count missing from validation")
                    return
                if "mean_mad" not in visual_metrics:
                    fail(f"{current_mode}: MAD missing from validation")
                    return
                # Editable formulas preserve caret/underscore structure as
                # superscript/subscript runs; allow the small text-reader
                # delta while keeping the smoke test strict on content loss.
                if current_mode == "editable" and float(text_metrics.get("character_error_rate") or 1.0) > 0.005:
                    fail(f"{current_mode}: CER is {text_metrics.get('character_error_rate')}")
                    return
                results[current_mode] = result
                QTimer.singleShot(100, lambda: start_modes(window, next_index))

            worker.completed.connect(completed)
            worker.failed.connect(fail)

        def ready(window) -> None:
            if not window._source_edit.acceptDrops():
                fail("PDF source field does not accept file drops")
                return
            window._source_edit.setText(str(pdf_path))
            window._pages_edit.setText("1-11")

            def preflight_completed(payload) -> None:
                if not isinstance(payload, dict) or len(payload.get("pages", [])) != 11:
                    fail("preflight did not return all 11 pages")
                    return
                QTimer.singleShot(100, lambda: start_modes(window))

            def start_preflight() -> None:
                window._preflight_button.click()
                worker = window._worker
                worker.completed.connect(preflight_completed)
                worker.failed.connect(fail)

            QTimer.singleShot(0, start_preflight)

        app = QApplication.instance() or QApplication([])
        exit_code = launch_gui(on_ready=ready)
        self.assertEqual(exit_code, 0)
        self.assertFalse(errors, errors)
        self.assertEqual(set(results), set(modes))


if __name__ == "__main__":
    unittest.main()
