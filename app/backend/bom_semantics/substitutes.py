from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from typing import Iterable

from app.backend.bom_semantics.models import (
    BoardBOM,
    CanonicalRow,
    FindingSeverity,
    MaterialItem,
    MaterialVariant,
    NonPlacementItem,
    PhysicalPlacement,
    SubstituteGroup,
    ValidationFinding,
)
from app.backend.bom_semantics.normalization import NormalizedSource
from app.backend.bom_semantics.references import natural_reference_key
from app.backend.bom_semantics.validation import (
    build_group_fingerprint,
    stable_semantic_fingerprint,
    validate_material_membership,
    validate_substitute_members,
    validate_unique_placements,
)


def _variant(row: CanonicalRow) -> MaterialVariant:
    return MaterialVariant(
        material_code=row.material_code,
        name=row.name,
        value=row.value,
        model=row.model,
        description=row.description,
        unit=row.unit,
        grade=row.grade,
        manufacturer=row.extra_fields.get("manufacturer", ""),
        pcb_footprint=row.extra_fields.get("pcb_footprint", ""),
        pcb_package=row.extra_fields.get("pcb_package", ""),
        source_ids=(row.source_id,),
    )


def _casefold_signature(variant: MaterialVariant) -> tuple[str, ...]:
    return tuple(" ".join(value.split()).casefold() for value in variant.signature)


def _merge_variants(rows: Iterable[CanonicalRow]) -> tuple[MaterialVariant, ...]:
    by_signature: dict[tuple[str, ...], list[MaterialVariant]] = defaultdict(list)
    for row in rows:
        variant = _variant(row)
        by_signature[_casefold_signature(variant)].append(variant)
    merged: list[MaterialVariant] = []
    for variants in by_signature.values():
        first = variants[0]
        merged.append(
            replace(
                first,
                source_ids=tuple(
                    source_id
                    for variant in variants
                    for source_id in variant.source_ids
                ),
            )
        )
    return tuple(merged)


def _merge_quantity(rows: list[CanonicalRow]) -> Decimal | None:
    values = [row.quantity for row in rows if row.quantity is not None]
    if not values:
        return None
    if len(rows) > 1 and any(row.references for row in rows):
        return sum(values, Decimal("0"))
    return values[0] if len(set(values)) == 1 else sum(values, Decimal("0"))


def _build_items(rows: Iterable[CanonicalRow]) -> tuple[MaterialItem, ...]:
    grouped: dict[tuple[str, str, str, int | None, str], list[CanonicalRow]] = defaultdict(list)
    for row in rows:
        identity_key = row.material_code or f"source:{row.source_id}"
        grouped[
            (
                row.parent_code,
                row.material_code,
                row.substitute_group_code,
                row.substitute_priority,
                identity_key,
            )
        ].append(row)
    items: list[MaterialItem] = []
    for (parent_code, material_code, group_code, priority, _), source_rows in grouped.items():
        references = sorted(
            {reference for row in source_rows for reference in row.references},
            key=natural_reference_key,
        )
        items.append(
            MaterialItem(
                parent_code=parent_code,
                material_code=material_code,
                quantity=_merge_quantity(source_rows),
                references=tuple(references),
                variants=_merge_variants(source_rows),
                source_rows=tuple(source_rows),
                substitute_group_code=group_code,
                substitute_priority=priority,
            )
        )
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.parent_code,
                item.substitute_group_code,
                item.substitute_priority if item.substitute_priority is not None else -1,
                item.material_code,
                tuple(row.source_id for row in item.source_rows),
            ),
        )
    )


def _build_groups(items: Iterable[MaterialItem]) -> tuple[SubstituteGroup, ...]:
    grouped: dict[tuple[str, str], list[MaterialItem]] = defaultdict(list)
    for item in items:
        if item.substitute_group_code:
            grouped[(item.parent_code, item.substitute_group_code)].append(item)
    groups: list[SubstituteGroup] = []
    for (parent_code, group_code), members in grouped.items():
        findings = validate_substitute_members(parent_code, group_code, members)
        main = next((item for item in members if item.substitute_priority == 0), None)
        alternatives = tuple(
            sorted(
                (item for item in members if item is not main),
                key=lambda item: (
                    item.substitute_priority if item.substitute_priority is not None else 10**9,
                    item.material_code,
                ),
            )
        )
        groups.append(
            SubstituteGroup(
                parent_code=parent_code,
                group_code=group_code,
                main_item=main,
                alternative_items=alternatives,
                physical_references=(
                    tuple(
                        sorted(
                            {
                                reference
                                for row in main.source_rows
                                if not row.is_nc
                                for reference in row.references
                            },
                            key=natural_reference_key,
                        )
                    )
                    if main
                    else ()
                ),
                quantity=main.quantity if main else None,
                validation_findings=findings,
                group_fingerprint=build_group_fingerprint(parent_code, group_code, members),
            )
        )
    return tuple(sorted(groups, key=lambda group: (group.parent_code, group.group_code)))


