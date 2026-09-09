"""Pixel-space <-> real-world DXF-space coordinate conversion.

Two things differ between the raster image space entities are detected
in and the space DXF/PDF export needs:

1. **Units.** Detected geometry is in pixels; DXF needs real-world units
   (mm/inches), derived from the page's DPI.
2. **Y-axis direction.** Image space has Y increasing downward (origin
   top-left, as OpenCV/PIL/most raster formats use); DXF/CAD space has Y
   increasing upward (origin bottom-left). Getting this wrong silently
   produces a vertically-mirrored drawing — every writer must go through
   this module rather than reimplementing the flip.
"""

from __future__ import annotations

Point = tuple[float, float]


def px_to_units_scale(dpi: float, units: str) -> float:
    if units == "mm":
        return 25.4 / dpi
    if units == "in":
        return 1.0 / dpi
    raise ValueError(f"Unsupported units: {units!r}. Use 'mm' or 'in'.")


def point_px_to_units(point: Point, page_height_px: float, scale: float) -> Point:
    x_px, y_px = point
    x = x_px * scale
    y = (page_height_px - y_px) * scale
    return (x, y)


def length_px_to_units(length_px: float, scale: float) -> float:
    return length_px * scale


def flip_angle_deg(angle_deg: float) -> float:
    """Reflect an angle measured in image space (Y-down) into DXF space
    (Y-up): mirroring about the X-axis negates the angle.
    """
    return (-angle_deg) % 360.0


def arc_angles_px_to_dxf(start_deg: float, end_deg: float) -> tuple[float, float]:
    """Convert an image-space CCW-in-Y-down arc's (start, end) angles into
    DXF's Y-up CCW convention.

    Mirroring about the X-axis reverses rotational sense (CCW becomes
    CW), so to keep DXF's required CCW start->end convention we both
    negate *and* swap the two angles.
    """
    return flip_angle_deg(end_deg), flip_angle_deg(start_deg)
