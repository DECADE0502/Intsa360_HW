from __future__ import annotations

from pathlib import Path
from typing import Mapping

from app.backend.tools.bom_classify import (
    PlacementAnalysis,
    analyze_placement,
    apply_resolutions,
    load_classification_config,
)
from app.backend.tools.common import (
    USER_INPUT_EXCEPTIONS,
    _error,
    _output_dir,
    _required_file,
    _timestamp,
    _user_error,
)


def _find_plm_template(root: Path) -> Path | None:
    filename = "203010100819_ERP_BOM导入模板.xlsx"
    for candidate in (
        root / "tools" / "bom" / "templates" / filename,
        root / "templates" / filename,
    ):
        if candidate.is_file():
            return candidate
    return None


def _placement_review(
    analysis: PlacementAnalysis,
    message: str = "请完成装机审查后继续。",
) -> dict[str, object]:
    payload = analysis.payload()
    return {
        "status": "needs_confirmation",
        "tool": "bom_process",
        "reason": "placement_review",
        "schema_version": 1,
        "message": message,
        "groups": payload["groups"],
        "readonly_nc": payload["readonly_nc"],
        "summary": payload["summary"],
    }


def _legacy_placement_resolutions(
    analysis: PlacementAnalysis,
    params: Mapping[str, object],
) -> dict[str, object]:
    """Translate one release of legacy confirmation parameters into the unified contract."""

    resolutions: dict[str, object] = {}
    missing = params.get("missing_part_number_resolutions")
    missing_map = missing if isinstance(missing, Mapping) else {}
    process_keeps_raw = params.get("process_material_keeps")
    process_keeps = {
        str(value)
        for value in process_keeps_raw
        if str(value).strip()
    } if isinstance(process_keeps_raw, list) else set()
    has_process_decision = "confirm_process_materials" in params
    has_shield_decision = "confirm_shields" in params

    for group in analysis.review_groups:
        legacy_row_key = f"rows:{','.join(str(value) for value in group.row_numbers)}"
        old_missing = missing_map.get(legacy_row_key)
        if isinstance(old_missing, Mapping):
            resolutions[group.key] = {
                "action": str(old_missing.get("action") or ""),
                "part_number": str(old_missing.get("part_number") or ""),
                "field_patch": {
                    field: str(old_missing.get(field) or "")
                    for field in ("name", "model", "desc", "grade", "unit")
                },
            }
            continue
        if group.classification.sh_review and has_shield_decision:
            resolutions[group.key] = {
                "action": "keep" if bool(params.get("confirm_shields")) else "exclude",
                "part_number": group.inferred_fields.get("part_number", ""),
                "field_patch": {},
            }
            continue
        if group.classification.state == "suspected_process" and has_process_decision:
            code = group.inferred_fields.get("part_number", "")
            legacy_key = f"{code}|{','.join(group.refs)}"
            resolutions[group.key] = {
                "action": "keep" if legacy_key in process_keeps else "exclude",
                "part_number": code,
                "field_patch": {},
            }
    return resolutions


def _run_bom_process_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    from app.backend.tools import bom_process

    source, error = _required_file(params, "source_bom", "原始 BOM 文件")
    if error:
        return _error("bom_process", error)
    formats = params.get("formats") or ["plm", "oa"]
    if isinstance(formats, str):
        formats = [formats]
    formats = [value for value in formats if value in ("plm", "oa")] or ["plm"]
    extras = params.get("extras") if isinstance(params.get("extras"), list) else []
    out_dir = _output_dir(params, root, "bom")
    template = _find_plm_template(root)

    parsed = bom_process.parse_source(source)
    config = load_classification_config(root)
    analysis = analyze_placement(parsed.normalized_rows, config)

    raw_resolutions = params.get("placement_resolutions")
    if isinstance(raw_resolutions, Mapping):
        placement_resolutions: Mapping[str, object] = raw_resolutions
    else:
        placement_resolutions = _legacy_placement_resolutions(analysis, params)
    try:
        resolved, placement_summary = apply_resolutions(parsed, analysis, placement_resolutions)
    except ValueError as exc:
        return _placement_review(analysis, str(exc))

    source_rows, _ = bom_process.filter_rows(resolved)
    conflicts = bom_process.conflict_summary(source_rows)
    if conflicts and "merge_conflicts" not in params:
        return {
            "status": "needs_confirmation",
            "tool": "bom_process",
            "reason": "part_property_conflicts",
            "message": "发现相同物料编码存在不同型号、描述、名称、等级或单位，请选择推荐合并或逐项确认。",
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "placement_summary": placement_summary,
            "summary": {
                "conflicts": len(conflicts),
                "recommended_conflicts": sum(1 for conflict in conflicts if conflict.get("high_confidence")),
                "manual_conflicts": sum(1 for conflict in conflicts if not conflict.get("high_confidence")),
                "placement_review": placement_summary,
            },
        }
    merge_conflicts = bool(params.get("merge_conflicts"))
    conflict_choices = params.get("conflict_choices") if isinstance(params.get("conflict_choices"), dict) else {}
    unresolved_conflicts = (
        bom_process.unresolved_part_conflicts(source_rows, conflict_choices)
        if merge_conflicts
        else []
    )
    if unresolved_conflicts:
        return {
            "status": "needs_confirmation",
            "tool": "bom_process",
            "reason": "part_property_conflicts",
            "message": "部分冲突不能自动确认，必须逐项选择一个完整的原始候选。",
            "conflict_count": len(unresolved_conflicts),
            "conflicts": unresolved_conflicts,
            "placement_summary": placement_summary,
            "summary": {
                "conflicts": len(conflicts),
                "recommended_conflicts": sum(1 for conflict in conflicts if conflict.get("high_confidence")),
                "unresolved_conflicts": len(unresolved_conflicts),
                "placement_review": placement_summary,
            },
        }

    result = bom_process.process(
        parsed=resolved,
        formats=formats,
        parent_code=str(params.get("parent_code") or ""),
        parent_desc=str(params.get("parent_desc") or ""),
        name=str(params.get("name") or ""),
        extras=extras,
        out_dir=out_dir,
        stamp=_timestamp(),
        template=template,
        merge_conflicts=merge_conflicts,
        conflict_choices=conflict_choices,
        confirm_shields=True,
        process_material_keeps=set(),
        placement_summary=placement_summary,
    )
    outputs = [str(path) for path in result["outputs"]] + [str(result["nc_summary"])]
    preview_rows = [
        [
            record["code"],
            record["model"],
            record["desc"],
            record["qty"],
            ",".join(record["refs"]),
            record["grade"],
            ",".join(record.get("user_touched") or []),
        ]
        for record in result["records"]
    ]
    return {
        "status": "ok",
        "tool": "bom_process",
        "outputs": outputs,
        "summary": result["summary"],
        "preview": {
            "headers": ["编码", "型号", "描述", "数量", "位号", "等级", "人工修改"],
            "rows": preview_rows,
        },
        "process_file": str(result["outputs"][0]) if result["outputs"] else "",
        "next_step": "成品 BOM 已生成，请完成风险审查后再导入 PLM/OA。",
    }


def run_bom_process(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_bom_process_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("bom_process", exc)
