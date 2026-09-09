"""Headless (offscreen-Qt) smoke test of the desktop app wiring: build a
real digitized document with the engine, feed it into `MainWindow` the
same way the pipeline worker's completion signal does, and exercise the
canvas/panel interactions a user would trigger — without needing a real
display or mouse input.
"""

import cv2

from engine.io.pdf_loader import RasterPage
from engine.model import EntitySource, EntityType, LayerCategory, VectorDocument
from engine.pipeline import PipelineConfig, digitize_page


def _build_document(tmp_path, synthetic_drawing_bgr):
    image_path = str(tmp_path / "page_0000.png")
    cv2.imwrite(image_path, synthetic_drawing_bgr)
    raster_page = RasterPage(index=0, width_px=1000, height_px=800, dpi=300.0, image_path=image_path)
    page = digitize_page(raster_page, PipelineConfig())
    document = VectorDocument(source_file=image_path, units="mm")
    document.add_page(page)
    return document, {0: image_path}


def test_main_window_loads_document_into_canvas(qapp, tmp_path, synthetic_drawing_bgr):
    from app.main_window import MainWindow

    document, raster_paths = _build_document(tmp_path, synthetic_drawing_bgr)

    window = MainWindow()
    window._source_path = document.source_file
    window._pipeline_config = PipelineConfig()
    window._on_pipeline_finished(document, raster_paths)

    page = document.pages[0]
    assert len(window.canvas._entity_items) == len(page.entities)
    assert window._page_label.text() == "Page 1 / 1 — not reviewed"

    # Layer visibility toggling shouldn't raise, and should hide items.
    window.canvas.set_layer_visible(LayerCategory.GRID, False)
    grid_entities = [e for e in page.entities if e.layer == LayerCategory.GRID]
    assert grid_entities, "expected at least one GRID entity from the synthetic drawing"
    for e in grid_entities:
        assert window.canvas._entity_items[e.id].isVisible() is False

    # Confidence heatmap toggle shouldn't raise.
    window.canvas.set_confidence_heatmap(True)
    window.canvas.set_confidence_heatmap(False)

    window.close()


def test_canvas_add_and_delete_line(qapp, tmp_path, synthetic_drawing_bgr):
    from app.main_window import MainWindow

    document, raster_paths = _build_document(tmp_path, synthetic_drawing_bgr)
    window = MainWindow()
    window._source_path = document.source_file
    window._pipeline_config = PipelineConfig()
    window._on_pipeline_finished(document, raster_paths)

    page = document.pages[0]
    initial_count = len(page.entities)

    from PySide6.QtCore import QPointF

    window.canvas._finish_add_line(QPointF(10, 10), QPointF(90, 10))
    assert len(page.entities) == initial_count + 1
    new_entity = page.entities[-1]
    assert new_entity.source == EntitySource.USER
    assert new_entity.type == EntityType.LINE
    assert new_entity.id in window.canvas._entity_items

    window.canvas._delete_entity(new_entity.id)
    assert len(page.entities) == initial_count
    assert new_entity.id not in window.canvas._entity_items

    window.close()


def test_annotation_line_creates_locked_user_entity(qapp, tmp_path, synthetic_drawing_bgr):
    from app.main_window import MainWindow
    from app.tools.edit_tools import Tool

    document, raster_paths = _build_document(tmp_path, synthetic_drawing_bgr)
    window = MainWindow()
    window._source_path = document.source_file
    window._pipeline_config = PipelineConfig()
    window._on_pipeline_finished(document, raster_paths)

    page = document.pages[0]
    window.canvas.set_tool(Tool.ANNOTATE_LINE)
    window.canvas._finish_annotation([(5, 5), (95, 95)])

    assert len(page.annotations) == 1
    locked_entities = [e for e in page.entities if e.locked and e.source == EntitySource.USER]
    assert locked_entities, "expected the annotation line to also create a locked USER entity"

    window.close()


def test_mark_reviewed_then_edit_clears_review(qapp, tmp_path, synthetic_drawing_bgr, monkeypatch):
    from app.main_window import MainWindow
    from PySide6.QtWidgets import QInputDialog

    document, raster_paths = _build_document(tmp_path, synthetic_drawing_bgr)
    window = MainWindow()
    window._source_path = document.source_file
    window._pipeline_config = PipelineConfig()
    window._on_pipeline_finished(document, raster_paths)
    page = document.pages[0]

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("J. Engineer", True)))
    monkeypatch.setattr(QInputDialog, "getMultiLineText", staticmethod(lambda *a, **k: ("Looks good.", True)))

    window.mark_current_page_reviewed()
    assert page.is_reviewed
    assert page.reviewed_by == "J. Engineer"
    assert "reviewed by J. Engineer" in window._page_label.text()

    from PySide6.QtCore import QPointF

    window.canvas._finish_add_line(QPointF(10, 10), QPointF(50, 10))
    assert not page.is_reviewed, "editing the page after sign-off should clear the review status"
    assert "not reviewed" in window._page_label.text()

    window.close()
