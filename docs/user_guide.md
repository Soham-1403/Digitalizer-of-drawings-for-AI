# User Guide

## 1. Digitizing a drawing

**File → Open Drawing…**, pick a PDF or image (PNG/JPG/TIFF, including
multi-page TIFF scans). Two settings matter here:

- **Assumed DPI**: only used if the file itself doesn't carry DPI
  metadata (most scanners embed it; some old TIFFs and most PDFs need
  you to state it, since a PDF page has no inherent physical scale).
  Getting this right matters — it's what makes the exported DXF/PDF
  dimensionally correct in real-world units, not just "looks right on
  screen."
- **Enable AI-vision assist**: only available if `ANTHROPIC_API_KEY` is
  set in your environment. When on, any page whose deterministic
  confidence comes out low automatically gets a Claude-vision pass to
  fill gaps; when off, you still get full deterministic digitization,
  just without that fallback.

Digitization runs in the background — the app stays responsive. When it
finishes, page 1 loads into the canvas automatically.

## 2. The canvas

The canvas always shows the original scan underneath the digitized
vector geometry, in the same coordinate space — nothing is offset or
rescaled between the two.

**Toolbar (left side)** — one tool active at a time:

| Tool | What it does |
|---|---|
| Select / Move | Click to select an entity (see it in the Properties panel); drag to move it. Moving an entity locks it (confidence 1.0, source = user) so it won't get silently overwritten by a later re-run. |
| Pan | Click-drag to pan the view. Scroll wheel zooms at any time, in any tool. |
| Add Line | Click-drag to draw a new line entity on the currently-selected default layer. |
| Add Circle | Click-drag from center outward. |
| Add Text | Click, then type the text in the prompt. |
| Delete | Click an entity to remove it. |
| Markup: Freehand | Draw a scribble over the original scan to flag a problem area — this is context for AI-assist, not drawing geometry itself. |
| Markup: Corrected Line | Draw a straight line directly over the scan where you know the *actual* correct geometry is — this **does** become real, locked drawing geometry immediately. |
| Markup: Region | Click to place polygon vertices, double-click to close — flags an area for reprocessing without drawing a specific correction. |

**Right-click** near any markup stroke → **"Reprocess this region with
AI"** to trigger a targeted Claude-vision pass using that markup as
context (only available if this document was opened with AI-assist
enabled).

## 3. Panels (right side)

- **Layers**: one checkbox per layer (see `docs/layer_standard.md`) —
  independent toggles, so you can isolate exactly what you want to look
  at (e.g. only `S-WALL` and `S-DIMS`).
- **Confidence**: overall page confidence, a heatmap toggle (recolors
  every entity red→amber→green by its own confidence, independent of
  layer color), and a sorted list of every low-confidence detection —
  click one to jump straight to it on the canvas.
- **Properties**: shows the selected entity's type, confidence, source,
  and lets you reassign its layer or edit its text. Any edit here also
  locks the entity.

## 4. Multi-page documents

Use the **◀ Prev / Next ▶** buttons in the top toolbar. Each page is
digitized and held independently — annotations and edits on one page
never affect another. Page count and current position are shown between
the nav buttons.

## 5. Saving your work

**File → Save Project…** writes a single `.dgz` file containing the
original page images, every digitized entity and annotation, and a
version history entry for this save. **File → Open Project…** reads it
back exactly — including all your manual edits and markup — so you can
resume later even without the original PDF/scan file.

## 6. Exporting

**File → Export…** lets you choose:

- **DXF** — always available. Real named layers, correct colors/
  lineweights, real-world units derived from the page DPI. Opens
  natively in AutoCAD.
- **Vector PDF** — a true vector re-render (not a screenshot), so it
  stays crisp at any zoom and matches the DXF's layer colors exactly.
- **DWG** — only available if the free **ODA File Converter** is
  installed on your machine (the checkbox is disabled with an
  explanation if not). This app never bundles a proprietary DWG writer;
  see `engine/cad/dwg_export.py` and `ARCHITECTURE.md` for why.

## 7. Tips for old / degraded drawings

- If a page's overall confidence looks low, turn on the confidence
  heatmap first — it's usually one specific region (a stain, a fold, a
  faded corner), not the whole page.
- Use **Markup: Region** over that specific area rather than re-running
  AI-assist on the whole page — it's faster and gives the model tighter
  context.
- If OCR keeps failing on hand-lettered dimensions, don't fight it —
  select the text entity in Properties and just type the correct value;
  that's faster than trying to get OCR to read handwriting, and the
  entity gets locked immediately.
- Skew correction happens automatically, but if a page was scanned at a
  severe enough angle that skew estimation itself struggled (rare, but
  possible on a poor photo-of-a-drawing), consider re-scanning rather
  than trying to correct it in-app — vectorization accuracy depends on
  the deskew step running correctly first.
