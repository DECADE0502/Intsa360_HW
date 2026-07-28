from __future__ import annotations

from decimal import Decimal

from app.backend.bom_semantics.contracts import (
    BOM_COMPARE_SCHEMA_VERSION,
    CompareResult,
    CompareSummary,
)
from app.backend.bom_semantics.models import (
    BoardBOM,
    BomChangeEvent,
    CanonicalRow,
    ChangeKind,
    FindingSeverity,
    FunctionalImpact,
    MaterialItem,
    MaterialVariant,
    PhysicalPlacement,
    ValidationFinding,
    WorkbookProfile,
)


def test_contract_enums_are_stable() -> None:
    assert BOM_COMPARE_SCHEMA_VERSION == 2
    assert WorkbookProfile.PLM_SINGLE_BOARD.value == "plm_single_board"
    assert ChangeKind.MAIN_CHANGED_REFS_MIGRATED.value == "main_changed_refs_migrated"
    assert FindingSeverity.BLOCKER.value == "blocker"


def test_board_payload_keeps_identifier_text_and_decimal_quantity() -> None:
    row = CanonicalRow(
        source_id="src:sheet:3",
        sheet_name="BOM",
        row_number=3,
        parent_code="00123",
        material_code="00045",
        quantity=Decimal("4"),
        references=("C1", "C2", "C3", "C4"),
    )
    variant = MaterialVariant(material_code="00045", model="1uF", source_ids=(row.source_id,))
    item = MaterialItem(
        parent_code="00123",
        material_code="00045",
        quantity=Decimal("4"),
        references=row.references,
        variants=(variant,),
        source_rows=(row,),
    )
    board = BoardBOM(
        parent_code="00123",
        parent_description="Board",
        hardware_version="V1",
        rows=(row,),
        items=(item,),
        substitute_groups=(),
        placements=(
            PhysicalPlacement("00123", "C1", "00045", (row.source_id,)),
        ),
        non_placement_items=(),
        findings=(),
        source_fingerprint="fingerprint",
    )

    payload = board.payload()
    assert payload["parent_code"] == "00123"
    assert payload["items"][0]["material_code"] == "00045"
    assert payload["items"][0]["quantity"] == "4"


def test_compare_result_blocks_export_when_blocker_exists() -> None:
    blocker = ValidationFinding(
        code="duplicate_main",
        severity=FindingSeverity.BLOCKER,
        message="存在两个主料",
    )
    event = BomChangeEvent(
        event_id="event-1",
        kind=ChangeKind.SUBSTITUTE_STRUCTURE_INVALID,
        parent_code="BOARD",
        title="替代组结构错误",
        impact=FunctionalImpact.BLOCKER,
        blocker_reasons=("duplicate_main",),
    )
    result = CompareResult(
        analysis_fingerprint="analysis",
        old_source_fingerprint="old",
        new_source_fingerprint="new",
        summary=CompareSummary(
            blocker_count=1,
            blocking_record_count=1,
            changed_event_count=1,
            review_event_count=1,
            metadata_field_count=2,
        ),
        events=(event,),
        blockers=(blocker,),
    )

    assert result.can_export is False
    assert result.payload()["can_export"] is False
    assert result.payload()["events"][0]["kind"] == "substitute_structure_invalid"
    assert result.payload()["summary"]["blocking_record_count"] == 1
    assert result.payload()["summary"]["review_event_count"] == 1
    assert result.payload()["summary"]["metadata_field_count"] == 2
