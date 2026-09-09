"""Shared fixtures: a synthetic structural-drawing-like raster image,
built with OpenCV drawing primitives rather than a stored binary fixture
file, so tests never depend on committing real drawing scans.
"""

from __future__ import annotations

import os

import cv2
import numpy as np
import pytest

# Qt needs a platform plugin even for widget-construction-only tests; on a
# headless CI/sandbox box there's no real display, so default to the
# offscreen plugin unless the environment already set one.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def synthetic_drawing_bgr() -> np.ndarray:
    width, height = 1000, 800
    img = np.full((height, width, 3), 255, dtype=np.uint8)

    line_color = (0, 0, 0)
    thickness = 3

    # "Grid" lines: 3 regularly-spaced, long horizontal lines.
    for y in (100, 300, 500):
        cv2.line(img, (50, y), (950, y), line_color, thickness)

    # "Wall": two close, parallel vertical lines.
    cv2.line(img, (200, 50), (200, 750), line_color, thickness)
    cv2.line(img, (212, 50), (212, 750), line_color, thickness)

    # "Column": a small square outline.
    cv2.rectangle(img, (600, 600), (640, 640), line_color, thickness)

    # A circle (candidate grid bubble) at the end of one grid line, with a label.
    cv2.circle(img, (950, 100), 18, line_color, thickness)
    cv2.putText(img, "A", (943, 107), cv2.FONT_HERSHEY_SIMPLEX, 0.5, line_color, 1)

    # A dimension-like numeric label near a line.
    cv2.putText(img, "1200", (400, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.6, line_color, 1)

    return img
