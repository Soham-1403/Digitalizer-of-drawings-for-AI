# Confidence Scoring Methodology

Implemented in `engine/confidence/scoring.py`. This document explains
what the number means and why it's computed this way, so a reviewer
trusts (or correctly distrusts) it.

## The formula

```
confidence = 0.55 × geometric_consistency
           + 0.25 × source_agreement
           + 0.20 × local_image_quality
```

unless the entity is `locked` (user-confirmed), in which case confidence
is pinned to `1.0` and the formula doesn't run at all.

### Geometric consistency (weight 0.55, the dominant term)

How well the fitted primitive actually matches raw pixel evidence:

- **Lines**: fraction of sample points along the fitted segment that
  have foreground pixels nearby in the binary mask
  (`vectorize/lines.py:score_segment_confidence`). A line that "connects
  the dots" across a gap that was never really solid scores low.
- **Circles/arcs**: fraction of the fitted circumference with pixel
  support (`vectorize/curves.py:_circumference_coverage`), or the
  algebraic circle-fit residual for arcs.
- **Hatch/closed regions**: how well the simplified polygon explains the
  original contour's perimeter, blended with the gradient-orientation
  concentration used to detect genuine hatch texture
  (`vectorize/contours.py`).
- **Text**: the OCR engine's own per-word confidence (falling back to a
  baseline if OCR is unavailable, since the region was still detected as
  text-shaped by connected-component geometry even without a legible
  reading).

This term also incorporates *classification* confidence for lines (how
sure the grid/wall/dimension pattern-matcher is), blended 50/50 with the
raw geometric detection confidence — see `engine/pipeline.py`.

### Source agreement (weight 0.25)

- **1.0**: the deterministic pass and an LLM-vision pass independently
  produced the same entity for this region — two different methods
  agreeing is real evidence.
- **0.5** (neutral): only one pass has run; there's nothing to agree or
  disagree with yet.
- **0.0**: the two passes actively disagree. Both versions are kept
  (tagged by `source`), and this pulls confidence down so the
  disagreement surfaces for human review instead of one version being
  silently chosen.

### Local image quality (weight 0.20)

Local contrast (`np.std`) in the entity's bounding box, normalized
against the page's own contrast distribution
(`estimate_local_image_quality`). This is *relative to the page*, not an
absolute brightness cutoff — a perfectly legible dark scan and a
perfectly legible light scan should both score well; what should score
low is a region that's washed out *relative to the rest of that same
drawing* (a classic old-blueprint failure mode: one corner faded, the
rest fine).

## Page-level rollup

`rollup_page_confidence` isn't a plain mean — it subtracts a penalty
proportional to the *standard deviation* of entity confidences:

```
page_confidence = mean(confidences) - 0.3 × std(confidences)
```

Rationale: a page that's uniformly mediocre (say, every entity around
0.6) is a different, more tractable situation than a page that's half
excellent and half garbage (many entities at 0.95, several at 0.1) —
the second case usually means one specific region genuinely failed
(a stain, a tear, a missed corner) and deserves targeted attention, not
just "this page is fine on average."

## What confidence drives

- **`needs_llm_fallback`** (threshold 0.55 by default): a page whose
  rolled-up confidence falls below this automatically becomes a
  candidate for the LLM-vision fallback pass, if AI-assist is enabled
  for this document.
- **Canvas heatmap**: per-entity confidence, colored red → amber → green,
  toggleable independently of layer visibility.
- **Confidence panel triage list**: every entity below the threshold,
  sorted worst-first, so a reviewer works the actual problem list
  instead of scanning the whole drawing.
- **DXF XDATA**: every exported entity carries its confidence and source
  as XDATA under the `DIGITALIZER` appid, so the number survives being
  opened in AutoCAD — a firm's QA process can query it there too, not
  just in this app.
