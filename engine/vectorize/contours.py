"""Closed-region detection: hatch patterns and solid fills.

Structural drawings use hatching to denote material (concrete cross-hatch,
earth/fill, insulation) and solid fills for poured/existing concrete. We
distinguish "hatch" (repetitive parallel-line texture inside a boundary)
from plain noise/text by measuring line-density and directional
consistency inside each candidate contour.
"""

from __future__ import annotations

import cv2
import numpy as np


def detect_hatch_regions(
    binary: np.ndarray,
    min_area_px: float = 200.0,
    approx_epsilon_ratio: float = 0.01,
) -> list[dict]:
    """Find closed boundaries and classify their interior as hatch-like.

    Returns dicts: {"boundary": [(x,y), ...], "confidence": float,
    "fill_ratio": float, "is_hatch_pattern": bool}
    """
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    results = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area_px:
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        epsilon = approx_epsilon_ratio * perimeter
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) < 3:
            continue

        mask = np.zeros(binary.shape, dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
        interior = cv2.bitwise_and(binary, mask)

        interior_area = float(np.count_nonzero(mask))
        fill_ratio = float(np.count_nonzero(interior)) / interior_area if interior_area else 0.0

        is_hatch, directionality = _hatch_texture_score(interior, mask)

        # Fit quality: how well the simplified polygon explains the
        # original contour perimeter (fewer vertices needed relative to
        # arc length => cleaner geometric boundary => higher confidence).
        fit_quality = min(1.0, perimeter / max(1.0, cv2.arcLength(approx, True)))
        confidence = float(np.clip(0.5 * fit_quality + 0.5 * directionality, 0.0, 1.0))

        boundary = [(float(p[0][0]), float(p[0][1])) for p in approx]
        results.append(
            {
                "boundary": boundary,
                "confidence": confidence,
                "fill_ratio": fill_ratio,
                "is_hatch_pattern": is_hatch,
            }
        )

    return results


def _hatch_texture_score(interior: np.ndarray, mask: np.ndarray) -> tuple[bool, float]:
    """Detect repetitive parallel-line texture via gradient orientation
    histogram concentration: real hatch fill has gradients concentrated
    at one or two dominant angles; noise/text has a flatter, more
    uniform orientation distribution.
    """
    if np.count_nonzero(interior) < 30:
        return False, 0.3

    gx = cv2.Sobel(interior, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(interior, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    valid = mag > (0.2 * mag.max() if mag.max() > 0 else 1.0)
    if not np.any(valid):
        return False, 0.3

    angles = (np.degrees(np.arctan2(gy[valid], gx[valid])) % 180.0)
    hist, _ = np.histogram(angles, bins=18, range=(0, 180))
    hist = hist / max(1, hist.sum())
    concentration = float(hist.max())  # 1.0 = all gradients one direction

    is_hatch = concentration > 0.35
    return is_hatch, concentration
