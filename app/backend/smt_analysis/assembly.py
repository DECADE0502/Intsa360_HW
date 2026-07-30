from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from app.backend.contracts.smt_analysis import (
    AssemblyState,
    CoordinateScope,
    PlacementRole,
    SmtBomRequirement,
    SmtCoordinateOccurrence,
    SmtCoordinateSet,
    SmtEvidence,
    SmtMaterialOption,
    SmtPlacement,
)
from app.backend.parsers.refs import natural_key
from app.backend.smt_analysis.evidence import evidence
from app.backend.smt_analysis.roles import infer_role


@dataclass(frozen=True)
class ExplicitAssemblyDecision:
    destination: str
    exclusion_kind: str
    role: str
    subtype: str = ""


@dataclass(frozen=True)
class AssemblyResult:
    placements: tuple[SmtPlacement, ...]
    blocking_reasons: tuple[str, ...]


def blocking_reasons_for_placements(
    placements: Sequence[SmtPlacement],
) -> tuple[str, ...]:
    reasons = [
        (
            f"{placement.ref}: "
            f"{placement.blocking_reasons[0] if placement.blocking_reasons else placement.assembly_state}"
        )
        for placement in placements
        if placement.assembly_state
        in {"conflicting", "unresolved", "bom_only", "coordinate_only"}
    ]
    return tuple(dict.fromkeys(reasons))


def _placement_id(ref: str) -> str:
    digest = hashlib.sha256(ref.casefold().encode("utf-8")).hexdigest()
    return f"placement-{digest[:24]}"


def _normalized_refs(values: Iterable[str]) -> set[str]:
    return {str(value).strip().upper() for value in values if str(value).strip()}


def _source_rows_location(rows: Iterable[int], *, max_length: int = 240) -> str | None:
    normalized = sorted({int(row) for row in rows if int(row) > 0})
    if not normalized:
        return None
    complete = ",".join(str(row) for row in normalized)
    if len(complete) <= max_length:
        return complete

    suffix = f"…（共 {len(normalized)} 行）"
    available = max_length - len(suffix)
    visible: list[str] = []
    used = 0
    for row in normalized:
        token = str(row)
        extra = len(token) + (1 if visible else 0)
        if used + extra > available:
            break
        visible.append(token)
        used += extra
    return ",".join(visible) + suffix


def _scope_for_occurrences(
    occurrences: Sequence[tuple[SmtCoordinateOccurrence, CoordinateScope]],
) -> CoordinateScope:
    scopes = {scope for _, scope in occurrences}
    if len(scopes) == 1:
        return next(iter(scopes))
    if "unknown" in scopes:
        return "unknown"
    if scopes == {"placement_only", "smt_only"}:
        return "placement_only"
    return "unknown"


def _coordinate_groups(
    coordinate_sets: Sequence[SmtCoordinateSet],
) -> dict[str, list[tuple[SmtCoordinateOccurrence, CoordinateScope]]]:
    result: dict[str, list[tuple[SmtCoordinateOccurrence, CoordinateScope]]] = {}
    for coordinate_set in coordinate_sets:
        for occurrence in coordinate_set.occurrences:
            result.setdefault(occurrence.ref.strip().upper(), []).append(
                (occurrence, coordinate_set.scope_semantics)
            )
    return result


def _decision_role(
    decision: ExplicitAssemblyDecision | None,
    occurrence: SmtCoordinateOccurrence | None,
) -> tuple[PlacementRole, list[SmtEvidence], bool]:
    inference = infer_role(
        occurrence.ref if occurrence else "",
        occurrence.footprint if occurrence else "",
        explicit_role=decision.role if decision else "",
        explicit_subtype=decision.subtype if decision else "",
    )
    return inference.role, list(inference.evidence), inference.strong_process_role


