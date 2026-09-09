"""Canvas tool definitions and their pure-geometry helpers.

Kept separate from `app/widgets/canvas_view.py` so the tool-mode enum and
the (Qt-free) geometry math — simplifying a freehand stroke, computing a
move delta — are independently testable without instantiating a
QGraphicsView.
"""
