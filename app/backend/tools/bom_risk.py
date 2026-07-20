from __future__ import annotations

from pathlib import Path

from app.backend.tools import bom_process
from app.backend.tools.bom_rules import evaluate_bom_risks, find_type_mismatches
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
    _write_table,
)
def _run_bom_risk_check_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    bom, error = _required_file(params, "bom", "BOM 文件")
    if error:
        return _error("bom_risk_check", error)

    rows = _read_bom_rows(bom, require_refs=False)
    findings = evaluate_bom_risks(rows)
    positions = sum(len(row.get("refs") or []) for row in rows)
    parts = len({row["part_number"] for row in rows if row.get("part_number")})

    level_cn = {"ok": "通过", "warn": "警告", "info": "提示"}
    headers = ["检查项", "结果", "说明"]
    report_rows = [[f["name"], level_cn.get(f["status"], f["status"]), f["message"]] for f in findings]
    output = _output_dir(params, root, "risk") / f"BOM风险检查_{_timestamp()}.xlsx"
    _write_table(output, "风险检查", headers, report_rows)

    def _grade(row: dict[str, object]) -> str:
        return str(row.get("grade") or "").strip()

    grade_flags = [
        {"code": r.get("part_number", ""), "desc": r.get("description", ""),
         "refs": r.get("reference", ""), "grade": _grade(r)}
        for r in rows
        if _grade(r) and _grade(r) not in ("优选", "正常")
    ]
    review_headers = ["编号", "型号", "描述", "数量", "位号", "等级"]
    review_rows = [
        [r.get("part_number", ""), r.get("model", ""), r.get("description", ""),
         _jsonable(r.get("quantity")), r.get("reference", ""), _grade(r)]
        for r in rows
    ]

    warnings = sum(1 for f in findings if f["status"] == "warn")
    result = _result(
        "bom_risk_check",
        [output],
        {"rows": len(rows), "positions": positions, "parts": parts, "warnings": warnings, "grade_flags": len(grade_flags)},
    )
    result["risk_report"] = {
        "label": bom.name,
        "findings": findings,
        "stats": {"数据行": len(rows), "位号数": positions, "料号数": parts},
        "grade_flags": grade_flags,
        "type_flags": find_type_mismatches(rows),
        "review": {"headers": review_headers, "rows": review_rows, "grade_col": 5},
    }
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
