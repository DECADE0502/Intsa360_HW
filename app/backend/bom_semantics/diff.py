from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Sequence

from app.backend.bom_semantics.change_events import make_change_event
from app.backend.bom_semantics.contracts import CompareResult, CompareSummary
from app.backend.bom_semantics.models import (
    BoardBOM,
    BomChangeEvent,
    CanonicalRow,
    ChangeKind,
    FindingSeverity,
    FunctionalImpact,
    MaterialItem,
    SubstituteGroup,
    ValidationFinding,
)
from app.backend.bom_semantics.references import natural_reference_key
from app.backend.bom_semantics.substitute_equivalence import (
    SUBSTITUTE_CONFIGURATION_FINDING_CODES,
    compare_substitute_groups,
    structurally_changed_group_keys,
)
from app.backend.bom_semantics.validation import stable_semantic_fingerprint


@dataclass(frozen=True)
class GroupMatch:
    old: SubstituteGroup
    new: SubstituteGroup


def _row_snapshot(row: CanonicalRow) -> dict[str, object]:
    return {
        "item": row.item,
        "parent_code": row.parent_code,
        "source_parent_code": row.extra_fields.get(
            "source_parent_code",
            row.parent_code,
        ),
        "parent_description": row.parent_description,
        "hardware_version": row.hardware_version,
        "material_code": row.material_code,
        "name": row.name,
        "value": row.value,
        "model": row.model,
        "description": row.description,
        "unit": row.unit,
        "quantity": str(row.quantity) if row.quantity is not None else None,
        "references": list(row.references),
        "raw_reference": row.raw_reference,
        "is_nc": row.is_nc,
        "remark": row.remark,
        "grade": row.grade,
        "grade_remark": row.grade_remark,
        "substitute_group_code": row.substitute_group_code,
        "substitute_strategy": row.substitute_strategy,
        "substitute_priority": row.substitute_priority,
        "substitute_mode": row.substitute_mode,
        "issue_method": row.issue_method,
        "mrp": row.mrp,
        "jump_level": row.jump_level,
        "extra_fields": {
            key: value
            for key, value in row.extra_fields.items()
            if key != "source_parent_code"
        },
        "quality_flags": list(row.quality_flags),
    }


def _item_snapshot(item: MaterialItem | None) -> dict[str, object]:
    if item is None:
        return {}
    return {
        "parent_code": item.parent_code,
        "material_code": item.material_code,
        "quantity": str(item.quantity) if item.quantity is not None else None,
        "references": list(item.references),
        "substitute_group_code": item.substitute_group_code,
        "substitute_priority": item.substitute_priority,
        "variants": [variant.payload() for variant in item.variants],
    }


def _group_snapshot(group: SubstituteGroup) -> dict[str, object]:
    strategies = {
        item.material_code: sorted(
            {row.substitute_strategy for row in item.source_rows}
        )
        for item in group.members
    }
    modes = {
        item.material_code: sorted(
            {row.substitute_mode for row in item.source_rows}
        )
        for item in group.members
    }
    return {
        "parent_code": group.parent_code,
        "group_code": group.group_code,
        "main_material_code": group.main_item.material_code if group.main_item else "",
        "alternative_material_codes": [item.material_code for item in group.alternative_items],
        "members": [item.material_code for item in group.members],
        "priorities": {
            item.material_code: item.substitute_priority
            for item in group.members
        },
        "strategies": strategies,
        "modes": modes,
        "quantity": str(group.quantity) if group.quantity is not None else None,
        "references": list(group.physical_references),
        "valid": not any(
            finding.severity == FindingSeverity.BLOCKER
            for finding in group.validation_findings
            if finding.code not in SUBSTITUTE_CONFIGURATION_FINDING_CODES
        ),
        "configuration_complete": not any(
            finding.code in SUBSTITUTE_CONFIGURATION_FINDING_CODES
            for finding in group.validation_findings
        ),
    }


def _variant_signature(item: MaterialItem) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(variant.signature for variant in item.variants))


_ITEM_METADATA_FIELDS = (
    "name",
    "value",
    "model",
    "description",
    "unit",
    "remark",
    "grade",
    "grade_remark",
    "issue_method",
    "mrp",
    "jump_level",
)


