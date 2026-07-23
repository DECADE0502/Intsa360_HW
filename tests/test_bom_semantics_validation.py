from __future__ import annotations

from decimal import Decimal

from app.backend.bom_semantics.models import CanonicalRow, MaterialItem, MaterialVariant
from app.backend.bom_semantics.validation import validate_substitute_members


def _item(
    code: str,
    priority: int,
    quantity: str,
    refs: tuple[str, ...],
    *,
    strategy: str = "",
    mode: str = "",
) -> MaterialItem:
    row = CanonicalRow(
        source_id=f"source:{code}",
        sheet_name="BOM",
        row_number=priority + 3,
        parent_code="BOARD",
        material_code=code,
        quantity=Decimal(quantity),
        references=refs,
        substitute_group_code="MAT-A",
        substitute_strategy=strategy,
        substitute_mode=mode,
        substitute_priority=priority,
        raw_fields={
            "substitute_strategy": strategy,
            "substitute_mode": mode,
        },
    )
    return MaterialItem(
        parent_code="BOARD",
        material_code=code,
        quantity=Decimal(quantity),
        references=refs,
        variants=(MaterialVariant(material_code=code),),
        source_rows=(row,),
        substitute_group_code="MAT-A",
        substitute_priority=priority,
    )


def test_validation_blocks_priority_gap_quantity_mismatch_and_alternative_refs() -> None:
    findings = validate_substitute_members(
        "BOARD",
        "MAT-A",
        (
            _item("MAT-A", 0, "2", ("C1", "C2")),
            _item("MAT-B", 2, "3", ("C3",)),
        ),
    )
    codes = {finding.code for finding in findings}

    assert "substitute_priority_not_continuous" in codes
    assert "substitute_quantity_mismatch" in codes
    assert "substitute_alternative_has_references" in codes


def test_validation_blocks_missing_substitute_strategy_and_mode() -> None:
    findings = validate_substitute_members(
        "BOARD",
        "MAT-A",
        (
            _item(
                "MAT-A",
                0,
                "2",
                ("C1", "C2"),
                strategy="可替代",
                mode="替代",
            ),
            _item("MAT-B", 1, "2", ()),
        ),
    )
    codes = {finding.code for finding in findings}

    assert "substitute_strategy_missing" in codes
    assert "substitute_mode_missing" in codes
