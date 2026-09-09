"""Geometric heuristics for layer classification.

Every function here answers one narrow, checkable question ("do these
two lines form a wall pair?", "does this line look like a structural
grid line?") rather than trying to be one monolithic classifier. That
keeps each rule auditable and lets the firm tune individual thresholds
(e.g. expected wall thickness in pixels for their scan DPI) without
touching the rest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.model import LayerCategory

Line = dict  # {"points": [(x1,y1),(x2,y2)], "confidence": float, "length_px": float, "angle_deg": float}


@dataclass
class ClassifiedLine:
    line: Line
    layer: LayerCategory
    classification_confidence: float  # confidence in the *label*, separate from geometric confidence
    group_id: str | None = None  # e.g. wall-pair id, grid-set id


def classify_grid_lines(
    lines: list[Line],
    page_width_px: float,
    page_height_px: float,
    span_ratio_threshold: float = 0.55,
    dedup_tolerance_px: float = 6.0,
    min_pitch_spacing_px: float = 40.0,
    min_group_size: int = 2,
) -> list[ClassifiedLine]:
    """A structural grid line is long (spans most of the page along its
    own axis) and comes in a family of *distinct* parallel lines spaced
    well apart. A single long line alone is not enough evidence (it could
    be a match-line or a border) — we require at least `min_group_size`
    such lines.

    Two passes of clustering matter here, at very different scales:
      1. `dedup_tolerance_px` (small) collapses near-duplicate Hough
         detections of the *same* physical line into one.
      2. `min_pitch_spacing_px` (much larger) then rejects lines that are
         close together even after dedup — e.g. a wall's two parallel
         faces, which are long and parallel but only a wall-thickness
         apart, not a grid spacing apart. Without this check a wall pair
         gets misclassified as a 2-line grid family.
    """
    candidates = []
    for line in lines:
        (x1, y1), (x2, y2) = line["points"]
        length = line["length_px"]
        horizontal = abs(x2 - x1) >= abs(y2 - y1)
        span_ratio = length / (page_width_px if horizontal else page_height_px)
        if span_ratio >= span_ratio_threshold:
            candidates.append((line, horizontal))

    horiz = [c[0] for c in candidates if c[1]]
    vert = [c[0] for c in candidates if not c[1]]

    result: list[ClassifiedLine] = []
    for group, axis in ((horiz, "h"), (vert, "v")):
        key_index = 1 if axis == "h" else 0
        clusters = _cluster_by_pitch(group, axis, dedup_tolerance_px)
        if len(clusters) < min_group_size:
            continue

        centers = sorted(_line_position(cluster[0], key_index) for cluster in clusters)
        gaps = [b - a for a, b in zip(centers[:-1], centers[1:])]
        if not gaps or min(gaps) < min_pitch_spacing_px:
            continue  # distinct lines are too close together to be a grid family

        for gi, cluster in enumerate(clusters):
            group_id = f"grid-{axis}-{gi}"
            for line in cluster:
                result.append(
                    ClassifiedLine(line=line, layer=LayerCategory.GRID, classification_confidence=0.9, group_id=group_id)
                )
    return result


def _cluster_by_pitch(lines: list[Line], axis: str, tolerance_px: float) -> list[list[Line]]:
    key_index = 1 if axis == "h" else 0  # y-position for horizontal lines, x-position for vertical
    positions = [(_line_position(line, key_index), line) for line in lines]
    positions.sort(key=lambda p: p[0])

    clusters: list[list[Line]] = []
    for pos, line in positions:
        if clusters and abs(pos - clusters[-1][-1][0]) <= tolerance_px:
            clusters[-1].append((pos, line))
        else:
            clusters.append([(pos, line)])
    return [[line for _, line in cluster] for cluster in clusters]


def _line_position(line: Line, key_index: int) -> float:
    (x1, y1), (x2, y2) = line["points"]
    return ((x1, y1)[key_index] + (x2, y2)[key_index]) / 2.0


def classify_wall_pairs(
    lines: list[Line],
    min_wall_px: float,
    max_wall_px: float,
    angle_tol_deg: float = 2.5,
    overlap_ratio_threshold: float = 0.6,
    already_classified_ids: set[int] | None = None,
) -> list[ClassifiedLine]:
    """A wall is drawn as two parallel lines a consistent short distance
    apart (the wall thickness). We look for such pairs; both lines in a
    matched pair are classified WALL. `min_wall_px`/`max_wall_px` should
    be derived from the page's estimated stroke thickness and a
    reasonable real-world wall-thickness range for the drawing's scale.
    """
    already_classified_ids = already_classified_ids or set()
    result: list[ClassifiedLine] = []
    used = set()

    for i, a in enumerate(lines):
        if i in already_classified_ids or i in used:
            continue
        for j in range(i + 1, len(lines)):
            if j in already_classified_ids or j in used:
                continue
            b = lines[j]
            if abs(a["angle_deg"] - b["angle_deg"]) > angle_tol_deg and abs(
                abs(a["angle_deg"] - b["angle_deg"]) - 180
            ) > angle_tol_deg:
                continue

            perp_dist, overlap = _parallel_line_relationship(a, b)
            if perp_dist is None:
                continue
            if not (min_wall_px <= perp_dist <= max_wall_px):
                continue
            if overlap < overlap_ratio_threshold:
                continue

            group_id = f"wall-{i}-{j}"
            conf = 0.85 * overlap
            result.append(ClassifiedLine(line=a, layer=LayerCategory.WALL, classification_confidence=conf, group_id=group_id))
            result.append(ClassifiedLine(line=b, layer=LayerCategory.WALL, classification_confidence=conf, group_id=group_id))
            used.add(i)
            used.add(j)
            break

    return result


def _parallel_line_relationship(a: Line, b: Line) -> tuple[float | None, float]:
    """Return (perpendicular_distance, overlap_ratio) between two
    roughly-parallel segments, projected onto `a`'s direction.
    """
    (ax1, ay1), (ax2, ay2) = a["points"]
    (bx1, by1), (bx2, by2) = b["points"]

    dx, dy = ax2 - ax1, ay2 - ay1
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None, 0.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux

    def project(px, py):
        return (px - ax1) * ux + (py - ay1) * uy

    def perp(px, py):
        return (px - ax1) * nx + (py - ay1) * ny

    perp_dist = (abs(perp(bx1, by1)) + abs(perp(bx2, by2))) / 2.0

    a_lo, a_hi = 0.0, length
    b_lo, b_hi = sorted([project(bx1, by1), project(bx2, by2)])

    overlap_lo, overlap_hi = max(a_lo, b_lo), min(a_hi, b_hi)
    overlap_len = max(0.0, overlap_hi - overlap_lo)
    shorter = min(a_hi - a_lo, b_hi - b_lo)
    overlap_ratio = overlap_len / shorter if shorter > 1e-6 else 0.0

    return perp_dist, overlap_ratio


def classify_dimension_lines(
    lines: list[Line],
    dimension_text_boxes: list[dict],
    max_dist_px: float,
) -> list[ClassifiedLine]:
    """A line whose midpoint sits close to a text box already flagged
    `is_dimension` (by the OCR-side numeric/unit pattern match) is very
    likely the dimension line/leader for that measurement.
    """
    result = []
    for line in lines:
        (x1, y1), (x2, y2) = line["points"]
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        best_dist = None
        for tb in dimension_text_boxes:
            bx0, by0, bx1, by1 = tb["bbox"]
            tcx, tcy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
            dist = math.hypot(mx - tcx, my - tcy)
            if best_dist is None or dist < best_dist:
                best_dist = dist
        if best_dist is not None and best_dist <= max_dist_px:
            conf = max(0.5, 1.0 - best_dist / max_dist_px)
            result.append(ClassifiedLine(line=line, layer=LayerCategory.DIMENSION, classification_confidence=conf))
    return result


def classify_quad_as_column_or_footing(
    boundary: list[tuple[float, float]],
    line_thickness_px: float,
    column_max_side_px: float,
) -> tuple[LayerCategory, float] | None:
    """A roughly-square, small closed quadrilateral (not hatch-textured)
    is very likely a column cross-section. A larger rectangular closed
    region is more likely a footing/foundation outline. Anything else
    (irregular polygon, too large) is left for the caller to leave
    unclassified.
    """
    if len(boundary) < 4 or len(boundary) > 6:
        return None

    xs = [p[0] for p in boundary]
    ys = [p[1] for p in boundary]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    if w < line_thickness_px * 2 or h < line_thickness_px * 2:
        return None

    aspect = max(w, h) / max(min(w, h), 1e-6)
    if aspect > 1.6:
        return None  # not square-ish enough for a typical column

    if max(w, h) <= column_max_side_px:
        return LayerCategory.COLUMN, 0.75
    return LayerCategory.FOUNDATION, 0.55
