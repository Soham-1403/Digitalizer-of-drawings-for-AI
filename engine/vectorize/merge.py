"""Segment merging and endpoint snapping.

Hough-based line detection tends to shatter one real drafted line into
several overlapping/adjacent short segments (especially where the line
crosses hatching, text, or a faded region). Left unmerged, this produces
DXF output with dozens of tiny redundant LINE entities instead of one
clean wall — exactly the kind of "unusable at scale" output
`ARCHITECTURE.md` calls out. This module cleans that up before entities
are ever created.
"""

from __future__ import annotations

import math

import numpy as np

Segment = tuple[float, float, float, float]


def _angle_mod_180(x1: float, y1: float, x2: float, y2: float) -> float:
    a = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
    return a


def merge_collinear_segments(
    segments: list[Segment],
    angle_tol_deg: float = 3.0,
    perp_tol_px: float = 3.0,
    gap_tol_px: float = 15.0,
) -> list[Segment]:
    """Merge near-collinear, near-overlapping segments into single lines.

    Greedy clustering: group by angle (mod 180) within `angle_tol_deg`,
    then within each angle group, project all endpoints onto that group's
    dominant axis and merge any segments whose perpendicular offset from
    each other is within `perp_tol_px` and whose gap along the axis is
    within `gap_tol_px`, into one segment spanning the merged extent.
    """
    if not segments:
        return []

    remaining = list(segments)
    angle_groups: list[list[Segment]] = []

    while remaining:
        seed = remaining.pop(0)
        seed_angle = _angle_mod_180(*seed)
        group = [seed]
        still_remaining = []
        for seg in remaining:
            a = _angle_mod_180(*seg)
            diff = min(abs(a - seed_angle), 180 - abs(a - seed_angle))
            if diff <= angle_tol_deg:
                group.append(seg)
            else:
                still_remaining.append(seg)
        remaining = still_remaining
        angle_groups.append(group)

    merged: list[Segment] = []
    for group in angle_groups:
        merged.extend(_merge_within_angle_group(group, perp_tol_px, gap_tol_px))
    return merged


def _merge_within_angle_group(
    group: list[Segment], perp_tol_px: float, gap_tol_px: float
) -> list[Segment]:
    if len(group) == 1:
        return group

    xs = np.array([p for seg in group for p in (seg[0], seg[2])])
    ys = np.array([p for seg in group for p in (seg[1], seg[3])])
    dx, dy = xs.max() - xs.min(), ys.max() - ys.min()
    horizontal = abs(dx) >= abs(dy)
    direction = np.array([1.0, 0.0]) if horizontal else np.array([0.0, 1.0])
    normal = np.array([-direction[1], direction[0]])

    origin = np.array([xs[0], ys[0]])

    items = []
    for seg in group:
        p0 = np.array([seg[0], seg[1]])
        p1 = np.array([seg[2], seg[3]])
        mid = (p0 + p1) / 2.0
        perp_offset = float(np.dot(mid - origin, normal))
        proj0 = float(np.dot(p0 - origin, direction))
        proj1 = float(np.dot(p1 - origin, direction))
        lo, hi = min(proj0, proj1), max(proj0, proj1)
        items.append({"lo": lo, "hi": hi, "perp": perp_offset, "seg": seg})

    items.sort(key=lambda it: (it["perp"] // max(perp_tol_px, 0.5), it["lo"]))

    clusters: list[list[dict]] = []
    for it in items:
        placed = False
        for cluster in clusters:
            if abs(cluster[-1]["perp"] - it["perp"]) <= perp_tol_px and it["lo"] <= cluster[-1]["hi"] + gap_tol_px:
                cluster.append(it)
                placed = True
                break
        if not placed:
            clusters.append([it])

    results: list[Segment] = []
    for cluster in clusters:
        lo = min(c["lo"] for c in cluster)
        hi = max(c["hi"] for c in cluster)
        avg_perp = float(np.mean([c["perp"] for c in cluster]))
        p_lo = origin + direction * lo + normal * avg_perp
        p_hi = origin + direction * hi + normal * avg_perp
        results.append((float(p_lo[0]), float(p_lo[1]), float(p_hi[0]), float(p_hi[1])))

    return results


def snap_endpoints(segments: list[Segment], tolerance_px: float = 4.0) -> list[Segment]:
    """Snap endpoints that are within `tolerance_px` of each other to a
    shared coordinate, so lines that meet at a corner/junction actually
    share a vertex in the exported DXF instead of leaving a hairline gap
    or overlap — the difference between a clean joint and a CAD user
    having to manually fix every corner in the drawing.
    """
    if not segments:
        return []

    points: list[tuple[float, float]] = []
    for seg in segments:
        points.append((seg[0], seg[1]))
        points.append((seg[2], seg[3]))

    n = len(points)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            dx = points[i][0] - points[j][0]
            dy = points[i][1] - points[j][1]
            if dx * dx + dy * dy <= tolerance_px * tolerance_px:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    snapped_point = [None] * n
    for idxs in groups.values():
        cx = sum(points[i][0] for i in idxs) / len(idxs)
        cy = sum(points[i][1] for i in idxs) / len(idxs)
        for i in idxs:
            snapped_point[i] = (cx, cy)

    result: list[Segment] = []
    for k, seg in enumerate(segments):
        p0 = snapped_point[2 * k]
        p1 = snapped_point[2 * k + 1]
        result.append((p0[0], p0[1], p1[0], p1[1]))
    return result
