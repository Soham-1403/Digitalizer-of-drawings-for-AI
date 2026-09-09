"""Canonical vector-drawing data model.

This is the single source of truth shared by the deterministic
vectorizer, the LLM-vision assist module, the DXF/PDF writers, and the
desktop canvas editor. Every one of those reads or writes `Entity` /
`Page` / `VectorDocument` objects defined here — there is no separate
"preview" representation that could drift from what gets exported.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EntityType(str, Enum):
    LINE = "line"
    POLYLINE = "polyline"
    ARC = "arc"
    CIRCLE = "circle"
    TEXT = "text"
    DIMENSION = "dimension"
    HATCH = "hatch"


class EntitySource(str, Enum):
    """Where an entity's geometry came from — kept forever for audit."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"
    USER = "user"
    FUSED = "fused"  # deterministic + LLM agreed / were merged


class LayerCategory(str, Enum):
    """Structural-drawing layer taxonomy. See docs/layer_standard.md."""

    GRID = "S-GRID"
    COLUMN = "S-COLS"
    BEAM = "S-BEAM"
    WALL = "S-WALL"
    SLAB = "S-SLAB"
    FOUNDATION = "S-FDTN"
    REBAR = "S-REBAR"
    DIMENSION = "S-DIMS"
    TEXT = "S-ANNO-TEXT"
    TITLE_BLOCK = "S-ANNO-TTLB"
    HATCH = "S-HATCH"
    USER_MARKUP = "S-MARKUP"
    UNCLASSIFIED = "S-UNCLASSIFIED"


