"""Export dialog: choose which output files to write and where.

DWG is offered but honestly gated — the checkbox is disabled with an
explanation if the ODA File Converter isn't installed, rather than
letting the user pick it and then silently getting only a DXF.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from engine.cad.dwg_export import find_oda_file_converter


@dataclass
class ExportOptions:
    out_dir: str
    export_dxf: bool
    export_pdf: bool
    export_dwg: bool


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        self._dir_edit = QLineEdit()
        browse_button = QPushButton("Choose output folder…")
        browse_button.clicked.connect(self._browse)
        layout.addWidget(QLabel("Output folder"))
        layout.addWidget(self._dir_edit)
        layout.addWidget(browse_button)

        self._dxf_checkbox = QCheckBox("DXF (layered, always available)")
        self._dxf_checkbox.setChecked(True)
        layout.addWidget(self._dxf_checkbox)

        self._pdf_checkbox = QCheckBox("Vector PDF")
        self._pdf_checkbox.setChecked(True)
        layout.addWidget(self._pdf_checkbox)

        oda_available = find_oda_file_converter() is not None
        self._dwg_checkbox = QCheckBox("DWG (via ODA File Converter)")
        self._dwg_checkbox.setEnabled(oda_available)
        if not oda_available:
            self._dwg_checkbox.setToolTip(
                "ODA File Converter not found on this machine. Install it to also export DWG."
            )
            layout.addWidget(
                QLabel(
                    "<i>DWG unavailable: install the free ODA File Converter to enable it. "
                    "DXF export always works and opens natively in AutoCAD.</i>"
                )
            )
        layout.addWidget(self._dwg_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if path:
            self._dir_edit.setText(path)

    def options(self) -> ExportOptions | None:
        if not self._dir_edit.text():
            return None
        return ExportOptions(
            out_dir=self._dir_edit.text(),
            export_dxf=self._dxf_checkbox.isChecked(),
            export_pdf=self._pdf_checkbox.isChecked(),
            export_dwg=self._dwg_checkbox.isChecked() and self._dwg_checkbox.isEnabled(),
        )
