from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.backend.tools.bom_process import parse_source


REAL_BOMS = (
    (Path(r"D:\desktop\工具集\IAC4_MB_V05_20260507.xlsx"), 1037),
    (Path(r"D:\desktop\工具集\功耗版V2.xlsx"), 1315),
    (Path(r"D:\desktop\工具集\IAC3A_MB_V08_20250326.xlsx"), 1208),
)


def write_bom(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Item", "Quantity", "Reference", "Part Number", "Value", "PCB Footprint", "Source Part"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()


def test_item_quantity_and_provenance_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "source.xlsx"
    write_bom(path, [[7, 2, "R1，R2", "10000001", "10K", "R0402", "RES.Normal"]])

    parsed = parse_source(path)
    row = parsed.normalized_rows[0]

    assert row.value("item") == "7"
    assert row.quantity == "2"
    assert row.source_refs == ("R1", "R2")
    assert row.refs == ("R1", "R2")
    assert parsed.quality_report.payload()["issue_count"] == 0
    assert parsed.source_fingerprint


def test_reference_range_expands_only_when_quantity_verifies_it(tmp_path: Path) -> None:
    valid = tmp_path / "valid-range.xlsx"
    invalid = tmp_path / "invalid-range.xlsx"
    write_bom(valid, [[1, 3, "C1-C3", "10000001", "1uF", "C0402", "CAP.Normal"]])
    write_bom(invalid, [[1, 2, "C1-C3", "10000001", "1uF", "C0402", "CAP.Normal"]])

    valid_source = parse_source(valid)
    invalid_source = parse_source(invalid)

    assert valid_source.normalized_rows[0].refs == ("C1", "C2", "C3")
    assert invalid_source.normalized_rows[0].refs == ("C1-C3",)
    assert invalid_source.quality_report.payload()["code_counts"] == {
        "unexpanded_reference_range": 1,
        "quantity_mismatch": 1,
    }


def test_same_physical_reference_with_different_codes_is_blocking_quality_issue(tmp_path: Path) -> None:
    path = tmp_path / "conflicting-ref.xlsx"
    write_bom(path, [
        [1, 1, "U1", "10000001", "IC", "QFN", "IC.Normal"],
        [2, 1, "U1", "10000002", "IC", "QFN", "IC.Normal"],
    ])

    parsed = parse_source(path)

    assert parsed.quality_report.payload()["severity_counts"]["error"] == 1
    assert all("same_physical_ref_multiple_part_numbers" in row.physical_conflicts for row in parsed.normalized_rows)
    assert parsed.physical_parts[0].conflicts == ("same_physical_ref_multiple_part_numbers",)


@pytest.mark.parametrize(("path", "expected"), REAL_BOMS)
def test_real_bom_physical_reference_counts(path: Path, expected: int) -> None:
    if not path.is_file():
        pytest.skip(f"real BOM unavailable: {path}")

    parsed = parse_source(path)

    assert len(parsed.physical_parts) == expected
    assert parsed.quality_report.physical_part_count == expected
