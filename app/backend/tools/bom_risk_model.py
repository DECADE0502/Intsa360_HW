from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping
import re

from app.backend.bom_semantics.models import (
    CanonicalRow,
    SubstituteGroup,
    ValidationFinding,
    WorkbookProfile,
)
from app.backend.bom_semantics.normalization import normalize_workbook
from app.backend.bom_semantics.substitutes import build_board_boms


_PCB_RE = re.compile(r"PCB|PCBA|HDI|印制板|覆铜板|\d+\s*层", re.IGNORECASE)


@dataclass(frozen=True)
class RiskRow:
    source_id: str
    source_row: int
    parent_code: str
    hardware_version: str
    part_number: str
    name: str
    value: str
    model: str
    description: str
    unit: str
    quantity: Decimal | None
    refs: tuple[str, ...]
    grade: str
    remark: str
    issue_method: str
    mrp: str
    jump_level: str
    substitute_group_code: str
    substitute_strategy: str
    substitute_mode: str
    substitute_priority: int | None
    is_nc: bool
    is_parent: bool
    is_substitute_main: bool
    is_substitute_alternative: bool
    quality_flags: tuple[str, ...]
    extra_fields: Mapping[str, str]

    @property
    def is_placement(self) -> bool:
        return bool(
            self.refs
            and not self.is_parent
            and not self.is_substitute_alternative
        )

    @property
    def searchable_text(self) -> str:
        return " ".join(
            (
                self.part_number,
                self.name,
                self.value,
                self.model,
                self.description,
                self.remark,
            )
        )

    def payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_row": self.source_row,
            "parent_code": self.parent_code,
            "hardware_version": self.hardware_version,
            "part_number": self.part_number,
            "name": self.name,
            "value": self.value,
            "model": self.model,
            "description": self.description,
            "unit": self.unit,
            "quantity": str(self.quantity) if self.quantity is not None else "",
            "refs": list(self.refs),
            "reference": ",".join(self.refs),
            "grade": self.grade,
            "remark": self.remark,
            "issue_method": self.issue_method,
            "mrp": self.mrp,
            "jump_level": self.jump_level,
            "substitute_group_code": self.substitute_group_code,
            "substitute_strategy": self.substitute_strategy,
            "substitute_mode": self.substitute_mode,
            "substitute_priority": self.substitute_priority,
            "is_nc": self.is_nc,
            "is_parent": self.is_parent,
            "is_substitute_main": self.is_substitute_main,
            "is_substitute_alternative": self.is_substitute_alternative,
            "is_placement": self.is_placement,
            "quality_flags": list(self.quality_flags),
            "extra_fields": dict(self.extra_fields),
        }


@dataclass(frozen=True)
class RiskModel:
    source_path: Path
    source_fingerprint: str
    profile: WorkbookProfile
    rows: tuple[RiskRow, ...]
    substitute_groups: tuple[SubstituteGroup, ...]
    normalization_findings: tuple[ValidationFinding, ...]
    parent_codes: tuple[str, ...]

    @property
    def placement_rows(self) -> tuple[RiskRow, ...]:
        return tuple(row for row in self.rows if row.is_placement)

    @property
    def actual_references(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    ref
                    for row in self.placement_rows
                    if not row.is_nc
                    for ref in row.refs
                }
            )
        )

    def payload(self) -> dict[str, object]:
        return {
            "source_file": str(self.source_path),
            "source_fingerprint": self.source_fingerprint,
            "profile": self.profile.value,
            "rows": [row.payload() for row in self.rows],
            "substitute_groups": [
                group.payload() for group in self.substitute_groups
            ],
            "normalization_findings": [
                finding.payload() for finding in self.normalization_findings
            ],
            "parent_codes": list(self.parent_codes),
        }


def _is_parent_row(row: CanonicalRow) -> bool:
    if row.parent_code and row.material_code == row.parent_code:
        return True
    if row.references or row.is_substitute_alternative:
        return False
    return bool(
        row.material_code
        and _PCB_RE.search(
            " ".join(
                (
                    row.name,
                    row.value,
                    row.model,
                    row.description,
                    row.parent_description,
                )
            )
        )
    )


def _risk_row(row: CanonicalRow) -> RiskRow:
    return RiskRow(
        source_id=row.source_id,
        source_row=row.row_number,
        parent_code=row.parent_code,
        hardware_version=row.hardware_version,
        part_number=row.material_code,
        name=row.name,
        value=row.value,
        model=row.model,
        description=row.description,
        unit=row.unit,
        quantity=row.quantity,
        refs=row.references,
        grade=row.grade,
        remark=row.remark,
        issue_method=row.issue_method,
        mrp=row.mrp,
        jump_level=row.jump_level,
        substitute_group_code=row.substitute_group_code,
        substitute_strategy=row.substitute_strategy,
        substitute_mode=row.substitute_mode,
        substitute_priority=row.substitute_priority,
        is_nc=row.is_nc,
        is_parent=_is_parent_row(row),
        is_substitute_main=row.is_substitute_main,
        is_substitute_alternative=row.is_substitute_alternative,
        quality_flags=row.quality_flags,
        extra_fields=row.extra_fields,
    )


def build_risk_model(path: Path) -> RiskModel:
    source = normalize_workbook(path)
    boards = build_board_boms(source)
    return RiskModel(
        source_path=Path(source.envelope.source_path),
        source_fingerprint=source.envelope.source_fingerprint,
        profile=source.envelope.profile,
        rows=tuple(_risk_row(row) for row in source.rows),
        substitute_groups=tuple(
            group for board in boards for group in board.substitute_groups
        ),
        normalization_findings=source.findings,
        parent_codes=tuple(
            sorted({row.parent_code for row in source.rows if row.parent_code})
        ),
    )


build_risk_rows = build_risk_model