def _metadata_snapshot(item: MaterialItem) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for row in item.source_rows:
        snapshot = {
            field: getattr(row, field)
            for field in _ITEM_METADATA_FIELDS
        }
        snapshot["extra_fields"] = {
            key: value
            for key, value in row.extra_fields.items()
            if key != "source_parent_code"
        }
        rows.append(snapshot)
    rows.sort(
        key=lambda value: json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    )
    return {"rows": rows}


def _changed_metadata_fields(
    old_snapshot: Mapping[str, object],
    new_snapshot: Mapping[str, object],
) -> tuple[str, ...]:
    old_rows = old_snapshot.get("rows", [])
    new_rows = new_snapshot.get("rows", [])
    changed: list[str] = []
    for field in (*_ITEM_METADATA_FIELDS, "extra_fields"):
        old_values = sorted(
            {
                json.dumps(row.get(field), ensure_ascii=False, sort_keys=True)
                for row in old_rows
                if isinstance(row, dict)
            }
        )
        new_values = sorted(
            {
                json.dumps(row.get(field), ensure_ascii=False, sort_keys=True)
                for row in new_rows
                if isinstance(row, dict)
            }
        )
        if old_values != new_values:
            changed.append(field)
    return tuple(changed)


def _board_metadata_diff(
    old_boards: Sequence[BoardBOM],
    new_boards: Sequence[BoardBOM],
) -> tuple[Mapping[str, object], ...]:
    old_by_parent = {board.parent_code: board for board in old_boards}
    new_by_parent = {board.parent_code: board for board in new_boards}
    differences: list[Mapping[str, object]] = []
    for parent_code in sorted(set(old_by_parent) | set(new_by_parent)):
        old = old_by_parent.get(parent_code)
        new = new_by_parent.get(parent_code)
        old_snapshot = {
            "parent_code": (
                old.rows[0].extra_fields.get("source_parent_code", old.parent_code)
                if old and old.rows
                else old.parent_code if old else ""
            ),
            "parent_description": old.parent_description if old else "",
            "hardware_version": old.hardware_version if old else "",
        }
        new_snapshot = {
            "parent_code": (
                new.rows[0].extra_fields.get("source_parent_code", new.parent_code)
                if new and new.rows
                else new.parent_code if new else ""
            ),
            "parent_description": new.parent_description if new else "",
            "hardware_version": new.hardware_version if new else "",
        }
        changed_fields = [
            field
            for field in old_snapshot
            if old_snapshot[field] != new_snapshot[field]
        ]
        if changed_fields:
            differences.append(
                {
                    "comparison_parent_code": parent_code,
                    "old": old_snapshot,
                    "new": new_snapshot,
                    "changed_fields": changed_fields,
                }
            )
    return tuple(differences)


def _all_items(boards: Sequence[BoardBOM]) -> dict[tuple[str, str], MaterialItem]:
    items: dict[tuple[str, str], MaterialItem] = {}
    for board in boards:
        for item in board.items:
            key = board.parent_code, item.material_code
            if key not in items:
                items[key] = item
    return items


def _placements(boards: Sequence[BoardBOM]) -> dict[tuple[str, str], str]:
    return {
        placement.key: placement.material_code
        for board in boards
        for placement in board.placements
    }


def _groups(boards: Sequence[BoardBOM]) -> list[SubstituteGroup]:
    return [group for board in boards for group in board.substitute_groups]


def _group_score(old: SubstituteGroup, new: SubstituteGroup) -> int:
    if old.parent_code != new.parent_code:
        return -1
    old_members = {item.material_code for item in old.members}
    new_members = {item.material_code for item in new.members}
    old_refs = set(old.physical_references)
    new_refs = set(new.physical_references)
    score = 0
    if old_members == new_members:
        score += 100
    else:
        score += 10 * len(old_members & new_members)
    if old_refs == new_refs:
        score += 80
    else:
        score += len(old_refs & new_refs)
    if old.group_code == new.group_code:
        score += 20
    if old.main_item and new.main_item and old.main_item.material_code == new.main_item.material_code:
        score += 10
    return score


