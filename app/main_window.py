"""The main application window: menus/toolbar, page navigation, the
canvas, and the dock panels, all wired to `engine/` through plain
function calls plus the two background workers for anything slow.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolBar,
    QWidget,
)

from app.tools.edit_tools import Tool
from app.widgets.canvas_view import CanvasView
from app.widgets.confidence_panel import ConfidencePanel
from app.widgets.export_dialog import ExportDialog
from app.widgets.layers_panel import LayersPanel
from app.widgets.properties_panel import PropertiesPanel
from app.widgets.upload_dialog import UploadDialog
from app.workers import AiAssistWorker, PipelineWorker
from engine.audit import default_log_path, log_event
from engine.model import VectorDocument
from engine.project.manager import load_project, save_project
from engine.project.schema import Project

_TOOL_LABELS = [
    (Tool.SELECT_MOVE, "Select / Move"),
    (Tool.PAN, "Pan"),
    (Tool.ADD_LINE, "Add Line"),
    (Tool.ADD_CIRCLE, "Add Circle"),
    (Tool.ADD_TEXT, "Add Text"),
    (Tool.DELETE, "Delete"),
    (Tool.ANNOTATE_FREEHAND, "Markup: Freehand"),
    (Tool.ANNOTATE_LINE, "Markup: Corrected Line"),
    (Tool.ANNOTATE_REGION, "Markup: Region"),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digitalizer of Drawings for AI")
        self.resize(1400, 900)

        self._work_dir = tempfile.mkdtemp(prefix="digitalizer_")
        self.document: VectorDocument | None = None
        self.project: Project | None = None
        self.raster_paths: dict[int, str] = {}
        self.current_page_index = 0
        self._pipeline_worker: PipelineWorker | None = None
        self._ai_worker: AiAssistWorker | None = None
        self._pipeline_config = None
        self._source_path: str = ""
        self._audit_log_path = default_log_path(str(Path.home() / ".digitalizer"))

        self.canvas = CanvasView()
        self.setCentralWidget(self.canvas)

        self._build_menu()
        self._build_toolbar()
        self._build_docks()
        self._build_statusbar()
        self._connect_canvas_signals()

        self._set_project_loaded(False)

    def _log_audit_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Record a compliance-relevant event (see `engine/audit.py`).

        Logged persistently to `~/.digitalizer/audit_log.jsonl` (not the
        session's temp work dir, which is deleted on close) so the
        record survives across sessions and projects.
        """
        log_event(self._audit_log_path, event_type, details)

    # ------------------------------------------------------------- menu

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        open_action = QAction("Open Drawing…", self)
        open_action.triggered.connect(self.open_drawing)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        open_project_action = QAction("Open Project…", self)
        open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(open_project_action)

        self._save_project_action = QAction("Save Project…", self)
        self._save_project_action.triggered.connect(self.save_project_as)
        file_menu.addAction(self._save_project_action)

        file_menu.addSeparator()

        self._export_action = QAction("Export…", self)
        self._export_action.triggered.connect(self.export_drawing)
        file_menu.addAction(self._export_action)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        settings_menu = self.menuBar().addMenu("&Settings")

        load_standard_action = QAction("Load Firm CAD Standard…", self)
        load_standard_action.triggered.connect(self.load_firm_cad_standard)
        settings_menu.addAction(load_standard_action)

        export_template_action = QAction("Export CAD Standard Template…", self)
        export_template_action.triggered.connect(self.export_cad_standard_template)
        settings_menu.addAction(export_template_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Tools", self)
        toolbar.setOrientation(Qt.Orientation.Vertical)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, toolbar)

        group = QActionGroup(self)
        group.setExclusive(True)
        for tool, label in _TOOL_LABELS:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, t=tool: self.canvas.set_tool(t))
            group.addAction(action)
            toolbar.addAction(action)
        group.actions()[0].setChecked(True)

        toolbar.addSeparator()

        nav = QToolBar("Pages", self)
        prev_btn = QPushButton("◀ Prev")
        next_btn = QPushButton("Next ▶")
        prev_btn.clicked.connect(self.previous_page)
        next_btn.clicked.connect(self.next_page)
        self._page_label = QLabel("No document loaded")
        nav.addWidget(prev_btn)
        nav.addWidget(self._page_label)
        nav.addWidget(next_btn)

        nav.addSeparator()
        review_btn = QPushButton("Mark Page Reviewed…")
        review_btn.clicked.connect(self.mark_current_page_reviewed)
        nav.addWidget(review_btn)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, nav)

    def _build_docks(self) -> None:
        self.layers_panel = LayersPanel()
        self.layers_panel.layerVisibilityChanged.connect(self.canvas.set_layer_visible)
        self._add_dock("Layers", self.layers_panel, Qt.DockWidgetArea.RightDockWidgetArea)

        self.confidence_panel = ConfidencePanel()
        self.confidence_panel.heatmapToggled.connect(self.canvas.set_confidence_heatmap)
        self.confidence_panel.entitySelected.connect(self.canvas.focus_entity)
        self._add_dock("Confidence", self.confidence_panel, Qt.DockWidgetArea.RightDockWidgetArea)

        self.properties_panel = PropertiesPanel()
        self.properties_panel.layerChanged.connect(self._on_layer_changed)
        self.properties_panel.textChanged.connect(self._on_text_changed)
        self._add_dock("Properties", self.properties_panel, Qt.DockWidgetArea.RightDockWidgetArea)

    def _add_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> None:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)

    def _build_statusbar(self) -> None:
        self.statusBar().showMessage("Ready.")

    def _connect_canvas_signals(self) -> None:
        self.canvas.selectionChanged.connect(self.properties_panel.set_entity)
        self.canvas.entitiesChanged.connect(self._on_entities_changed)
        self.canvas.annotationCreated.connect(self._on_annotation_created)
        self.canvas.reprocessRequested.connect(self._on_reprocess_requested)

    # -------------------------------------------------------- open flow

    def open_drawing(self) -> None:
        ai_available = bool(os.environ.get("ANTHROPIC_API_KEY"))
        dialog = UploadDialog(self, ai_assist_available=ai_available)
        if dialog.exec() != UploadDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        if options is None:
            QMessageBox.warning(self, "No file selected", "Please choose a file to digitize.")
            return

        from engine.pipeline import PipelineConfig

        config = PipelineConfig(units=options.units, assumed_dpi=options.assumed_dpi, ai_assist_enabled=options.ai_assist_enabled)
        if options.ai_assist_enabled:
            from engine.llm_assist.claude_vision import ClaudeVisionProvider

            config.ai_provider = ClaudeVisionProvider()

        self._source_path = options.file_path
        self.statusBar().showMessage(f"Digitizing {os.path.basename(options.file_path)}…")
        self.setEnabled(False)

        self._pipeline_worker = PipelineWorker(options.file_path, self._work_dir, config)
        self._pipeline_worker.finished_ok.connect(self._on_pipeline_finished)
        self._pipeline_worker.failed.connect(self._on_pipeline_failed)
        self._pipeline_config = config
        self._pipeline_worker.start()

    def _on_pipeline_finished(self, document: VectorDocument, raster_paths: dict[int, str]) -> None:
        self.setEnabled(True)
        self.document = document
        self.raster_paths = raster_paths
        self.project = Project(
            name=os.path.splitext(os.path.basename(self._source_path))[0],
            source_file_name=self._source_path,
            document=document,
            dpi=document.pages[0].dpi if document.pages else 300.0,
            units=document.units,
            ai_assist_enabled=self._pipeline_config.ai_assist_enabled,
        )
        self.current_page_index = 0
        self._set_project_loaded(True)
        self._show_page(0)
        self._log_audit_event(
            "digitized",
            {
                "source_file": self._source_path,
                "page_count": len(document.pages),
                "ai_assist_enabled": self._pipeline_config.ai_assist_enabled,
            },
        )
        self.statusBar().showMessage(f"Digitized {len(document.pages)} page(s).")

    def _on_pipeline_failed(self, message: str) -> None:
        self.setEnabled(True)
        QMessageBox.critical(self, "Digitization failed", message)
        self.statusBar().showMessage("Digitization failed.")

    # ------------------------------------------------------------- pages

    def _show_page(self, index: int) -> None:
        if not self.document or not (0 <= index < len(self.document.pages)):
            return
        self.current_page_index = index
        page = self.document.pages[index]
        self.canvas.load_page(page, self.raster_paths[index])
        for category, visible in self.layers_panel.visibility_map().items():
            self.canvas.set_layer_visible(category, visible)
        self.confidence_panel.update_for_page(page)
        self.properties_panel.set_entity(None)
        self._update_page_label(page)

    def _update_page_label(self, page) -> None:
        review_status = f"✓ reviewed by {page.reviewed_by}" if page.is_reviewed else "not reviewed"
        self._page_label.setText(
            f"Page {self.current_page_index + 1} / {len(self.document.pages)} — {review_status}"
        )

    def next_page(self) -> None:
        self._show_page(self.current_page_index + 1)

    def previous_page(self) -> None:
        self._show_page(self.current_page_index - 1)

    def mark_current_page_reviewed(self) -> None:
        page = self.canvas.current_page()
        if not page:
            QMessageBox.warning(self, "No page loaded", "Open a drawing first.")
            return

        from PySide6.QtWidgets import QInputDialog

        reviewer, ok = QInputDialog.getText(self, "Mark Page Reviewed", "Reviewer name:")
        if not ok or not reviewer.strip():
            return
        notes, _ = QInputDialog.getMultiLineText(self, "Mark Page Reviewed", "Review notes (optional):")

        page.mark_reviewed(reviewer.strip(), notes.strip())
        self._log_audit_event("page_reviewed", {"page_index": page.index, "reviewer": reviewer.strip()})
        self._update_page_label(page)
        self.statusBar().showMessage(f"Page {page.index + 1} marked reviewed by {reviewer.strip()}.")

    # -------------------------------------------------------- editing

    def _on_entities_changed(self) -> None:
        page = self.canvas.current_page()
        if page:
            from engine.confidence.scoring import rollup_page_confidence

            page.overall_confidence = rollup_page_confidence([e.confidence for e in page.entities])
            self.confidence_panel.update_for_page(page)

            if page.is_reviewed:
                page.clear_review()
                self._update_page_label(page)
                self.statusBar().showMessage(
                    "Page edited after sign-off — review status cleared; please re-review before export.", 6000
                )
        self.setWindowTitle("Digitalizer of Drawings for AI — unsaved changes*")

    def _on_annotation_created(self, annotation) -> None:
        self.statusBar().showMessage(
            "Markup added — right-click it on the canvas to reprocess this region with AI.", 6000
        )

    def _on_layer_changed(self, entity_id: str, layer) -> None:
        self.canvas.update_entity(entity_id, layer=layer)

    def _on_text_changed(self, entity_id: str, text: str) -> None:
        self.canvas.update_entity(entity_id, text=text)

    def _on_reprocess_requested(self, annotation) -> None:
        page = self.canvas.current_page()
        if not page or not getattr(self, "_pipeline_config", None):
            QMessageBox.information(self, "AI assist unavailable", "Open a drawing with AI-assist enabled first.")
            return
        if not self._pipeline_config.ai_assist_enabled:
            QMessageBox.information(
                self, "AI assist disabled", "Re-open this drawing with AI-assist enabled to use this."
            )
            return

        self.statusBar().showMessage("Reprocessing region with AI…")
        self._log_audit_event(
            "ai_assist_invoked",
            {"page_index": page.index, "reason": "user-requested region reprocess"},
        )
        self.setEnabled(False)
        self._ai_worker = AiAssistWorker(page, self._pipeline_config)
        self._ai_worker.finished_ok.connect(self._on_ai_assist_finished)
        self._ai_worker.failed.connect(self._on_pipeline_failed)
        self._ai_worker.start()

    def _on_ai_assist_finished(self, ran: bool) -> None:
        self.setEnabled(True)
        self.canvas.refresh()
        page = self.canvas.current_page()
        if page:
            self.confidence_panel.update_for_page(page)
        self.statusBar().showMessage("AI assist finished." if ran else "AI assist did not run (provider unavailable).")

    # ---------------------------------------------------- CAD standard

    def load_firm_cad_standard(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Firm CAD Standard", "", "JSON (*.json)")
        if not path:
            return
        from engine.cad.layer_registry import load_layer_standard_from_file

        try:
            load_layer_standard_from_file(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not load CAD standard", str(exc))
            return

        self.layers_panel.refresh_from_standard()
        self.canvas.refresh()
        self.statusBar().showMessage(f"Loaded CAD standard from {path}")

    def export_cad_standard_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CAD Standard Template", "layer_standard.json", "JSON (*.json)"
        )
        if not path:
            return
        from engine.cad.layer_registry import export_layer_standard_to_file

        export_layer_standard_to_file(path)
        self.statusBar().showMessage(f"Exported current CAD standard to {path}")

    # ------------------------------------------------------------- save

    def save_project_as(self) -> None:
        if not self.project or not self.document:
            QMessageBox.warning(self, "Nothing to save", "Open a drawing first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Digitalizer Project (*.dgz)")
        if not path:
            return
        self.project.document = self.document
        self.project.snapshot(note="Manual save")
        save_project(self.project, self.raster_paths, path)
        self._log_audit_event("project_saved", {"path": path, "page_count": len(self.document.pages)})
        self.setWindowTitle("Digitalizer of Drawings for AI")
        self.statusBar().showMessage(f"Saved project to {path}")

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Digitalizer Project (*.dgz)")
        if not path:
            return
        extract_dir = tempfile.mkdtemp(prefix="digitalizer_project_")
        project, raster_paths = load_project(path, extract_dir)
        self.project = project
        self.document = project.document
        self.raster_paths = raster_paths
        self.current_page_index = 0
        self._set_project_loaded(True)
        self._show_page(0)
        self._log_audit_event("project_opened", {"path": path})
        self.statusBar().showMessage(f"Opened project {path}")

    # ------------------------------------------------------------ export

    def _confidence_threshold(self) -> float:
        from engine.confidence.scoring import LOW_CONFIDENCE_THRESHOLD

        if self._pipeline_config is not None:
            return self._pipeline_config.confidence_threshold
        return LOW_CONFIDENCE_THRESHOLD

    def export_drawing(self) -> None:
        if not self.document:
            QMessageBox.warning(self, "Nothing to export", "Open a drawing first.")
            return

        from engine.review import evaluate_document_readiness

        readiness = evaluate_document_readiness(self.document, self._confidence_threshold())
        if not readiness.is_clean:
            proceed = QMessageBox.warning(
                self,
                "Not all pages are review-ready",
                "This export has open items:\n\n"
                + "\n".join(readiness.summary_lines())
                + "\n\nConfidence scores are the pipeline's own estimate, not an engineer's "
                "sign-off. Export anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            self._log_audit_event(
                "export_readiness_warning",
                {"issues": readiness.summary_lines(), "proceeded": proceed == QMessageBox.StandardButton.Yes},
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        dialog = ExportDialog(self)
        if dialog.exec() != ExportDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        if options is None:
            return

        os.makedirs(options.out_dir, exist_ok=True)
        messages = []

        dxf_path = os.path.join(options.out_dir, "output.dxf")
        if options.export_dxf or options.export_dwg:
            from engine.cad.dxf_writer import write_dxf

            write_dxf(self.document, dxf_path)
            if options.export_dxf:
                messages.append(f"DXF: {dxf_path}")

        if options.export_pdf:
            from engine.cad.pdf_writer import write_pdf

            pdf_path = os.path.join(options.out_dir, "output.pdf")
            write_pdf(self.document, pdf_path)
            messages.append(f"PDF: {pdf_path}")

        if options.export_dwg:
            from engine.cad.dwg_export import convert_dxf_to_dwg

            result = convert_dxf_to_dwg(dxf_path, options.out_dir)
            messages.append(result.message if not result.success else f"DWG: {result.dwg_path}")
            if not options.export_dxf:
                os.remove(dxf_path)  # was only staged for the DWG conversion step

        self._log_audit_event(
            "exported",
            {
                "out_dir": options.out_dir,
                "dxf": options.export_dxf,
                "pdf": options.export_pdf,
                "dwg": options.export_dwg,
                "all_pages_reviewed": all(p.is_reviewed for p in self.document.pages),
            },
        )
        QMessageBox.information(self, "Export complete", "\n".join(messages) or "Nothing selected.")

    # ------------------------------------------------------------- misc

    def _set_project_loaded(self, loaded: bool) -> None:
        self._save_project_action.setEnabled(loaded)
        self._export_action.setEnabled(loaded)

    def closeEvent(self, event) -> None:
        import shutil

        shutil.rmtree(self._work_dir, ignore_errors=True)
        super().closeEvent(event)
