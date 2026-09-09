"""The structural-drawing DXF layer & color standard.

Design goals (see ARCHITECTURE.md §4):
  - Every category gets a genuinely distinct hue — no two categories rely
    on red vs. green alone as their only distinguishing signal, so the
    drawing stays legible for color-blind users.
  - Structural members (columns/beams/walls/foundations) are visually
    heavier (thicker lineweight) than annotation/dimension layers.
  - A dedicated, always-distinct **user markup** layer (bright magenta,
    dashed) so a QA reviewer can immediately tell human-flagged markup
    apart from digitized drawing content.
  - **Unclassified** geometry is dashed gray, not silently dumped onto
    layer 0 with everything else — it stays visually flagged as
    "needs review" all the way through to the exported file.

`aci` (AutoCAD Color Index) values here are reasonable legacy-viewer
approximations of the curated `rgb_hex`; `rgb_hex` is written to the DXF
as the entity/layer true-color and is what any modern viewer (AutoCAD
2004+, most open-source DXF viewers) actually renders.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.model import LayerCategory


@dataclass(frozen=True)
class LayerSpec:
    aci: int
    rgb_hex: str
    linetype: str
    lineweight_hundredth_mm: int
    description: str


# Lineweight values must be members of DXF's discrete valid set
# (hundredths of a mm): 0,5,9,13,15,18,20,25,30,35,40,50,53,60,70,80,90,
# 100,106,120,140,158,200,211.
STRUCTURAL_LAYER_STANDARD: dict[LayerCategory, LayerSpec] = {
    LayerCategory.GRID: LayerSpec(
        aci=1, rgb_hex="#E03131", linetype="CENTER", lineweight_hundredth_mm=13,
        description="Structural grid lines and grid bubbles.",
    ),
    LayerCategory.COLUMN: LayerSpec(
        aci=7, rgb_hex="#212529", linetype="CONTINUOUS", lineweight_hundredth_mm=60,
        description="Columns (primary vertical structural members).",
    ),
    LayerCategory.BEAM: LayerSpec(
        aci=5, rgb_hex="#3B5BDB", linetype="CONTINUOUS", lineweight_hundredth_mm=40,
        description="Beams and other primary horizontal framing.",
    ),
    LayerCategory.WALL: LayerSpec(
        aci=4, rgb_hex="#0C8599", linetype="CONTINUOUS", lineweight_hundredth_mm=50,
        description="Walls (parallel-line pairs at wall-thickness spacing).",
    ),
    LayerCategory.SLAB: LayerSpec(
        aci=9, rgb_hex="#ADB5BD", linetype="CONTINUOUS", lineweight_hundredth_mm=20,
        description="Slab/floor boundaries.",
    ),
    LayerCategory.FOUNDATION: LayerSpec(
        aci=30, rgb_hex="#E8590C", linetype="CONTINUOUS", lineweight_hundredth_mm=50,
        description="Footings and foundation outlines.",
    ),
    LayerCategory.REBAR: LayerSpec(
        aci=42, rgb_hex="#E0A800", linetype="CONTINUOUS", lineweight_hundredth_mm=25,
        description="Reinforcement bars/callouts.",
    ),
    LayerCategory.DIMENSION: LayerSpec(
        aci=3, rgb_hex="#2F9E44", linetype="CONTINUOUS", lineweight_hundredth_mm=18,
        description="Dimension lines and leaders.",
    ),
    LayerCategory.TEXT: LayerSpec(
        aci=216, rgb_hex="#7048E8", linetype="CONTINUOUS", lineweight_hundredth_mm=13,
        description="General notes/labels/annotation text.",
    ),
    LayerCategory.TITLE_BLOCK: LayerSpec(
        aci=63, rgb_hex="#862E1B", linetype="CONTINUOUS", lineweight_hundredth_mm=30,
        description="Title block, border, and sheet metadata.",
    ),
    LayerCategory.HATCH: LayerSpec(
        aci=254, rgb_hex="#CED4DA", linetype="CONTINUOUS", lineweight_hundredth_mm=9,
        description="Material hatch patterns and fills.",
    ),
    LayerCategory.USER_MARKUP: LayerSpec(
        aci=6, rgb_hex="#E64980", linetype="DASHED", lineweight_hundredth_mm=25,
        description="User-drawn correction/markup strokes — never digitized geometry.",
    ),
    LayerCategory.UNCLASSIFIED: LayerSpec(
        aci=251, rgb_hex="#868E96", linetype="DASHED", lineweight_hundredth_mm=13,
        description="Detected but not confidently classified — flagged for review.",
    ),
}


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
