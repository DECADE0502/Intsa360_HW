from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping, Sequence


class WorkbookProfile(str, Enum):
    CAPTURE_RAW = "capture_raw"
    PLM_SINGLE_BOARD = "plm_single_board"
    PLM_MULTI_BOARD = "plm_multi_board"
    OA_BOM = "oa_bom"
    OA_ECR = "oa_ecr"
    UNKNOWN = "unknown"


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class ChangeKind(str, Enum):
    UNCHANGED = "unchanged"
    METADATA_ONLY = "metadata_only"
    SUBSTITUTE_PRIORITY_ONLY = "substitute_priority_only"
    SUBSTITUTE_CONFIGURATION_CHANGED = "substitute_configuration_changed"
    MAIN_CHANGED_REFS_MIGRATED = "main_changed_refs_migrated"
    ALTERNATIVE_ADDED = "alternative_added"
    ALTERNATIVE_REMOVED = "alternative_removed"
    REPLACEMENT = "replacement"
    QUANTITY_CHANGED = "quantity_changed"
    REFERENCE_ADDED = "reference_added"
    REFERENCE_REMOVED = "reference_removed"
    REFERENCE_MIGRATED = "reference_migrated"
    REFERENCE_SET_CHANGED = "reference_set_changed"
    MATERIAL_ADDED = "material_added"
    MATERIAL_REMOVED = "material_removed"
    SUBSTITUTE_STRUCTURE_INVALID = "substitute_structure_invalid"
    PLACEMENT_BLOCKER = "placement_blocker"


class FunctionalImpact(str, Enum):
    NONE = "none"
    METADATA = "metadata"
    SUPPLY = "supply"
    PLACEMENT = "placement"
    BLOCKER = "blocker"


@dataclass(frozen=True)
class SourceCell:
    sheet_name: str
    coordinate: str
    row: int
    column: int
    raw_value: object = None
    display_value: str = ""
    data_type: str = ""
    number_format: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "sheet_name": self.sheet_name,
            "coordinate": self.coordinate,
            "row": self.row,
            "column": self.column,
            "raw_value": self.raw_value,
            "display_value": self.display_value,
            "data_type": self.data_type,
            "number_format": self.number_format,
        }


@dataclass(frozen=True)
class SourceSheet:
    name: str
    index: int
    state: str
    max_row: int
    max_column: int
    merged_ranges: tuple[str, ...] = ()
    freeze_panes: str = ""
    header_rows: tuple[int, ...] = ()
    data_start_row: int = 0
    data_end_row: int = 0
    field_columns: Mapping[str, int] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "index": self.index,
            "state": self.state,
            "max_row": self.max_row,
            "max_column": self.max_column,
            "merged_ranges": list(self.merged_ranges),
            "freeze_panes": self.freeze_panes,
            "header_rows": list(self.header_rows),
            "data_start_row": self.data_start_row,
            "data_end_row": self.data_end_row,
            "field_columns": dict(self.field_columns),
        }


@dataclass(frozen=True)
class WorkbookEnvelope:
    source_path: str
    source_fingerprint: str
    profile: WorkbookProfile
    sheets: tuple[SourceSheet, ...]
    data_sheet: str = ""
    mapping_candidates: Mapping[str, tuple[int, ...]] = field(default_factory=dict)
    preserved_metadata: Mapping[str, object] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "source_fingerprint": self.source_fingerprint,
            "profile": self.profile.value,
            "sheets": [sheet.payload() for sheet in self.sheets],
            "data_sheet": self.data_sheet,
            "mapping_candidates": {key: list(value) for key, value in self.mapping_candidates.items()},
            "preserved_metadata": dict(self.preserved_metadata),
        }


