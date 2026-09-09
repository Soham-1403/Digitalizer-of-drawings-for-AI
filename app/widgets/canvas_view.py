"""The canvas: raster underlay + vector overlay + annotation/edit tools.

This is the one widget where "the visualizer" and "the editor" are the
same surface, on purpose — a reviewer marks up the original scan, sees
the digitized geometry, and corrects it, all in one coordinate space
(page pixel space; `engine.model` entities are already in that space, so
no transform is needed to lay them over the raster image).
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QInputDialog,
    QMenu,
)

from app.tools.annotation_tools import build_annotation
from app.tools.edit_tools import Tool, translate_points
from engine.cad.layer_registry import get_layer_standard
from engine.model import Entity, EntitySource, EntityType, LayerCategory, Page

ENTITY_ID_KEY = 0

_HEATMAP_STOPS = [
    (0.0, (224, 49, 49)),
    (0.5, (240, 180, 20)),
    (1.0, (47, 158, 68)),
]


def _confidence_color(confidence: float) -> QColor:
    c = max(0.0, min(1.0, confidence))
    for (t0, c0), (t1, c1) in zip(_HEATMAP_STOPS[:-1], _HEATMAP_STOPS[1:]):
        if t0 <= c <= t1:
            f = (c - t0) / (t1 - t0) if t1 > t0 else 0.0
            return QColor(
                round(c0[0] + f * (c1[0] - c0[0])),
                round(c0[1] + f * (c1[1] - c0[1])),
                round(c0[2] + f * (c1[2] - c0[2])),
            )
    return QColor(*_HEATMAP_STOPS[-1][1])


def _pen_for_layer(layer: LayerCategory) -> QPen:
    spec = get_layer_standard()[layer]
    pen = QPen(QColor(spec.rgb_hex))
    pen.setWidthF(max(1.0, spec.lineweight_hundredth_mm / 12.0))
    pen.setStyle(Qt.PenStyle.DashLine if spec.linetype in ("DASHED", "CENTER") else Qt.PenStyle.SolidLine)
    return pen


def _markup_pen() -> QPen:
    pen = QPen(QColor(get_layer_standard()[LayerCategory.USER_MARKUP].rgb_hex))
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setWidthF(2.0)
    return pen


class CanvasView(QGraphicsView):
    entitiesChanged = Signal()
    annotationCreated = Signal(object)  # Annotation
    selectionChanged = Signal(object)  # Optional[Entity]
    reprocessRequested = Signal(object)  # Annotation

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self._page: Optional[Page] = None
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._entity_items: dict[str, QGraphicsItem] = {}
        self._annotation_items: list[QGraphicsItem] = []
        self._layer_visibility: dict[LayerCategory, bool] = {c: True for c in LayerCategory}
        self._heatmap_enabled = False
        self._tool = Tool.SELECT_MOVE
        self._default_new_layer = LayerCategory.UNCLASSIFIED

        self._drag_start: Optional[QPointF] = None
        self._stroke_points: list[tuple[float, float]] = []
        self._temp_item: Optional[QGraphicsItem] = None

        self._scene.selectionChanged.connect(self._on_selection_changed)

    # ---------------------------------------------------------------- page

    def load_page(self, page: Page, image_path: str) -> None:
        self._scene.clear()
        self._entity_items.clear()
        self._annotation_items.clear()
        self._page = page

        pixmap = QPixmap(image_path)
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._pixmap_item.setZValue(-100)
        self._scene.setSceneRect(0, 0, max(1, pixmap.width()), max(1, pixmap.height()))

        self._render_entities()
        self._render_annotations()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def refresh(self) -> None:
        """Full re-render — used after AI-assist fuses new entities into
        `page.entities` from outside this widget.
        """
        for item in self._entity_items.values():
            self._scene.removeItem(item)
        self._entity_items.clear()
        self._render_entities()
        self._render_annotations()

    def current_page(self) -> Optional[Page]:
        return self._page

    def focus_entity(self, entity_id: str) -> None:
        """Select an entity and scroll it into view — used by the
        confidence panel's "jump to this detection" list.
        """
        item = self._entity_items.get(entity_id)
        if not item:
            return
        self._scene.clearSelection()
        item.setSelected(True)
        self.centerOn(item)

    # ------------------------------------------------------------ layers

    def set_layer_visible(self, layer: LayerCategory, visible: bool) -> None:
        self._layer_visibility[layer] = visible
        if not self._page:
            return
        for entity in self._page.entities:
            if entity.layer == layer:
                item = self._entity_items.get(entity.id)
                if item:
                    item.setVisible(visible)

    def set_confidence_heatmap(self, enabled: bool) -> None:
        self._heatmap_enabled = enabled
        if not self._page:
            return
        for entity in self._page.entities:
            item = self._entity_items.get(entity.id)
            if not item:
                continue
            pen = _pen_for_layer(entity.layer)
            if enabled:
                pen.setColor(_confidence_color(entity.confidence))
            self._apply_pen_recursive(item, pen)

    def set_default_new_layer(self, layer: LayerCategory) -> None:
        self._default_new_layer = layer

    def _apply_pen_recursive(self, item: QGraphicsItem, pen: QPen) -> None:
        if isinstance(item, QGraphicsSimpleTextItem):
            item.setBrush(pen.color())
        elif hasattr(item, "setPen"):
            item.setPen(pen)
        for child in item.childItems():
            self._apply_pen_recursive(child, pen)

    # ------------------------------------------------------------- tools

    def set_tool(self, tool: Tool) -> None:
        self._tool = tool
        self._stroke_points = []
        self._drag_start = None
        self._clear_temp_item()

        movable = tool == Tool.SELECT_MOVE
        for item in self._entity_items.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)

        self.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag if tool == Tool.PAN else QGraphicsView.DragMode.NoDrag
        )

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    # --------------------------------------------------------- rendering

    def _render_entities(self) -> None:
        if not self._page:
            return
        for entity in self._page.entities:
            self._add_entity_item(entity)

    def _add_entity_item(self, entity: Entity) -> None:
        item = self._make_entity_item(entity)
        if item is None:
            return
        item.setData(ENTITY_ID_KEY, entity.id)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, self._tool == Tool.SELECT_MOVE)
        item.setVisible(self._layer_visibility.get(entity.layer, True))
        self._scene.addItem(item)
        self._entity_items[entity.id] = item

    def _make_entity_item(self, entity: Entity) -> Optional[QGraphicsItem]:
        pen = _pen_for_layer(entity.layer)
        if self._heatmap_enabled:
            pen.setColor(_confidence_color(entity.confidence))

        if entity.type == EntityType.LINE:
            (x0, y0), (x1, y1) = entity.points
            item = self._scene_line_item(x0, y0, x1, y1, pen)

        elif entity.type == EntityType.POLYLINE:
            path = QPainterPath()
            path.moveTo(*entity.points[0])
            for p in entity.points[1:]:
                path.lineTo(*p)
            item = QGraphicsPathItem(path)
            item.setPen(pen)

        elif entity.type == EntityType.CIRCLE:
            cx, cy = entity.points[0]
            r = float(entity.params.get("radius", 5.0))
            item = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
            item.setPen(pen)

        elif entity.type == EntityType.ARC:
            cx, cy = entity.points[0]
            r = float(entity.params.get("radius", 5.0))
            start = float(entity.params.get("start_angle_deg", 0.0))
            end = float(entity.params.get("end_angle_deg", 90.0))
            span = (end - start) % 360 or 360.0
            path = QPainterPath()
            path.arcMoveTo(cx - r, cy - r, r * 2, r * 2, -start)
            path.arcTo(cx - r, cy - r, r * 2, r * 2, -start, -span)
            item = QGraphicsPathItem(path)
            item.setPen(pen)

        elif entity.type == EntityType.HATCH:
            path = QPainterPath()
            path.moveTo(*entity.points[0])
            for p in entity.points[1:]:
                path.lineTo(*p)
            path.closeSubpath()
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            if entity.params.get("is_hatch_pattern"):
                fill = QColor(pen.color())
                fill.setAlpha(40)
                item.setBrush(fill)

        elif entity.type in (EntityType.TEXT, EntityType.DIMENSION):
            x, y = entity.points[0]
            height = float(entity.params.get("height_px", 12.0))
            item = QGraphicsSimpleTextItem(entity.text or "")
            font = item.font()
            font.setPixelSize(max(6, int(height)))
            item.setFont(font)
            item.setPos(x, y - height)
            item.setBrush(pen.color())
            if entity.type == EntityType.DIMENSION and len(entity.points) >= 2:
                x1, y1 = entity.points[1]
                leader = self._scene_line_item(x - item.x(), y - item.y(), x1 - item.x(), y1 - item.y(), pen, parent=item)

        else:  # pragma: no cover - exhaustive over EntityType
            return None

        return item

    @staticmethod
    def _scene_line_item(x0, y0, x1, y1, pen, parent=None):
        from PySide6.QtWidgets import QGraphicsLineItem

        item = QGraphicsLineItem(x0, y0, x1, y1, parent) if parent else QGraphicsLineItem(x0, y0, x1, y1)
        item.setPen(pen)
        return item

    def _render_annotations(self) -> None:
        for item in self._annotation_items:
            self._scene.removeItem(item)
        self._annotation_items = []

        if not self._page:
            return
        for annotation in self._page.annotations:
            path = QPainterPath()
            path.moveTo(*annotation.points[0])
            for p in annotation.points[1:]:
                path.lineTo(*p)
            if annotation.kind == "region":
                path.closeSubpath()
            item = self._scene.addPath(path, _markup_pen())
            item.setZValue(100)
            item.setToolTip(annotation.note or "(no note)")
            self._annotation_items.append(item)

    # ------------------------------------------------------------ mouse

    def mousePressEvent(self, event) -> None:
        pos = self.mapToScene(event.pos())

        if self._tool == Tool.DELETE:
            item = self._scene.itemAt(pos, self.transform())
            entity_id = item.data(ENTITY_ID_KEY) if item else None
            if entity_id:
                self._delete_entity(entity_id)
            return

        if self._tool == Tool.ADD_TEXT:
            self._prompt_add_text(pos)
            return

        if self._tool == Tool.ANNOTATE_REGION:
            self._stroke_points.append((pos.x(), pos.y()))
            self._update_polyline_preview(self._stroke_points, _markup_pen())
            return

        if self._tool in (Tool.ADD_LINE, Tool.ADD_CIRCLE, Tool.ANNOTATE_LINE):
            self._drag_start = pos
            self._stroke_points = [(pos.x(), pos.y())]
            return

        if self._tool == Tool.ANNOTATE_FREEHAND:
            self._stroke_points = [(pos.x(), pos.y())]
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = self.mapToScene(event.pos())

        if self._tool in (Tool.ADD_LINE, Tool.ANNOTATE_LINE) and self._drag_start is not None:
            pen = _markup_pen() if self._tool == Tool.ANNOTATE_LINE else _pen_for_layer(self._default_new_layer)
            self._update_polyline_preview([(self._drag_start.x(), self._drag_start.y()), (pos.x(), pos.y())], pen)
        elif self._tool == Tool.ADD_CIRCLE and self._drag_start is not None:
            self._update_circle_preview(self._drag_start, pos)
        elif self._tool == Tool.ANNOTATE_FREEHAND and self._stroke_points:
            self._stroke_points.append((pos.x(), pos.y()))
            self._update_polyline_preview(self._stroke_points, _markup_pen())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        pos = self.mapToScene(event.pos())

        if self._tool == Tool.ADD_LINE and self._drag_start is not None:
            self._finish_add_line(self._drag_start, pos)
        elif self._tool == Tool.ADD_CIRCLE and self._drag_start is not None:
            self._finish_add_circle(self._drag_start, pos)
        elif self._tool == Tool.ANNOTATE_LINE and self._drag_start is not None:
            self._finish_annotation([(self._drag_start.x(), self._drag_start.y()), (pos.x(), pos.y())])
        elif self._tool == Tool.ANNOTATE_FREEHAND and self._stroke_points:
            self._stroke_points.append((pos.x(), pos.y()))
            self._finish_annotation(self._stroke_points)
        elif self._tool == Tool.SELECT_MOVE:
            super().mouseReleaseEvent(event)
            self._finish_move()
        else:
            super().mouseReleaseEvent(event)

        self._drag_start = None
        if self._tool != Tool.ANNOTATE_REGION:
            self._stroke_points = []
        self._clear_temp_item()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._tool == Tool.ANNOTATE_REGION and len(self._stroke_points) >= 3:
            self._finish_annotation(self._stroke_points)
            self._stroke_points = []
            self._clear_temp_item()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        if not self._page or not self._page.annotations:
            super().contextMenuEvent(event)
            return

        pos = self.mapToScene(event.pos())
        nearest = min(
            self._page.annotations,
            key=lambda a: min(math.hypot(pos.x() - ax, pos.y() - ay) for ax, ay in a.points),
        )
        menu = QMenu(self)
        action = menu.addAction("Reprocess this region with AI")
        chosen = menu.exec(event.globalPos())
        if chosen == action:
            self.reprocessRequested.emit(nearest)

    # -------------------------------------------------------- edit ops

    def _clear_temp_item(self) -> None:
        if self._temp_item is not None:
            self._scene.removeItem(self._temp_item)
            self._temp_item = None

    def _update_polyline_preview(self, points: list[tuple[float, float]], pen: QPen) -> None:
        self._clear_temp_item()
        if len(points) < 2:
            return
        path = QPainterPath()
        path.moveTo(*points[0])
        for p in points[1:]:
            path.lineTo(*p)
        self._temp_item = self._scene.addPath(path, pen)
        self._temp_item.setZValue(200)

    def _update_circle_preview(self, start: QPointF, end: QPointF) -> None:
        self._clear_temp_item()
        r = math.hypot(end.x() - start.x(), end.y() - start.y())
        pen = _pen_for_layer(self._default_new_layer)
        self._temp_item = self._scene.addEllipse(start.x() - r, start.y() - r, r * 2, r * 2, pen)
        self._temp_item.setZValue(200)

    def _finish_add_line(self, start: QPointF, end: QPointF) -> None:
        if not self._page or (start - end).manhattanLength() < 1:
            return
        entity = Entity(
            type=EntityType.LINE,
            points=[(start.x(), start.y()), (end.x(), end.y())],
            layer=self._default_new_layer,
            confidence=1.0,
            source=EntitySource.USER,
            page_index=self._page.index,
            locked=True,
        )
        self._page.entities.append(entity)
        self._add_entity_item(entity)
        self.entitiesChanged.emit()

    def _finish_add_circle(self, start: QPointF, end: QPointF) -> None:
        if not self._page:
            return
        r = math.hypot(end.x() - start.x(), end.y() - start.y())
        if r < 2:
            return
        entity = Entity(
            type=EntityType.CIRCLE,
            points=[(start.x(), start.y())],
            layer=self._default_new_layer,
            confidence=1.0,
            source=EntitySource.USER,
            page_index=self._page.index,
            locked=True,
            params={"radius": r},
        )
        self._page.entities.append(entity)
        self._add_entity_item(entity)
        self.entitiesChanged.emit()

    def _prompt_add_text(self, pos: QPointF) -> None:
        if not self._page:
            return
        text, ok = QInputDialog.getText(self, "Add Text", "Text:")
        if not ok or not text.strip():
            return
        entity = Entity(
            type=EntityType.TEXT,
            points=[(pos.x(), pos.y())],
            layer=LayerCategory.TEXT,
            confidence=1.0,
            source=EntitySource.USER,
            page_index=self._page.index,
            locked=True,
            text=text.strip(),
            params={"height_px": 14.0},
        )
        self._page.entities.append(entity)
        self._add_entity_item(entity)
        self.entitiesChanged.emit()

    def _delete_entity(self, entity_id: str) -> None:
        if not self._page:
            return
        self._page.entities = [e for e in self._page.entities if e.id != entity_id]
        item = self._entity_items.pop(entity_id, None)
        if item:
            self._scene.removeItem(item)
        self.entitiesChanged.emit()

    def _finish_annotation(self, raw_points: list[tuple[float, float]]) -> None:
        if not self._page:
            return
        annotation = build_annotation(self._tool, raw_points, self._page.index)
        if annotation is None:
            return
        self._page.annotations.append(annotation)
        self._render_annotations()

        if annotation.kind == "line":
            from engine.llm_assist.fusion import apply_user_annotation

            entity = apply_user_annotation(self._page, annotation)
            if entity:
                self._add_entity_item(entity)

        self.annotationCreated.emit(annotation)
        self.entitiesChanged.emit()

    def _finish_move(self) -> None:
        if not self._page:
            return
        moved_any = False
        for item in list(self._scene.selectedItems()):
            entity_id = item.data(ENTITY_ID_KEY)
            if not entity_id:
                continue
            delta = item.pos()
            if delta.isNull():
                continue
            entity = next((e for e in self._page.entities if e.id == entity_id), None)
            if entity is None:
                continue

            entity.points = translate_points(entity.points, delta.x(), delta.y())
            entity.source = EntitySource.USER
            entity.confidence = 1.0
            entity.locked = True
            entity.touch()
            moved_any = True

            self._scene.removeItem(item)
            del self._entity_items[entity_id]
            self._add_entity_item(entity)
            self._entity_items[entity_id].setSelected(True)

        if moved_any:
            self.entitiesChanged.emit()

    def update_entity(self, entity_id: str, **fields) -> None:
        """Apply a properties-panel edit (layer reassignment, text, ...)."""
        if not self._page:
            return
        entity = next((e for e in self._page.entities if e.id == entity_id), None)
        if not entity:
            return
        for key, value in fields.items():
            setattr(entity, key, value)
        entity.source = EntitySource.USER
        entity.locked = True
        entity.touch()

        old_item = self._entity_items.pop(entity_id, None)
        if old_item:
            self._scene.removeItem(old_item)
        self._add_entity_item(entity)
        self.entitiesChanged.emit()

    def _on_selection_changed(self) -> None:
        items = self._scene.selectedItems()
        if not items or not self._page:
            self.selectionChanged.emit(None)
            return
        entity_id = items[0].data(ENTITY_ID_KEY)
        entity = next((e for e in self._page.entities if e.id == entity_id), None)
        self.selectionChanged.emit(entity)
