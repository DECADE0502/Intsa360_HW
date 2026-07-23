from __future__ import annotations

from typing import Mapping

from app.backend.bom_semantics.models import (
    BomChangeEvent,
    ChangeKind,
    FunctionalImpact,
)
from app.backend.bom_semantics.validation import stable_semantic_fingerprint


OA_CHANGE_TYPES: Mapping[ChangeKind, str] = {
    ChangeKind.MATERIAL_ADDED: "新增",
    ChangeKind.MATERIAL_REMOVED: "删除",
    ChangeKind.REPLACEMENT: "更换(A换成B)",
    ChangeKind.ALTERNATIVE_ADDED: "替代(AB共存)",
    ChangeKind.ALTERNATIVE_REMOVED: "替代(AB共存)",
    ChangeKind.SUBSTITUTE_PRIORITY_ONLY: "替代(AB共存)",
    ChangeKind.MAIN_CHANGED_REFS_MIGRATED: "替代(AB共存)",
    ChangeKind.QUANTITY_CHANGED: "数量(位号)修改",
    ChangeKind.REFERENCE_ADDED: "数量(位号)修改",
    ChangeKind.REFERENCE_REMOVED: "数量(位号)修改",
    ChangeKind.REFERENCE_MIGRATED: "更换(A换成B)",
}


def make_change_event(
    kind: ChangeKind,
    parent_code: str,
    title: str,
    impact: FunctionalImpact,
    *,
    old_snapshot: Mapping[str, object] | None = None,
    new_snapshot: Mapping[str, object] | None = None,
    references: tuple[str, ...] = (),
    group_codes: tuple[str, ...] = (),
    blocker_reasons: tuple[str, ...] = (),
    source_ids: tuple[str, ...] = (),
    oa_change_type: str | None = None,
) -> BomChangeEvent:
    identity = {
        "kind": kind.value,
        "parent_code": parent_code,
        "old": dict(old_snapshot or {}),
        "new": dict(new_snapshot or {}),
        "references": list(references),
        "group_codes": list(group_codes),
        "blocker_reasons": list(blocker_reasons),
    }
    return BomChangeEvent(
        event_id=stable_semantic_fingerprint("bom-change-event", identity),
        kind=kind,
        parent_code=parent_code,
        title=title,
        impact=impact,
        old_snapshot=dict(old_snapshot or {}),
        new_snapshot=dict(new_snapshot or {}),
        references=references,
        group_codes=group_codes,
        blocker_reasons=blocker_reasons,
        oa_change_type=oa_change_type if oa_change_type is not None else OA_CHANGE_TYPES.get(kind, ""),
        source_ids=source_ids,
    )

