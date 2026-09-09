"""Symbol detection hook.

We deliberately do *not* ship a hard-coded library of every possible
drafting symbol — a fixed library is guaranteed to be wrong for some
firm's own conventions, some era's drafting standard, or a legacy
drawing that predates any convention at all. Instead this module
provides:

  1. A tiny, generic, extensible shape-signature registry
     (`register_shape_signature` / `match_registered_symbols`) a firm can
     grow with its own symbols once it has labeled examples.
  2. One concrete, broadly-safe example built on top of it: **grid
     bubble** detection (a circle containing a short label at the end of
     a structural grid line) — common across most structural drafting
     conventions, and useful as a cross-check that boosts confidence in
     the grid-line classification itself, not just a standalone label.

Anything not matched here is left unclassified rather than guessed —
consistent with `ARCHITECTURE.md` §1.2.
"""

from __future__ import annotations

import math
from typing import Callable, Optional


def find_grid_bubbles(
    circles: list[dict],
    text_boxes: list[dict],
    grid_line_endpoints: list[tuple[float, float]],
    max_dist_px: float,
) -> list[dict]:
    """Circles near a grid-line endpoint that contain a short text label.

    Returns the matched circles augmented with `label` and a boosted
    confidence (agreement between two independent detections — the
    circle detector and the OCR/grid-line detector — is itself evidence).
    """
    bubbles = []
    for circle in circles:
        cx, cy = circle["center"]
        r = circle["radius"]

        near_grid_end = any(
            math.hypot(cx - ex, cy - ey) <= max_dist_px for ex, ey in grid_line_endpoints
        )
        if not near_grid_end:
            continue

        label = None
        for tb in text_boxes:
            x0, y0, x1, y1 = tb["bbox"]
            tcx, tcy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            if math.hypot(tcx - cx, tcy - cy) <= r * 0.9 and tb.get("text"):
                label = tb["text"]
                break

        if label:
            bubbles.append(
                {
                    **circle,
                    "label": label,
                    "confidence": min(1.0, circle.get("confidence", 0.5) + 0.15),
                }
            )
    return bubbles


ShapeMatcher = Callable[[list[tuple[float, float]]], Optional[dict]]
_SHAPE_SIGNATURE_REGISTRY: dict[str, ShapeMatcher] = {}


def register_shape_signature(name: str, matcher: ShapeMatcher) -> None:
    """Register a custom symbol matcher.

    `matcher` receives a closed-boundary polygon (list of (x, y) points,
    already simplified via `approxPolyDP` upstream) and should return a
    dict of extra fields (e.g. `{"confidence": 0.7}`) if it matches, or
    `None` otherwise.
    """
    _SHAPE_SIGNATURE_REGISTRY[name] = matcher


def match_registered_symbols(boundaries: list[list[tuple[float, float]]]) -> list[dict]:
    matches = []
    for name, matcher in _SHAPE_SIGNATURE_REGISTRY.items():
        for boundary in boundaries:
            result = matcher(boundary)
            if result:
                matches.append({"symbol": name, "boundary": boundary, **result})
    return matches
