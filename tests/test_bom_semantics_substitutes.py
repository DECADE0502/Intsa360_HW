from __future__ import annotations

import runpy
from pathlib import Path

from openpyxl import Workbook

from app.backend.bom_semantics.normalization import normalize_workbook
from app.backend.bom_semantics.substitutes import build_board_boms


BUILDER = Path(__file__).resolve().parent / "fixtures" / "bom_semantics" / "build_fixtures.py"


def _fixtures(tmp_path: Path) -> dict[str, Path]:
    return runpy.run_path(str(BUILDER))["build_all"](tmp_path)


def test_three_member_group_counts_only_main_references(tmp_path: Path) -> None:
    board = build_board_boms(normalize_workbook(_fixtures(tmp_path)["substitutes"]))[0]

    assert len(board.substitute_groups) == 1
    group = board.substitute_groups[0]
    assert group.main_item is not None
    assert group.main_item.material_code == "MAT-A"
    assert [item.material_code for item in group.alternative_items] == ["MAT-B", "MAT-C"]
    assert group.physical_references == ("C1", "C2", "C3", "C4")
    assert len(board.placements) == 4
    assert {item.material_code for item in board.placements} == {"MAT-A"}
    assert group.validation_findings == ()


def test_same_reference_on_different_parents_is_not_a_conflict(tmp_path: Path) -> None:
    path = _fixtures(tmp_path)["multi_parent"]
    source = normalize_workbook(path)
    numeric_row = next(row for row in source.rows if row.raw_reference == "72")
    resolved = normalize_workbook(
        path,
        reference_resolutions={numeric_row.source_id: "empty"},
    )
    boards = build_board_boms(resolved)

    assert len(boards) == 2
    assert sum(len(board.placements) for board in boards) == 2
    assert not any(
        finding.code == "reference_mapped_to_multiple_main_materials"
        for board in boards
        for finding in board.findings
    )


def test_blank_material_codes_do_not_collapse_unrelated_source_rows(tmp_path: Path) -> None:
    path = tmp_path / "blank-code.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["Reference", "Part Number", "Quantity", "Value"])
    worksheet.append(["H1", "", 1, "SC.DAX0501"])
    worksheet.append(["H2", "", 1, "SC.DAX0501"])
    workbook.save(path)
    workbook.close()

    board = build_board_boms(normalize_workbook(path))[0]

    blank_items = [item for item in board.items if not item.material_code]
    assert len(blank_items) == 2
    assert {item.references for item in blank_items} == {("H1",), ("H2",)}


def test_invalid_substitute_group_preserves_its_real_references(tmp_path: Path) -> None:
    path = tmp_path / "invalid-substitute-group.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(
        ["父项编码", "子项编码", "数量", "位号", "替代组编码", "替代优先级"]
    )
    worksheet.append(["BOARD", "MAT-A", 2, "R1,R2", "ALT-1", 2])
    workbook.save(path)
    workbook.close()

    board = build_board_boms(normalize_workbook(path))[0]

    assert {placement.reference for placement in board.placements} == {"R1", "R2"}
    assert {placement.material_code for placement in board.placements} == {"MAT-A"}
    assert {
        finding.code
        for finding in board.findings
    }.issuperset(
        {
            "substitute_main_count_invalid",
            "substitute_priority_not_continuous",
            "substitute_alternative_has_references",
        }
    )


def test_source_level_findings_are_not_duplicated_into_each_board(tmp_path: Path) -> None:
    source = normalize_workbook(_fixtures(tmp_path)["multi_parent"])
    boards = build_board_boms(source)

    assert any(item.code == "repeated_header_skipped" for item in source.findings)
    assert all(
        finding.parent_code
        for board in boards
        for finding in board.findings
    )