def match_substitute_groups(
    old_groups: Sequence[SubstituteGroup],
    new_groups: Sequence[SubstituteGroup],
) -> tuple[tuple[GroupMatch, ...], tuple[SubstituteGroup, ...], tuple[SubstituteGroup, ...]]:
    candidates: list[tuple[int, int, int]] = []
    for old_index, old in enumerate(old_groups):
        for new_index, new in enumerate(new_groups):
            score = _group_score(old, new)
            if score >= 20:
                candidates.append((score, old_index, new_index))
    used_old: set[int] = set()
    used_new: set[int] = set()
    matches: list[GroupMatch] = []
    for _, old_index, new_index in sorted(candidates, reverse=True):
        if old_index in used_old or new_index in used_new:
            continue
        used_old.add(old_index)
        used_new.add(new_index)
        matches.append(GroupMatch(old_groups[old_index], new_groups[new_index]))
    unmatched_old = tuple(group for index, group in enumerate(old_groups) if index not in used_old)
    unmatched_new = tuple(group for index, group in enumerate(new_groups) if index not in used_new)
    return tuple(matches), unmatched_old, unmatched_new


def _raw_row_diff(
    old_boards: Sequence[BoardBOM],
    new_boards: Sequence[BoardBOM],
) -> tuple[Mapping[str, object], ...]:
    def indexed(boards: Sequence[BoardBOM]) -> dict[tuple[str, str], list[CanonicalRow]]:
        result: dict[tuple[str, str], list[CanonicalRow]] = defaultdict(list)
        for board in boards:
            for row in board.rows:
                result[(row.parent_code, row.material_code)].append(row)
        return result

    old_rows = indexed(old_boards)
    new_rows = indexed(new_boards)
    differences: list[Mapping[str, object]] = []
    for key in sorted(set(old_rows) | set(new_rows)):
        old_values = [_row_snapshot(row) for row in old_rows.get(key, ())]
        new_values = [_row_snapshot(row) for row in new_rows.get(key, ())]
        if old_values == new_values:
            continue
        status = "changed"
        if not old_values:
            status = "added"
        elif not new_values:
            status = "removed"
        differences.append(
            {
                "parent_code": key[0],
                "material_code": key[1],
                "status": status,
                "old_rows": old_values,
                "new_rows": new_values,
                "old_source_ids": [row.source_id for row in old_rows.get(key, ())],
                "new_source_ids": [row.source_id for row in new_rows.get(key, ())],
            }
        )
    return tuple(differences)


def _placement_diff(
    old_map: Mapping[tuple[str, str], str],
    new_map: Mapping[tuple[str, str], str],
) -> tuple[Mapping[str, object], ...]:
    differences: list[Mapping[str, object]] = []
    for parent_code, reference in sorted(
        set(old_map) | set(new_map),
        key=lambda item: (item[0], natural_reference_key(item[1])),
    ):
        key = parent_code, reference
        old_code = old_map.get(key, "")
        new_code = new_map.get(key, "")
        if old_code == new_code:
            continue
        if old_code and new_code:
            status = "migrated"
        elif new_code:
            status = "added"
        else:
            status = "removed"
        differences.append(
            {
                "parent_code": parent_code,
                "reference": reference,
                "status": status,
                "old_material_code": old_code,
                "new_material_code": new_code,
            }
        )
    return tuple(differences)


def group_placement_differences(
    differences: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """Group identical business changes while preserving every physical reference."""
    grouped: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    for item in differences:
        key = (
            str(item.get("parent_code") or ""),
            str(item.get("status") or ""),
            str(item.get("old_material_code") or ""),
            str(item.get("new_material_code") or ""),
        )
        reference = str(item.get("reference") or "").strip()
        if reference:
            grouped[key].append(reference)

    result: list[Mapping[str, object]] = []
    for (parent_code, status, old_code, new_code), references in grouped.items():
        ordered = tuple(sorted(set(references), key=natural_reference_key))
        identity = {
            "parent_code": parent_code,
            "status": status,
            "old_material_code": old_code,
            "new_material_code": new_code,
        }
        result.append(
            {
                "group_id": stable_semantic_fingerprint(
                    "placement-change-group",
                    identity,
                ),
                **identity,
                "references": list(ordered),
                "reference_count": len(ordered),
            }
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                str(item["parent_code"]),
                str(item["status"]),
                natural_reference_key(str(item["references"][0])),
            ),
        )
    )


