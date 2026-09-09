"""Text and dimension-label detection.

Runs *before* line detection conceptually consumes the same mask: we
isolate small, text-sized connected components, cluster them into text
lines by proximity, and only then hand each cluster's bounding box to
OCR. This keeps short text strokes from being swallowed into nearby wall
lines by the line-merging step, and keeps OCR (slow, and weak on
hand lettering) confined to regions that actually look like text.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

try:
    import pytesseract
except ImportError:  # pragma: no cover - optional at import time
    pytesseract = None

_DIMENSION_PATTERN = re.compile(
    r"""^\s*\d+([.,]\d+)?\s*(mm|cm|m|ft|in|')?\s*[-–]?\s*
        (\d+([.,]\d+)?\s*(mm|cm|m|ft|in|"|')?)?\s*$""",
    re.VERBOSE,
)


def find_text_component_boxes(
    binary: np.ndarray,
    line_thickness_px: float,
    min_height_px: float | None = None,
    max_height_px: float | None = None,
    cluster_gap_px: float | None = None,
) -> list[tuple[int, int, int, int]]:
    """Find bounding boxes likely to contain text, by connected-component
    size filtering followed by horizontal-proximity clustering into
    text-line-sized groups.

    Height bounds default to a multiple of the estimated stroke
    thickness, since text glyph height scales with drafting pen/line
    weight in a way that's roughly DPI/scale-consistent within one page.
    """
    min_height_px = min_height_px or max(6.0, line_thickness_px * 2.5)
    max_height_px = max_height_px or line_thickness_px * 30.0
    cluster_gap_px = cluster_gap_px or line_thickness_px * 6.0

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    glyph_boxes = []
    for label in range(1, num_labels):
        x, y, w, h, area = stats[label]
        if min_height_px <= h <= max_height_px and w <= max_height_px * 6 and area >= 3:
            aspect = w / max(h, 1)
            if 0.05 <= aspect <= 20.0:
                glyph_boxes.append((x, y, x + w, y + h))

    if not glyph_boxes:
        return []

    glyph_boxes.sort(key=lambda b: (b[1], b[0]))
    clusters: list[list[tuple[int, int, int, int]]] = []
    for box in glyph_boxes:
        placed = False
        for cluster in clusters:
            cx0, cy0, cx1, cy1 = cluster[-1]
            same_row = abs(((box[1] + box[3]) / 2) - ((cy0 + cy1) / 2)) <= max_height_px * 0.6
            close_enough = box[0] - cx1 <= cluster_gap_px
            if same_row and close_enough and box[0] >= cx0 - cluster_gap_px:
                cluster.append(box)
                placed = True
                break
        if not placed:
            clusters.append([box])

    merged_boxes = []
    for cluster in clusters:
        x0 = min(b[0] for b in cluster)
        y0 = min(b[1] for b in cluster)
        x1 = max(b[2] for b in cluster)
        y1 = max(b[3] for b in cluster)
        merged_boxes.append((x0, y0, x1, y1))
    return merged_boxes


def ocr_text_boxes(
    gray: np.ndarray, boxes: list[tuple[int, int, int, int]], padding_px: int = 4
) -> list[dict]:
    """Run OCR on each candidate text box.

    Returns dicts: {"bbox": (x0,y0,x1,y1), "text": str, "confidence": float,
    "is_dimension": bool}. If pytesseract isn't installed/available at
    runtime, returns boxes with empty text and confidence 0 so downstream
    code degrades gracefully instead of crashing.
    """
    results = []
    h, w = gray.shape[:2]
    for x0, y0, x1, y1 in boxes:
        px0, py0 = max(0, x0 - padding_px), max(0, y0 - padding_px)
        px1, py1 = min(w, x1 + padding_px), min(h, y1 + padding_px)
        crop = gray[py0:py1, px0:px1]

        text, conf = "", 0.0
        if pytesseract is not None and crop.size > 0:
            text, conf = _ocr_single_crop(crop)

        is_dimension = bool(_DIMENSION_PATTERN.match(text.strip())) if text else False
        results.append(
            {
                "bbox": (x0, y0, x1, y1),
                "text": text.strip(),
                "confidence": conf,
                "is_dimension": is_dimension,
            }
        )
    return results


def _ocr_single_crop(crop: np.ndarray) -> tuple[str, float]:
    scaled = cv2.resize(crop, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    try:
        data = pytesseract.image_to_data(
            scaled, config="--psm 7", output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractNotFoundError:
        return "", 0.0

    words = [w for w in data.get("text", []) if w.strip()]
    if not words:
        return "", 0.0
    confs = [float(c) for c in data.get("conf", []) if c not in ("-1", -1)]
    text = " ".join(words)
    mean_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return text, mean_conf
