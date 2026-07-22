from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from app.backend.tools.bom_decisions import load_decision_manifest
from app.backend.tools.bom_process_adapter import run_bom_process


def _write(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([
        "Reference",
        "Part Number",
        "Value",
        "规格型号",
        "器件描述（新整理）",
        "物料名称",
        "PCB Footprint",
        "Source Part",
    ])
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()


def test_multi_occurrence_part_has_one_physical_decision(tmp_path: Path) -> None:
    source = tmp_path / "multi-unit.xlsx"
    _write(source, [
        ["U1", "IC-1001", "SOC", "A1", "主芯片", "芯片", "BGA", "SOC.Normal"],
        ["U1", "IC-1001", "SOC", "A1", "主芯片", "处理器", "BGA", "SOC.Normal"],
    ])

    params: dict[str, object] = {
        "source_bom": str(source),
        "formats": ["plm", "oa"],
        "name": "MULTI",
    }
    review = run_bom_process(tmp_path, params)
    assert review["reason"] == "part_property_conflicts"
    result = run_bom_process(tmp_path, {
        **params,
        "merge_conflicts": True,
        "conflict_choices": {
            "IC-1001": {"action": "select_variant", "variant_index": 0},
        },
    })

    assert result["status"] == "ok"
    manifest = load_decision_manifest(Path(result["decision_manifest"]))
    assert len(manifest.placements) == 1
    assert manifest.placements[0]["refs"] == ["U1"]
    assert manifest.placements[0]["destination"] == "smt"


def test_selected_conflict_variant_is_recorded_as_a_user_decision(tmp_path: Path) -> None:
    source = tmp_path / "conflict.xlsx"
    _write(source, [
        ["R1", "RES-1001", "10K", "R0402-A", "10K 电阻", "电阻", "R0402", "RES.Normal"],
        ["R2", "RES-1001", "22K", "R0402-B", "22K 电阻", "电阻", "R0402", "RES.Normal"],
    ])
    params: dict[str, object] = {
        "source_bom": str(source),
        "formats": ["plm"],
        "name": "CONFLICT",
    }
    review = run_bom_process(tmp_path, params)
    assert review["reason"] == "part_property_conflicts"

    result = run_bom_process(tmp_path, {
        **params,
        "merge_conflicts": True,
        "conflict_choices": {
            "RES-1001": {"action": "select_variant", "variant_index": 0},
        },
    })

    assert result["status"] == "ok"
    manifest = load_decision_manifest(Path(result["decision_manifest"]))
    assert {item["decision_source"] for item in manifest.placements} == {"user"}
    assert set(manifest.by_ref()) == {"R1", "R2"}
