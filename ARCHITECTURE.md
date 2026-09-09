# Architecture & Design Rationale

This document explains *why* the system is shaped the way it is. It's
written from the perspective of a structural/consulting engineering firm
that needs to digitize both incoming survey scans and a large legacy
archive, at a quality bar where the output is actually usable in AutoCAD,
not just a pretty picture.

## 1. The real-world problem space

### 1.1 What kinds of source documents actually show up

- Clean, recent PDF exports from AutoCAD/Revit (best case — often has
  selectable vector text and even a vector drawing already inside the PDF).
- Scanned prints of digital drawings (300–600 DPI, moderate noise).
- Scanned **old hand-drafted or blueline/blueprint drawings** — decades
  old, faded, uneven line weight from pencil/ink, torn corners, taped
  repairs, coffee stains, non-standard title blocks, imperial units on
  drawings that predate metric standardization at the firm.
- Photographs of drawings taken in the field (perspective distortion,
  uneven lighting, shadows from the photographer, curled paper).
- Multi-page sets where later pages reference earlier ones ("see grid on
  S-101"), continuous drawings split across multiple sheets with
  match-lines, and drawings with multiple details/views on one sheet.
- Mixed content sheets: a structural plan next to a detail callout, a
  section, a schedule table, and a general-notes text block, all on one
  page.

### 1.2 Difficulties this creates, and how the design responds

| Difficulty | Design response |
|---|---|
| Skewed/rotated scans (fed at an angle) | `engine/preprocess/deskew.py` estimates and corrects rotation before vectorization; skew angle is stored and shown to the user rather than silently discarded. |
| Faded/inconsistent line weight on old drawings | `preprocess/binarize.py` uses adaptive (local) thresholding, not a single global threshold, plus optional CLAHE contrast normalization — a single brightness cutoff fails across a drawing with both faded and dark regions. |
| Noise: dust, stains, tape marks, fold lines | `preprocess/denoise.py` uses morphological opening/closing and small-component removal sized relative to expected line width, so it clears specks without erasing thin hatching. |
| Non-standard/inconsistent old drafting symbols | Symbol/legend recognition is intentionally a **pluggable, low-confidence-by-default** module (`classify/symbols.py`) rather than a hard-coded symbol library — it flags candidate symbol regions for either LLM-vision interpretation or human confirmation instead of guessing silently. |
| Text and dimensions mixed into line geometry | Text-region detection (`vectorize/text_regions.py`) runs a stroke-width/aspect-ratio filter *before* line detection, so short text strokes aren't merged into wall lines, and OCR only runs on regions already isolated as text-like. |
| Multi-page continuity (match-lines, shared grids) | The project/pipeline layer processes pages independently but keeps a shared `page_index` and lets the user link grid references across pages; nothing assumes a single page is the whole drawing. |
| Deterministic CV fails outright on a region | Confidence score per entity + per-region drops below threshold → automatic flag for LLM-vision fallback *or* explicit user annotation-guided reprocessing. Never silently emits low-quality geometry as if it were certain. |
| Users need to tell the tool "this is wrong" precisely | The annotation/markup layer is drawn **in the same coordinate space** as the source raster and the vector overlay, and is passed as literal geometry (regions + strokes) into the fusion step and into the LLM vision prompt — not just a free-text comment the model has to guess the location of. |
| Firm needs an audit trail (who/what produced each line) | Every entity carries `source` (`deterministic`, `llm`, `user`), `confidence`, and a timestamp/version in `project/schema.py`; edit history is retained, not overwritten. |
| Output has to survive contact with real AutoCAD users | DXF is generated with real named layers, ACI colors, and lineweights per `docs/layer_standard.md` — never single-layer "layer 0 dump" output, which is unusable at scale and immediately flagged by any CAD manager. |
| DWG is often what's actually asked for | DWG is not natively written (no legitimate free path to Autodesk's format); the app is explicit about this and offers DXF-native + optional ODA File Converter handoff, rather than pretending to produce DWG. |

## 2. Pipeline flow

