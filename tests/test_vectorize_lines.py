import cv2
import numpy as np

from engine.preprocess.binarize import binarize_page
from engine.vectorize.lines import detect_lines


def test_detect_lines_finds_grid_lines(synthetic_drawing_bgr):
    gray = cv2.cvtColor(synthetic_drawing_bgr, cv2.COLOR_BGR2GRAY)
    binary = binarize_page(gray)

    lines = detect_lines(binary, min_length_px=100)

    long_horizontal = [
        l for l in lines
        if l["length_px"] > 800 and abs(l["points"][0][1] - l["points"][1][1]) < 5
    ]
    assert len(long_horizontal) >= 3, f"expected >=3 long horizontal lines, got {len(long_horizontal)}"

    for line in lines:
        assert 0.0 <= line["confidence"] <= 1.0


def test_merge_collinear_segments_reduces_fragment_count():
    from engine.vectorize.merge import merge_collinear_segments

    # Simulate Hough shattering one long line into overlapping fragments.
    fragments = [(0, 0, 50, 0), (48, 0, 100, 0), (98, 0, 150, 0)]
    merged = merge_collinear_segments(fragments)
    assert len(merged) == 1
    x1, y1, x2, y2 = merged[0]
    assert min(x1, x2) <= 2
    assert max(x1, x2) >= 148
