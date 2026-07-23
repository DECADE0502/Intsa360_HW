from __future__ import annotations

from decimal import Decimal

from app.backend.bom_semantics.models import (
    BomChangeEvent,
    CanonicalRow,
    ChangeKind,
    FunctionalImpact,
    MaterialItem,
    MaterialVariant,
    SubstituteGroup,
)
from app.backend.bom_semantics.oa_export import (
    OAChangeType,
    build_oa_ecr_export,
    expand_substitute_group,
)


def _item(
    code: str,
    priority: int,
    references: tuple[str, ...],
    *,
    quantity: str = "4",
) -> MaterialItem:
    row = CanonicalRow(
        source_id=f"source:{code}",
        sheet_name="BOM",
        row_number=priority + 3,
        parent_code="BOARD-A",
        material_code=code,
        name=f"Name {code}",
        model=f"Model {code}",
        description=f"Description {code}",
        unit="EA",
        quantity=Decimal(quantity),
        references=references,
        substitute_group_code="MAT-A",
        substitute_priority=priority,
    )
    return MaterialItem(
        parent_code="BOARD-A",
        material_code=code,
        quantity=Decimal(quantity),
        references=references,
        variants=(
            MaterialVariant(
                material_code=code,
                name=row.name,
                model=row.model,
                description=row.description,
                unit=row.unit,
            ),
        ),
        source_rows=(row,),
        substitute_group_code="MAT-A",
        substitute_priority=priority,
    )


def _three_member_group() -> SubstituteGroup:
    main = _item("MAT-A", 0, ("C1", "C2", "C3", "C4"))
    alternative_b = _item("MAT-B", 1, ("60",))
    alternative_c = _item("MAT-C", 2, ())
    return SubstituteGroup(
        parent_code="BOARD-A",
        group_code="MAT-A",
        main_item=main,
        alternative_items=(alternative_b, alternative_c),
        physical_references=main.references,
        quantity=Decimal("4"),
    )


def test_three_member_substitute_group_expands_to_two_paired_oa_items() -> None:
    items = expand_substitute_group(_three_member_group(), event_id="evt-sub")

    assert len(items) == 2
    assert all(item.change_type == OAChangeType.SUBSTITUTE for item in items)
    assert all(len(item.rows) == 2 for item in items)
    assert [item.rows[1].material_code for item in items] == ["MAT-B", "MAT-C"]
    assert all(item.rows[0].material_code == "MAT-A" for item in items)
    assert all(item.rows[0].references == ("C1", "C2", "C3", "C4") for item in items)
    assert all(item.rows[1].references == () for item in items)
    assert all(item.rows[0].substitute_group_code == "MAT-A" for item in items)
    assert all(item.rows[1].substitute_group_code == "MAT-A" for item in items)


def test_export_supports_all_ecr_change_types_without_confusing_replacement_and_substitute() -> None:
    group = _three_member_group()
    events = (
        BomChangeEvent(
            event_id="evt-sub",
            kind=ChangeKind.ALTERNATIVE_ADDED,
            parent_code="BOARD-A",
            title="Add substitute",
            impact=FunctionalImpact.SUPPLY,
            group_codes=("MAT-A",),
        ),
        {
            "event_id": "evt-add",
            "kind": "material_added",
            "parent_code": "BOARD-A",
            "new_snapshot": {"material_code": "MAT-D", "quantity": "2", "references": "R1,R2"},
        },
        {
            "event_id": "evt-delete",
            "kind": "material_removed",
            "parent_code": "BOARD-A",
            "old_snapshot": {"material_code": "MAT-E", "quantity": "1", "references": ("U1",)},
        },
        {
            "event_id": "evt-replace",
            "kind": "replacement",
            "parent_code": "BOARD-A",
            "old_snapshot": {"material_code": "MAT-F", "quantity": 1, "references": "D1"},
            "new_snapshot": {"material_code": "MAT-G", "quantity": 1, "references": "D1"},
        },
        {
            "event_id": "evt-qty",
            "kind": "quantity_changed",
            "parent_code": "BOARD-A",
            "old_snapshot": {"material_code": "MAT-H", "quantity": 1, "references": "J1"},
            "new_snapshot": {"material_code": "MAT-H", "quantity": 2, "references": "J1,J2"},
        },
    )

    result = build_oa_ecr_export(events, substitute_groups=(group,))
    by_event = {item.event_id: item for item in result.change_items if item.event_id != "evt-sub"}
    substitute_items = [item for item in result.change_items if item.event_id == "evt-sub"]

    assert len(substitute_items) == 2
    assert {item.change_type for item in substitute_items} == {OAChangeType.SUBSTITUTE}
    assert by_event["evt-add"].change_type == OAChangeType.ADD
    assert len(by_event["evt-add"].rows) == 1
    assert by_event["evt-delete"].change_type == OAChangeType.DELETE
    assert len(by_event["evt-delete"].rows) == 1
    assert by_event["evt-replace"].change_type == OAChangeType.REPLACE
    assert [row.material_code for row in by_event["evt-replace"].rows] == ["MAT-F", "MAT-G"]
    assert by_event["evt-qty"].change_type == OAChangeType.QUANTITY_REFERENCE_MODIFIED
    assert [row.references for row in by_event["evt-qty"].rows] == [("J1",), ("J1", "J2")]
    assert result.issues == ()


