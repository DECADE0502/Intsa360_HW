from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from app.backend.smt_analysis.coordinates import default_coordinate_registry


def test_cadence_adapter_does_not_require_xy_filename(tmp_path: Path) -> None:
    path = tmp_path / "vendor-export.data"
    path.write_text(
        "VERSION=2.0\nUUNITS=MILS\nR1 ! 100 ! 200 ! 90 ! m ! R0402\n",
        encoding="utf-8",
    )
    registry = default_coordinate_registry()

    result = registry.parse_best(path)

    assert result.adapter_id == "cadence_xy_v1"
    assert result.normalized_unit == "mil"
    assert result.occurrences[0].normalized_x == 2.54
    assert result.occurrences[0].side == "bottom"


def test_tabular_unknown_units_are_not_silently_millimeters(tmp_path: Path) -> None:
    path = tmp_path / "coordinates.csv"
    path.write_text("Reference,X,Y,Side\nR1,1.5,2.5,Top\n", encoding="utf-8")
    registry = default_coordinate_registry()

    result = registry.parse_best(path)

    assert result.adapter_id == "tabular_coordinates_v1"
    assert result.unit_state == "unknown"
    assert result.normalized_unit is None
    assert result.occurrences[0].normalized_x is None
    assert any(issue.code == "coordinate_unit_unknown" for issue in result.quality_report.issues)


def test_tabular_numeric_side_is_unknown_without_mapping_evidence(tmp_path: Path) -> None:
    path = tmp_path / "coordinates.csv"
    path.write_text("Reference,X(mm),Y(mm),Side\nR1,1,2,1\nR2,3,4,2\n", encoding="utf-8")

    result = default_coordinate_registry().parse_best(path)

    assert [item.side for item in result.occurrences] == ["unknown", "unknown"]


def test_tabular_xlsx_discovers_coordinate_sheet(tmp_path: Path) -> None:
    path = tmp_path / "coordinates.xlsx"
    workbook = Workbook()
    cover = workbook.active
    cover.title = "说明"
    cover.append(["供应商导出"])
    data = workbook.create_sheet("Placement")
    data.append(["Designator", "X Coordinate (mm)", "Y Coordinate (mm)", "Rotation", "Layer"])
    data.append(["C1", 10.5, 20.5, 90, "Bottom"])
    workbook.save(path)
    workbook.close()

    registry = default_coordinate_registry()
    probes = registry.probes(path)
    result = registry.parse(path, probes[0])

    assert probes[0].sheet_or_section == "Placement"
    assert result.normalized_unit == "mm"
    assert result.occurrences[0].ref == "C1"
    assert result.occurrences[0].side == "bottom"


def test_duplicate_coordinate_refs_are_blocking(tmp_path: Path) -> None:
    path = tmp_path / "coordinates.csv"
    path.write_text("Reference,X(mm),Y(mm)\nR1,1,2\nR1,3,4\n", encoding="utf-8")

    result = default_coordinate_registry().parse_best(path)

    assert result.quality_report.duplicate_refs == ["R1"]
    assert any(issue.severity == "blocking" for issue in result.quality_report.issues)


def test_multiple_header_candidates_require_confirmation(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous.csv"
    path.write_text(
        "Reference,X(mm),Y(mm)\nR1,1,2\nReference,X(mm),Y(mm)\nR2,3,4\n",
        encoding="utf-8",
    )

    registry = default_coordinate_registry()
    probes = registry.probes(path)

    assert len(probes) == 2
