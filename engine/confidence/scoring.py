"""Confidence scoring.

Final entity confidence is a weighted blend of four independent signals,
deliberately kept separate (rather than one opaque number from a single
model) so a reviewer — or this codebase, in `engine.llm_assist.fusion`
and the pipeline's fallback routing — can tell *why* something scored
low: bad pixel evidence? disagreement between deterministic and LLM
passes? a genuinely degraded region of the source scan?

    confidence = w_geo   * geometric_consistency
               + w_agree * source_agreement
               + w_qual  * local_image_quality

User-confirmed entities bypass this entirely and are pinned to 1.0.
"""

from __future__ import annotations

import numpy as np

WEIGHT_GEOMETRIC = 0.55
WEIGHT_AGREEMENT = 0.25
WEIGHT_IMAGE_QUALITY = 0.20

LOW_CONFIDENCE_THRESHOLD = 0.55  # below this: route to LLM fallback / flag for review


def estimate_local_image_quality(gray: np.ndarray, bbox: tuple[float, float, float, float]) -> float:
    """Proxy for "is this region of the scan even legible?"

    Uses local contrast (std-dev of pixel intensity) normalized against
    the page's own contrast distribution, so the metric is relative to
    this drawing rather than an absolute brightness threshold that would
    fail differently on a dark vs. light scan.
    """
    h, w = gray.shape[:2]
    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(w, int(x1)), min(h, int(y1))
    if x1 <= x0 or y1 <= y0:
        return 0.5

    region = gray[y0:y1, x0:x1]
    if region.size == 0:
        return 0.5

    local_std = float(np.std(region))
    page_std = float(np.std(gray)) or 1.0
    ratio = local_std / page_std
    return float(np.clip(ratio, 0.0, 1.0))


def score_entity_confidence(
    geometric_confidence: float,
    source_agreement: float = 0.5,
    local_image_quality: float = 0.75,
    user_locked: bool = False,
) -> float:
    """Combine the three signals into one final confidence in [0, 1].

    `source_agreement` should be:
      - 1.0 if deterministic and LLM-vision independently produced the
        same entity for this region,
      - 0.5 (neutral) if only one pass ran and there's nothing to agree
        or disagree with,
      - 0.0 if the two passes actively disagree on this region.
    """
    if user_locked:
        return 1.0

    score = (
        WEIGHT_GEOMETRIC * geometric_confidence
        + WEIGHT_AGREEMENT * source_agreement
        + WEIGHT_IMAGE_QUALITY * local_image_quality
    )
    return float(np.clip(score, 0.0, 1.0))


def rollup_page_confidence(entity_confidences: list[float]) -> float:
    """Page-level confidence for triage: the mean, but with a penalty if
    the *variance* is high (a page that's half perfect and half garbage
    is more concerning than one that's uniformly mediocre, because it
    usually means one region genuinely failed rather than the whole
    page being a hard scan).
    """
    if not entity_confidences:
        return 0.0
    arr = np.array(entity_confidences)
    mean = float(np.mean(arr))
    spread_penalty = float(np.std(arr)) * 0.3
    return float(np.clip(mean - spread_penalty, 0.0, 1.0))


def needs_llm_fallback(entity_confidences: list[float], threshold: float = LOW_CONFIDENCE_THRESHOLD) -> bool:
    if not entity_confidences:
        return True
    return rollup_page_confidence(entity_confidences) < threshold
