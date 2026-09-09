"""Noise removal and line-thickness estimation.

Old prints accumulate dust specks, tape-mark shadows, and fold-line
artifacts that survive binarization as tiny isolated components. We
remove components smaller than a size derived from the drawing's own
line thickness (rather than a fixed pixel count) so the same code works
sensibly whether the page was scanned at 150 DPI or 600 DPI.
"""

from __future__ import annotations

import cv2
import numpy as np


def estimate_line_thickness(binary: np.ndarray) -> float:
    """Estimate the typical stroke width (in pixels) of the drawing.

    Uses the distance transform: for a stroke of width w, pixels on its
    centerline have distance-to-background ~w/2. We take a high
    percentile (not the max, which is dominated by large filled/hatched
    regions) of the positive distance values as a robust proxy for w/2.
    """
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    nonzero = dist[dist > 0]
    if nonzero.size == 0:
        return 1.0
    thickness = 2.0 * float(np.percentile(nonzero, 85))
    return max(1.0, thickness)


def denoise_binary(binary: np.ndarray, min_component_px: int = 4) -> np.ndarray:
    """Remove small speckle components and bridge tiny gaps.

    `min_component_px` is treated as a linear size (e.g. the estimated
    line thickness); components with area below that value squared are
    dropped as noise. A single-pixel morphological opening runs first to
    strip isolated noise pixels before connected-component analysis, and
    a small closing pass afterward bridges the short gaps common in
    faded/old scans without merging genuinely separate lines.
    """
    open_kernel = np.ones((2, 2), np.uint8)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_kernel)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    min_area = max(4, min_component_px * min_component_px // 2)

    cleaned = np.zeros_like(opened)
    for label in range(1, num_labels):
        if stats[label, cv2.CC_STAT_AREA] >= min_area:
            cleaned[labels == label] = 255

    close_kernel = np.ones((3, 3), np.uint8)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, close_kernel)
    return cleaned
