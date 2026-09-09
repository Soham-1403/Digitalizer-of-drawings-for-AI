"""Constructor helpers for `engine.model.Annotation`.

Three kinds, matching what the canvas annotation tool offers (see
`app/tools/annotation_tools.py`):

  - "freehand": an arbitrary scribble circling/underlining a problem area.
    Consumed only as *context* (rendered + described to the LLM) — never
    turned into drawing geometry itself.
  - "region": a rectangle/lasso marking an area to reprocess. Also
    context-only.
  - "line": a single corrected straight line the user drew to replace or
    add real geometry. This one *is* turned directly into a locked,
    fully-confident entity by `engine.llm_assist.fusion.apply_user_annotation`.
"""

from __future__ import annotations

from engine.model import Annotation, Point


def new_freehand_annotation(points: list[Point], page_index: int, note: str = "") -> Annotation:
    return Annotation(points=points, page_index=page_index, note=note, kind="freehand")


def new_region_annotation(points: list[Point], page_index: int, note: str = "") -> Annotation:
    if len(points) < 3:
        raise ValueError("A region annotation needs at least 3 points.")
    return Annotation(points=points, page_index=page_index, note=note, kind="region")


def new_line_annotation(start: Point, end: Point, page_index: int, note: str = "") -> Annotation:
    return Annotation(points=[start, end], page_index=page_index, note=note, kind="line")