@dataclass(frozen=True)
class ValidationFinding:
    code: str
    severity: FindingSeverity
    message: str
    source_ids: tuple[str, ...] = ()
    parent_code: str = ""
    references: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "source_ids": list(self.source_ids),
            "parent_code": self.parent_code,
            "references": list(self.references),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class CanonicalRow:
    source_id: str
    sheet_name: str
    row_number: int
    item: str = ""
    parent_code: str = ""
    parent_description: str = ""
    hardware_version: str = ""
    material_code: str = ""
    name: str = ""
    value: str = ""
    model: str = ""
    description: str = ""
    unit: str = ""
    quantity: Decimal | None = None
    references: tuple[str, ...] = ()
    raw_reference: str = ""
    is_nc: bool = False
    remark: str = ""
    grade: str = ""
    grade_remark: str = ""
    substitute_group_code: str = ""
    substitute_strategy: str = ""
    substitute_mode: str = ""
    substitute_priority: int | None = None
    issue_method: str = ""
    mrp: str = ""
    jump_level: str = ""
    extra_fields: Mapping[str, str] = field(default_factory=dict)
    raw_fields: Mapping[str, object] = field(default_factory=dict)
    quality_flags: tuple[str, ...] = ()

    @property
    def is_substitute_member(self) -> bool:
        return bool(self.substitute_group_code)

    @property
    def is_substitute_main(self) -> bool:
        return self.is_substitute_member and self.substitute_priority == 0

    @property
    def is_substitute_alternative(self) -> bool:
        return self.is_substitute_member and self.substitute_priority is not None and self.substitute_priority > 0

    def payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "sheet_name": self.sheet_name,
            "row_number": self.row_number,
            "item": self.item,
            "parent_code": self.parent_code,
            "parent_description": self.parent_description,
            "hardware_version": self.hardware_version,
            "material_code": self.material_code,
            "name": self.name,
            "value": self.value,
            "model": self.model,
            "description": self.description,
            "unit": self.unit,
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "references": list(self.references),
            "raw_reference": self.raw_reference,
            "is_nc": self.is_nc,
            "remark": self.remark,
            "grade": self.grade,
            "grade_remark": self.grade_remark,
            "substitute_group_code": self.substitute_group_code,
            "substitute_strategy": self.substitute_strategy,
            "substitute_mode": self.substitute_mode,
            "substitute_priority": self.substitute_priority,
            "issue_method": self.issue_method,
            "mrp": self.mrp,
            "jump_level": self.jump_level,
            "extra_fields": dict(self.extra_fields),
            "quality_flags": list(self.quality_flags),
        }


@dataclass(frozen=True)
class MaterialVariant:
    material_code: str
    name: str = ""
    value: str = ""
    model: str = ""
    description: str = ""
    unit: str = ""
    grade: str = ""
    manufacturer: str = ""
    pcb_footprint: str = ""
    pcb_package: str = ""
    source_ids: tuple[str, ...] = ()

    @property
    def signature(self) -> tuple[str, ...]:
        return (
            self.name,
            self.value,
            self.model,
            self.description,
            self.unit,
            self.grade,
            self.manufacturer,
            self.pcb_footprint,
            self.pcb_package,
        )

    def payload(self) -> dict[str, object]:
        return {
            "material_code": self.material_code,
            "name": self.name,
            "value": self.value,
            "model": self.model,
            "description": self.description,
            "unit": self.unit,
            "grade": self.grade,
            "manufacturer": self.manufacturer,
            "pcb_footprint": self.pcb_footprint,
            "pcb_package": self.pcb_package,
            "source_ids": list(self.source_ids),
        }


@dataclass(frozen=True)
class MaterialItem:
    parent_code: str
    material_code: str
    quantity: Decimal | None
    references: tuple[str, ...]
    variants: tuple[MaterialVariant, ...]
    source_rows: tuple[CanonicalRow, ...]
    substitute_group_code: str = ""
    substitute_priority: int | None = None

    def payload(self) -> dict[str, object]:
        return {
            "parent_code": self.parent_code,
            "material_code": self.material_code,
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "references": list(self.references),
            "variants": [variant.payload() for variant in self.variants],
            "source_ids": [row.source_id for row in self.source_rows],
            "substitute_group_code": self.substitute_group_code,
            "substitute_priority": self.substitute_priority,
        }


