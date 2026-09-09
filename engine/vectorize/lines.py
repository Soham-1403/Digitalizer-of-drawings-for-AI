"""Straight-line detection.

Pipeline: probabilistic Hough transform for candidate segments -> merge
collinear fragments -> snap shared endpoints -> score each resulting
segment's confidence by re-sampling the binary mask along its length
(a segment that "looks like a line" to Hough but has poor actual pixel
support gets penalized rather than trusted).
"""

from __future__ import annotations

import cv2
import numpy as np

from engine.vectorize.merge import Segment, merge_collinear_segments, snap_endpoints


def detect_line_segments(
    binary: np.ndarray,
    min_length_px: float = 20.0,
    max_gap_px: float = 6.0,
    hough_threshold: int = 30,
) -> list[Segment]:
    """Raw Hough candidate segments, before merging/snapping/scoring."""
    lines = cv2.HoughLinesP(
        binary,
        rho=1,
        theta=np.pi / 360,
        threshold=hough_threshold,
        minLineLength=min_length_px,
        maxLineGap=max_gap_px,
    )
    if lines is None:
        return []
    return [tuple(map(float, l)) for l in lines.reshape(-1, 4)]


def score_segment_confidence(binary: np.ndarray, seg: Segment, sample_stride_px: float = 1.5) -> float:
    """Confidence = fraction of sampled points along the segment that
    actually have foreground pixels nearby in the binary mask.

    This catches the case where merging/Hough produced a segment that
    "connects the dots" across a gap that was never really a solid line
    (e.g. bridging across unrelated nearby strokes).
    """
    x1, y1, x2, y2 = seg
    length = float(np.hypot(x2 - x1, y2 - y1))
    if length < 1e-6:
        return 0.0

    n_samples = max(2, int(length / sample_stride_px))
    h, w = binary.shape[:2]
    hits = 0
    for t in np.linspace(0.0, 1.0, n_samples):
        x = int(round(x1 + t * (x2 - x1)))
        y = int(round(y1 + t * (y2 - y1)))
        found = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h and binary[yy, xx] > 0:
                    found = True
                    break
            if found:
                break
        if found:
            hits += 1
    return hits / n_samples


def detect_lines(
    binary: np.ndarray,
    min_length_px: float = 20.0,
    max_gap_px: float = 6.0,
    snap_tolerance_px: float = 4.0,
) -> list[dict]:
    """Full straight-line pipeline. Returns dicts with geometry + confidence.

    Each result: {"points": [(x1,y1), (x2,y2)], "confidence": float,
    "length_px": float, "angle_deg": float}
    """
    raw = detect_line_segments(binary, min_length_px=min_length_px, max_gap_px=max_gap_px)
    merged = merge_collinear_segments(raw)
    snapped = snap_endpoints(merged, tolerance_px=snap_tolerance_px)

    results = []
    for seg in snapped:
        x1, y1, x2, y2 = seg
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length < min_length_px * 0.6:
            continue
        confidence = score_segment_confidence(binary, seg)
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180)
        results.append(
            {
                "points": [(x1, y1), (x2, y2)],
                "confidence": confidence,
                "length_px": length,
                "angle_deg": angle,
            }
        )
    return results
