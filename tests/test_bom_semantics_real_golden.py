from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.backend.bom_semantics.normalization import normalize_workbook
from app.backend.bom_semantics.substitutes import build_board_boms
from app.backend.tools import bom_process
from app.backend.tools.bom_classify import (
    analyze_placement,
    load_classification_config,
)


GOLDEN_ROOT = os.environ.get("HWAGENT_BOM_GOLDEN_ROOT", "").strip()
SAMPLE_EXPECTATIONS = {
    "IAC4_MB_V05_20260507.xlsx": 1037,
    "功耗版V2.xlsx": 1315,
    "IAC3A_MB_V08_20250326.xlsx": 1208,
}


def _root() -> Path:
    if not GOLDEN_ROOT:
        pytest.skip("real BOM golden directory is not configured")
    root = Path(GOLDEN_ROOT)
    if not root.is_dir():
        pytest.skip("real BOM golden directory is not configured")
    return root


def _classification_by_ref(path: Path) -> dict[str, object]:
    parsed = bom_process.parse_source(path)
    analysis = analyze_placement(
        parsed.normalized_rows,
        load_classification_config(Path(__file__).resolve().parents[1]),
        source_fingerprint=parsed.source_fingerprint,
        quality_report=parsed.quality_report,
    )
    return {
        ref: item.classification
        for item in analysis.rows
        for ref in item.row.refs
    }


@pytest.mark.parametrize(("filename", "expected_references"), SAMPLE_EXPECTATIONS.items())
def test_real_capture_bom_preserves_every_physical_reference(
    filename: str,
    expected_references: int,
) -> None:
    source = normalize_workbook(_root() / filename)
    boards = build_board_boms(source)
    source_refs = {
        reference
        for row in source.rows
        for reference in row.references
    }
    installed_refs = {
        placement.reference
        for board in boards
        for placement in board.placements
    }
    excluded_refs = {
        reference
        for board in boards
        for item in board.non_placement_items
        for reference in item.references
    }

    assert len(boards) == 1
    assert len(source_refs) == expected_references
    assert installed_refs.isdisjoint(excluded_refs)
    assert installed_refs | excluded_refs == source_refs
    assert sum(len(board.placements) for board in boards) == len(installed_refs)


def test_iac4_mechanical_and_shield_rows_are_never_silently_removed() -> None:
    path = _root() / "IAC4_MB_V05_20260507.xlsx"
    classifications = _classification_by_ref(path)

    for ref in ("H1", "H2", "H3", "H4"):
        item = classifications[ref]
        assert item.state == "suspected_material"
        assert item.role == "smt_mechanical"
        assert item.recommended_action == "keep"
    assert classifications["SH1"].role == "shield"
    assert classifications["SH1"].state == "conflicting"
    assert classifications["SH1"].recommended_action is None


def test_power_board_process_symbols_and_mechanical_parts_keep_distinct_roles() -> None:
    path = _root() / "功耗版V2.xlsx"
    classifications = _classification_by_ref(path)

    assert len([ref for ref in classifications if ref.startswith("JP")]) == 178
    for ref in ("H1", "H2", "H3", "H4", "MTG5400", "MTG5401", "MTG5402", "MTG5403"):
        assert classifications[ref].state == "suspected_material"
        assert classifications[ref].role == "smt_mechanical"
    assert classifications["JP1"].state == "suspected_process"
    assert classifications["JP1"].role == "short_symbol"
    assert classifications["JP1"].suggested_destination == "non_smt"


def test_iac3_blank_code_materials_and_nc_remain_distinguishable() -> None:
    path = _root() / "IAC3A_MB_V08_20250326.xlsx"
    source = normalize_workbook(path)
    classifications = _classification_by_ref(path)
    rows_by_ref = {
        reference: row
        for row in source.rows
        for reference in row.references
    }

    for ref in ("D4", "D5", "LED1", "LED2", "LED3", "U16"):
        assert rows_by_ref[ref].material_code == ""
        assert rows_by_ref[ref].value
        assert classifications[ref].state == "suspected_material"
    assert rows_by_ref["D8"].is_nc is True
    assert classifications["D8"].state == "confirmed_nc"
    for ref in ("H1", "H2", "H4", "H5", "H6"):
        assert classifications[ref].state == "suspected_process"
        assert classifications[ref].role == "mounting_hole"