@dataclass(frozen=True)
class PhysicalPlacement:
    parent_code: str
    reference: str
    material_code: str
    source_ids: tuple[str, ...]
    substitute_group_code: str = ""
    is_nc: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return self.parent_code, self.reference

    def payload(self) -> dict[str, object]:
        return {
            "parent_code": self.parent_code,
            "reference": self.reference,
            "material_code": self.material_code,
            "source_ids": list(self.source_ids),
            "substitute_group_code": self.substitute_group_code,
            "is_nc": self.is_nc,
        }


@dataclass(frozen=True)
class NonPlacementItem:
    parent_code: str
    material_code: str
    quantity: Decimal | None
    source_ids: tuple[str, ...]
    references: tuple[str, ...] = ()
    reason: str = "no_reference"

    def payload(self) -> dict[str, object]:
        return {
            "parent_code": self.parent_code,
            "material_code": self.material_code,
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "source_ids": list(self.source_ids),
            "references": list(self.references),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SubstituteGroup:
    parent_code: str
    group_code: str
    main_item: MaterialItem | None
    alternative_items: tuple[MaterialItem, ...]
    physical_references: tuple[str, ...]
    quantity: Decimal | None
    validation_findings: tuple[ValidationFinding, ...] = ()
    group_fingerprint: str = ""

    @property
    def members(self) -> tuple[MaterialItem, ...]:
        if self.main_item is None:
            return self.alternative_items
        return (self.main_item, *self.alternative_items)

    def payload(self) -> dict[str, object]:
        return {
            "parent_code": self.parent_code,
            "group_code": self.group_code,
            "main_item": self.main_item.payload() if self.main_item else None,
            "alternative_items": [item.payload() for item in self.alternative_items],
            "physical_references": list(self.physical_references),
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "validation_findings": [finding.payload() for finding in self.validation_findings],
            "group_fingerprint": self.group_fingerprint,
        }


@dataclass(frozen=True)
class BoardBOM:
    parent_code: str
    parent_description: str
    hardware_version: str
    rows: tuple[CanonicalRow, ...]
    items: tuple[MaterialItem, ...]
    substitute_groups: tuple[SubstituteGroup, ...]
    placements: tuple[PhysicalPlacement, ...]
    non_placement_items: tuple[NonPlacementItem, ...]
    findings: tuple[ValidationFinding, ...]
    source_fingerprint: str

    def payload(self) -> dict[str, object]:
        return {
            "parent_code": self.parent_code,
            "parent_description": self.parent_description,
            "hardware_version": self.hardware_version,
            "rows": [row.payload() for row in self.rows],
            "items": [item.payload() for item in self.items],
            "substitute_groups": [group.payload() for group in self.substitute_groups],
            "placements": [placement.payload() for placement in self.placements],
            "non_placement_items": [item.payload() for item in self.non_placement_items],
            "findings": [finding.payload() for finding in self.findings],
            "source_fingerprint": self.source_fingerprint,
        }


@dataclass(frozen=True)
class BomChangeEvent:
    event_id: str
    kind: ChangeKind
    parent_code: str
    title: str
    impact: FunctionalImpact
    old_snapshot: Mapping[str, object] = field(default_factory=dict)
    new_snapshot: Mapping[str, object] = field(default_factory=dict)
    references: tuple[str, ...] = ()
    group_codes: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    oa_change_type: str = ""
    source_ids: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "kind": self.kind.value,
            "parent_code": self.parent_code,
            "title": self.title,
            "impact": self.impact.value,
            "old_snapshot": dict(self.old_snapshot),
            "new_snapshot": dict(self.new_snapshot),
            "references": list(self.references),
            "group_codes": list(self.group_codes),
            "blocker_reasons": list(self.blocker_reasons),
            "oa_change_type": self.oa_change_type,
            "source_ids": list(self.source_ids),
        }


def flatten_findings(boards: Sequence[BoardBOM]) -> tuple[ValidationFinding, ...]:
    return tuple(finding for board in boards for finding in board.findings)
