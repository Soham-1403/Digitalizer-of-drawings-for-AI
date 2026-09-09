# Structural Drawing Layer Standard

Implemented in `engine/model.py` (`LayerCategory`) and
`engine/cad/layers.py` (`STRUCTURAL_LAYER_STANDARD`). Every entity the
pipeline produces — deterministic, LLM-assisted, or user-drawn — carries
exactly one of these layers, and it's the layer this table controls when
exported to DXF or drawn on the canvas.

| Layer name | Meaning | Color | ACI | Linetype | Lineweight |
|---|---|---|---|---|---|
| `S-GRID` | Structural grid lines and grid bubbles | 🔴 `#E03131` | 1 | CENTER | 0.13 mm |
| `S-COLS` | Columns | ⚫ `#212529` | 7 | CONTINUOUS | 0.60 mm |
| `S-BEAM` | Beams / primary horizontal framing | 🔵 `#3B5BDB` | 5 | CONTINUOUS | 0.40 mm |
| `S-WALL` | Walls | 🟦 `#0C8599` (teal) | 4 | CONTINUOUS | 0.50 mm |
| `S-SLAB` | Slab/floor boundaries | ⚪ `#ADB5BD` | 9 | CONTINUOUS | 0.20 mm |
| `S-FDTN` | Footings/foundations | 🟠 `#E8590C` | 30 | CONTINUOUS | 0.50 mm |
| `S-REBAR` | Reinforcement bars/callouts | 🟡 `#E0A800` (amber) | 42 | CONTINUOUS | 0.25 mm |
| `S-DIMS` | Dimension lines/leaders | 🟢 `#2F9E44` | 3 | CONTINUOUS | 0.18 mm |
| `S-ANNO-TEXT` | Notes/labels | 🟣 `#7048E8` (violet) | 216 | CONTINUOUS | 0.13 mm |
| `S-ANNO-TTLB` | Title block/border/sheet metadata | 🟤 `#862E1B` (sienna) | 63 | CONTINUOUS | 0.30 mm |
| `S-HATCH` | Material hatch/fill | ⚪ `#CED4DA` (pale) | 254 | CONTINUOUS | 0.09 mm |
| `S-MARKUP` | User correction/markup strokes | 🌸 `#E64980` (magenta) | 6 | DASHED | 0.25 mm |
| `S-UNCLASSIFIED` | Detected but not confidently classified | ⚫ `#868E96` (gray) | 251 | DASHED | 0.13 mm |

## Design rules behind this table

1. **No two categories share red vs. green as their only distinguishing
   signal.** The palette spans red, near-black, blue, teal, orange,
   amber, green, violet, brown, and magenta — legible for color-blind
   users, not just default-palette AutoCAD colors 1–7 picked in order.
2. **Weight follows structural importance.** Columns (0.60mm) > walls/
   foundations (0.50mm) > beams (0.40mm) > rebar/markup (0.25mm) >
   dimensions/text/grid (0.13–0.18mm) > hatch (0.09mm).
3. **`S-MARKUP` is never digitized geometry.** It's exclusively for
   on-canvas human correction strokes — a QA reviewer or a client's CAD
   manager should be able to tell at a glance what a human flagged
   versus what the pipeline produced. It's also always dashed and always
   drawn on top (`z-order` in the canvas; DXF has no z-order but the
   distinct color/linetype serves the same purpose there).
4. **`S-UNCLASSIFIED` is never layer 0.** Anything the classifier
   couldn't confidently place stays visually flagged (dashed gray) all
   the way through to the exported file, rather than silently blending
   into "everything else." A firm's QA process should treat a DXF with a
   populated `S-UNCLASSIFIED` layer as "needs review," not as finished.
5. **ACI values are legacy-viewer approximations.** The `rgb_hex` value
   is written as each entity/layer's DXF true-color (24-bit), which any
   AutoCAD 2004+ or modern open-source DXF viewer renders exactly; the
   ACI index is a reasonable nearby standard-palette color for older
   viewers that ignore true-color.

## Using your own firm's CAD standard (no code changes needed)

The table above is a sensible **default**, not a mandate. Most MNC
structural/consulting firms already have their own CAD standards manual
— their own layer names, colors, and lineweights, often required by a
client contract or an internal BIM/CAD department — and this tool is
meant to be pointed at that standard, not to impose its own.

Every writer (DXF, PDF) and the canvas reads the *active* standard via
`engine.cad.layer_registry.get_layer_standard()`, not the hardcoded
Python dict directly. To use your firm's own standard:

1. **Settings → Export CAD Standard Template…** writes the current
   standard out as JSON (also available as `config/layer_standard.example.json`
   in this repo) — edit the fields you want to change; anything you
   leave out keeps its built-in default.
2. **Settings → Load Firm CAD Standard…** loads that JSON and applies it
   immediately, everywhere (open documents' canvas re-renders, and every
   subsequent DXF/PDF export uses it) — no restart, no code change.

Programmatically (e.g. for the batch/headless CLI):

```python
from engine.cad.layer_registry import load_layer_standard_from_file
load_layer_standard_from_file("path/to/firm_standard.json")
```

A partial override file only needs the layers you're changing:

```json
{
  "S-COLS": {"rgb_hex": "#101010", "lineweight_hundredth_mm": 70,
             "description": "Columns per Firm CAD Standard §4.2"}
}
```

## Adding an entirely new layer category

Add a new `LayerCategory` member in `engine/model.py`, then add its
default `LayerSpec` to `STRUCTURAL_LAYER_STANDARD` in
`engine/cad/layers.py`. Nothing else needs to change — the registry,
writers, and canvas all key off the same enum.
