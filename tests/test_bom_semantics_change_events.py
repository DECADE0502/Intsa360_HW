from __future__ import annotations

from app.backend.bom_semantics.change_events import make_change_event
from app.backend.bom_semantics.models import ChangeKind, FunctionalImpact


def test_change_event_id_is_stable_and_oa_type_is_semantic() -> None:
    first = make_change_event(
        ChangeKind.ALTERNATIVE_ADDED,
        "BOARD-A",
        "新增替代料",
        FunctionalImpact.SUPPLY,
        new_snapshot={"members": ["A", "B"]},
        references=("C1",),
    )
    second = make_change_event(
        ChangeKind.ALTERNATIVE_ADDED,
        "BOARD-A",
        "标题改变也不影响身份",
        FunctionalImpact.SUPPLY,
        new_snapshot={"members": ["A", "B"]},
        references=("C1",),
    )

    assert first.event_id == second.event_id
    assert first.oa_change_type == "替代(AB共存)"