def _group_events(
    matches: Sequence[GroupMatch],
    unmatched_old: Sequence[SubstituteGroup],
    unmatched_new: Sequence[SubstituteGroup],
) -> tuple[list[BomChangeEvent], list[Mapping[str, object]], set[tuple[str, str]]]:
    events: list[BomChangeEvent] = []
    differences: list[Mapping[str, object]] = []
    handled_placements: set[tuple[str, str]] = set()
    for match in matches:
        old, new = match.old, match.new
        delta = compare_substitute_groups(old, new)
        if not delta.changed:
            continue
        old_snapshot = _group_snapshot(old)
        new_snapshot = _group_snapshot(new)
        differences.append(
            {
                "status": "changed",
                "change_dimensions": list(delta.changed_dimensions),
                "old": old_snapshot,
                "new": new_snapshot,
            }
        )
        blockers = tuple(
            finding.code
            for finding in (*old.validation_findings, *new.validation_findings)
            if finding.severity == FindingSeverity.BLOCKER
            and finding.code not in SUBSTITUTE_CONFIGURATION_FINDING_CODES
        )
        if blockers:
            events.append(
                make_change_event(
                    ChangeKind.SUBSTITUTE_STRUCTURE_INVALID,
                    new.parent_code,
                    f"替代组 {new.group_code or old.group_code} 结构无效",
                    FunctionalImpact.BLOCKER,
                    old_snapshot=old_snapshot,
                    new_snapshot=new_snapshot,
                    group_codes=tuple(dict.fromkeys((old.group_code, new.group_code))),
                    blocker_reasons=blockers,
                )
            )
            continue

        old_main = old.main_item.material_code if old.main_item else ""
        new_main = new.main_item.material_code if new.main_item else ""
        old_members = {item.material_code for item in old.members}
        new_members = {item.material_code for item in new.members}
        same_refs = old.physical_references == new.physical_references
        if old_main != new_main and old_members == new_members and same_refs:
            events.append(
                make_change_event(
                    ChangeKind.MAIN_CHANGED_REFS_MIGRATED,
                    new.parent_code,
                    f"替代组主料由 {old_main} 调整为 {new_main}",
                    FunctionalImpact.SUPPLY,
                    old_snapshot=old_snapshot,
                    new_snapshot=new_snapshot,
                    references=new.physical_references,
                    group_codes=tuple(dict.fromkeys((old.group_code, new.group_code))),
                )
            )
            handled_placements.update((new.parent_code, ref) for ref in new.physical_references)

        added = sorted(new_members - old_members)
        removed = sorted(old_members - new_members)
        if added:
            events.append(
                make_change_event(
                    ChangeKind.ALTERNATIVE_ADDED,
                    new.parent_code,
                    f"替代关系新增物料：{', '.join(added)}",
                    FunctionalImpact.SUPPLY,
                    old_snapshot=old_snapshot,
                    new_snapshot=new_snapshot,
                    references=new.physical_references,
                    group_codes=tuple(dict.fromkeys((old.group_code, new.group_code))),
                )
            )
        if removed:
            events.append(
                make_change_event(
                    ChangeKind.ALTERNATIVE_REMOVED,
                    new.parent_code,
                    f"替代关系删除物料：{', '.join(removed)}",
                    FunctionalImpact.SUPPLY,
                    old_snapshot=old_snapshot,
                    new_snapshot=new_snapshot,
                    references=old.physical_references,
                    group_codes=tuple(dict.fromkeys((old.group_code, new.group_code))),
                )
            )

        if (
            old_main == new_main
            and old_members == new_members
            and same_refs
            and "priorities" in delta.changed_dimensions
        ):
            events.append(
                make_change_event(
                    ChangeKind.SUBSTITUTE_PRIORITY_ONLY,
                    new.parent_code,
                    f"替代组 {new.group_code} 仅调整优先级",
                    FunctionalImpact.SUPPLY,
                    old_snapshot=old_snapshot,
                    new_snapshot=new_snapshot,
                    references=new.physical_references,
                    group_codes=(new.group_code,),
                )
            )
        if (
            old_main == new_main
            and old_members == new_members
            and same_refs
            and delta.configuration_changed
        ):
            events.append(
                make_change_event(
                    ChangeKind.SUBSTITUTE_CONFIGURATION_CHANGED,
                    new.parent_code,
                    f"替代组 {new.group_code} 的策略或方式变化",
                    FunctionalImpact.SUPPLY,
                    old_snapshot=old_snapshot,
                    new_snapshot=new_snapshot,
                    references=new.physical_references,
                    group_codes=(new.group_code,),
                )
            )
        if (
            old_main == new_main
            and old_members == new_members
            and "quantities" in delta.changed_dimensions
        ):
            events.append(
                make_change_event(
                    ChangeKind.QUANTITY_CHANGED,
                    new.parent_code,
                    f"替代组 {new.group_code} 的组内数量变化",
                    FunctionalImpact.SUPPLY,
                    old_snapshot=old_snapshot,
                    new_snapshot=new_snapshot,
                    references=tuple(
                        sorted(
                            set(old.physical_references) | set(new.physical_references),
                            key=natural_reference_key,
                        )
                    ),
                    group_codes=tuple(dict.fromkeys((old.group_code, new.group_code))),
                )
            )

    for old in unmatched_old:
        snapshot = _group_snapshot(old)
        differences.append({"status": "removed", "old": snapshot, "new": {}})
        if old.alternative_items:
            events.append(
                make_change_event(
                    ChangeKind.ALTERNATIVE_REMOVED,
                    old.parent_code,
                    f"删除替代关系 {old.group_code}",
                    FunctionalImpact.SUPPLY,
                    old_snapshot=snapshot,
                    references=old.physical_references,
                    group_codes=(old.group_code,),
                )
            )
    for new in unmatched_new:
        snapshot = _group_snapshot(new)
        differences.append({"status": "added", "old": {}, "new": snapshot})
        if new.alternative_items:
            events.append(
                make_change_event(
                    ChangeKind.ALTERNATIVE_ADDED,
                    new.parent_code,
                    f"新增替代关系 {new.group_code}",
                    FunctionalImpact.SUPPLY,
                    new_snapshot=snapshot,
                    references=new.physical_references,
                    group_codes=(new.group_code,),
                )
            )
    return events, differences, handled_placements


