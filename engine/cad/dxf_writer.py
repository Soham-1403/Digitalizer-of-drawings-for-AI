"""VectorDocument -> DXF.

Emits real named layers with the curated color/lineweight standard from
`engine.cad.layers` (never a single-layer dump), converts every entity
from pixel space into real-world units via `engine.cad.coords`, and
stamps each DXF entity with its confidence/source as XDATA so the audit
trail survives round-tripping through AutoCAD.
"""

from __future__ import annotations

import ezdxf
from ezdxf import colors as ezdxf_colors

from engine.cad.coords import (
    arc_angles_px_to_dxf,
    length_px_to_units,
    point_px_to_units,
    px_to_units_scale,
)
from engine.cad.layer_registry import get_layer_standard
from engine.cad.layers import hex_to_rgb
from engine.model import Entity, EntityType, VectorDocument

XDATA_APPID = "DIGITALIZER"


def _ensure_appid(doc) -> None:
    if XDATA_APPID not in doc.appids:
        doc.appids.new(XDATA_APPID)


def _ensure_layers(doc) -> None:
    for category, spec in get_layer_standard().items():
        name = category.value
        if name in doc.layers:
            continue
        layer = doc.layers.new(
            name=name,
            dxfattribs={
                "color": spec.aci,
                "linetype": spec.linetype,
                "lineweight": spec.lineweight_hundredth_mm,
            },
        )
        r, g, b = hex_to_rgb(spec.rgb_hex)
        layer.dxf.true_color = ezdxf_colors.rgb2int((r, g, b))


def _stamp_xdata(dxf_entity, entity: Entity) -> None:
    try:
        dxf_entity.set_xdata(
            XDATA_APPID,
            [
                (1000, entity.source.value),
                (1040, round(float(entity.confidence), 4)),
                (1000, entity.id),
            ],
        )
    except Exception:
        # XDATA is metadata, not core geometry — never let a stamping
        # failure (e.g. an unusual DXF version) break the export.
        pass


def _write_entity(msp, entity: Entity, page_height_px: float, scale: float, x_offset: float = 0.0) -> None:
    layer_name = entity.layer.value
    attribs = {"layer": layer_name}

    def to_units(point_px):
        x, y = point_px_to_units(point_px, page_height_px, scale)
        return (x + x_offset, y)

    if entity.type == EntityType.LINE:
        p0 = to_units(entity.points[0])
        p1 = to_units(entity.points[1])
        dxf_e = msp.add_line(p0, p1, dxfattribs=attribs)

    elif entity.type == EntityType.POLYLINE:
        pts = [to_units(p) for p in entity.points]
        dxf_e = msp.add_lwpolyline(pts, dxfattribs=attribs)

    elif entity.type == EntityType.CIRCLE:
        center = to_units(entity.points[0])
        radius = length_px_to_units(float(entity.params.get("radius", 0.0)), scale)
        dxf_e = msp.add_circle(center, radius, dxfattribs=attribs)

    elif entity.type == EntityType.ARC:
        center = to_units(entity.points[0])
        radius = length_px_to_units(float(entity.params.get("radius", 0.0)), scale)
        start_deg, end_deg = arc_angles_px_to_dxf(
            float(entity.params.get("start_angle_deg", 0.0)),
            float(entity.params.get("end_angle_deg", 0.0)),
        )
        dxf_e = msp.add_arc(center, radius, start_deg, end_deg, dxfattribs=attribs)

    elif entity.type == EntityType.HATCH:
        pts = [to_units(p) for p in entity.points]
        if entity.params.get("is_hatch_pattern"):
            hatch = msp.add_hatch(dxfattribs=attribs)
            hatch.set_pattern_fill("ANSI31", scale=1.0)
            hatch.paths.add_polyline_path(pts, is_closed=True)
            dxf_e = hatch
        else:
            pl = msp.add_lwpolyline(pts, dxfattribs=attribs)
            pl.closed = True
            dxf_e = pl

    elif entity.type in (EntityType.TEXT, EntityType.DIMENSION):
        insertion = to_units(entity.points[0])
        height = length_px_to_units(float(entity.params.get("height_px", 12.0)), scale)
        text_attribs = dict(attribs)
        text_attribs["height"] = max(height, 0.5)
        dxf_e = msp.add_text(entity.text or "", dxfattribs=text_attribs)
        dxf_e.set_placement(insertion)
        if entity.type == EntityType.DIMENSION and len(entity.points) >= 2:
            p1 = to_units(entity.points[1])
            msp.add_line(insertion, p1, dxfattribs={"layer": layer_name})

    else:  # pragma: no cover - exhaustive over EntityType
        return

    _stamp_xdata(dxf_e, entity)


def write_dxf(document: VectorDocument, out_path: str, dxf_version: str = "R2010") -> str:
    """Write the full multi-page VectorDocument to a single DXF file.

    Multi-page documents are laid out side by side on the model space
    X-axis (page N offset by the running width of pages 0..N-1 plus a
    fixed gap), each on its own DXF layout-independent region, so the
    whole set opens as one file with all sheets visible and nothing
    overlapping. A firm wanting one DXF per sheet can call this once per
    `Page` by constructing a single-page VectorDocument.
    """
    doc = ezdxf.new(dxf_version, setup=True)
    _ensure_appid(doc)
    _ensure_layers(doc)
    msp = doc.modelspace()

    gap_units = 50.0
    x_offset = 0.0

    for page in document.pages:
        scale = px_to_units_scale(page.dpi, document.units)
        page_width_units = page.width_px * scale

        for entity in page.entities:
            _write_entity(msp, entity, page.height_px, scale, x_offset=x_offset)

        x_offset += page_width_units + gap_units

    doc.saveas(out_path)
    return out_path
