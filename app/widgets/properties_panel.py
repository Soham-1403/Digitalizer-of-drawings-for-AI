"""Properties panel for the currently-selected canvas entity: layer
reassignment and text editing, the two corrections a reviewer makes most
often without needing to redraw geometry from scratch.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from engine.model import Entity, LayerCategory


class PropertiesPanel(QWidget):
    layerChanged = Signal(str, object)  # entity_id, LayerCategory
    textChanged = Signal(str, str)  # entity_id, text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entity: Optional[Entity] = None
        self._suspend_signals = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Properties</b>"))

        form = QFormLayout()
        self._id_label = QLabel("—")
        self._type_label = QLabel("—")
        self._confidence_label = QLabel("—")
        self._source_label = QLabel("—")

        self._layer_combo = QComboBox()
        for category in LayerCategory:
            self._layer_combo.addItem(category.value, category)
        self._layer_combo.currentIndexChanged.connect(self._on_layer_changed)

        self._text_edit = QLineEdit()
        self._text_edit.editingFinished.connect(self._on_text_changed)

        form.addRow("ID", self._id_label)
        form.addRow("Type", self._type_label)
        form.addRow("Confidence", self._confidence_label)
        form.addRow("Source", self._source_label)
        form.addRow("Layer", self._layer_combo)
        form.addRow("Text", self._text_edit)

        layout.addLayout(form)
        layout.addStretch(1)
        self.set_entity(None)

    def set_entity(self, entity: Optional[Entity]) -> None:
        self._entity = entity
        self._suspend_signals = True
        try:
            self._layer_combo.setEnabled(entity is not None)

            if entity is None:
                self._id_label.setText("—")
                self._type_label.setText("—")
                self._confidence_label.setText("—")
                self._source_label.setText("—")
                self._text_edit.setText("")
                self._text_edit.setEnabled(False)
                return

            self._id_label.setText(entity.id)
            self._type_label.setText(entity.type.value)
            self._confidence_label.setText(f"{entity.confidence:.0%}")
            self._source_label.setText(entity.source.value)
            self._layer_combo.setCurrentIndex(self._layer_combo.findData(entity.layer))
            self._text_edit.setText(entity.text or "")
            self._text_edit.setEnabled(entity.text is not None)
        finally:
            self._suspend_signals = False

    def _on_layer_changed(self, index: int) -> None:
        if self._suspend_signals or self._entity is None:
            return
        new_layer = self._layer_combo.itemData(index)
        self.layerChanged.emit(self._entity.id, new_layer)

    def _on_text_changed(self) -> None:
        if self._suspend_signals or self._entity is None:
            return
        self.textChanged.emit(self._entity.id, self._text_edit.text())