def _comparison_findings(
    findings: Iterable[ValidationFinding],
    changed_group_keys: set[tuple[str, str]],
) -> tuple[ValidationFinding, ...]:
    """Treat missing optional source evidence as unknown for unchanged groups."""
    contextualized: list[ValidationFinding] = []
    for finding in findings:
        group_code = str(finding.details.get("group_code") or "")
        group_key = finding.parent_code, group_code
        if (
            finding.code in SUBSTITUTE_CONFIGURATION_FINDING_CODES
            and group_code
            and group_key not in changed_group_keys
            and finding.severity == FindingSeverity.BLOCKER
        ):
            contextualized.append(replace(finding, severity=FindingSeverity.WARNING))
        else:
            contextualized.append(finding)
    return tuple(contextualized)


def _replacement_events(
    placement_diff: Sequence[Mapping[str, object]],
    old_items: Mapping[tuple[str, str], MaterialItem],
    new_items: Mapping[tuple[str, str], MaterialItem],
    handled: set[tuple[str, str]],
) -> tuple[list[BomChangeEvent], set[tuple[str, str]]]:
    migrations: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for item in placement_diff:
        key = str(item["parent_code"]), str(item["reference"])
        if key in handled or item["status"] != "migrated":
            continue
        migrations[
            (
                str(item["parent_code"]),
                str(item["old_material_code"]),
                str(item["new_material_code"]),
            )
        ].append(str(item["reference"]))

    targets_by_old: dict[tuple[str, str], set[str]] = defaultdict(set)
    for parent_code, old_code, new_code in migrations:
        targets_by_old[(parent_code, old_code)].add(new_code)

    events: list[BomChangeEvent] = []
    for (parent_code, old_code, new_code), references in migrations.items():
        old_item = old_items.get((parent_code, old_code))
        new_item = new_items.get((parent_code, new_code))
        reference_set = set(references)
        full_old = old_item is not None and reference_set == set(old_item.references)
        old_still_exists = (parent_code, old_code) in new_items
        kind = (
            ChangeKind.REPLACEMENT
            if (
                full_old
                and not old_still_exists
                and len(targets_by_old[(parent_code, old_code)]) == 1
            )
            else ChangeKind.REFERENCE_MIGRATED
        )
        title = (
            f"{old_code} 完全更换为 {new_code}"
            if kind == ChangeKind.REPLACEMENT
            else f"{old_code} 的部分位号迁移到 {new_code}"
        )
        events.append(
            make_change_event(
                kind,
                parent_code,
                title,
                FunctionalImpact.PLACEMENT,
                old_snapshot=_item_snapshot(old_item),
                new_snapshot=_item_snapshot(new_item),
                references=tuple(sorted(references, key=natural_reference_key)),
            )
        )
        handled.update((parent_code, reference) for reference in references)
    return events, handled


