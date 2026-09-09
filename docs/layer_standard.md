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

## Extending the standard

Add a new `LayerCategory` member in `engine/model.py`, then add its
`LayerSpec` (color/linetype/lineweight/description) to
`STRUCTURAL_LAYER_STANDARD` in `engine/cad/layers.py`. Nothing else needs
to change — the DXF writer, PDF writer, and canvas all read the same
table, so a new layer is automatically colored/weighted consistently
everywhere the moment it's added here.
