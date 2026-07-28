from __future__ import annotations

from pathlib import Path

from app.backend.tools import bom_process
from app.backend.tools.bom_decisions import load_decision_manifest
from app.backend.tools.bom_risk_model import build_risk_model
from app.backend.tools.bom_rules import (
    evaluate_bom_risk_report,
    load_risk_rule_config,
)
from app.backend.tools.bom_semantic_manifest import load_semantic_manifest
from app.backend.tools.common import (
    USER_INPUT_EXCEPTIONS,
    _error,
    _jsonable,
    _output_dir,
    _read_bom_rows,
    _required_file,
    _result,
    _timestamp,
    _user_error,
    _write_sheets,
    _write_table,
)


def _sheet_rows(
    items: list[dict[str, object]],
    fields: list[tuple[str, str]],
) -> tuple[list[str], list[list[object]]]:
    return (
        [label for _, label in fields],
        [[_jsonable(item.get(key)) for key, _ in fields] for item in items],
    )


def _run_bom_risk_check_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    bom, error = _required_file(params, "bom", "BOM 文件")
    if error:
        return _error("bom_risk_check", error)

    model = build_risk_model(bom)
    manifest_path: Path | None = None
    semantic_manifest_path: Path | None = None
    semantic_findings: list[dict[str, object]] = []
    placement_decisions: list[dict[str, object]] | None = None
    if str(params.get("semantic_manifest") or "").strip():
        semantic_manifest_path, semantic_error = _required_file(
            params,
            "semantic_manifest",
            "BOM 语义清单",
        )
        if semantic_error:
            return _error("bom_risk_check", semantic_error)
        assert semantic_manifest_path is not None
        semantic_manifest = load_semantic_manifest(semantic_manifest_path)
        placement_decisions = [dict(item) for item in semantic_manifest.decisions]
        semantic_findings = [dict(item) for item in semantic_manifest.findings]
    if str(params.get("decision_manifest") or "").strip():
        manifest_path, manifest_error = _required_file(params, "decision_manifest", "BOM 决策清单")
        if manifest_error:
            return _error("bom_risk_check", manifest_error)
        assert manifest_path is not None
        decision_manifest = load_decision_manifest(manifest_path)
        if placement_decisions is not None:
            semantic_refs = {
                str(ref).strip().upper()
                for item in placement_decisions
                for ref in item.get("refs") or []
                if str(ref).strip()
            }
            if semantic_refs != set(decision_manifest.by_ref()):
                raise ValueError("BOM 决策清单与语义清单的位号集合不一致。")
        else:
            placement_decisions = [dict(item) for item in decision_manifest.placements]
    review_summary = params.get("review_summary")
    report = evaluate_bom_risk_report(
        model,
        review_summary if isinstance(review_summary, dict) else None,
        placement_decisions,
        load_risk_rule_config(root),
    )
    semantic_issues = [
        item for item in semantic_findings
        if str(item.get("severity") or "") in {"warning", "blocker"}
    ]
    if semantic_manifest_path:
        semantic_level = "warn" if semantic_issues else "ok"
        report["findings"].append(
            {
                "code": "semantic_model_validation",
                "name": "BOM 语义模型校验",
                "level": semantic_level,
                "status": semantic_level,
                "message": (
                    f"语义清单发现 {len(semantic_issues)} 项问题。"
                    if semantic_issues
                    else "语义清单与当前 BOM 已完成一致性校验。"
                ),
                "details": semantic_issues,
                "detail_count": len(semantic_issues),
                "applicable": True,
            }
        )
        counts = dict(report["counts_by_level"])
        counts[semantic_level] = int(counts.get(semantic_level, 0)) + 1
        report["counts_by_level"] = counts
    findings = list(report["findings"])
    level_cn = {"blocker": "阻断", "warn": "警告", "info": "提示", "ok": "通过"}
    overview_rows = [
        [
            item.get("name", ""),
            level_cn.get(str(item.get("level") or ""), item.get("level", "")),
            item.get("message", ""),
            item.get("detail_count", 0),
        ]
        for item in findings
    ]
    output = _output_dir(params, root, "risk") / f"BOM风险检查_{_timestamp()}.xlsx"
    common_fields = [
        ("source_row", "源行"),
        ("code", "子项编码"),
        ("name", "名称"),
        ("model", "型号"),
        ("desc", "描述"),
        ("quantity", "数量"),
        ("refs", "位号"),
    ]
    grade_headers, grade_rows = _sheet_rows(
        list(report["grade_flags"]),
        [*common_fields, ("grade", "等级")],
    )
    type_headers, type_rows = _sheet_rows(
        list(report["type_flags"]),
        [("ref", "位号"), ("code", "子项编码"), ("expected", "位号期望"), ("actual", "识别类型"), ("note", "说明")],
    )
    group_headers, group_rows = _sheet_rows(
        list(report["substitute_groups"]),
        [
            ("parent_code", "父项编码"), ("group_code", "替代组编码"),
            ("main_code", "主料"), ("alternative_codes", "替代料"),
            ("priorities", "优先级"), ("quantity", "数量"), ("refs", "实际位号"),
            ("strategy", "替代策略"), ("mode", "替代方式"), ("issues", "问题"),
        ],
    )
    category_items = [
        *({**item, "category": "屏蔽类"} for item in report["shield_items"]),
        *({**item, "category": "机构件"} for item in report["mechanical_items"]),
        *({**item, "category": "工艺项"} for item in report["process_items"]),
    ]
    category_headers, category_rows = _sheet_rows(
        category_items,
        [("category", "类别"), *common_fields, ("subtype", "子类型")],
    )
    version_headers, version_rows = _sheet_rows(
        list(report["version_sensitive"]),
        common_fields,
    )
    nc_headers, nc_rows = _sheet_rows(list(report["nc_items"]), common_fields)
    _write_sheets(
        output,
        [
            ("风险概览", ["检查项", "级别", "结论", "明细数"], overview_rows),
            ("等级明细", grade_headers, grade_rows),
            ("位号类型冲突", type_headers, type_rows),
            ("替代组", group_headers, group_rows),
            ("屏蔽机构工艺项", category_headers, category_rows),
            ("版本敏感料", version_headers, version_rows),
            ("NC明细", nc_headers, nc_rows),
        ],
    )

    counts = dict(report["counts_by_level"])
    stats = dict(report["stats"])
    warnings = int(counts.get("blocker", 0)) + int(counts.get("warn", 0))
    result = _result(
        "bom_risk_check",
        [output],
        {
            "rows": stats.get("数据行", 0),
            "positions": stats.get("位号数", 0),
            "parts": stats.get("料号数", 0),
            "warnings": warnings,
            "grade_flags": len(report["grade_flags"]),
            "blockers": counts.get("blocker", 0),
            "profile": report["profile"],
        },
    )
    result["risk_report"] = {
        **report,
        "label": bom.name,
        "source_file": str(bom),
        "decision_manifest": str(manifest_path) if manifest_path else "",
        "semantic_manifest": str(semantic_manifest_path) if semantic_manifest_path else "",
    }
    result["source_file"] = str(bom)
    return result


