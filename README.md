# Digitalizer of Drawings for AI

A desktop application that converts scanned/PDF structural and architectural
drawings — new or decades-old — into clean, layered, editable CAD data
(DXF, with optional DWG conversion), with an in-app visualizer/editor,
per-entity confidence scoring, and a hybrid **deterministic + LLM-vision**
digitization pipeline.

Built with the assumption that this is an internal tool for a structural
engineering / consulting firm digitizing large archives of legacy drawings
as well as processing new incoming survey/as-built scans.

## Why hybrid (deterministic + LLM vision)?

Classical computer-vision vectorization (Hough transforms, contour tracing,
skeletonization) is fast, fully explainable, and free to run at scale — but
it struggles with degraded scans, inconsistent old drafting conventions,
overlapping annotations, and symbol/text semantics. Vision-capable LLMs are
good at exactly that kind of ambiguous, context-heavy interpretation, but are
slower, non-deterministic, and expensive to run on every page.

So the pipeline runs deterministic CV first (fast, cheap, consistent), scores
its own confidence per entity, and only calls out to an LLM vision model for:

1. Pages/regions where deterministic confidence is low (automatic fallback).
2. Regions the user explicitly flags via on-canvas annotation (targeted
   re-interpretation, guided by what the user drew).
3. Optional "AI pass" the user can trigger on demand for a whole page.

The two outputs are fused (see `engine/llm_assist/fusion.py`), with LLM
suggestions clearly tagged by source and confidence so a human editor can
always tell what came from where before signing off.

## Core features

- Ingest multi-page PDFs, PNG/JPG/TIFF scans, at any resolution/DPI.
- Deterministic vectorization: lines, polylines, arcs/circles, hatch/fill
  regions, text/dimension regions (OCR-backed).
- Optional LLM-vision digitization and correction-assist pass.
- Per-entity **confidence score** (0–1), visualized as a heatmap overlay.
- Structural-drawing-oriented **DXF layer standard** with a curated,
  non-default ACI color palette (see `docs/layer_standard.md`) — real
  layers, not everything dumped on layer 0.
- DXF export (native); optional DWG export via the free ODA File Converter
  if installed locally (no proprietary SDK is bundled — see
  `engine/cad/dwg_export.py`).
- Accurate vector PDF export (re-rendered from the vector model, not a
  screenshot).
- In-app canvas visualizer/editor:
  - Raster underlay + vector overlay, per-layer visibility, pan/zoom.
  - **Markup/annotation tool**: draw directly on top of the source scan to
    flag errors or clarify intent for the deterministic/LLM pipeline —
    annotations are geometry the fusion step reads, not just comments.
  - **Correction tools**: select/move/add/delete/reshape entities, snap to
    existing geometry, re-layer entities, edit text.
  - Re-run digitization on a region after edits/annotations; the vector
    view and exported files update together.
- Project files bundle the source pages, vector model, annotations, and
  edit history so work can be saved/resumed and audited later.

## Repository layout

```
engine/         Headless, Qt-free digitization engine (importable, testable)
  io/           PDF/image loading
  preprocess/   Deskew, denoise, binarize
  vectorize/    Deterministic CV vectorization
  classify/     Layer classification heuristics, symbol detection hooks
  confidence/   Confidence scoring
  cad/          Layer/color standard, DXF/DWG/PDF writers
  llm_assist/   Vision-LLM provider interface + Claude implementation + fusion
  annotations/  On-canvas markup data model
  project/      Project file schema + save/load/versioning
  pipeline.py   Orchestrates the full multi-page run

app/            PySide6 desktop application (UI only; calls into engine/)
  widgets/      Canvas visualizer/editor, layers panel, confidence panel, ...
  tools/        Edit tools, annotation drawing tools

tests/          Pytest suite for the engine (headless, no Qt needed)
docs/           Layer standard, confidence scoring methodology, user guide
packaging/      PyInstaller spec for building distributable executables
```

## System requirements

- Python 3.10+.
- **Linux**: Qt needs a few system libraries beyond what pip installs —
  `libegl1`, `libgl1`, `libxkbcommon0`, `libxcb-cursor0` (Debian/Ubuntu:
  `apt install libegl1 libgl1 libxkbcommon0 libxcb-cursor0`). Without
  them the app fails to import PySide6 with an `ImportError` naming the
  missing `.so`.
- **Tesseract OCR** (optional but recommended): install the `tesseract`
  binary for your OS so `pytesseract` can read dimension/label text.
  Without it, text/dimension regions are still *detected* (by shape),
  just without a recognized string — the app degrades gracefully rather
  than failing.
- **ODA File Converter** (optional): only needed for DWG export; DXF
  export always works without it.

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the desktop app
python -m app.main

# Or run the engine headlessly (useful for batch jobs / CI / testing)
python -m engine.pipeline path/to/drawing.pdf --out out/
```

LLM-vision assist requires an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Without it, the app runs in deterministic-only mode — the AI-assist buttons
are disabled with an explanation rather than failing silently.

## Status

Early but functional end-to-end skeleton: upload → deterministic
vectorization → classification → confidence scoring → canvas
visualization/editing → DXF/PDF export all work on a real pipeline (see
`tests/`). LLM-vision fallback, symbol recognition, and DWG conversion are
wired up behind clean interfaces so they can be strengthened independently.
See `ARCHITECTURE.md` for the full design rationale, known limitations, and
roadmap.
