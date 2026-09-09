"""Background QThread workers.

Digitization (CV + OCR, and optionally an LLM call) takes real time —
running it on the UI thread would freeze the whole app on every upload
and every "reprocess with AI" click.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from engine.model import Page
from engine.pipeline import PipelineConfig, rerun_ai_assist_on_page, run_pipeline


class PipelineWorker(QThread):
    finished_ok = Signal(object, dict)  # VectorDocument, {page_index: image_path}
    failed = Signal(str)

    def __init__(self, source_path: str, out_dir: str, config: PipelineConfig, parent=None):
        super().__init__(parent)
        self._source_path = source_path
        self._out_dir = out_dir
        self._config = config

    def run(self) -> None:
        try:
            document = run_pipeline(self._source_path, self._out_dir, self._config)
            image_paths = {p.index: p.source_image_path for p in document.pages}
            self.finished_ok.emit(document, image_paths)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self.failed.emit(str(exc))


class AiAssistWorker(QThread):
    finished_ok = Signal(bool)  # True if the provider actually ran
    failed = Signal(str)

    def __init__(self, page: Page, config: PipelineConfig, parent=None):
        super().__init__(parent)
        self._page = page
        self._config = config

    def run(self) -> None:
        try:
            ran = rerun_ai_assist_on_page(self._page, self._config)
            self.finished_ok.emit(ran)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
