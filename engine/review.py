"""Export-readiness evaluation.

A confidence score is a machine's estimate, not an engineer's sign-off.
For a deliverable that a structural/consulting firm will stamp its name
on, the app should make it hard to *accidentally* export a page nobody
has actually reviewed — not impossible (a firm's process is theirs to
define), but visible and requiring a deliberate acknowledgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.confidence.scoring import LOW_CONFIDENCE_THRESHOLD
from engine.model import Page, VectorDocument


@dataclass
class PageReadiness:
    page_index: int
    is_reviewed: bool
    low_confidence_count: int
    unresolved_annotation_count: int

    @property
    def warnings(self) -> list[str]:
        messages = []
        if not self.is_reviewed:
            messages.append("not reviewed/signed off by an engineer")
        if self.low_confidence_count:
            messages.append(f"{self.low_confidence_count} detection(s) below confidence threshold")
        if self.unresolved_annotation_count:
            messages.append(f"{self.unresolved_annotation_count} unresolved markup annotation(s)")
        return messages

    @property
    def is_clean(self) -> bool:
        return not self.warnings


def evaluate_page_readiness(page: Page, confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD) -> PageReadiness:
    low_confidence = page.entities_below_confidence(confidence_threshold)
    unresolved = [a for a in page.annotations if not a.resolved]
    return PageReadiness(
        page_index=page.index,
        is_reviewed=page.is_reviewed,
        low_confidence_count=len(low_confidence),
        unresolved_annotation_count=len(unresolved),
    )


@dataclass
class DocumentReadiness:
    pages: list[PageReadiness] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return all(p.is_clean for p in self.pages)

    def summary_lines(self) -> list[str]:
        lines = []
        for p in self.pages:
            if not p.is_clean:
                lines.append(f"Page {p.page_index + 1}: {', '.join(p.warnings)}")
        return lines


def evaluate_document_readiness(
    document: VectorDocument, confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD
) -> DocumentReadiness:
    return DocumentReadiness(
        pages=[evaluate_page_readiness(p, confidence_threshold) for p in document.pages]
    )