def test_export_accepts_exact_oa_change_labels_from_semantic_events() -> None:
    group = _three_member_group()
    result = build_oa_ecr_export(
        (
            BomChangeEvent(
                event_id="evt-sub-label",
                kind=ChangeKind.ALTERNATIVE_ADDED,
                parent_code="BOARD-A",
                title="Add substitute",
                impact=FunctionalImpact.SUPPLY,
                group_codes=("MAT-A",),
                oa_change_type="替代(AB共存)",
            ),
            BomChangeEvent(
                event_id="evt-replace-label",
                kind=ChangeKind.REPLACEMENT,
                parent_code="BOARD-A",
                title="Replace material",
                impact=FunctionalImpact.PLACEMENT,
                old_snapshot={"material_code": "OLD", "quantity": "1", "references": ["U1"]},
                new_snapshot={"material_code": "NEW", "quantity": "1", "references": ["U1"]},
                oa_change_type="更换(A换成B)",
            ),
        ),
        substitute_groups=(group,),
    )

    assert result.issues == ()
    assert {item.change_type for item in result.change_items} == {
        OAChangeType.SUBSTITUTE,
        OAChangeType.REPLACE,
    }


def test_invalid_substitute_group_is_reported_and_not_silently_exported() -> None:
    invalid = SubstituteGroup(
        parent_code="BOARD-A",
        group_code="MAT-A",
        main_item=None,
        alternative_items=(_item("MAT-B", 1, ()),),
        physical_references=(),
        quantity=Decimal("4"),
    )
    event = {
        "event_id": "evt-invalid",
        "kind": "alternative_added",
        "parent_code": "BOARD-A",
        "group_codes": ["MAT-A"],
    }

    result = build_oa_ecr_export((event,), substitute_groups=(invalid,))

    assert result.change_items == ()
    assert result.issues[0].code == "substitute_main_missing"
    assert result.issues[0].event_id == "evt-invalid"


def test_real_alternative_reference_blocks_export_but_the_60_placeholder_does_not() -> None:
    main = _item("MAT-A", 0, ("C1", "C2"), quantity="2")
    invalid = SubstituteGroup(
        parent_code="BOARD-A",
        group_code="MAT-A",
        main_item=main,
        alternative_items=(_item("MAT-B", 1, ("C3",), quantity="2"),),
        physical_references=main.references,
        quantity=Decimal("2"),
    )
    event = {
        "event_id": "evt-real-reference",
        "kind": "alternative_added",
        "parent_code": "BOARD-A",
        "group_codes": ["MAT-A"],
    }

    result = build_oa_ecr_export((event,), substitute_groups=(invalid,))

    assert result.change_items == ()
    assert result.issues[0].code == "substitute_alternative_has_references"


def test_payload_dictionary_group_uses_the_same_semantic_pairing_contract() -> None:
    group = {
        "parent_code": "BOARD-B",
        "group_code": "MAIN-1",
        "physical_references": "R1; R2",
        "main_item": {
            "material_code": "MAIN-1",
            "quantity": "2",
            "references": "R1,R2",
            "substitute_priority": 0,
        },
        "alternative_items": [
            {
                "material_code": "ALT-1",
                "quantity": "2",
                "references": "60",
                "substitute_priority": 1,
            },
        ],
    }

    (item,) = expand_substitute_group(group, event_id="evt-payload")

    assert item.parent_code == "BOARD-B"
    assert item.rows[0].references == ("R1", "R2")
    assert item.rows[1].references == ()
    assert item.rows[0].substitute_group_code == "MAIN-1"
    assert item.rows[1].substitute_group_code == "MAIN-1"
