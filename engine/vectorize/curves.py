"""Circle and arc detection.

Full circles (column markers, bolt/rebar callouts, north arrows) are
detected directly via Hough circle transform. Arcs (door swings, fillets,
partial curves) are found by fitting a circle to contour fragments and
checking whether the fragment's angular span is a genuine partial circle
rather than a full one or an unrelated blob.
"""

from __future__ import annotations

import math

import cv2
import numpy as np


def detect_circles(
    binary: np.ndarray,
    min_radius_px: int = 6,
    max_radius_px: int = 200,
) -> list[dict]:
    """Hough-circle detection. Returns dicts with center/radius/confidence.

    Confidence combines the Hough accumulator strength (queried via a
    second pass at a stricter accumulator threshold: a circle that still
    survives a stricter vote count is more reliable) with edge-coverage
    sampling around the fitted circumference, analogous to line scoring.
    """
    blurred = cv2.GaussianBlur(binary, (5, 5), 0)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=min_radius_px * 1.5,
        param1=50,
        param2=25,
        minRadius=min_radius_px,
        maxRadius=max_radius_px,
    )
    if circles is None:
        return []

    results = []
    h, w = binary.shape[:2]
    for cx, cy, r in circles.reshape(-1, 3):
        coverage = _circumference_coverage(binary, cx, cy, r, h, w)
        results.append(
            {
                "center": (float(cx), float(cy)),
                "radius": float(r),
                "confidence": coverage,
            }
        )
    return results


def _circumference_coverage(
    binary: np.ndarray, cx: float, cy: float, r: float, h: int, w: int, n_samples: int = 72
) -> float:
    hits = 0
    for i in range(n_samples):
        theta = 2 * math.pi * i / n_samples
        x = int(round(cx + r * math.cos(theta)))
        y = int(round(cy + r * math.sin(theta)))
        if 0 <= x < w and 0 <= y < h:
            window = binary[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2]
            if window.size and window.max() > 0:
                hits += 1
    return hits / n_samples


def detect_arcs(
    binary: np.ndarray,
    min_radius_px: int = 8,
    max_radius_px: int = 300,
    min_arc_span_deg: float = 20.0,
    max_arc_span_deg: float = 340.0,
) -> list[dict]:
    """Fit circles to open contour fragments and keep genuine partial arcs.

    A contour is a candidate arc if a least-squares circle fit has low
    residual (it really is circular) and the points span less than a
    full circle (otherwise it's a closed circle/hatch boundary, handled
    elsewhere).
    """
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    results = []
    for contour in contours:
        pts = contour.reshape(-1, 2).astype(np.float64)
        if len(pts) < 20:
            continue

        fit = _fit_circle_least_squares(pts)
        if fit is None:
            continue
        cx, cy, r, residual = fit
        if not (min_radius_px <= r <= max_radius_px):
            continue
        if residual > max(1.5, r * 0.05):
            continue  # not circular enough to trust as an arc

        angles = np.degrees(np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)) % 360
        span = _angular_span(angles)
        if not (min_arc_span_deg <= span <= max_arc_span_deg):
            continue

        start_angle = float(np.min(angles))
        end_angle = float(np.max(angles))
        confidence = max(0.0, 1.0 - residual / max(1.5, r * 0.05))
        results.append(
            {
                "center": (float(cx), float(cy)),
                "radius": float(r),
                "start_angle_deg": start_angle,
                "end_angle_deg": end_angle,
                "confidence": float(confidence),
            }
        )
    return results


def _fit_circle_least_squares(pts: np.ndarray) -> tuple[float, float, float, float] | None:
    """Algebraic (Kasa) circle fit; returns (cx, cy, r, mean_residual)."""
    x = pts[:, 0]
    y = pts[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x**2 + y**2
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx = sol[0] / 2.0
    cy = sol[1] / 2.0
    r_sq = sol[2] + cx**2 + cy**2
    if r_sq <= 0:
        return None
    r = float(math.sqrt(r_sq))
    residual = float(np.mean(np.abs(np.hypot(x - cx, y - cy) - r)))
    return cx, cy, r, residual


def _angular_span(angles_deg: np.ndarray) -> float:
    """Angular span of a set of angles on a circle, handling wraparound
    by testing the largest gap between consecutive sorted angles and
    treating the complement as the span (span = 360 - largest_gap).
    """
    sorted_angles = np.sort(angles_deg)
    gaps = np.diff(sorted_angles)
    wrap_gap = 360.0 - (sorted_angles[-1] - sorted_angles[0])
    largest_gap = max(float(np.max(gaps)) if len(gaps) else 0.0, wrap_gap)
    return 360.0 - largest_gap