```
PDF/Image ──▶ io.load ──▶ preprocess (deskew/denoise/binarize)
                                   │
                                   ▼
                     vectorize (lines, curves, contours, text)
                                   │
                                   ▼
                    classify (layer rules + symbol hooks)
                                   │
                                   ▼
                     confidence.score (per entity + per page)
                                   │
                     ┌─────────────┴──────────────┐
                     │ confidence < threshold      │ confidence OK
                     ▼                              │
        llm_assist (Claude vision fallback)         │
                     │                              │
                     └─────────────┬────────────────┘
                                   ▼
                          fusion (merge + annotation hints)
                                   │
                                   ▼
                    engine.model VectorDocument (canonical)
                                   │
                 ┌─────────────────┼─────────────────┐
                 ▼                 ▼                  ▼
           cad.dxf_writer   cad.pdf_writer      app canvas (edit)
                 │                                    │
                 ▼                                    ▼
         optional dwg_export               user edits/annotates
                                                       │
                                            re-run pipeline on region
                                            (loops back to fusion)
```

The important property: **the canvas, the DXF, and the PDF are all views
of the same `VectorDocument`.** There's no separate "preview" model that
can drift from what's exported — editing in the canvas mutates the same
entities that `dxf_writer`/`pdf_writer` serialize.

## 3. Confidence scoring

Documented in `docs/confidence_scoring.md`; summarized here. Confidence is
a weighted combination of:

- **Geometric consistency** — how well raw pixel evidence supports the
  fitted primitive (inlier ratio for Hough lines/circles, contour fit
  residual).
- **Source agreement** — deterministic and LLM outputs agreeing on the
  same region raises confidence; disagreement lowers it and both are kept,
  tagged, for human review rather than silently picking one.
- **Local image quality** — noise/contrast estimate in the entity's
  neighborhood (a perfectly fitted line in a badly degraded region is
  still flagged lower than the same fit in a clean region).
- **User confirmation** — an entity a human has touched/approved in the
  editor is pinned to confidence 1.0 and excluded from automatic
  re-processing unless the user explicitly asks to redo it.

Confidence is per-entity (so the canvas can heatmap individual lines) and
rolled up per-page (so a reviewer can triage which pages need attention
without opening every one).

## 4. Layer & color standard

See `docs/layer_standard.md` for the full table. Design goals: distinct
hues that stay distinguishable to color-blind users (avoiding pure
red/green as the *only* distinguishing pair), consistent lineweight-by-
category (structural members heavier than annotations), and a dedicated
**user-markup layer** (bright magenta, always on top, never mixed into
the digitized geometry) so a firm's QA reviewer can immediately tell what
came from the pipeline versus what a human flagged.

## 5. Known limitations / roadmap (honest, not glossed over)

- **Symbol/legend recognition** (e.g., firm-specific rebar callouts,
  door/window swing symbols) ships as a hook with a generic
  shape-signature matcher, not a trained classifier — it's the first
  place to invest in a learned model once there's labeled data from this
  firm's own drawing archive.
- **DWG export** depends on an external, optionally-installed tool
  (ODA File Converter); there is no bundled DWG writer.
- **OCR** (`pytesseract`) is adequate for clean printed dimension text; it
  is noticeably weaker on hand-lettered old drawings, which is exactly the
  case the LLM-vision fallback exists to cover.
- **LLM-vision calls are not free or instant** — the pipeline is designed
  so they're the exception path (low confidence or explicit request), not
  the default per-page behavior, to keep cost/latency acceptable at
  archive scale.
- **True vector text extraction from "born-digital" PDFs** (i.e., PDFs
  that already contain real vector paths/text from AutoCAD, not just a
  raster scan) is not yet special-cased — today every input is rasterized
  and rebuilt. A fast-path that reuses existing vector paths directly when
  present is a natural next step and would improve accuracy further for
  that subset of inputs.

## 6. Why these tools/options exist in the UI

- **Per-page AI-assist toggle**, not a global on/off — a firm processing a
  mixed batch (some clean recent PDFs, some rough old scans) needs
  per-document control over cost/latency vs. accuracy.
- **Layer visibility + confidence heatmap as independent toggles** — a
  reviewer often wants "show me only low-confidence beam lines," not just
  "show me all beams."
- **Annotation tool is a first-class drawing tool** (not a sticky-note),
  because the most useful correction signal is *exactly where* on the
  drawing something is wrong, in the same units/scale as the drawing.
- **Save re-runs export**, not just the in-memory view — so the DXF/PDF
  a firm hands to a client always matches the last thing a human looked
  at on screen, with no separate "remember to re-export" step to forget.
