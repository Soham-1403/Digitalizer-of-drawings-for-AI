"""Preprocessing: deskew, contrast-normalize, denoise, binarize.

These three concerns are kept in separate modules because old/degraded
drawings often need different combinations of them independently (a
crisp recent scan might need none of this; a 40-year-old blueprint scan
needs all three, tuned aggressively).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from engine.preprocess.binarize import binarize_page
from engine.preprocess.deskew import deskew_image, estimate_skew_angle
from engine.preprocess.denoise import denoise_binary, estimate_line_thickness


@dataclass
class PreprocessResult:
    gray: np.ndarray
    binary: np.ndarray
    skew_angle_deg: float
    estimated_line_thickness_px: float


def preprocess_page(image_bgr: np.ndarray) -> PreprocessResult:
    """Run the full preprocessing chain on one page's raster image.

    Order matters: deskew before binarize (rotation interpolation is
    cleaner on grayscale than on a binary mask), and estimate line
    thickness *after* denoising so stray specks don't skew the estimate.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    angle = estimate_skew_angle(gray)
    if abs(angle) > 0.05:
        gray = deskew_image(gray, angle)

    binary = binarize_page(gray)
    line_thickness = estimate_line_thickness(binary)
    binary = denoise_binary(binary, min_component_px=max(4, int(line_thickness)))

    return PreprocessResult(
        gray=gray,
        binary=binary,
        skew_angle_deg=angle,
        estimated_line_thickness_px=line_thickness,
    )
