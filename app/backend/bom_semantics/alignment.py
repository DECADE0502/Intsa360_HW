from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from app.backend.bom_semantics.models import (
    BoardBOM,
    CanonicalRow,
    MaterialItem,
    ValidationFinding,
)


@dataclass(frozen=True)
class ScopeEvidence:
    old_reference_count: int
    new_reference_count: int
    shared_reference_count: int
    reference_overlap: float
    old_material_count: int
    new_material_count: int
    shared_material_count: int
    material_overlap: float

    def payload(self) -> dict[str, object]:
        return {
            "old_reference_count": self.old_reference_count,
            "new_reference_count": self.new_reference_count,
            "shared_reference_count": self.shared_reference_count,
            "reference_overlap": self.reference_overlap,
            "old_material_count": self.old_material_count,
            "new_material_count": self.new_material_count,
            "shared_material_count": self.shared_material_count,
            "material_overlap": self.material_overlap,
        }


@dataclass(frozen=True)
class ScopePair:
    old_parent_code: str
    new_parent_code: str
    old_parent_description: str
    new_parent_description: str
    status: str
    evidence: ScopeEvidence

    def payload(self) -> dict[str, object]:
        return {
            "old_parent_code": self.old_parent_code,
            "new_parent_code": self.new_parent_code,
            "old_parent_description": self.old_parent_description,
            "new_parent_description": self.new_parent_description,
            "status": self.status,
            "evidence": self.evidence.payload(),
        }


@dataclass(frozen=True)
class ComparisonScope:
    status: str
    pairs: tuple[ScopePair, ...]
    unresolved_old_parent_codes: tuple[str, ...] = ()
    unresolved_new_parent_codes: tuple[str, ...] = ()

    @property
    def needs_confirmation(self) -> bool:
        return bool(
            self.unresolved_old_parent_codes
            or self.unresolved_new_parent_codes
            or any(pair.status == "suggested" for pair in self.pairs)
        )

    @property
    def old_to_new(self) -> dict[str, str]:
        return {
            pair.old_parent_code: pair.new_parent_code
            for pair in self.pairs
            if pair.status in {"exact", "confirmed"}
        }

    def payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "needs_confirmation": self.needs_confirmation,
            "pairs": [pair.payload() for pair in self.pairs],
            "unresolved_old_parent_codes": list(self.unresolved_old_parent_codes),
            "unresolved_new_parent_codes": list(self.unresolved_new_parent_codes),
        }


def _overlap(left: set[str], right: set[str]) -> float:
    union = left | right
    return round(len(left & right) / len(union), 4) if union else 1.0


def _scope_evidence(old: BoardBOM, new: BoardBOM) -> ScopeEvidence:
    old_references = {placement.reference for placement in old.placements}
    new_references = {placement.reference for placement in new.placements}
    old_materials = {item.material_code for item in old.items if item.material_code}
    new_materials = {item.material_code for item in new.items if item.material_code}
    return ScopeEvidence(
        old_reference_count=len(old_references),
        new_reference_count=len(new_references),
        shared_reference_count=len(old_references & new_references),
        reference_overlap=_overlap(old_references, new_references),
        old_material_count=len(old_materials),
        new_material_count=len(new_materials),
        shared_material_count=len(old_materials & new_materials),
        material_overlap=_overlap(old_materials, new_materials),
    )


