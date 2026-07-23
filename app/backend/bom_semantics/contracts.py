from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from app.backend.bom_semantics.models import (
    BoardBOM,
    BomChangeEvent,
    ValidationFinding,
    WorkbookEnvelope,
)


BOM_COMPARE_SCHEMA_VERSION = 2
BOM_SEMANTIC_MODEL_VERSION = "1.0.0"


@dataclass(frozen=True)
class SourceInspection:
    envelope: WorkbookEnvelope
    boards: tuple[BoardBOM, ...]
    findings: tuple[ValidationFinding, ...]
    can_compare: bool

    def payload(self) -> dict[str, object]:
        return {
            "envelope": self.envelope.payload(),
            "boards": [board.payload() for board in self.boards],
            "findings": [finding.payload() for finding in self.findings],
            "can_compare": self.can_compare,
        }


@dataclass(frozen=True)
class CompareSummary:
    parent_count_old: int = 0
    parent_count_new: int = 0
    material_count_old: int = 0
    material_count_new: int = 0
    actual_reference_count_old: int = 0
    actual_reference_count_new: int = 0
    substitute_group_count_old: int = 0
    substitute_group_count_new: int = 0
    changed_event_count: int = 0
    blocker_count: int = 0
    event_counts: Mapping[str, int] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {
            "parent_count_old": self.parent_count_old,
            "parent_count_new": self.parent_count_new,
            "material_count_old": self.material_count_old,
            "material_count_new": self.material_count_new,
            "actual_reference_count_old": self.actual_reference_count_old,
            "actual_reference_count_new": self.actual_reference_count_new,
            "substitute_group_count_old": self.substitute_group_count_old,
            "substitute_group_count_new": self.substitute_group_count_new,
            "changed_event_count": self.changed_event_count,
            "blocker_count": self.blocker_count,
            "event_counts": dict(self.event_counts),
        }


@dataclass(frozen=True)
class CompareResult:
    analysis_fingerprint: str
    old_source_fingerprint: str
    new_source_fingerprint: str
    summary: CompareSummary
    events: tuple[BomChangeEvent, ...]
    raw_row_diff: tuple[Mapping[str, object], ...] = ()
    placement_diff: tuple[Mapping[str, object], ...] = ()
    substitute_diff: tuple[Mapping[str, object], ...] = ()
    board_metadata_diff: tuple[Mapping[str, object], ...] = ()
    metadata_diff: tuple[Mapping[str, object], ...] = ()
    blockers: tuple[ValidationFinding, ...] = ()
    warnings: tuple[ValidationFinding, ...] = ()

    @property
    def can_export(self) -> bool:
        return not self.blockers

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": BOM_COMPARE_SCHEMA_VERSION,
            "model_version": BOM_SEMANTIC_MODEL_VERSION,
            "analysis_fingerprint": self.analysis_fingerprint,
            "old_source_fingerprint": self.old_source_fingerprint,
            "new_source_fingerprint": self.new_source_fingerprint,
            "summary": self.summary.payload(),
            "events": [event.payload() for event in self.events],
            "raw_row_diff": [dict(item) for item in self.raw_row_diff],
            "placement_diff": [dict(item) for item in self.placement_diff],
            "substitute_diff": [dict(item) for item in self.substitute_diff],
            "board_metadata_diff": [
                dict(item) for item in self.board_metadata_diff
            ],
            "metadata_diff": [dict(item) for item in self.metadata_diff],
            "blockers": [finding.payload() for finding in self.blockers],
            "warnings": [finding.payload() for finding in self.warnings],
            "can_export": self.can_export,
        }