Point = tuple[float, float]


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Entity:
    """One vector primitive on one page.

    `points` holds the geometry, meaning depends on `type`:
      LINE       -> [p0, p1]
      POLYLINE   -> [p0, p1, ..., pn]
      ARC        -> [center]; radius/start_angle/end_angle in `params`
      CIRCLE     -> [center]; radius in `params`
      TEXT       -> [insertion_point]; `text`, `height` in `params`
      DIMENSION  -> [p0, p1]; `text` holds the measured value/label
      HATCH      -> [boundary points...] (closed polygon)
    """

    type: EntityType
    points: list[Point]
    layer: LayerCategory = LayerCategory.UNCLASSIFIED
    confidence: float = 0.0
    source: EntitySource = EntitySource.DETERMINISTIC
    page_index: int = 0
    text: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=_new_id)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    locked: bool = False  # user-confirmed; excluded from auto re-processing

    def touch(self) -> None:
        self.updated_at = time.time()

    def bounds(self) -> tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y), accounting for radius."""
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        if self.type in (EntityType.ARC, EntityType.CIRCLE):
            r = float(self.params.get("radius", 0.0))
            cx, cy = self.points[0]
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
        return min(xs), min(ys), max(xs), max(ys)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "points": [list(p) for p in self.points],
            "layer": self.layer.value,
            "confidence": self.confidence,
            "source": self.source.value,
            "page_index": self.page_index,
            "text": self.text,
            "params": self.params,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "locked": self.locked,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Entity":
        return Entity(
            id=d.get("id", _new_id()),
            type=EntityType(d["type"]),
            points=[tuple(p) for p in d["points"]],
            layer=LayerCategory(d.get("layer", LayerCategory.UNCLASSIFIED.value)),
            confidence=float(d.get("confidence", 0.0)),
            source=EntitySource(d.get("source", EntitySource.DETERMINISTIC.value)),
            page_index=int(d.get("page_index", 0)),
            text=d.get("text"),
            params=d.get("params", {}),
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            locked=bool(d.get("locked", False)),
        )


@dataclass
class Annotation:
    """A user-drawn markup stroke/region overlapping the source raster.

    Distinct from `Entity` (which is *digitized drawing* geometry) —
    an Annotation is an instruction *about* the digitization, consumed by
    `engine.llm_assist.fusion` and by targeted re-processing, then kept
    for audit even after it's been acted on.
    """

    points: list[Point]
    page_index: int
    note: str = ""
    kind: str = "freehand"  # "freehand" | "line" | "region"
    resolved: bool = False
    id: str = field(default_factory=_new_id)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "points": [list(p) for p in self.points],
            "page_index": self.page_index,
            "note": self.note,
            "kind": self.kind,
            "resolved": self.resolved,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Annotation":
        return Annotation(
            id=d.get("id", _new_id()),
            points=[tuple(p) for p in d["points"]],
            page_index=int(d["page_index"]),
            note=d.get("note", ""),
            kind=d.get("kind", "freehand"),
            resolved=bool(d.get("resolved", False)),
            created_at=d.get("created_at", time.time()),
        )


@dataclass
class Page:
    index: int
    width_px: int
    height_px: int
    dpi: float
    source_image_path: str
    entities: list[Entity] = field(default_factory=list)
    annotations: list[Annotation] = field(default_factory=list)
    skew_angle_deg: float = 0.0
    overall_confidence: Optional[float] = None
    notes: str = ""
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[float] = None
    review_notes: str = ""

    def entities_by_layer(self, layer: LayerCategory) -> list[Entity]:
        return [e for e in self.entities if e.layer == layer]

    def entities_below_confidence(self, threshold: float) -> list[Entity]:
        return [e for e in self.entities if e.confidence < threshold and not e.locked]

    @property
    def is_reviewed(self) -> bool:
        return self.reviewed_by is not None

    def mark_reviewed(self, reviewer: str, notes: str = "") -> None:
        """Record an explicit human sign-off on this page's digitized
        content. This is a deliberate, separate step from confidence
        scoring — a reviewer might accept a page with some low-confidence
        entities they've manually checked, and no automatic score should
        substitute for that judgment on an engineering deliverable.
        """
        self.reviewed_by = reviewer
        self.reviewed_at = time.time()
        self.review_notes = notes

    def clear_review(self) -> None:
        """Invalidate sign-off — called whenever the page's geometry
        changes after it was reviewed, since a prior approval no longer
        describes the current content.
        """
        self.reviewed_by = None
        self.reviewed_at = None
        self.review_notes = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "dpi": self.dpi,
            "source_image_path": self.source_image_path,
            "entities": [e.to_dict() for e in self.entities],
            "annotations": [a.to_dict() for a in self.annotations],
            "skew_angle_deg": self.skew_angle_deg,
            "overall_confidence": self.overall_confidence,
            "notes": self.notes,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "review_notes": self.review_notes,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Page":
        return Page(
            index=d["index"],
            width_px=d["width_px"],
            height_px=d["height_px"],
            dpi=d["dpi"],
            source_image_path=d["source_image_path"],
            entities=[Entity.from_dict(e) for e in d.get("entities", [])],
            annotations=[Annotation.from_dict(a) for a in d.get("annotations", [])],
            skew_angle_deg=d.get("skew_angle_deg", 0.0),
            overall_confidence=d.get("overall_confidence"),
            notes=d.get("notes", ""),
            reviewed_by=d.get("reviewed_by"),
            reviewed_at=d.get("reviewed_at"),
            review_notes=d.get("review_notes", ""),
        )


@dataclass
class VectorDocument:
    """The whole digitized drawing set — the canonical in-memory model."""

    source_file: str
    units: str = "mm"  # "mm" | "in" — drawing units, not pixel units
    pages: list[Page] = field(default_factory=list)
    schema_version: int = 1

    def add_page(self, page: Page) -> None:
        self.pages.append(page)

    def all_entities(self) -> list[Entity]:
        return [e for p in self.pages for e in p.entities]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_file": self.source_file,
            "units": self.units,
            "pages": [p.to_dict() for p in self.pages],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "VectorDocument":
        return VectorDocument(
            source_file=d["source_file"],
            units=d.get("units", "mm"),
            pages=[Page.from_dict(p) for p in d.get("pages", [])],
            schema_version=d.get("schema_version", 1),
        )
