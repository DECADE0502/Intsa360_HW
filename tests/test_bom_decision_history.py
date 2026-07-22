from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from app.backend import history
from app.backend.tools.bom_process_adapter import run_bom_process


def write_shield(path: Path, description: str = "屏蔽支架") -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Item", "Quantity", "Reference", "Part Number", "Value", "Description", "Name", "PCB Footprint"])
    sheet.append([1, 1, "SH1", "MAT-1001", "SHIELD", description, "屏蔽件", "SHIELD_FIX"])
    workbook.save(path)
    workbook.close()


def bracket_resolution(group: dict[str, object]) -> dict[str, object]:
    return {
        "destination": "smt",
        "exclusion_kind": "",
        "role": "shield",
        "subtype": "bracket",
        "part_number_override": "MAT-1001",
        "field_patch": {},
        "decision_source": "user",
    }


def test_exact_history_is_reused_but_changed_attributes_only_show_hint(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    write_shield(source)
    params: dict[str, object] = {"source_bom": str(source), "formats": ["plm"], "name": "HISTORY"}

    review = run_bom_process(tmp_path, params)
    group = review["groups"][0]
    completed_params = {**params, "placement_resolutions": {group["group_id"]: bracket_resolution(group)}}
    completed = run_bom_process(tmp_path, completed_params)
    assert completed["status"] == "ok"
    history.record(tmp_path, "bom_process", "BOM 处理", completed_params, completed)

    replay = run_bom_process(tmp_path, params)
    assert replay["status"] == "ok"
    assert replay["decisions"]["placements"][0]["decision_source"] == "history_exact"

    write_shield(source, "屏蔽结构件，属性已变更")
    changed = run_bom_process(tmp_path, params)
    assert changed["status"] == "needs_confirmation"
    assert changed["groups"][0]["history_hint"]["previous_destination"] == "smt"
    assert "history_exact_resolution" not in changed["groups"][0]


def test_current_user_resolution_overrides_exact_history(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    write_shield(source)
    params: dict[str, object] = {"source_bom": str(source), "formats": ["plm"], "name": "OVERRIDE"}
    review = run_bom_process(tmp_path, params)
    group = review["groups"][0]
    completed_params = {**params, "placement_resolutions": {group["group_id"]: bracket_resolution(group)}}
    completed = run_bom_process(tmp_path, completed_params)
    history.record(tmp_path, "bom_process", "BOM 处理", completed_params, completed)

    cover = {
        "destination": "non_smt",
        "exclusion_kind": "scope_excluded",
        "role": "shield",
        "subtype": "cover",
        "part_number_override": "MAT-1001",
        "field_patch": {},
        "decision_source": "user",
    }
    overridden = run_bom_process(tmp_path, {**params, "placement_resolutions": {group["group_id"]: cover}})

    assert overridden["status"] == "ok"
    decision = overridden["decisions"]["placements"][0]
    assert decision["decision_source"] == "user"
    assert decision["destination"] == "non_smt"
    assert decision["subtype"] == "cover"
