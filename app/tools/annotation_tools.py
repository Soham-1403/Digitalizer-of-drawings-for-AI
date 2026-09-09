"""Turns a raw mouse stroke captured by the canvas into an
`engine.model.Annotation`, applying simplification so freehand strokes
don't balloon into hundreds of points.
"""

from __future__ import annotations

from app.tools.edit_tools import Tool, simplify_polyline
from engine.annotations.model import (
    new_freehand_annotation,
    new_line_annotation,
    new_region_annotation,
)
from engine.model import Annotation, Point


def build_annotation(tool: Tool, raw_points: list[Point], page_index: int, note: str = "") -> Annotation | None:
    if tool == Tool.ANNOTATE_FREEHAND:
        simplified = simplify_polyline(raw_points, epsilon_px=2.5)
        if len(simplified) < 2:
            return None
        return new_freehand_annotation(simplified, page_index, note)

    if tool == Tool.ANNOTATE_LINE:
        if len(raw_points) < 2:
            return None
        return new_line_annotation(raw_points[0], raw_points[-1], page_index, note)

    if tool == Tool.ANNOTATE_REGION:
        if len(raw_points) < 3:
            return None
        return new_region_annotation(raw_points, page_index, note)

    return None