def _state_without_data(
    *,
    has_coordinate: bool,
    has_bom: bool,
    scope: CoordinateScope,
    role: PlacementRole,
    strong_process_role: bool,
    decision: ExplicitAssemblyDecision | None,
) -> tuple[AssemblyState, list[str]]:
    if decision is not None:
        if decision.destination == "smt":
            return ("installed" if has_coordinate and has_bom else "bom_only"), []
        if decision.exclusion_kind == "nc":
            if has_bom:
                return "conflicting", ["明确 NC 位号仍存在于成品 BOM。"]
            return "confirmed_nc", []
        if decision.exclusion_kind in {"process_only", "scope_excluded", "user_excluded"}:
            if has_bom:
                return "conflicting", ["明确非贴片位号仍存在于成品 BOM。"]
            return "non_smt", []
        return "unresolved", ["BOM 处理记录的排除类型无法识别。"]

    if has_bom and has_coordinate:
        return "installed", []
    if has_bom:
        return "bom_only", ["成品 BOM 要求装机，但坐标数据中没有该位号。"]
    if strong_process_role or role in {"test_point", "fiducial", "tooling_hole", "mounting_hole", "panel_object"}:
        return "non_smt", []
    if has_coordinate:
        if scope == "full_design_set":
            return "confirmed_nc", []
        if scope == "unknown":
            return "candidate_nc", ["坐标数据范围未确认，不能把坐标减 BOM 自动判为明确 NC。"]
        return "coordinate_only", ["该坐标集只声明贴装范围，坐标减 BOM 不代表 NC。"]
    return "unresolved", ["位号仅存在于辅助证据中。"]


def analyze_assembly(
    *,
    coordinate_sets: Sequence[SmtCoordinateSet],
    bom_requirements: Mapping[str, SmtBomRequirement],
    explicit_decisions: Mapping[str, ExplicitAssemblyDecision] | None = None,
    netlist_refs: Iterable[str] | None = None,
    drawing_refs: Iterable[str] | None = None,
) -> AssemblyResult:
    coordinates = _coordinate_groups(coordinate_sets)
    requirements = {
        str(ref).strip().upper(): requirement
        for ref, requirement in bom_requirements.items()
        if str(ref).strip()
    }
    decisions = {
        str(ref).strip().upper(): decision
        for ref, decision in (explicit_decisions or {}).items()
        if str(ref).strip()
    }
    netlist = _normalized_refs(netlist_refs or ())
    drawing = _normalized_refs(drawing_refs or ())
    all_refs = set(coordinates) | set(requirements) | set(decisions) | netlist | drawing
    placements: list[SmtPlacement] = []

    for ref in sorted(all_refs, key=natural_key):
        coordinate_items = coordinates.get(ref, [])
        occurrences = [item for item, _ in coordinate_items]
        primary_occurrence = occurrences[0] if occurrences else None
        requirement = requirements.get(ref)
        decision = decisions.get(ref)
        role, role_evidence, strong_process_role = _decision_role(decision, primary_occurrence)
        chain: list[SmtEvidence] = list(role_evidence)
        if occurrences:
            chain.append(
                evidence(
                    "coordinate_membership",
                    "坐标数据包含该物理位号。",
                    weight="strong",
                    value=str(len(occurrences)),
                )
            )
        if requirement is not None:
            chain.append(
                evidence(
                    "bom_membership",
                    "处理后成品 BOM 要求该位号装机。",
                    weight="strong",
                    source_location=_source_rows_location(requirement.source_rows),
                )
            )
        if decision is not None:
            chain.append(
                evidence(
                    "bom_process_decision",
                    "已自动关联 BOM 处理阶段的明确归类结果。",
                    weight="strong",
                    value=f"{decision.destination}:{decision.exclusion_kind}:{decision.role}:{decision.subtype}",
                )
            )
        if ref in netlist:
            chain.append(
                evidence(
                    "netlist_membership",
                    "Cadence 网表包含该位号；网表只作为辅助证据。",
                    weight="supporting",
                )
            )
        if ref in drawing:
            chain.append(
                evidence(
                    "drawing_membership",
                    "位号图页面提取到该位号。",
                    weight="supporting",
                )
            )

        blocking: list[str] = []
        scope = _scope_for_occurrences(coordinate_items) if coordinate_items else "unknown"
        state, state_blocking = _state_without_data(
            has_coordinate=bool(occurrences),
            has_bom=requirement is not None,
            scope=scope,
            role=role,
            strong_process_role=strong_process_role,
            decision=decision,
        )
        blocking.extend(state_blocking)

        if len(occurrences) > 1:
            distinct_positions = {
                (item.normalized_x, item.normalized_y, item.side)
                for item in occurrences
            }
            if len(distinct_positions) > 1 or len(occurrences) > 1:
                state = "conflicting"
                blocking.append("同一物理位号在坐标数据中出现多次。")
                chain.append(
                    evidence(
                        "duplicate_coordinate",
                        "同一位号对应多条坐标记录，必须先确认重复、拼板或版本问题。",
                        weight="conflicting",
                        value=str(len(occurrences)),
                    )
                )
        if primary_occurrence is not None and (
            primary_occurrence.normalized_x is None or primary_occurrence.normalized_y is None
        ):
            blocking.append("坐标单位尚未确认，不能生成可信图像热点。")
        if primary_occurrence is not None and primary_occurrence.side == "unknown":
            blocking.append("坐标面别尚未确认。")
        placements.append(
            SmtPlacement(
                placement_id=_placement_id(ref),
                ref=ref,
                side=primary_occurrence.side if primary_occurrence is not None else "unknown",
                coordinate_occurrence_ids=[item.occurrence_id for item in occurrences],
                image_x=None,
                image_y=None,
                bom_requirement=requirement,
                netlist_present=ref in netlist if netlist_refs is not None else None,
                drawing_present=ref in drawing if drawing_refs is not None else None,
                role=role,
                assembly_state=state,
                blocking_reasons=list(dict.fromkeys(blocking)),
                evidence_chain=chain,
                decision=None,
            )
        )
    return AssemblyResult(
        placements=tuple(placements),
        blocking_reasons=blocking_reasons_for_placements(placements),
    )


