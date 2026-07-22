from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.backend.tools import bom_process
from app.backend.tools.bom_process_adapter import run_bom_process


def write_conflict(path: Path, rows: list[list[object]], headers: list[str] | None = None) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or [
        "Reference",
        "Part Number",
        "Value",
        "Model",
        "Description",
        "Name",
        "PCB Footprint",
        "PCB封装",
        "Manufacturer",
        "等级",
        "Unit",
    ])
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()


@pytest.mark.parametrize(
    ("field_index", "left", "right", "reason"),
    [
        (2, "1uF", "2.2uF", "numeric_or_version_conflict"),
        (6, "C0402", "C0603", "footprint_conflict"),
        (8, "VENDOR-A", "VENDOR-B", "model_or_manufacturer_conflict"),
        (9, "正常", "优选", "grade_conflict"),
    ],
)
def test_sensitive_conflict_fields_never_auto_merge(
    tmp_path: Path,
    field_index: int,
    left: str,
    right: str,
    reason: str,
) -> None:
    base = ["R1", "MAT-1", "10K", "R0402", "电阻", "电阻", "R0402", "R0402", "VENDOR", "正常", "ea"]
    first = list(base)
    second = list(base)
    second[0] = "R2"
    first[field_index] = left
    second[field_index] = right
    path = tmp_path / "conflict.xlsx"
    write_conflict(path, [first, second])

    rows, _ = bom_process.load_source(path)
    conflict = bom_process.detect_part_conflicts(rows)[0]

    assert conflict["reason"] == reason
    assert conflict["high_confidence"] is False
    assert conflict["recommended_index"] is None


def test_case_whitespace_and_punctuation_only_difference_is_safe(tmp_path: Path) -> None:
    path = tmp_path / "cosmetic.xlsx"
    write_conflict(path, [
        ["R1", "MAT-1", "10K", "ABC-123", "Chip resistor", "RESISTOR", "R0402", "R0402", "VENDOR", "正常", "EA"],
        ["R2", "MAT-1", "10K", "abc 123", "chip-resistor", "resistor", "R0402", "R0402", "vendor", "正常", "ea"],
    ])

    rows, _ = bom_process.load_source(path)
    conflict = bom_process.detect_part_conflicts(rows)[0]

    assert conflict["reason"] == "cosmetic_equivalence"
    assert conflict["high_confidence"] is True


def test_split_variants_assigns_new_codes_without_synthesizing_fields(tmp_path: Path) -> None:
    source = tmp_path / "split.xlsx"
    write_conflict(source, [
        ["R1", "MAT-1", "10K", "R0402-A", "描述 A", "电阻", "R0402", "R0402", "VENDOR", "正常", "ea"],
        ["R2", "MAT-1", "22K", "R0402-B", "描述 B", "电阻", "R0402", "R0402", "VENDOR", "正常", "ea"],
    ])
    review = run_bom_process(tmp_path, {"source_bom": str(source), "formats": ["plm"], "name": "SPLIT"})
    assert review["reason"] == "part_property_conflicts"

    completed = run_bom_process(tmp_path, {
        "source_bom": str(source),
        "formats": ["plm"],
        "name": "SPLIT",
        "merge_conflicts": True,
        "conflict_choices": {
            "MAT-1": {
                "action": "split_refs",
                "assignments": [
                    {"variant_index": 0, "part_number": "MAT-1-A"},
                    {"variant_index": 1, "part_number": "MAT-1-B"},
                ],
            },
        },
    })

    assert completed["status"] == "ok"
    preview = {row[0]: row for row in completed["preview"]["rows"]}
    assert set(preview) == {"MAT-1-A", "MAT-1-B"}
    assert preview["MAT-1-A"][1:3] == ["R0402-A", "描述 A"]
    assert preview["MAT-1-B"][1:3] == ["R0402-B", "描述 B"]


def test_variant_can_move_to_non_smt_and_leave_one_material_variant(tmp_path: Path) -> None:
    source = tmp_path / "move.xlsx"
    write_conflict(source, [
        ["R1", "MAT-1", "10K", "R0402", "贴片电阻", "电阻", "R0402", "R0402", "VENDOR", "正常", "ea"],
        ["R2", "MAT-1", "22K", "R0603", "辅助变体", "电阻", "R0603", "R0603", "VENDOR", "正常", "ea"],
    ])
    completed = run_bom_process(tmp_path, {
        "source_bom": str(source),
        "formats": ["plm"],
        "name": "MOVE",
        "merge_conflicts": True,
        "conflict_choices": {
            "MAT-1": {
                "action": "move_non_smt",
                "variant_indices": [1],
                "exclusion_kind": "scope_excluded",
            },
        },
    })

    assert completed["status"] == "ok"
    assert completed["summary"]["records"] == 1
    assert completed["preview"]["rows"][0][4] == "R1"


def test_return_to_capture_is_never_treated_as_a_resolution(tmp_path: Path) -> None:
    source = tmp_path / "return.xlsx"
    write_conflict(source, [
        ["R1", "MAT-1", "10K", "R0402", "描述 A", "电阻", "R0402", "R0402", "VENDOR", "正常", "ea"],
        ["R2", "MAT-1", "22K", "R0402", "描述 B", "电阻", "R0402", "R0402", "VENDOR", "正常", "ea"],
    ])

    result = run_bom_process(tmp_path, {
        "source_bom": str(source),
        "formats": ["plm"],
        "name": "RETURN",
        "merge_conflicts": True,
        "conflict_choices": {"MAT-1": {"action": "return_to_capture"}},
    })

    assert result["status"] == "needs_confirmation"
    assert result["reason"] == "part_property_conflicts"
