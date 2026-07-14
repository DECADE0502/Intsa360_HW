from __future__ import annotations

from pathlib import Path

from app.backend.tools.common import (
    USER_INPUT_EXCEPTIONS,
    _error,
    _output_dir,
    _required_file,
    _timestamp,
    _user_error,
)
def _run_bom_process_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    from app.backend.tools import bom_process

    source, error = _required_file(params, "source_bom", "原始 BOM 文件")
    if error:
        return _error("bom_process", error)
    formats = params.get("formats") or ["plm", "oa"]
    if isinstance(formats, str):
        formats = [formats]
    formats = [f for f in formats if f in ("plm", "oa")] or ["plm"]
    extras = params.get("extras") if isinstance(params.get("extras"), list) else []
    out_dir = _output_dir(params, root, "bom")
    template = next(root.rglob("203010100819_ERP_BOM导入模板.xlsx"), None)
    source_rows_for_checks, _ = bom_process.load_source(source, include_shields=True)
    shield_candidates = bom_process.detect_shield_candidates(source_rows_for_checks)
    if shield_candidates and "confirm_shields" not in params:
        return {
            "status": "needs_confirmation",
            "tool": "bom_process",
            "reason": "shield_bracket_candidates",
            "message": "发现 SH 位号物料，疑似屏蔽支架。请确认是否作为结构件进入最终 BOM。",
            "shield_count": len(shield_candidates),
            "shield_candidates": shield_candidates,
            "summary": {"shield_candidates": len(shield_candidates)},
        }
    confirm_shields = bool(params.get("confirm_shields"))
    source_rows, _ = bom_process.load_source(source, include_shields=confirm_shields)
    conflicts = bom_process.conflict_summary(source_rows)
    if conflicts and "merge_conflicts" not in params:
        return {
            "status": "needs_confirmation",
            "tool": "bom_process",
            "reason": "part_property_conflicts",
            "message": "发现相同物料编码存在不同型号/描述/名称/等级/单位，请选择推荐合并或逐项确认。",
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "summary": {
                "conflicts": len(conflicts),
                "recommended_conflicts": sum(1 for conflict in conflicts if conflict.get("high_confidence")),
                "manual_conflicts": sum(1 for conflict in conflicts if not conflict.get("high_confidence")),
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
            "message": "推荐合并只处理高置信冲突；其余物料必须逐项选择一个完整的原始候选。",
            "conflict_count": len(unresolved_conflicts),
            "conflicts": unresolved_conflicts,
            "summary": {
                "conflicts": len(conflicts),
                "recommended_conflicts": sum(1 for conflict in conflicts if conflict.get("high_confidence")),
                "unresolved_conflicts": len(unresolved_conflicts),
            },
        }
    result = bom_process.process(
        source,
        formats,
        str(params.get("parent_code") or ""),
        str(params.get("parent_desc") or ""),
        str(params.get("name") or ""),
        extras,
        out_dir,
        _timestamp(),
        template,
        merge_conflicts,
        conflict_choices,
        confirm_shields,
    )
    outputs = [str(p) for p in result["outputs"]] + [str(result["nc_summary"])]
    preview_rows = [
        [r["code"], r["model"], r["desc"], r["qty"], ",".join(r["refs"]), r["grade"]]
        for r in result["records"]
    ]
    return {
        "status": "ok",
        "tool": "bom_process",
        "outputs": outputs,
        "summary": result["summary"],
        "preview": {"headers": ["编号", "型号", "描述", "数量", "位号", "等级"], "rows": preview_rows},
        "process_file": str(result["outputs"][0]) if result["outputs"] else "",
        "next_step": "成品 BOM 已生成，请核对后走 OA YF25 备料 / PLM 导入。",
    }
def run_bom_process(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_bom_process_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("bom_process", exc)
