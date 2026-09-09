"""Desktop app entry point: `python -m app.main` or the `digitalizer`
console script installed by `pyproject.toml`.
"""

from __future__ import annotations

import sys


def main() -> None:
    from PySide6.QtWidgets import QApplication

    from app.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Digitalizer of Drawings for AI")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
