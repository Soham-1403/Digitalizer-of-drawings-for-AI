"""Layer visibility panel.

A reviewer often wants to isolate one layer ("show me only beams") —
these are independent checkboxes, not a single "show all" switch, per
ARCHITECTURE.md §6.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from engine.cad.layer_registry import get_layer_standard
from engine.model import LayerCategory


class LayersPanel(QWidget):
    layerVisibilityChanged = Signal(object, bool)  # LayerCategory, visible

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Layers</b>"))

        self._checkboxes: dict[LayerCategory, QCheckBox] = {}
        for category in get_layer_standard():
            row = QCheckBox()
            row.setChecked(True)
            row.toggled.connect(lambda checked, c=category: self.layerVisibilityChanged.emit(c, checked))
            layout.addWidget(row)
            self._checkboxes[category] = row

        layout.addStretch(1)
        self.refresh_from_standard()

    def refresh_from_standard(self) -> None:
        """Re-read names/colors/descriptions from the active layer
        standard — called after a firm loads their own CAD standard
        config, so the panel reflects it without rebuilding the widget
        (and without losing the current checked/visibility state).
        """
        for category, checkbox in self._checkboxes.items():
            spec = get_layer_standard()[category]
            checkbox.setText(f"{category.value} — {spec.description}")
            checkbox.setIcon(_swatch_icon(spec.rgb_hex))

    def set_all_visible(self, visible: bool) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(visible)

    def visibility_map(self) -> dict[LayerCategory, bool]:
        """Current checked state of every layer — reapplied whenever a
        new page is shown, so panel state persists across page navigation.
        """
        return {category: checkbox.isChecked() for category, checkbox in self._checkboxes.items()}


def _swatch_icon(hex_color: str) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(hex_color))
    return QIcon(pixmap)
