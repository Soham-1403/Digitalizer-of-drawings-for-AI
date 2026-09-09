"""VectorDocument -> accurate vector PDF.

This is a real re-render from the vector model (lines, arcs, text drawn
as PDF vector primitives), not a screenshot/rasterization of the canvas
— so "save as PDF" produces something that stays sharp at any zoom and
whose layer colors match the DXF standard exactly.
"""

from __future__ import annotations

from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from shapely.geometry import LineString, Polygon

from engine.cad.coords import (
    arc_angles_px_to_dxf,
    length_px_to_units,
    point_px_to_units,
    px_to_units_scale,
)
from engine.cad.layers import STRUCTURAL_LAYER_STANDARD
from engine.model import Entity, EntityType, VectorDocument

POINTS_PER_HUNDREDTH_MM = (1.0 / 100.0) * (72.0 / 25.4)


def write_pdf(document: VectorDocument, out_path: str) -> str:
    unit_factor = mm if document.units == "mm" else inch
    c: canvas.Canvas | None = None

    for page in document.pages:
        scale = px_to_units_scale(page.dpi, document.units)
        width_pt = page.width_px * scale * unit_factor
        height_pt = page.height_px * scale * unit_factor

        if c is None:
            c = canvas.Canvas(out_path, pagesize=(width_pt, height_pt))
        else:
            c.showPage()
            c.setPageSize((width_pt, height_pt))

        for entity in page.entities:
            _draw_entity(c, entity, page.height_px, scale, unit_factor)

    if c is not None:
        c.save()
    return out_path


def _to_pt(point, page_height_px, scale, unit_factor):
    x, y = point_px_to_units(point, page_height_px, scale)
    return x * unit_factor, y * unit_factor


def _apply_layer_style(c: canvas.Canvas, entity: Entity, unit_factor: float) -> None:
    spec = STRUCTURAL_LAYER_STANDARD[entity.layer]
    color = HexColor(spec.rgb_hex)
    c.setStrokeColor(color)
    c.setFillColor(color)
    line_width_pt = spec.lineweight_hundredth_mm * POINTS_PER_HUNDREDTH_MM
    c.setLineWidth(max(line_width_pt, 0.25))


def _draw_entity(c: canvas.Canvas, entity: Entity, page_height_px: float, scale: float, unit_factor: float) -> None:
    _apply_layer_style(c, entity, unit_factor)

    if entity.type == EntityType.LINE:
        x0, y0 = _to_pt(entity.points[0], page_height_px, scale, unit_factor)
        x1, y1 = _to_pt(entity.points[1], page_height_px, scale, unit_factor)
        c.line(x0, y0, x1, y1)

    elif entity.type == EntityType.POLYLINE:
        path = c.beginPath()
        pts = [_to_pt(p, page_height_px, scale, unit_factor) for p in entity.points]
        path.moveTo(*pts[0])
        for p in pts[1:]:
            path.lineTo(*p)
        c.drawPath(path, stroke=1, fill=0)

    elif entity.type == EntityType.CIRCLE:
        cx, cy = _to_pt(entity.points[0], page_height_px, scale, unit_factor)
        r = length_px_to_units(float(entity.params.get("radius", 0.0)), scale) * unit_factor
        c.circle(cx, cy, r, stroke=1, fill=0)

    elif entity.type == EntityType.ARC:
        cx, cy = _to_pt(entity.points[0], page_height_px, scale, unit_factor)
        r = length_px_to_units(float(entity.params.get("radius", 0.0)), scale) * unit_factor
        start_deg, end_deg = arc_angles_px_to_dxf(
            float(entity.params.get("start_angle_deg", 0.0)),
            float(entity.params.get("end_angle_deg", 0.0)),
        )
        extent = (end_deg - start_deg) % 360.0
        c.arc(cx - r, cy - r, cx + r, cy + r, startAng=start_deg, extent=extent)

    elif entity.type == EntityType.HATCH:
        pts = [_to_pt(p, page_height_px, scale, unit_factor) for p in entity.points]
        path = c.beginPath()
        path.moveTo(*pts[0])
        for p in pts[1:]:
            path.lineTo(*p)
        path.close()
        c.drawPath(path, stroke=1, fill=0)
        if entity.params.get("is_hatch_pattern"):
            _draw_hatch_fill(c, pts)

    elif entity.type in (EntityType.TEXT, EntityType.DIMENSION):
        x, y = _to_pt(entity.points[0], page_height_px, scale, unit_factor)
        height_pt = max(
            length_px_to_units(float(entity.params.get("height_px", 12.0)), scale) * unit_factor, 4.0
        )
        c.setFont("Helvetica", height_pt)
        c.drawString(x, y, entity.text or "")
        if entity.type == EntityType.DIMENSION and len(entity.points) >= 2:
            x1, y1 = _to_pt(entity.points[1], page_height_px, scale, unit_factor)
            c.line(x, y, x1, y1)


def _draw_hatch_fill(c: canvas.Canvas, boundary_pts: list[tuple[float, float]], spacing_pt: float = 6.0) -> None:
    """Manual 45-degree hatch fill: generate parallel diagonal lines across
    the boundary's bounding box and clip each to the polygon interior via
    Shapely, since PDF has no native "ANSI31"-style hatch pattern.
    """
    polygon = Polygon(boundary_pts)
    if not polygon.is_valid or polygon.area == 0:
        return

    minx, miny, maxx, maxy = polygon.bounds
    diag = ((maxx - minx) ** 2 + (maxy - miny) ** 2) ** 0.5
    n_lines = max(1, int(diag / spacing_pt))

    for i in range(-n_lines, n_lines + 1):
        offset = i * spacing_pt
        line = LineString(
            [
                (minx - diag, miny + offset + diag),
                (minx + diag, miny + offset - diag),
            ]
        )
        clipped = polygon.intersection(line)
        if clipped.is_empty:
            continue
        segments = [clipped] if clipped.geom_type == "LineString" else list(getattr(clipped, "geoms", []))
        for seg in segments:
            coords = list(seg.coords)
            if len(coords) >= 2:
                c.line(coords[0][0], coords[0][1], coords[-1][0], coords[-1][1])