def _reference_set_events(
    placement_diff: Sequence[Mapping[str, object]],
    old_items: Mapping[tuple[str, str], MaterialItem],
    new_items: Mapping[tuple[str, str], MaterialItem],
    handled: set[tuple[str, str]],
) -> tuple[list[BomChangeEvent], set[tuple[str, str]]]:
    changes: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(
        lambda: {"added": [], "removed": []}
    )
    for item in placement_diff:
        parent_code = str(item["parent_code"])
        reference = str(item["reference"])
        if (parent_code, reference) in handled:
            continue
        status = str(item["status"])
        if status not in {"added", "removed"}:
            continue
        material_code = str(
            item["new_material_code"] if status == "added" else item["old_material_code"]
        )
        changes[(parent_code, material_code)][status].append(reference)

    events: list[BomChangeEvent] = []
    for (parent_code, material_code), references in changes.items():
        added = tuple(
            sorted(references["added"], key=natural_reference_key)
        )
        removed = tuple(
            sorted(references["removed"], key=natural_reference_key)
        )
        if not added or not removed:
            continue
        events.append(
            make_change_event(
                ChangeKind.REFERENCE_SET_CHANGED,
                parent_code,
                (
                    f"{material_code} 位号集合调整："
                    f"删除 {', '.join(removed)}；新增 {', '.join(added)}"
                ),
                FunctionalImpact.PLACEMENT,
                old_snapshot=_item_snapshot(
                    old_items.get((parent_code, material_code))
                ),
                new_snapshot=_item_snapshot(
                    new_items.get((parent_code, material_code))
                ),
                references=tuple(
                    sorted((*removed, *added), key=natural_reference_key)
                ),
            )
        )
        handled.update(
            (parent_code, reference)
            for reference in (*removed, *added)
        )
    return events, handled


def _remaining_placement_events(
    placement_diff: Sequence[Mapping[str, object]],
    old_items: Mapping[tuple[str, str], MaterialItem],
    new_items: Mapping[tuple[str, str], MaterialItem],
    handled: set[tuple[str, str]],
) -> list[BomChangeEvent]:
    grouped: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for item in placement_diff:
        key = str(item["parent_code"]), str(item["reference"])
        if key in handled:
            continue
        grouped[
            (
                str(item["parent_code"]),
                str(item["status"]),
                str(item["new_material_code"] or item["old_material_code"]),
            )
        ].append(str(item["reference"]))

    events: list[BomChangeEvent] = []
    kinds = {
        "added": ChangeKind.REFERENCE_ADDED,
        "removed": ChangeKind.REFERENCE_REMOVED,
        "migrated": ChangeKind.REFERENCE_MIGRATED,
    }
    for (parent_code, status, material_code), references in grouped.items():
        old_item = old_items.get((parent_code, material_code))
        new_item = new_items.get((parent_code, material_code))
        events.append(
            make_change_event(
                kinds[status],
                parent_code,
                f"{material_code} 位号{ {'added': '新增', 'removed': '删除', 'migrated': '迁移'}[status] }",
                FunctionalImpact.PLACEMENT,
                old_snapshot=_item_snapshot(old_item),
                new_snapshot=_item_snapshot(new_item),
                references=tuple(sorted(references, key=natural_reference_key)),
            )
        )
    return events