def requirements_from_rows(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, SmtBomRequirement]:
    """Build one physical placement per real reference.

    Rows without references are treated as alternate-material metadata and do
    not create additional placements or increase the physical quantity.
    """
    requirements: dict[str, SmtBomRequirement] = {}
    alternatives_by_group: dict[tuple[str, str], list[SmtMaterialOption]] = {}
    source_rows_by_group: dict[tuple[str, str], list[int]] = {}
    primaries: list[tuple[Mapping[str, object], list[str], tuple[str, str]]] = []

    for index, row in enumerate(rows, start=1):
        parent = str(row.get("parent_code") or "")
        material_code = str(row.get("material_code") or row.get("part_number") or "")
        group_code = str(row.get("substitute_group_code") or material_code)
        key = (parent, group_code)
        priority_raw = row.get("substitute_priority")
        try:
            priority = int(priority_raw) if priority_raw not in (None, "") else 0
        except (TypeError, ValueError):
            priority = 0
        option = SmtMaterialOption(
            part_number=material_code,
            description=str(row.get("description") or ""),
            model=str(row.get("model") or ""),
            grade=str(row.get("grade") or ""),
            is_primary=priority == 0,
        )
        alternatives_by_group.setdefault(key, []).append(option)
        source_rows_by_group.setdefault(key, []).append(int(row.get("source_row") or index))
        raw_refs = row.get("refs") or row.get("references") or []
        refs = (
            [str(value).strip().upper() for value in raw_refs if str(value).strip()]
            if isinstance(raw_refs, (list, tuple, set))
            else [part.strip().upper() for part in str(raw_refs).replace("，", ",").split(",") if part.strip()]
        )
        if priority == 0 and refs:
            primaries.append((row, refs, key))

    for row, refs, key in primaries:
        quantity_raw = row.get("quantity")
        try:
            quantity = float(quantity_raw) if quantity_raw not in (None, "") else float(len(refs))
        except (TypeError, ValueError):
            quantity = float(len(refs))
        requirement = SmtBomRequirement(
            parent_code=key[0],
            quantity=quantity,
            materials=alternatives_by_group.get(key, []),
            source_rows=source_rows_by_group.get(key, []),
        )
        for ref in refs:
            if ref in requirements and requirements[ref] != requirement:
                raise ValueError(f"同一父项位号 {ref} 映射到多个主料或替代组")
            requirements[ref] = requirement
    return requirements
