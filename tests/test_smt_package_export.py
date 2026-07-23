from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook

from app.backend.tools.bom_decisions import load_decision_manifest
from app.backend.tools.bom_semantic_manifest import (
    load_semantic_manifest,
    write_semantic_manifest,
)
from app.backend.tools.smt_package import (
    _build_alternative_compatibility,
    _build_smt_package_review,
    run_smt_package_check,
)


def _bom_row(refs: list[str], part_number: str, package: str, name: str = "") -> dict[str, object]:
    return {
        "refs": refs,
        "part_number": part_number,
        "package": package,
        "model": package,
        "description": package,
        "name": name,
        "grade": "A",
    }


def _export_status(status: str) -> str:
    if status in {"通过", "近似通过"}:
        return "机器初筛通过"
    return status


def _semantic_inputs(tmp_path: Path) -> tuple[Path, Path]:
    bom = tmp_path / "processed.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "父项编码",
            "子项编码",
            "名称",
            "型号",
            "描述",
            "数量",
            "位号",
            "替代组编码",
            "替代优先级",
            "PCB Footprint",
        ]
    )
    sheet.append(["PCBA-1", "A", "电阻", "10K", "主料", 2, "R1,R2", "A", 0, "R0402"])
    sheet.append(["PCBA-1", "B", "电阻", "10K", "替代料", 2, "", "A", 1, "R0402"])
    workbook.save(bom)
    workbook.close()
    decisions = tmp_path / "decisions.json"
    decisions.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "rule_version": "2.0.0",
                "source_fingerprint": "source",
                "placements": [
                    {
                        "refs": ["R1", "R2"],
                        "destination": "smt",
                        "exclusion_kind": "",
                        "role": "electronic",
                        "subtype": "",
                        "decision_fingerprint": "installed",
                        "material_snapshot": {"part_number": "A"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    semantic = tmp_path / "semantic.json"
    write_semantic_manifest(
        semantic,
        bom,
        load_decision_manifest(decisions),
    )
    return bom, semantic


def test_export_rows_cover_all_review_items() -> None:
    parts = {
        "U1": "BGA153",
        "C1": "CAP_0402",
        "C2": "CAP_0603",
        "R1": "RES_0402",
        "U9": "NC",
        "TP1": "TEST_POINT",
    }
    bom_rows = [
        _bom_row(["U1"], "U.001", "BGA153", "eMMC"),
        _bom_row(["C1"], "C.001", "CAP_0402", "电容"),
        _bom_row(["C2"], "C.001", "CAP_0603", "电容"),
        _bom_row(["R99"], "R.099", "RES_0402", "电阻"),
    ]

    review = _build_smt_package_review(parts, bom_rows)

    item_projection = Counter(
        (str(item["ref"]), _export_status(str(item["status"])))
        for item in review["items"]
    )
    row_projection = Counter((str(row[0]), str(row[5])) for row in review["table_rows"])
    assert row_projection == item_projection


def test_export_row_preserves_review_item_details() -> None:
    review = _build_smt_package_review(
        {"U1": "BGA153"},
        [_bom_row(["U1"], "U.001", "BGA153", "eMMC")],
    )

    high_risk = next(item for item in review["items"] if item["status"] == "高风险封装")
    exported = next(row for row in review["table_rows"] if row[0] == "U1" and row[5] == "高风险封装")
    assert exported == [
        high_risk["ref"],
        high_risk["net_package"],
        high_risk["bom_package"] or high_risk["model"],
        high_risk["description"],
        high_risk["name"],
        high_risk["status"],
        high_risk["note"],
    ]


def test_alternative_compatibility_uses_main_references_without_counting_alternative(
    tmp_path: Path,
) -> None:
    _, semantic = _semantic_inputs(tmp_path)
    manifest = load_semantic_manifest(semantic)

    result = _build_alternative_compatibility(
        {"R1": "R0402", "R2": "R0402"},
        manifest,
    )

    assert result["summary"] == {"total": 1, "compatible": 1, "manual": 0}
    assert result["items"][0]["main_material_code"] == "A"
    assert result["items"][0]["alternative_material_code"] == "B"
    assert result["items"][0]["references"] == ["R1", "R2"]


def test_smt_package_semantic_mode_exports_alternative_report(tmp_path: Path) -> None:
    bom, semantic = _semantic_inputs(tmp_path)
    netlist = tmp_path / "netlist"
    netlist.mkdir()
    (netlist / "pstxprt.dat").write_text(
        "R1 'R0402'\nR2 'R0402'\n",
        encoding="utf-8",
    )

    result = run_smt_package_check(
        tmp_path,
        {
            "netlist": str(netlist),
            "bom": str(bom),
            "semantic_manifest": str(semantic),
        },
    )

    assert result["status"] == "ok"
    assert result["smt_package_review"]["semantic_manifest_used"] is True
    assert result["alternative_compatibility"]["summary"]["total"] == 1
    assert len(result["outputs"]) == 2
    assert all(Path(path).is_file() for path in result["outputs"])