def _material_and_metadata_events(
    old_items: Mapping[tuple[str, str], MaterialItem],
    new_items: Mapping[tuple[str, str], MaterialItem],
    substitute_member_keys: set[tuple[str, str]],
) -> tuple[list[BomChangeEvent], list[Mapping[str, object]]]:
    events: list[BomChangeEvent] = []
    metadata: list[Mapping[str, object]] = []
    for key in sorted(set(old_items) | set(new_items)):
        old = old_items.get(key)
        new = new_items.get(key)
        if (
            old is None
            and new is not None
            and not new.references
            and key not in substitute_member_keys
        ):
            events.append(
                make_change_event(
                    ChangeKind.MATERIAL_ADDED,
                    key[0],
                    f"新增物料 {key[1]}",
                    FunctionalImpact.SUPPLY,
                    new_snapshot=_item_snapshot(new),
                )
            )
            continue
        if (
            new is None
            and old is not None
            and not old.references
            and key not in substitute_member_keys
        ):
            events.append(
                make_change_event(
                    ChangeKind.MATERIAL_REMOVED,
                    key[0],
                    f"删除物料 {key[1]}",
                    FunctionalImpact.SUPPLY,
                    old_snapshot=_item_snapshot(old),
                )
            )
            continue
        if old is None or new is None:
            continue
        old_metadata = _metadata_snapshot(old)
        new_metadata = _metadata_snapshot(new)
        changed_fields = _changed_metadata_fields(
            old_metadata,
            new_metadata,
        )
        if (
            _variant_signature(old) != _variant_signature(new)
            or changed_fields
        ):
            item = {
                "parent_code": key[0],
                "material_code": key[1],
                "old_variants": [variant.payload() for variant in old.variants],
                "new_variants": [variant.payload() for variant in new.variants],
                "old_metadata": old_metadata,
                "new_metadata": new_metadata,
                "changed_fields": list(changed_fields),
            }
            metadata.append(item)
            events.append(
                make_change_event(
                    ChangeKind.METADATA_ONLY,
                    key[0],
                    f"{key[1]} 的描述或元数据变化",
                    FunctionalImpact.METADATA,
                    old_snapshot=_item_snapshot(old),
                    new_snapshot=_item_snapshot(new),
                )
            )
        elif old.quantity != new.quantity and old.references == new.references:
            events.append(
                make_change_event(
                    ChangeKind.QUANTITY_CHANGED,
                    key[0],
                    f"{key[1]} 数量变化",
                    FunctionalImpact.PLACEMENT,
                    old_snapshot=_item_snapshot(old),
                    new_snapshot=_item_snapshot(new),
                    references=new.references or old.references,
                )
            )
    return events, metadata


def _blocker_events(findings: Iterable[ValidationFinding]) -> list[BomChangeEvent]:
    by_parent: dict[str, list[ValidationFinding]] = defaultdict(list)
    for finding in findings:
        if finding.severity == FindingSeverity.BLOCKER:
            by_parent[finding.parent_code].append(finding)
    return [
        make_change_event(
            ChangeKind.PLACEMENT_BLOCKER,
            parent_code,
            "BOM 结构或贴装映射存在阻断项",
            FunctionalImpact.BLOCKER,
            references=tuple(
                sorted(
                    {reference for finding in group for reference in finding.references},
                    key=natural_reference_key,
                )
            ),
            blocker_reasons=tuple(dict.fromkeys(finding.code for finding in group)),
            source_ids=tuple(
                dict.fromkeys(source_id for finding in group for source_id in finding.source_ids)
            ),
        )
        for parent_code, group in sorted(by_parent.items())
    ]


def _blocking_record_count(findings: Iterable[ValidationFinding]) -> int:
    records: set[tuple[object, ...]] = set()
    for finding in findings:
        if finding.source_ids:
            records.update(("source", source_id) for source_id in finding.source_ids)
            continue
        details = dict(finding.details)
        material_codes = details.get("material_codes")
        if isinstance(material_codes, (list, tuple)):
            material_target = tuple(str(code) for code in material_codes)
        else:
            material_target = (
                str(
                    details.get("material_code")
                    or details.get("main_code")
                    or details.get("group_code")
                    or ""
                ),
            )
        target = (
            "target",
            finding.parent_code,
            str(details.get("group_code") or ""),
            material_target,
            tuple(finding.references),
        )
        if target[2:] == ("", ("",), ()):
            target = (
                "finding",
                finding.parent_code,
                finding.code,
                tuple(finding.references),
            )
        records.add(target)
    return len(records)