def build_board_boms(source: NormalizedSource) -> tuple[BoardBOM, ...]:
    by_parent: dict[str, list[CanonicalRow]] = defaultdict(list)
    for row in source.rows:
        by_parent[row.parent_code].append(row)
    boards: list[BoardBOM] = []
    for parent_code, rows in by_parent.items():
        items = _build_items(rows)
        groups = _build_groups(items)
        group_findings = [
            finding
            for group in groups
            for finding in group.validation_findings
        ]
        group_findings.extend(validate_material_membership(groups))

        placement_candidates: list[tuple[str, str, str, tuple[str, ...], str, bool]] = []
        non_placement: list[NonPlacementItem] = []
        group_item_keys = {
            (item.material_code, item.substitute_group_code, item.substitute_priority)
            for group in groups
            for item in group.members
        }
        valid_group_keys = {
            (group.parent_code, group.group_code)
            for group in groups
            if not group.validation_findings
        }
        for item in items:
            is_group_member = (
                item.material_code,
                item.substitute_group_code,
                item.substitute_priority,
            ) in group_item_keys
            is_valid_alternative = (
                is_group_member
                and (item.parent_code, item.substitute_group_code) in valid_group_keys
                and item.substitute_priority != 0
            )
            if is_valid_alternative:
                continue
            installed_rows = [row for row in item.source_rows if row.references and not row.is_nc]
            for row in installed_rows:
                for reference in row.references:
                    placement_candidates.append(
                        (
                            parent_code,
                            reference,
                            item.material_code,
                            (row.source_id,),
                            item.substitute_group_code,
                            False,
                        )
                    )
            excluded_rows = [row for row in item.source_rows if row.references and row.is_nc]
            for row in excluded_rows:
                non_placement.append(
                    NonPlacementItem(
                        parent_code=parent_code,
                        material_code=item.material_code,
                        quantity=row.quantity,
                        source_ids=(row.source_id,),
                        references=row.references,
                        reason="nc",
                    )
                )
            if not item.references:
                non_placement.append(
                    NonPlacementItem(
                        parent_code=parent_code,
                        material_code=item.material_code,
                        quantity=item.quantity,
                        source_ids=tuple(row.source_id for row in item.source_rows),
                        references=(),
                        reason="no_reference",
                    )
                )

        merged_candidates: dict[
            tuple[str, str, str, str, bool],
            set[str],
        ] = defaultdict(set)
        for parent, reference, code, source_ids, group_code, is_nc in placement_candidates:
            merged_candidates[(parent, reference, code, group_code, is_nc)].update(source_ids)
        placement_candidates = [
            (parent, reference, code, tuple(sorted(source_ids)), group_code, is_nc)
            for (parent, reference, code, group_code, is_nc), source_ids in merged_candidates.items()
        ]

        placement_findings = validate_unique_placements(
            (parent, reference, code, source_ids)
            for parent, reference, code, source_ids, _, _ in placement_candidates
        )
        material_findings: list[ValidationFinding] = []
        for item in items:
            if len(item.variants) > 1:
                material_findings.append(
                    ValidationFinding(
                        code="material_variant_conflict",
                        severity=FindingSeverity.BLOCKER,
                        message="同一父项下的同一物料编码存在不同型号、描述、封装或等级。",
                        source_ids=tuple(row.source_id for row in item.source_rows),
                        parent_code=parent_code,
                        details={
                            "material_code": item.material_code,
                            "variant_count": len(item.variants),
                        },
                    )
                )

        all_findings = tuple(
            group_findings
            + list(placement_findings)
            + material_findings
        )
        placements = tuple(
            PhysicalPlacement(
                parent_code=parent,
                reference=reference,
                material_code=code,
                source_ids=source_ids,
                substitute_group_code=group_code,
                is_nc=is_nc,
            )
            for parent, reference, code, source_ids, group_code, is_nc in sorted(
                placement_candidates,
                key=lambda item: natural_reference_key(item[1]),
            )
        )
        parent_description = next((row.parent_description for row in rows if row.parent_description), "")
        hardware_version = next((row.hardware_version for row in rows if row.hardware_version), "")
        board_fingerprint = stable_semantic_fingerprint(
            "board-bom",
            {
                "source": source.envelope.source_fingerprint,
                "parent": parent_code,
                "rows": [row.source_id for row in rows],
            },
        )
        boards.append(
            BoardBOM(
                parent_code=parent_code,
                parent_description=parent_description,
                hardware_version=hardware_version,
                rows=tuple(rows),
                items=items,
                substitute_groups=groups,
                placements=placements,
                non_placement_items=tuple(non_placement),
                findings=all_findings,
                source_fingerprint=board_fingerprint,
            )
        )
    return tuple(sorted(boards, key=lambda board: board.parent_code))
