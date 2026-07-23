from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Iterable

from app.backend.bom_semantics.models import (
    FindingSeverity,
    MaterialItem,
    SubstituteGroup,
    ValidationFinding,
)


def stable_semantic_fingerprint(namespace: str, payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(f"{namespace}\x1e{encoded}".encode("utf-8")).hexdigest()[:24]


def validate_substitute_members(
    parent_code: str,
    group_code: str,
    members: Iterable[MaterialItem],
) -> tuple[ValidationFinding, ...]:
    member_list = list(members)
    findings: list[ValidationFinding] = []
    mains = [item for item in member_list if item.substitute_priority == 0]
    source_ids = tuple(
        source_id
        for item in member_list
        for source_id in (row.source_id for row in item.source_rows)
    )
    if len(mains) != 1:
        findings.append(
            ValidationFinding(
                code="substitute_main_count_invalid",
                severity=FindingSeverity.BLOCKER,
                message="替代组必须有且只有一个优先级 0 主料。",
                source_ids=source_ids,
                parent_code=parent_code,
                details={"group_code": group_code, "main_count": len(mains)},
            )
        )

    priorities = [item.substitute_priority for item in member_list]
    if any(priority is None for priority in priorities):
        findings.append(
            ValidationFinding(
                code="substitute_priority_missing",
                severity=FindingSeverity.BLOCKER,
                message="替代组成员缺少替代优先级。",
                source_ids=source_ids,
                parent_code=parent_code,
                details={"group_code": group_code},
            )
        )
    else:
        ordered = sorted(int(priority) for priority in priorities if priority is not None)
        if ordered != list(range(len(member_list))):
            findings.append(
                ValidationFinding(
                    code="substitute_priority_not_continuous",
                    severity=FindingSeverity.BLOCKER,
                    message="替代优先级必须从 0 开始连续排列。",
                    source_ids=source_ids,
                    parent_code=parent_code,
                    details={"group_code": group_code, "priorities": ordered},
                )
            )

    if len(mains) == 1:
        main = mains[0]
        if group_code != main.material_code:
            findings.append(
                ValidationFinding(
                    code="substitute_group_code_not_main",
                    severity=FindingSeverity.BLOCKER,
                    message="替代组编码必须等于优先级 0 主料编码。",
                    source_ids=source_ids,
                    parent_code=parent_code,
                    details={"group_code": group_code, "main_code": main.material_code},
                )
            )
        if main.quantity is not None and main.quantity != Decimal(len(main.references)):
            findings.append(
                ValidationFinding(
                    code="substitute_main_quantity_reference_mismatch",
                    severity=FindingSeverity.BLOCKER,
                    message="替代组主料数量必须等于实际位号数。",
                    source_ids=source_ids,
                    parent_code=parent_code,
                    references=main.references,
                    details={"group_code": group_code, "quantity": str(main.quantity), "reference_count": len(main.references)},
                )
            )

    quantities = {item.quantity for item in member_list}
    if len(quantities) > 1:
        findings.append(
            ValidationFinding(
                code="substitute_quantity_mismatch",
                severity=FindingSeverity.BLOCKER,
                message="替代组内各行数量必须一致。",
                source_ids=source_ids,
                parent_code=parent_code,
                details={"group_code": group_code, "quantities": [str(value) for value in quantities]},
            )
        )

    for item in member_list:
        if item.substitute_priority not in (None, 0) and item.references:
            findings.append(
                ValidationFinding(
                    code="substitute_alternative_has_references",
                    severity=FindingSeverity.BLOCKER,
                    message="替代料位号必须为空。",
                    source_ids=tuple(row.source_id for row in item.source_rows),
                    parent_code=parent_code,
                    references=item.references,
                    details={"group_code": group_code, "material_code": item.material_code},
                )
            )

    strategy_field_present = any(
        "substitute_strategy" in row.raw_fields
        for item in member_list
        for row in item.source_rows
    )
    missing_strategy = (
        [
            (item, row)
            for item in member_list
            for row in item.source_rows
            if not row.substitute_strategy.strip()
        ]
        if strategy_field_present
        else []
    )
    if missing_strategy:
        findings.append(
            ValidationFinding(
                code="substitute_strategy_missing",
                severity=FindingSeverity.BLOCKER,
                message="替代组成员缺少替代策略，不能生成可靠的 PLM/OA 变更。",
                source_ids=tuple(row.source_id for _, row in missing_strategy),
                parent_code=parent_code,
                details={
                    "group_code": group_code,
                    "material_codes": sorted(
                        {item.material_code for item, _ in missing_strategy}
                    ),
                },
            )
        )

    mode_field_present = any(
        "substitute_mode" in row.raw_fields
        for item in member_list
        for row in item.source_rows
    )
    missing_mode = (
        [
            (item, row)
            for item in member_list
            for row in item.source_rows
            if not row.substitute_mode.strip()
        ]
        if mode_field_present
        else []
    )
    if missing_mode:
        findings.append(
            ValidationFinding(
                code="substitute_mode_missing",
                severity=FindingSeverity.BLOCKER,
                message="替代组成员缺少替代方式，不能生成可靠的 PLM/OA 变更。",
                source_ids=tuple(row.source_id for _, row in missing_mode),
                parent_code=parent_code,
                details={
                    "group_code": group_code,
                    "material_codes": sorted(
                        {item.material_code for item, _ in missing_mode}
                    ),
                },
            )
        )
    return tuple(findings)


def build_group_fingerprint(
    parent_code: str,
    group_code: str,
    members: Iterable[MaterialItem],
) -> str:
    member_list = list(members)
    main = next((item for item in member_list if item.substitute_priority == 0), None)
    payload = {
        "parent_code": parent_code,
        "references": sorted(main.references if main else ()),
        "members": sorted(item.material_code for item in member_list),
        "group_code": group_code,
    }
    return stable_semantic_fingerprint("substitute-group", payload)


def validate_material_membership(groups: Iterable[SubstituteGroup]) -> tuple[ValidationFinding, ...]:
    memberships: dict[tuple[str, str], set[str]] = defaultdict(set)
    source_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for group in groups:
        for member in group.members:
            key = member.parent_code, member.material_code
            memberships[key].add(group.group_code)
            source_ids[key].extend(row.source_id for row in member.source_rows)
    findings: list[ValidationFinding] = []
    for (parent_code, material_code), group_codes in memberships.items():
        if len(group_codes) <= 1:
            continue
        findings.append(
            ValidationFinding(
                code="material_in_multiple_substitute_groups",
                severity=FindingSeverity.BLOCKER,
                message="同一父项下的同一物料出现在多个替代组。",
                source_ids=tuple(source_ids[(parent_code, material_code)]),
                parent_code=parent_code,
                details={"material_code": material_code, "group_codes": sorted(group_codes)},
            )
        )
    return tuple(findings)


def validate_unique_placements(
    placements: Iterable[tuple[str, str, str, tuple[str, ...]]],
) -> tuple[ValidationFinding, ...]:
    by_key: dict[tuple[str, str], list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
    for parent_code, reference, material_code, source_ids in placements:
        by_key[(parent_code, reference)].append((material_code, source_ids))
    findings: list[ValidationFinding] = []
    for (parent_code, reference), values in by_key.items():
        codes = Counter(code for code, _ in values)
        if len(codes) <= 1:
            continue
        findings.append(
            ValidationFinding(
                code="reference_mapped_to_multiple_main_materials",
                severity=FindingSeverity.BLOCKER,
                message="同一父项下的同一位号映射到多个主料。",
                source_ids=tuple(source_id for _, ids in values for source_id in ids),
                parent_code=parent_code,
                references=(reference,),
                details={"material_codes": sorted(codes)},
            )
        )
    return tuple(findings)
