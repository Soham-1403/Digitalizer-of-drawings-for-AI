"""Runtime-configurable layer/color standard.

`engine.cad.layers.STRUCTURAL_LAYER_STANDARD` is a sensible *default*,
not a mandate — an MNC structural/consulting firm almost certainly has
its own CAD standards manual (its own layer names, colors, lineweights,
often required by client contracts or a corporate BIM/CAD department).
This module lets a firm supply their own mapping — as a JSON file — and
have every writer (DXF, PDF) and the canvas UI use it, without touching
Python code.

Every consumer in this codebase calls `get_layer_standard()` rather than
importing `STRUCTURAL_LAYER_STANDARD` directly, so loading a firm's
config at startup (or via a menu action in the app) takes effect
everywhere at once.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.cad.layers import STRUCTURAL_LAYER_STANDARD, LayerSpec
from engine.model import LayerCategory

_active_standard: dict[LayerCategory, LayerSpec] = dict(STRUCTURAL_LAYER_STANDARD)


def get_layer_standard() -> dict[LayerCategory, LayerSpec]:
    """The layer standard every writer/canvas should currently use."""
    return _active_standard


def reset_to_default() -> None:
    global _active_standard
    _active_standard = dict(STRUCTURAL_LAYER_STANDARD)


def set_layer_standard(mapping: dict[LayerCategory, LayerSpec]) -> None:
    """Replace the active standard wholesale (e.g. after validating a
    firm-supplied config). Every `LayerCategory` must be present —
    partial overrides go through `load_layer_standard_from_file`
    instead, which merges onto the built-in default.
    """
    missing = set(LayerCategory) - set(mapping)
    if missing:
        raise ValueError(f"Layer standard is missing entries for: {sorted(m.value for m in missing)}")
    global _active_standard
    _active_standard = dict(mapping)


def load_layer_standard_from_file(path: str) -> dict[LayerCategory, LayerSpec]:
    """Load a firm's CAD standard from JSON and make it active.

    Expected shape — one entry per `LayerCategory` value the firm wants
    to override; any category not listed keeps its built-in default:

        {
          "S-COLS": {"aci": 7, "rgb_hex": "#101010", "linetype": "CONTINUOUS",
                     "lineweight_hundredth_mm": 70, "description": "Columns (firm std. §4.2)"}
        }

    Returns the resulting full standard for convenience (e.g. to show in
    a confirmation dialog before committing to it).
    """
    with open(path, encoding="utf-8") as f:
        overrides = json.load(f)

    merged = dict(STRUCTURAL_LAYER_STANDARD)
    for layer_name, spec_dict in overrides.items():
        try:
            category = LayerCategory(layer_name)
        except ValueError as exc:
            valid = ", ".join(c.value for c in LayerCategory)
            raise ValueError(f"Unknown layer name {layer_name!r} in {path}. Valid names: {valid}") from exc

        base = merged[category]
        merged[category] = LayerSpec(
            aci=spec_dict.get("aci", base.aci),
            rgb_hex=spec_dict.get("rgb_hex", base.rgb_hex),
            linetype=spec_dict.get("linetype", base.linetype),
            lineweight_hundredth_mm=spec_dict.get("lineweight_hundredth_mm", base.lineweight_hundredth_mm),
            description=spec_dict.get("description", base.description),
        )

    set_layer_standard(merged)
    return merged


def export_layer_standard_to_file(path: str, standard: dict[LayerCategory, LayerSpec] | None = None) -> str:
    """Write the (currently active, by default) standard out as JSON —
    a starting point a firm can hand-edit into their own config rather
    than writing one from scratch.
    """
    standard = standard or get_layer_standard()
    data = {
        category.value: {
            "aci": spec.aci,
            "rgb_hex": spec.rgb_hex,
            "linetype": spec.linetype,
            "lineweight_hundredth_mm": spec.lineweight_hundredth_mm,
            "description": spec.description,
        }
        for category, spec in standard.items()
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