def _run_generic_bom_import_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    source, error = _required_file(params, "source_bom", "原始 BOM 文件")
    if error:
        return _error("bom_import", error)
    rows = _read_bom_rows(source)
    main_rows = []
    excluded_rows = []
    for row in rows:
        refs = row["refs"]
        mapped_row = {
            "part_number": str(row.get("part_number") or ""),
            "value": str(row.get("value") or ""),
            "name": str(row.get("name") or ""),
            "desc": str(row.get("description") or ""),
            "model": str(row.get("model") or ""),
        }
        reason = bom_process.exclusion_reason(mapped_row, refs, include_shields=False)

        if reason:
            excluded_rows.append(
                [
                    row["source_row"],
                    row["reference"],
                    row["part_number"],
                    row["name"],
                    row["package"],
                    row["description"],
                    reason,
                ]
            )
        else:
            main_rows.append(
                [
                    row["part_number"],
                    row["name"],
                    row["package"],
                    row["description"],
                    len(refs),
                    row["reference"],
                    "直接领料",
                    "是",
                    "否",
                ]
            )

    out_dir = _output_dir(params, root, "bom")
    stem = source.stem
    main_output = out_dir / f"{stem}_主BOM.xlsx"
    nc_output = out_dir / f"{stem}_NC未贴器件汇总.xlsx"
    _write_table(main_output, "主BOM", ["子项编码", "名称", "型号/封装", "描述", "数量", "位号", "发料方式", "是否参与MRP运算", "是否跳层"], main_rows)
    _write_table(nc_output, "NC未贴汇总", ["原始行号", "位号", "子项编码", "名称", "型号/封装", "描述", "过滤原因"], excluded_rows)
    return _result(
        "bom_import",
        [main_output, nc_output],
        {"main_rows": len(main_rows), "excluded_rows": len(excluded_rows)},
    )


def run_generic_bom_import(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_generic_bom_import_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("bom_import", exc)


def run_bom_risk_check(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_bom_risk_check_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("bom_risk_check", exc)
