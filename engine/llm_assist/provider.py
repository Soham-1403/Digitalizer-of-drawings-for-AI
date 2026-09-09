"""Abstract vision-assist provider interface.

Kept deliberately narrow: one method that takes an image plus context
about what the deterministic pass already found (and, when this is a
user-triggered correction, what the user annotated) and returns
normalized-coordinate entity suggestions. Coordinate normalization
(0..1 relative to the image sent) means providers never need to know
the page's DPI/real-world scale — that mapping happens in
`engine.llm_assist.fusion`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SuggestedEntity:
    type: str  # matches engine.model.EntityType values
    points_norm: list[tuple[float, float]]  # 0..1, relative to the image sent
    layer_hint: Optional[str] = None  # matches engine.model.LayerCategory values, best-effort
    text: Optional[str] = None
    radius_norm: Optional[float] = None
    start_angle_deg: Optional[float] = None
    end_angle_deg: Optional[float] = None
    self_reported_confidence: float = 0.5
    note: str = ""


@dataclass
class VisionSuggestion:
    entities: list[SuggestedEntity] = field(default_factory=list)
    summary: str = ""
    raw_response: str = ""


class VisionAssistProvider(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        """Whether this provider is usable right now (e.g. API key set)."""

    @abstractmethod
    def suggest_entities(
        self,
        image_bytes: bytes,
        media_type: str,
        deterministic_summary: str,
        annotation_notes: list[str],
    ) -> VisionSuggestion:
        """Ask the model to digitize (or re-digitize) the given image.

        `deterministic_summary` is a short text description of what the
        deterministic pass already found in this region (counts by
        layer, overall confidence) — giving the model context on what to
        *check/improve* rather than digitize from a blank slate.

        `annotation_notes` are the user's on-canvas markup notes for this
        region, if any (e.g. "this wall continues behind the text" or
        "missing column here") — the single most useful signal for a
        targeted correction pass.
        """
