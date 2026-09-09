"""Skew estimation and correction.

Scanned/photographed drawings are rarely perfectly aligned to the page
axes. Vectorization downstream (especially Hough line detection, which
groups lines by angle) is far more accurate once the dominant grid is
axis-aligned, so we correct skew before anything else.
"""

from __future__ import annotations

import cv2
import numpy as np


def estimate_skew_angle(gray: np.ndarray, max_angle_deg: float = 15.0) -> float:
    """Estimate the dominant skew angle in degrees.

    Approach: find straight edge segments via Canny + probabilistic Hough
    transform, keep the ones within `max_angle_deg` of horizontal (drawings
    are dominated by horizontal/vertical structure — grid lines, walls,
    dimension lines), and take the median angle. Median (not mean) is
    used because it's robust to the occasional diagonal hatch/leader line
    that survives the angle filter.

    Returns 0.0 if too few reliable lines are found rather than guessing.
    """
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    min_len = max(30, gray.shape[1] // 8)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 720, threshold=80, minLineLength=min_len, maxLineGap=10
    )
    if lines is None or len(lines) < 5:
        return 0.0

    angles = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Fold to [-45, 45] treating near-vertical lines as (angle - 90)
        # so both wall/grid orientations contribute to the same estimate.
        folded = angle % 90
        if folded > 45:
            folded -= 90
        if abs(folded) <= max_angle_deg:
            angles.append(folded)

    if len(angles) < 5:
        return 0.0
    return float(np.median(angles))


def deskew_image(gray: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate `gray` by `-angle_deg` about its center, expanding the
    canvas so no content is cropped, and filling new border area with
    white (background) rather than black.
    """
    h, w = gray.shape[:2]
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)

    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)

    matrix[0, 2] += (new_w / 2.0) - center[0]
    matrix[1, 2] += (new_h / 2.0) - center[1]

    return cv2.warpAffine(
        gray,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )
