from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.backend.tools.bom_decisions import load_decision_manifest
from app.backend.tools.bom_semantic_manifest import (
    load_semantic_manifest,
    write_semantic_manifest,
)


def _write_processed_bom(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "父项编码",
            "子项编码",
            "名称",
            "型号",
            "描述",
            "单位",
            "数量",
            "位号",
            "替代组编码",
            "替代优先级",
            "PCB Footprint",
        ]
    )
    sheet.append(["PCBA-1", "A", "电阻", "10K", "主料", "pcs", 2, "R1,R2", "A", 0, "R0402"])
    sheet.append(["PCBA-1", "B", "电阻", "10K", "替代料", "pcs", 2, "", "A", 1, "R0402"])
    workbook.save(path)
    workbook.close()


def _write_decisions(path: Path, *, smt_refs: list[str] | None = None) -> None:
    refs = smt_refs or ["R1", "R2"]
    placements = [
        {
            "refs": refs,
            "destination": "smt",
            "exclusion_kind": "",
            "role": "electronic",
            "subtype": "",
            "decision_fingerprint": "installed",
            "material_snapshot": {
                "part_number": "A",
                "model": "10K",
                "desc": "主料",
                "name": "电阻",
                "pcb_footprint": "R0402",
            },
        },
        {
            "refs": ["TP1"],
            "destination": "non_smt",
            "exclusion_kind": "process_only",
            "role": "test_point",
            "subtype": "",
            "decision_fingerprint": "process",
            "material_snapshot": {"part_number": "TP-PN"},
        },
    ]
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "rule_version": "2.0.0",
                "source_fingerprint": "capture-source",
                "placements": placements,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_semantic_manifest_uses_only_main_material_references(tmp_path: Path) -> None:
    bom = tmp_path / "processed.xlsx"
    decisions = tmp_path / "decisions.json"
    output = tmp_path / "semantic.json"
    _write_processed_bom(bom)
    _write_decisions(decisions)

    write_semantic_manifest(
        output,
        bom,
        load_decision_manifest(decisions),
    )
    manifest = load_semantic_manifest(output)

    assert set(manifest.installed_by_ref()) == {"R1", "R2"}
    assert manifest.installed_by_ref()["R1"]["material_code"] == "A"
    assert set(manifest.non_smt_by_ref()) == {"TP1"}
    assert manifest.summary["actual_reference_count"] == 2
    assert manifest.summary["alternative_material_count"] == 1
    assert manifest.alternative_items()[0]["material_code"] == "B"
    assert manifest.alternative_items()[0]["references"] == []


def test_semantic_manifest_rejects_divergent_smt_decisions(tmp_path: Path) -> None:
    bom = tmp_path / "processed.xlsx"
    decisions = tmp_path / "decisions.json"
    output = tmp_path / "semantic.json"
    _write_processed_bom(bom)
    _write_decisions(decisions, smt_refs=["R1", "R3"])

    with pytest.raises(ValueError, match="R2|R3"):
        write_semantic_manifest(
            output,
            bom,
            load_decision_manifest(decisions),
        )


def test_semantic_manifest_round_trip_preserves_substitute_group(tmp_path: Path) -> None:
    bom = tmp_path / "processed.xlsx"
    decisions = tmp_path / "decisions.json"
    output = tmp_path / "semantic.json"
    _write_processed_bom(bom)
    _write_decisions(decisions)

    write_semantic_manifest(output, bom, load_decision_manifest(decisions))
    payload = json.loads(output.read_text(encoding="utf-8"))
    manifest = load_semantic_manifest(output)

    assert payload["manifest_kind"] == "bom_process_semantic_manifest"
    assert payload["boards"][0]["substitute_groups"][0]["group_code"] == "A"
    assert manifest.substitute_groups()[0]["physical_references"] == ["R1", "R2"]
