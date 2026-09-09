"""Merge deterministic entities with LLM-vision suggestions and
annotation hints into the page's final entity list.

Fusion rules (see ARCHITECTURE.md §3):
  - An LLM suggestion that geometrically matches an existing deterministic
    entity is treated as *agreement*: the existing entity's confidence is
    boosted and its source becomes FUSED, rather than adding a duplicate.
  - An LLM suggestion with no nearby deterministic match is added as a
    new entity with source=LLM, with its own (generally lower, since
    it's unverified by geometry) confidence.
  - Annotations never directly become drawing entities by themselves —
    they're the *reason* a region gets reprocessed / the *context* fed
    to the LLM. An annotation of kind "line" is the one exception: it is
    literal corrected geometry drawn by a human, so it's added directly
    as a locked, confidence=1.0, source=USER entity.
"""

from __future__ import annotations

import math

from engine.confidence.scoring import score_entity_confidence
from engine.llm_assist.provider import SuggestedEntity, VisionSuggestion
from engine.model import Annotation, Entity, EntitySource, EntityType, LayerCategory, Page

BBox = tuple[float, float, float, float]  # x0, y0, x1, y1 in page pixel space

_LAYER_HINT_LOOKUP = {c.value: c for c in LayerCategory}


def denormalize_point(point_norm: tuple[float, float], crop_bbox: BBox) -> tuple[float, float]:
    x0, y0, x1, y1 = crop_bbox
    nx, ny = point_norm
    return (x0 + nx * (x1 - x0), y0 + ny * (y1 - y0))


def _entity_anchor(entity: Entity) -> tuple[float, float]:
    xs = [p[0] for p in entity.points]
    ys = [p[1] for p in entity.points]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _find_geometric_match(
    candidate_points: list[tuple[float, float]],
    existing: list[Entity],
    dist_tol_px: float,
) -> Entity | None:
    if not candidate_points:
        return None
    cx = sum(p[0] for p in candidate_points) / len(candidate_points)
    cy = sum(p[1] for p in candidate_points) / len(candidate_points)

    best, best_dist = None, dist_tol_px
    for entity in existing:
        ex, ey = _entity_anchor(entity)
        dist = math.hypot(cx - ex, cy - ey)
        if dist <= best_dist:
            best, best_dist = entity, dist
    return best


def suggestion_to_entity(
    suggestion: SuggestedEntity,
    crop_bbox: BBox,
    page_index: int,
    local_image_quality: float,
) -> Entity | None:
    try:
        entity_type = EntityType(suggestion.type)
    except ValueError:
        return None

    points = [denormalize_point(p, crop_bbox) for p in suggestion.points_norm]
    if not points:
        return None

    layer = _LAYER_HINT_LOOKUP.get(suggestion.layer_hint or "", LayerCategory.UNCLASSIFIED)

    params: dict = {}
    if suggestion.radius_norm is not None:
        crop_width = crop_bbox[2] - crop_bbox[0]
        params["radius"] = suggestion.radius_norm * crop_width
    if suggestion.start_angle_deg is not None:
        params["start_angle_deg"] = suggestion.start_angle_deg
    if suggestion.end_angle_deg is not None:
        params["end_angle_deg"] = suggestion.end_angle_deg

    confidence = score_entity_confidence(
        geometric_confidence=suggestion.self_reported_confidence,
        source_agreement=0.5,  # no deterministic counterpart, by construction of this path
        local_image_quality=local_image_quality,
    )

    return Entity(
        type=entity_type,
        points=points,
        layer=layer,
        confidence=confidence,
        source=EntitySource.LLM,
        page_index=page_index,
        text=suggestion.text,
        params=params,
        metadata={"llm_note": suggestion.note},
    )


def fuse_llm_suggestions(
    page: Page,
    suggestion: VisionSuggestion,
    crop_bbox: BBox,
    local_image_quality: float,
    match_dist_px: float = 25.0,
) -> dict:
    """Apply an LLM suggestion batch to `page.entities` in place.

    Returns a small report dict: {"agreed": int, "added": int} for
    logging/UI feedback (e.g. "AI assist agreed with 12 of 14 existing
    detections and added 3 new ones").
    """
    agreed = 0
    added = 0

    for suggested in suggestion.entities:
        points = [denormalize_point(p, crop_bbox) for p in suggested.points_norm]
        match = _find_geometric_match(points, page.entities, match_dist_px)

        if match is not None and not match.locked:
            match.confidence = score_entity_confidence(
                geometric_confidence=max(match.confidence, suggested.self_reported_confidence),
                source_agreement=1.0,
                local_image_quality=local_image_quality,
            )
            match.source = EntitySource.FUSED
            match.metadata["llm_note"] = suggested.note
            match.touch()
            agreed += 1
            continue

        new_entity = suggestion_to_entity(suggested, crop_bbox, page.index, local_image_quality)
        if new_entity is not None:
            page.entities.append(new_entity)
            added += 1

    return {"agreed": agreed, "added": added}


def apply_user_annotation(page: Page, annotation: Annotation) -> Entity | None:
    """A "line"-kind annotation is literal corrected geometry: add it
    directly as a locked, fully-confident, user-sourced entity so it's
    never overwritten by a later automatic re-run.
    """
    if annotation.kind != "line" or len(annotation.points) < 2:
        return None

    entity = Entity(
        type=EntityType.LINE,
        points=[annotation.points[0], annotation.points[-1]],
        layer=LayerCategory.UNCLASSIFIED,
        confidence=1.0,
        source=EntitySource.USER,
        page_index=page.index,
        locked=True,
        metadata={"from_annotation_id": annotation.id, "note": annotation.note},
    )
    page.entities.append(entity)
    return entity


def find_entities_near_annotation(page: Page, annotation: Annotation, max_dist_px: float = 20.0) -> list[Entity]:
    """Entities whose geometry lies close to a (freehand/region)
    annotation — candidates for re-processing / confidence demotion when
    a human flags "this is wrong" over an area.
    """
    nearby = []
    for entity in page.entities:
        if entity.locked:
            continue
        ex, ey = _entity_anchor(entity)
        if any(math.hypot(ex - ax, ey - ay) <= max_dist_px for ax, ay in annotation.points):
            nearby.append(entity)
    return nearby
