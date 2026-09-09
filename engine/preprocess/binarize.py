"""Grayscale -> binary (foreground=255, background=0) conversion.

A single global brightness threshold reliably fails on old drawings where
one corner is faded and another is stained/dark. We use CLAHE (local
contrast normalization) followed by adaptive (locally-computed) Otsu-style
thresholding so each region of the page gets its own effective cutoff.
"""

from __future__ import annotations

import cv2
import numpy as np


def binarize_page(
    gray: np.ndarray,
    block_size: int = 35,
    c: int = 10,
) -> np.ndarray:
    """Return a binary image where drawing strokes are 255, background 0.

    `block_size`/`c` follow OpenCV's `adaptiveThreshold` semantics: each
    pixel's threshold is the mean of its `block_size` neighborhood minus
    `c`. Smaller `block_size` adapts faster to local fading but is more
    sensitive to noise; the default is tuned for 300 DPI drawing scans.
    """
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(16, 16))
    normalized = clahe.apply(gray)

    block_size = block_size if block_size % 2 == 1 else block_size + 1
    binary = cv2.adaptiveThreshold(
        normalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,  # dark strokes on light paper -> foreground=255
        block_size,
        c,
    )
    return binary