def resolve_comparison_scope(
    old_boards: Sequence[BoardBOM],
    new_boards: Sequence[BoardBOM],
    *,
    confirmed: bool = False,
    parent_mappings: Mapping[str, str] | None = None,
) -> ComparisonScope:
    old_by_parent = {board.parent_code: board for board in old_boards}
    new_by_parent = {board.parent_code: board for board in new_boards}
    pairs: list[ScopePair] = []
    used_old: set[str] = set()
    used_new: set[str] = set()

    for parent_code in sorted(set(old_by_parent) & set(new_by_parent)):
        old = old_by_parent[parent_code]
        new = new_by_parent[parent_code]
        pairs.append(
            ScopePair(
                old_parent_code=parent_code,
                new_parent_code=parent_code,
                old_parent_description=old.parent_description,
                new_parent_description=new.parent_description,
                status="exact",
                evidence=_scope_evidence(old, new),
            )
        )
        used_old.add(parent_code)
        used_new.add(parent_code)

    for old_parent, new_parent in dict(parent_mappings or {}).items():
        if (
            old_parent in used_old
            or new_parent in used_new
            or old_parent not in old_by_parent
            or new_parent not in new_by_parent
        ):
            continue
        old = old_by_parent[old_parent]
        new = new_by_parent[new_parent]
        pairs.append(
            ScopePair(
                old_parent_code=old_parent,
                new_parent_code=new_parent,
                old_parent_description=old.parent_description,
                new_parent_description=new.parent_description,
                status="confirmed",
                evidence=_scope_evidence(old, new),
            )
        )
        used_old.add(old_parent)
        used_new.add(new_parent)

    unmatched_old = [code for code in old_by_parent if code not in used_old]
    unmatched_new = [code for code in new_by_parent if code not in used_new]
    if len(unmatched_old) == 1 and len(unmatched_new) == 1:
        old_parent = unmatched_old[0]
        new_parent = unmatched_new[0]
        old = old_by_parent[old_parent]
        new = new_by_parent[new_parent]
        pair_status = "confirmed" if confirmed else "suggested"
        pairs.append(
            ScopePair(
                old_parent_code=old_parent,
                new_parent_code=new_parent,
                old_parent_description=old.parent_description,
                new_parent_description=new.parent_description,
                status=pair_status,
                evidence=_scope_evidence(old, new),
            )
        )
        if confirmed:
            used_old.add(old_parent)
            used_new.add(new_parent)

    unresolved_old = tuple(code for code in old_by_parent if code not in used_old)
    unresolved_new = tuple(code for code in new_by_parent if code not in used_new)
    suggested = any(pair.status == "suggested" for pair in pairs)
    if suggested:
        status = "suggested"
    elif unresolved_old or unresolved_new:
        status = "unresolved"
    elif any(pair.status == "confirmed" for pair in pairs):
        status = "confirmed"
    else:
        status = "exact"
    return ComparisonScope(
        status=status,
        pairs=tuple(pairs),
        unresolved_old_parent_codes=unresolved_old,
        unresolved_new_parent_codes=unresolved_new,
    )


def _item_key(item: MaterialItem) -> tuple[object, ...]:
    return (
        item.material_code,
        item.substitute_group_code,
        item.substitute_priority,
        tuple(row.source_id for row in item.source_rows),
    )


def _align_row(row: CanonicalRow, target_parent: str) -> CanonicalRow:
    if row.parent_code == target_parent:
        return row
    return replace(
        row,
        parent_code=target_parent,
        extra_fields={
            **row.extra_fields,
            "source_parent_code": row.parent_code,
        },
    )


def _align_board(board: BoardBOM, target_parent: str) -> BoardBOM:
    if board.parent_code == target_parent:
        return board
    aligned_rows = tuple(_align_row(row, target_parent) for row in board.rows)
    rows_by_id = {row.source_id: row for row in aligned_rows}
    aligned_items = tuple(
        replace(
            item,
            parent_code=target_parent,
            source_rows=tuple(rows_by_id[row.source_id] for row in item.source_rows),
        )
        for item in board.items
    )
    items_by_key = {_item_key(item): item for item in aligned_items}

    def aligned_item(item: MaterialItem) -> MaterialItem:
        return items_by_key[_item_key(item)]

    aligned_groups = tuple(
        replace(
            group,
            parent_code=target_parent,
            main_item=(
                aligned_item(group.main_item)
                if group.main_item is not None
                else None
            ),
            alternative_items=tuple(
                aligned_item(item) for item in group.alternative_items
            ),
            validation_findings=tuple(
                _align_finding(finding, target_parent, board.parent_code)
                for finding in group.validation_findings
            ),
        )
        for group in board.substitute_groups
    )
    return replace(
        board,
        parent_code=target_parent,
        rows=aligned_rows,
        items=aligned_items,
        substitute_groups=aligned_groups,
        placements=tuple(
            replace(placement, parent_code=target_parent)
            for placement in board.placements
        ),
        non_placement_items=tuple(
            replace(item, parent_code=target_parent)
            for item in board.non_placement_items
        ),
        findings=tuple(
            _align_finding(finding, target_parent, board.parent_code)
            for finding in board.findings
        ),
    )


def _align_finding(
    finding: ValidationFinding,
    target_parent: str,
    source_parent: str,
) -> ValidationFinding:
    if not finding.parent_code or finding.parent_code == target_parent:
        return finding
    return replace(
        finding,
        parent_code=target_parent,
        details={
            **finding.details,
            "source_parent_code": source_parent,
        },
    )


def align_old_boards(
    old_boards: Sequence[BoardBOM],
    old_to_new: Mapping[str, str],
) -> tuple[BoardBOM, ...]:
    return tuple(
        _align_board(board, old_to_new.get(board.parent_code, board.parent_code))
        for board in old_boards
    )
