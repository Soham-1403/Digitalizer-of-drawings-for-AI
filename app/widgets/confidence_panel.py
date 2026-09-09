"""Confidence panel: heatmap toggle + a triage list of low-confidence
detections for the current page, so a reviewer can jump straight to
what needs attention instead of scanning the whole drawing.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from engine.model import Page


class ConfidencePanel(QWidget):
    heatmapToggled = Signal(bool)
    entitySelected = Signal(str)  # entity id

    def __init__(self, parent=None, low_confidence_threshold: float = 0.55):
        super().__init__(parent)
        self._threshold = low_confidence_threshold

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Confidence</b>"))

        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setFormat("Page confidence: %p%")
        layout.addWidget(self._overall_bar)

        self._heatmap_checkbox = QCheckBox("Show confidence heatmap")
        self._heatmap_checkbox.toggled.connect(self.heatmapToggled.emit)
        layout.addWidget(self._heatmap_checkbox)

        layout.addWidget(QLabel(f"Detections below {low_confidence_threshold:.0%} confidence:"))
        self._low_conf_list = QListWidget()
        self._low_conf_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._low_conf_list)

    def update_for_page(self, page: Page) -> None:
        overall = page.overall_confidence or 0.0
        self._overall_bar.setValue(round(overall * 100))

        self._low_conf_list.clear()
        low_confidence = sorted(
            (e for e in page.entities if e.confidence < self._threshold),
            key=lambda e: e.confidence,
        )
        for entity in low_confidence:
            label = f"{entity.layer.value} · {entity.type.value} · {entity.confidence:.0%} ({entity.source.value})"
            item = QListWidgetItem(label)
            item.setData(1, entity.id)
            self._low_conf_list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        entity_id = item.data(1)
        if entity_id:
            self.entitySelected.emit(entity_id)
