"""Project data model.

A `Project` wraps a `VectorDocument` with the settings it was produced
under and a version history of snapshots, so a firm can later answer
"what did this look like before the last edit" or "was AI-assist even
enabled when this was digitized" — both real audit questions for
engineering deliverables.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from engine.model import VectorDocument

PROJECT_SCHEMA_VERSION = 1


@dataclass
class ProjectSnapshot:
    timestamp: float
    note: str
    document: dict[str, Any]  # VectorDocument.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return {"timestamp": self.timestamp, "note": self.note, "document": self.document}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ProjectSnapshot":
        return ProjectSnapshot(timestamp=d["timestamp"], note=d["note"], document=d["document"])


@dataclass
class Project:
    name: str
    source_file_name: str
    document: VectorDocument
    dpi: float
    units: str = "mm"
    ai_assist_enabled: bool = False
    confidence_threshold: float = 0.55
    history: list[ProjectSnapshot] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    schema_version: int = PROJECT_SCHEMA_VERSION

    def snapshot(self, note: str = "") -> None:
        self.history.append(
            ProjectSnapshot(timestamp=time.time(), note=note, document=self.document.to_dict())
        )
        self.updated_at = time.time()

    def restore(self, history_index: int) -> None:
        snap = self.history[history_index]
        self.document = VectorDocument.from_dict(snap.document)
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "source_file_name": self.source_file_name,
            "document": self.document.to_dict(),
            "dpi": self.dpi,
            "units": self.units,
            "ai_assist_enabled": self.ai_assist_enabled,
            "confidence_threshold": self.confidence_threshold,
            "history": [h.to_dict() for h in self.history],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Project":
        return Project(
            name=d["name"],
            source_file_name=d["source_file_name"],
            document=VectorDocument.from_dict(d["document"]),
            dpi=d["dpi"],
            units=d.get("units", "mm"),
            ai_assist_enabled=d.get("ai_assist_enabled", False),
            confidence_threshold=d.get("confidence_threshold", 0.55),
            history=[ProjectSnapshot.from_dict(h) for h in d.get("history", [])],
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            schema_version=d.get("schema_version", PROJECT_SCHEMA_VERSION),
        )
