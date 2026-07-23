from __future__ import annotations

from pathlib import Path

from app.backend.bom_semantics.alignment import (
    ComparisonScope,
    align_old_boards,
    resolve_comparison_scope,
)
from app.backend.bom_semantics.contracts import (
    BOM_COMPARE_SCHEMA_VERSION,
    BOM_SEMANTIC_MODEL_VERSION,
    SourceInspection,
)
from app.backend.bom_semantics.diff import compare_board_boms
from app.backend.bom_semantics.models import FindingSeverity, WorkbookProfile
from app.backend.bom_semantics.normalization import NormalizedSource, normalize_workbook
from app.backend.bom_semantics.oa_export import build_oa_ecr_export
from app.backend.bom_semantics.plm_export import export_plm_template
from app.backend.bom_semantics.report_export import export_compare_report
from app.backend.bom_semantics.serialization import write_compare_result_json
from app.backend.bom_semantics.substitutes import build_board_boms
from app.backend.parsers.refs import natural_key
from app.backend.tools.bom_rules import evaluate_bom_risks
from app.backend.tools.common import (
    USER_INPUT_EXCEPTIONS,
    _compare,
    _error,
    _jsonable,
    _output_dir,
    _read_bom_rows,
    _required_file,
    _result,
    _table,
    _timestamp,
    _to_qty,
    _user_error,
    _write_sheets,
)
def _index_by_ref(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """位号 -> 该位号上的元件（编号/型号/描述）。位号是板上物理位置，是对比的主轴。"""
    by_ref: dict[str, dict[str, object]] = {}
    for row in rows:
        for ref in row.get("refs") or []:
            by_ref[ref] = {
                "编号": row.get("part_number", ""),
                "型号": row.get("model", ""),
                "描述": row.get("description", ""),
            }
    return by_ref


def _part_usage(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """按编号统计用量：有位号者用量=位号数；无位号的整板/父项用量取数量列。"""
    parts: dict[str, dict[str, object]] = {}
    for row in rows:
        part_number = str(row.get("part_number") or "").strip()
        if not part_number:
            continue
        part = parts.setdefault(part_number, {"refs": set(), "model": "", "desc": "", "qty_field": 0, "has_ref": False})
        refs = row.get("refs") or []
        if refs:
            part["refs"].update(refs)
            part["has_ref"] = True
        part["qty_field"] += _to_qty(row.get("quantity"))
        if not part["model"] and row.get("model"):
            part["model"] = row["model"]
        if not part["desc"] and row.get("description"):
            part["desc"] = row["description"]
    return parts


def _usage_count(part: dict[str, object]) -> int:
    return len(part["refs"]) if part["has_ref"] else part["qty_field"]


def _annotate_origin(
    rows: list[dict[str, object]],
    ref_other: dict[str, dict[str, object]],
    parts_other: set[str],
    side: str,
) -> list[dict[str, object]]:
    """把另一份 BOM 的差异标注到“本份原始行”上：状态 + 该行需高亮的位号。"""
    annotated: list[dict[str, object]] = []
    for row in rows:
        part_number = str(row.get("part_number") or "")
        refs = row.get("refs") or []
        # 区分：换料（位号仍在，但换成别的料号）vs 位号在对面缺失
        swapped = [r for r in refs if r in ref_other and str(ref_other[r].get("编号", "")) != part_number]
        gone = [r for r in refs if r not in ref_other]
        changed = swapped + gone
        if not refs:
            status = ("removed" if side == "left" else "added") if part_number and part_number not in parts_other else "same"
        elif swapped:
            status = "swap"
        elif gone and len(gone) == len(refs) and part_number not in parts_other:
            status = "removed" if side == "left" else "added"
        elif gone:
            status = "changed"
        else:
            status = "same"
        annotated.append(
            {
                "cells": [
                    part_number,
                    row.get("model", ""),
                    row.get("description", ""),
                    _jsonable(row.get("quantity")),
                    row.get("reference", ""),
                ],
                "status": status,
                "changed_refs": changed,
            }
        )
    return annotated
def _run_legacy_bom_compare_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    bom1, error = _required_file(params, "bom1", "BOM1 文件")
    if error:
        return _error("bom_compare", error)
    bom2, error = _required_file(params, "bom2", "BOM2 文件")
    if error:
        return _error("bom_compare", error)

    rows1 = _read_bom_rows(bom1, require_refs=False)
    rows2 = _read_bom_rows(bom2, require_refs=False)

    # —— 主轴：按位号对比，自动识别 换料 / 新增 / 删除 / 一致 ——
    ref1 = _index_by_ref(rows1)
    ref2 = _index_by_ref(rows2)
    all_refs = sorted(set(ref1) | set(ref2), key=natural_key)

    pos_rows: list[list[object]] = []
    pos_items: list[dict[str, object]] = []
    status_counts = {"same": 0, "swap": 0, "added": 0, "removed": 0, "param": 0}
    changed = 0
    for ref in all_refs:
        left = ref1.get(ref)
        right = ref2.get(ref)
        diffs: list[str] = []
        if left and not right:
            status, kind, badge = "删除/未贴", "only_left", "删除"
            status_counts["removed"] += 1
        elif right and not left:
            status, kind, badge = "新增贴装", "only_right", "新增"
            status_counts["added"] += 1
        else:
            for field in ("编号", "型号", "描述"):
                if str(left.get(field, "")) != str(right.get(field, "")):
                    diffs.append(field)
            if "编号" in diffs:
                status, kind, badge = "换料", "diff", "换料"
                status_counts["swap"] += 1
            elif diffs:
                status, kind, badge = "参数差异", "diff", "参数差异"
                status_counts["param"] += 1
            else:
                status, kind, badge = "一致", "same", "一致"
                status_counts["same"] += 1
        if kind != "same":
            changed += 1
        pos_rows.append(
            [
                ref,
                status,
                left["编号"] if left else "",
                right["编号"] if right else "",
                left["型号"] if left else "",
                right["型号"] if right else "",
                left["描述"] if left else "",
                right["描述"] if right else "",
            ]
        )
        pos_items.append(
            {
                "key": ref,
                "status": status,
                "kind": kind,
                "badge": badge,
                "left": left,
                "right": right,
                "diff": diffs,
            }
        )

    # —— 辅助：料号用量变化（采购/ERP 视角，能识别换料替入/替出，而非孤立的新增/移除）——
    usage1 = _part_usage(rows1)
    usage2 = _part_usage(rows2)
    summary_rows: list[list[object]] = []
    for part_number in sorted(set(usage1) | set(usage2), key=natural_key):
        s1 = usage1[part_number]["refs"] if part_number in usage1 else set()
        s2 = usage2[part_number]["refs"] if part_number in usage2 else set()
        count1 = _usage_count(usage1[part_number]) if part_number in usage1 else 0
        count2 = _usage_count(usage2[part_number]) if part_number in usage2 else 0
        if s1 == s2 and count1 == count2:
            continue
        ref_part = usage1.get(part_number) or usage2.get(part_number)
        lost, gained = s1 - s2, s2 - s1
        out_targets = sorted({ref2[r]["编号"] for r in lost if r in ref2 and ref2[r]["编号"]})
        in_sources = sorted({ref1[r]["编号"] for r in gained if r in ref1 and ref1[r]["编号"]})

        if count1 == 0:  # 本份没有 -> 该料是新出现的
            if gained and all(r in ref1 for r in gained):
                change = "换料替入 ← " + (in_sources[0] if len(in_sources) == 1 else "多项")
            elif in_sources:
                change = "新增(部分替换)"
            else:
                change = "新增"
        elif count2 == 0:  # 本份有、对面没有 -> 该料消失
            if lost and all(r in ref2 for r in lost):
                change = "换料替出 → " + (out_targets[0] if len(out_targets) == 1 else "多项")
            elif out_targets:
                change = "移除(部分被替换)"
            else:
                change = "移除"
        else:  # 同料号、位号增减
            delta = count2 - count1
            change = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "位号变更"
        summary_rows.append([part_number, ref_part["model"], ref_part["desc"], count1, count2, change])

    pos_headers = ["位号", "状态", "BOM1编号", "BOM2编号", "BOM1型号", "BOM2型号", "BOM1描述", "BOM2描述"]
    sum_headers = ["编号", "型号", "描述", "BOM1数量", "BOM2数量", "变化"]
    output = _output_dir(params, root, "bom") / f"BOM差异报告_{_timestamp()}.xlsx"
    _write_sheets(output, [("位号对照", pos_headers, pos_rows), ("料号用量小结", sum_headers, summary_rows)])

    table = _table(pos_headers, pos_rows, status_col=1, diff_pairs=[[2, 3], [4, 5], [6, 7]])
    compare = _compare("位号", "BOM1", "BOM2", ["编号", "型号", "描述"], pos_items)
    part_summary = _table(sum_headers, summary_rows, status_col=5, diff_pairs=[[3, 4]])
    origin = {
        "left_label": "BOM1",
        "right_label": "BOM2",
        "columns": ["编号", "型号", "描述", "数量", "位号"],
        "ref_col": 4,
        "left_rows": _annotate_origin(rows1, ref2, set(usage2), "left"),
        "right_rows": _annotate_origin(rows2, ref1, set(usage1), "right"),
        "total_left": len(rows1),
        "total_right": len(rows2),
    }

    focus_priority = {"换料": 0, "删除/未贴": 1, "新增贴装": 2, "参数差异": 3}
    focus_items = sorted(
        [item for item in pos_items if item["kind"] != "same"],
        key=lambda item: (focus_priority.get(str(item.get("status")), 9), natural_key(str(item.get("key", "")))),
    )[:200]
    review_guide = {
        "换料": "重点确认同一位号的物料编码是否按设计变更替换，并回查型号、描述和替代关系。",
        "新增贴装": "确认是否为新增器件、原 NC 改贴或设计补料，必要时同步工艺和采购。",
        "删除/未贴": "确认是否为删除器件、改 NC/DNP 或漏导出，避免误删应贴物料。",
        "参数差异": "料号未变但型号/描述变化，通常用于确认库属性、规格描述和 PLM 元数据是否同步。",
        "料号用量": "从采购/ERP 视角核对每个编码的数量变化，识别替入、替出、新增和移除。",
    }

    result = _result(
        "bom_compare",
        [output],
        {
            "total_positions": len(all_refs),
            "changed_positions": changed,
            "part_changes": len(summary_rows),
            "status_counts": status_counts,
        },
        table,
        compare,
    )
    result["part_summary"] = part_summary
    result["focus_items"] = focus_items
    result["review_guide"] = review_guide
    result["origin"] = origin
    result["risks"] = {
        "left_label": "BOM1",
        "right_label": "BOM2",
        "left": evaluate_bom_risks(rows1),
        "right": evaluate_bom_risks(rows2),
    }
    return result


def _reference_resolutions(
    params: dict[str, object],
    source_key: str,
) -> dict[str, dict[str, object] | str]:
    raw = params.get("reference_resolutions")
    if not isinstance(raw, dict):
        return {}
    nested = raw.get(source_key)
    if isinstance(nested, dict):
        return {
            str(key): value
            for key, value in nested.items()
            if isinstance(value, (dict, str))
        }
    return {
        str(key): value
        for key, value in raw.items()
        if isinstance(value, (dict, str))
    }


def _normalized_source(
    path: Path,
    params: dict[str, object],
    source_key: str,
    *,
    default_parent_code: str = "",
) -> NormalizedSource:
    return normalize_workbook(
        path,
        reference_resolutions=_reference_resolutions(params, source_key),
        default_parent_code=default_parent_code,
    )


def _inspection(source: NormalizedSource) -> SourceInspection:
    boards = build_board_boms(source)
    findings = tuple(source.findings) + tuple(
        finding
        for board in boards
        for finding in board.findings
    )
    return SourceInspection(
        envelope=source.envelope,
        boards=boards,
        findings=findings,
        can_compare=not any(
            finding.severity == FindingSeverity.BLOCKER
            for finding in findings
        ),
    )


def _align_single_board_sources(
    old_path: Path,
    new_path: Path,
    params: dict[str, object],
) -> tuple[NormalizedSource, NormalizedSource]:
    old = _normalized_source(old_path, params, "bom1")
    new = _normalized_source(new_path, params, "bom2")
    old_boards = build_board_boms(old)
    new_boards = build_board_boms(new)
    if len(old_boards) != 1 or len(new_boards) != 1:
        return old, new

    old_capture = old.envelope.profile == WorkbookProfile.CAPTURE_RAW
    new_capture = new.envelope.profile == WorkbookProfile.CAPTURE_RAW
    if old_capture and new_capture:
        parent_code = "__CAPTURE_SINGLE_BOARD__"
        return (
            _normalized_source(old_path, params, "bom1", default_parent_code=parent_code),
            _normalized_source(new_path, params, "bom2", default_parent_code=parent_code),
        )
    if old_capture and not new_capture:
        parent_code = new_boards[0].parent_code
        return (
            _normalized_source(old_path, params, "bom1", default_parent_code=parent_code),
            new,
        )
    if new_capture and not old_capture:
        parent_code = old_boards[0].parent_code
        return (
            old,
            _normalized_source(new_path, params, "bom2", default_parent_code=parent_code),
        )
    return old, new


def _semantic_compare(
    old_path: Path,
    new_path: Path,
    params: dict[str, object],
):
    old_source, new_source = _align_single_board_sources(old_path, new_path, params)
    old_inspection = _inspection(old_source)
    new_inspection = _inspection(new_source)
    raw_mappings = params.get("parent_mappings")
    parent_mappings = (
        {
            str(old_parent): str(new_parent)
            for old_parent, new_parent in raw_mappings.items()
            if str(old_parent).strip() and str(new_parent).strip()
        }
        if isinstance(raw_mappings, dict)
        else {}
    )
    scope = resolve_comparison_scope(
        old_inspection.boards,
        new_inspection.boards,
        confirmed=params.get("scope_confirmation") is True,
        parent_mappings=parent_mappings,
    )
    if scope.needs_confirmation:
        return old_inspection, new_inspection, None, scope
    aligned_old_boards = align_old_boards(
        old_inspection.boards,
        scope.old_to_new,
    )
    result = compare_board_boms(
        aligned_old_boards,
        new_inspection.boards,
        old_source_fingerprint=old_source.envelope.source_fingerprint,
        new_source_fingerprint=new_source.envelope.source_fingerprint,
        additional_findings=(*old_source.findings, *new_source.findings),
    )
    return old_inspection, new_inspection, result, scope


def _semantic_summary(
    old_inspection: SourceInspection,
    new_inspection: SourceInspection,
    result: object,
) -> dict[str, object]:
    return {
        "analysis_fingerprint": result.analysis_fingerprint,
        "old_parent_codes": [board.parent_code for board in old_inspection.boards],
        "new_parent_codes": [board.parent_code for board in new_inspection.boards],
        "old_hardware_versions": [
            board.hardware_version for board in old_inspection.boards if board.hardware_version
        ],
        "new_hardware_versions": [
            board.hardware_version for board in new_inspection.boards if board.hardware_version
        ],
        "actual_reference_count_old": result.summary.actual_reference_count_old,
        "actual_reference_count_new": result.summary.actual_reference_count_new,
        "substitute_group_count_old": result.summary.substitute_group_count_old,
        "substitute_group_count_new": result.summary.substitute_group_count_new,
        "changed_event_count": result.summary.changed_event_count,
        "blocker_count": result.summary.blocker_count,
    }


def _compact_inspection_payload(inspection: SourceInspection) -> dict[str, object]:
    return {
        "envelope": {
            "profile": inspection.envelope.profile.value,
            "source_path": inspection.envelope.source_path,
            "source_fingerprint": inspection.envelope.source_fingerprint,
            "data_sheet": inspection.envelope.data_sheet,
        },
        "boards": [
            {
                "parent_code": board.parent_code,
                "parent_description": board.parent_description,
                "hardware_version": board.hardware_version,
                "placement_count": len(board.placements),
                "substitute_group_count": len(board.substitute_groups),
                "material_count": len(board.items),
            }
            for board in inspection.boards
        ],
        "findings": [finding.payload() for finding in inspection.findings],
        "can_compare": inspection.can_compare,
    }


def _scope_pending_response(
    old_inspection: SourceInspection,
    new_inspection: SourceInspection,
    scope: ComparisonScope,
) -> dict[str, object]:
    return {
        "status": "ok",
        "tool": "bom_compare",
        "schema_version": BOM_COMPARE_SCHEMA_VERSION,
        "model_version": BOM_SEMANTIC_MODEL_VERSION,
        "action": "compare",
        "message": "两份 BOM 的父项编码不同，请先确认比较范围。",
        "needs_scope_confirmation": True,
        "comparison_scope": scope.payload(),
        "source_inspections": {
            "old": _compact_inspection_payload(old_inspection),
            "new": _compact_inspection_payload(new_inspection),
        },
        "can_export": False,
        "outputs": [],
        "summary": {
            "semantic": {
                "old_parent_codes": [
                    board.parent_code for board in old_inspection.boards
                ],
                "new_parent_codes": [
                    board.parent_code for board in new_inspection.boards
                ],
                "comparison_scope_status": scope.status,
            }
        },
    }


def _run_inspect(params: dict[str, object]) -> dict[str, object]:
    source_path, error = _required_file(
        params,
        "source" if params.get("source") else "bom1",
        "待体检 BOM 文件",
    )
    if error or source_path is None:
        return _error("bom_compare", error or "缺少待体检 BOM 文件")
    source = _normalized_source(source_path, params, "source")
    inspection = _inspection(source)
    return {
        "status": "ok",
        "tool": "bom_compare",
        "schema_version": BOM_COMPARE_SCHEMA_VERSION,
        "model_version": BOM_SEMANTIC_MODEL_VERSION,
        "action": "inspect",
        "inspection": inspection.payload(),
        "summary": {
            "parent_codes": [board.parent_code for board in inspection.boards],
            "hardware_versions": [
                board.hardware_version for board in inspection.boards if board.hardware_version
            ],
            "actual_reference_count": sum(len(board.placements) for board in inspection.boards),
            "substitute_group_count": sum(
                len(board.substitute_groups) for board in inspection.boards
            ),
            "blocker_count": sum(
                1
                for finding in inspection.findings
                if finding.severity == FindingSeverity.BLOCKER
            ),
        },
        "outputs": [],
    }


def _run_semantic_compare(
    root: Path,
    params: dict[str, object],
    *,
    include_legacy: bool,
) -> dict[str, object]:
    bom1, error = _required_file(params, "bom1", "旧版 BOM 文件")
    if error or bom1 is None:
        return _error("bom_compare", error or "缺少旧版 BOM 文件")
    bom2, error = _required_file(params, "bom2", "新版 BOM 文件")
    if error or bom2 is None:
        return _error("bom_compare", error or "缺少新版 BOM 文件")

    old_inspection, new_inspection, semantic, scope = _semantic_compare(
        bom1,
        bom2,
        params,
    )
    if semantic is None:
        return _scope_pending_response(old_inspection, new_inspection, scope)
    output_dir = _output_dir(params, root, "bom_compare")
    timestamp = _timestamp()
    json_output = write_compare_result_json(
        semantic,
        output_dir / f"BOM语义对比_{timestamp}.json",
    )
    report_output = export_compare_report(
        semantic,
        output_dir / f"BOM四层差异报告_{timestamp}.xlsx",
    )

    if include_legacy:
        legacy = _run_legacy_bom_compare_impl(root, params)
    else:
        legacy = _result("bom_compare", [], {}, None, None)
    legacy["schema_version"] = BOM_COMPARE_SCHEMA_VERSION
    legacy["model_version"] = BOM_SEMANTIC_MODEL_VERSION
    legacy["action"] = "compare"
    legacy["semantic"] = semantic.payload()
    legacy["source_inspections"] = {
        "old": _compact_inspection_payload(old_inspection),
        "new": _compact_inspection_payload(new_inspection),
    }
    legacy["needs_scope_confirmation"] = False
    legacy["comparison_scope"] = scope.payload()
    legacy["can_export"] = semantic.can_export
    legacy["outputs"] = list(dict.fromkeys([
        *legacy.get("outputs", []),
        str(report_output),
        str(json_output),
    ]))
    summary = legacy.setdefault("summary", {})
    if isinstance(summary, dict):
        summary["semantic"] = _semantic_summary(
            old_inspection,
            new_inspection,
            semantic,
        )
    return legacy


def _write_oa_payload(payload: object, path: Path) -> Path:
    import json

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _run_export(root: Path, params: dict[str, object]) -> dict[str, object]:
    bom1, error = _required_file(params, "bom1", "旧版 BOM 文件")
    if error or bom1 is None:
        return _error("bom_compare", error or "缺少旧版 BOM 文件")
    bom2, error = _required_file(params, "bom2", "新版 BOM 文件")
    if error or bom2 is None:
        return _error("bom_compare", error or "缺少新版 BOM 文件")
    old_inspection, new_inspection, semantic, scope = _semantic_compare(
        bom1,
        bom2,
        params,
    )
    if semantic is None:
        return {
            "status": "error",
            "tool": "bom_compare",
            "schema_version": BOM_COMPARE_SCHEMA_VERSION,
            "model_version": BOM_SEMANTIC_MODEL_VERSION,
            "action": "export",
            "error": "两份 BOM 的父项编码不同，请先在对比页面确认比较范围。",
            "needs_scope_confirmation": True,
            "comparison_scope": scope.payload(),
            "outputs": [],
        }
    output_dir = _output_dir(params, root, "bom_compare")
    timestamp = _timestamp()
    export_format = str(params.get("format") or "report").strip().casefold()
    outputs: list[Path] = []

    if export_format in {"report", "xlsx"}:
        outputs.append(
            export_compare_report(
                semantic,
                output_dir / f"BOM四层差异报告_{timestamp}.xlsx",
            )
        )
    elif export_format == "json":
        outputs.append(
            write_compare_result_json(
                semantic,
                output_dir / f"BOM语义对比_{timestamp}.json",
            )
        )
    elif export_format == "plm":
        template, template_error = _required_file(params, "template", "PLM 模板")
        if template_error or template is None:
            return _error("bom_compare", template_error or "缺少 PLM 模板")
        side = str(params.get("side") or "new").casefold()
        boards = old_inspection.boards if side == "old" else new_inspection.boards
        exported = export_plm_template(
            boards,
            template,
            output_dir / f"BOM_PLM_{side}_{timestamp}.xlsx",
        )
        outputs.append(exported.output_path)
    elif export_format in {"oa", "ecr"}:
        new_groups = tuple(
            group
            for board in new_inspection.boards
            for group in board.substitute_groups
        )
        oa = build_oa_ecr_export(semantic.events, substitute_groups=new_groups)
        if not oa.can_export:
            return {
                "status": "error",
                "tool": "bom_compare",
                "error": "OA/ECR 导出存在未解决语义问题。",
                "issues": [issue.payload() for issue in oa.issues],
            }
        outputs.append(
            _write_oa_payload(
                oa.payload(),
                output_dir / f"BOM_OA_ECR_{timestamp}.json",
            )
        )
    else:
        return _error("bom_compare", f"不支持的导出格式：{export_format}")

    return {
        "status": "ok",
        "tool": "bom_compare",
        "schema_version": BOM_COMPARE_SCHEMA_VERSION,
        "model_version": BOM_SEMANTIC_MODEL_VERSION,
        "action": "export",
        "format": export_format,
        "comparison_scope": scope.payload(),
        "outputs": [str(path) for path in outputs],
        "summary": {
            "semantic": _semantic_summary(old_inspection, new_inspection, semantic),
        },
    }


def run_bom_compare(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        action = str(params.get("action") or "compare").strip().casefold()
        if action == "inspect":
            return _run_inspect(params)
        if action == "export":
            return _run_export(root, params)
        if action != "compare":
            return _error("bom_compare", f"不支持的操作：{action}")
        return _run_semantic_compare(root, params, include_legacy=True)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("bom_compare", exc)
