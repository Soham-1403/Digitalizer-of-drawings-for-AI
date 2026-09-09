"""Canvas tool modes and the pure-geometry helpers behind editing.

Everything here is plain Python/math — no Qt imports — so it's testable
without a display and reusable if the canvas is ever ported to a
different widget toolkit.
"""

from __future__ import annotations

from enum import Enum

from engine.model import Point


class Tool(str, Enum):
    SELECT_MOVE = "select_move"
    PAN = "pan"
    ADD_LINE = "add_line"
    ADD_CIRCLE = "add_circle"
    ADD_TEXT = "add_text"
    DELETE = "delete"
    ANNOTATE_FREEHAND = "annotate_freehand"
    ANNOTATE_LINE = "annotate_line"
    ANNOTATE_REGION = "annotate_region"


# Tools where the underlying entity/annotation should be created on
# mouse-release rather than tracked live; used by the canvas to decide
# whether to show a live preview while dragging.
DRAG_PREVIEW_TOOLS = {Tool.ADD_LINE, Tool.ADD_CIRCLE, Tool.ANNOTATE_LINE, Tool.ANNOTATE_FREEHAND}


def translate_points(points: list[Point], dx: float, dy: float) -> list[Point]:
    return [(x + dx, y + dy) for x, y in points]


def simplify_polyline(points: list[Point], epsilon_px: float = 2.0) -> list[Point]:
    """Ramer-Douglas-Peucker simplification for freehand annotation
    strokes — a raw mouse-move trace can have hundreds of near-collinear
    points; this keeps only the ones that matter for shape, before the
    stroke is stored/serialized/sent to an LLM.
    """
    if len(points) < 3:
        return points

    def perpendicular_distance(pt: Point, start: Point, end: Point) -> float:
        (x, y), (x1, y1), (x2, y2) = pt, start, end
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
        t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
        proj_x, proj_y = x1 + t * dx, y1 + t * dy
        return ((x - proj_x) ** 2 + (y - proj_y) ** 2) ** 0.5

    def rdp(pts: list[Point]) -> list[Point]:
        if len(pts) < 3:
            return pts
        start, end = pts[0], pts[-1]
        max_dist, max_idx = 0.0, 0
        for i in range(1, len(pts) - 1):
            dist = perpendicular_distance(pts[i], start, end)
            if dist > max_dist:
                max_dist, max_idx = dist, i
        if max_dist > epsilon_px:
            left = rdp(pts[: max_idx + 1])
            right = rdp(pts[max_idx:])
            return left[:-1] + right
        return [start, end]

    return rdp(points)


def point_near_circle_edge(point: Point, center: Point, radius: float, tolerance_px: float = 6.0) -> bool:
    import math

    dist = math.hypot(point[0] - center[0], point[1] - center[1])
    return abs(dist - radius) <= tolerance_px