def compare_board_boms(
    old_boards: Sequence[BoardBOM],
    new_boards: Sequence[BoardBOM],
    *,
    old_source_fingerprint: str = "",
    new_source_fingerprint: str = "",
    additional_findings: Iterable[ValidationFinding] = (),
) -> CompareResult:
    old_items = _all_items(old_boards)
    new_items = _all_items(new_boards)
    old_placements = _placements(old_boards)
    new_placements = _placements(new_boards)
    placement_diff = _placement_diff(old_placements, new_placements)
    placement_groups = group_placement_differences(placement_diff)
    matches, unmatched_old, unmatched_new = match_substitute_groups(
        _groups(old_boards),
        _groups(new_boards),
    )
    changed_group_keys = structurally_changed_group_keys(
        matches,
        unmatched_old,
        unmatched_new,
    )
    group_events, substitute_diff, handled = _group_events(
        matches,
        unmatched_old,
        unmatched_new,
    )
    replacement_events, handled = _replacement_events(
        placement_diff,
        old_items,
        new_items,
        handled,
    )
    reference_set_events, handled = _reference_set_events(
        placement_diff,
        old_items,
        new_items,
        handled,
    )
    placement_events = _remaining_placement_events(
        placement_diff,
        old_items,
        new_items,
        handled,
    )
    substitute_member_keys = {
        (group.parent_code, item.material_code)
        for group in (*_groups(old_boards), *_groups(new_boards))
        for item in group.members
    }
    material_events, metadata_diff = _material_and_metadata_events(
        old_items,
        new_items,
        substitute_member_keys,
    )

    findings = _comparison_findings(
        (
            finding
            for board in (*old_boards, *new_boards)
            for finding in board.findings
        ),
        changed_group_keys,
    ) + tuple(additional_findings)
    blockers = tuple(
        finding for finding in findings if finding.severity == FindingSeverity.BLOCKER
    )
    warnings = tuple(
        finding for finding in findings if finding.severity == FindingSeverity.WARNING
    )
    events = [
        *_blocker_events(blockers),
        *group_events,
        *replacement_events,
        *reference_set_events,
        *placement_events,
        *material_events,
    ]
    unique_events = tuple(
        {event.event_id: event for event in events}.values()
    )
    counts = Counter(event.kind.value for event in unique_events)
    old_fingerprint = old_source_fingerprint or stable_semantic_fingerprint(
        "old-board-set",
        [board.source_fingerprint for board in old_boards],
    )
    new_fingerprint = new_source_fingerprint or stable_semantic_fingerprint(
        "new-board-set",
        [board.source_fingerprint for board in new_boards],
    )
    analysis_fingerprint = stable_semantic_fingerprint(
        "bom-comparison",
        {
            "old": old_fingerprint,
            "new": new_fingerprint,
            "events": [event.event_id for event in unique_events],
        },
    )
    board_metadata_diff = _board_metadata_diff(old_boards, new_boards)
    metadata_event_count = counts.get(ChangeKind.METADATA_ONLY.value, 0)
    metadata_field_count = sum(
        len(row.get("changed_fields") or ())
        for row in (*metadata_diff, *board_metadata_diff)
    )
    summary = CompareSummary(
        parent_count_old=len(old_boards),
        parent_count_new=len(new_boards),
        material_count_old=len(old_items),
        material_count_new=len(new_items),
        actual_reference_count_old=len(old_placements),
        actual_reference_count_new=len(new_placements),
        placement_change_group_count=len(placement_groups),
        placement_changed_reference_count=len(placement_diff),
        substitute_group_count_old=len(_groups(old_boards)),
        substitute_group_count_new=len(_groups(new_boards)),
        changed_event_count=len(unique_events),
        review_event_count=len(unique_events) - metadata_event_count,
        metadata_event_count=metadata_event_count,
        metadata_change_count=len(metadata_diff) + len(board_metadata_diff),
        metadata_field_count=metadata_field_count,
        blocker_count=len(blockers),
        blocking_record_count=_blocking_record_count(blockers),
        event_counts=dict(counts),
    )
    return CompareResult(
        analysis_fingerprint=analysis_fingerprint,
        old_source_fingerprint=old_fingerprint,
        new_source_fingerprint=new_fingerprint,
        summary=summary,
        events=unique_events,
        raw_row_diff=_raw_row_diff(old_boards, new_boards),
        placement_diff=placement_diff,
        placement_groups=placement_groups,
        substitute_diff=tuple(substitute_diff),
        board_metadata_diff=board_metadata_diff,
        metadata_diff=tuple(metadata_diff),
        blockers=blockers,
        warnings=warnings,
    )
