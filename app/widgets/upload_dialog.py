"""Upload dialog: pick a source file and set the per-document options
that genuinely need a human decision before processing starts — DPI (if
the scanner didn't embed it and the drawing is old enough that guessing
wrong would throw off every downstream measurement) and whether to spend
the time/cost on AI-assist for this particular document.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


@dataclass
class UploadOptions:
    file_path: str
    assumed_dpi: float
    ai_assist_enabled: bool
    units: str


class UploadDialog(QDialog):
    def __init__(self, parent=None, ai_assist_available: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Digitize a Drawing")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse)
        path_row = QVBoxLayout()
        path_row.addWidget(self._path_edit)
        path_row.addWidget(browse_button)
        form.addRow("Source file", path_row)

        self._dpi_spin = QDoubleSpinBox()
        self._dpi_spin.setRange(72, 2400)
        self._dpi_spin.setValue(300)
        self._dpi_spin.setSuffix(" dpi")
        form.addRow("Assumed DPI (used only if not in the file)", self._dpi_spin)

        self._ai_checkbox = QCheckBox("Enable AI-vision assist for low-confidence regions")
        self._ai_checkbox.setEnabled(ai_assist_available)
        if not ai_assist_available:
            self._ai_checkbox.setToolTip("Set ANTHROPIC_API_KEY to enable AI-vision assist.")
        form.addRow("", self._ai_checkbox)

        layout.addLayout(form)
        if not ai_assist_available:
            layout.addWidget(
                QLabel(
                    "<i>AI-assist is unavailable: no ANTHROPIC_API_KEY configured. "
                    "Deterministic-only digitization will still run.</i>"
                )
            )

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a drawing", "", "Drawings (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp)"
        )
        if path:
            self._path_edit.setText(path)

    def options(self) -> UploadOptions | None:
        if not self._path_edit.text():
            return None
        return UploadOptions(
            file_path=self._path_edit.text(),
            assumed_dpi=self._dpi_spin.value(),
            ai_assist_enabled=self._ai_checkbox.isChecked(),
            units="mm",
        )
