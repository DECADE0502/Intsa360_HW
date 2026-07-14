from __future__ import annotations

import re
from pathlib import Path

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
_NC_RE = re.compile(r"(^|[,/\s（(])NC([,/\s）)]|$)", re.IGNORECASE)
_MECH_KW = ["螺丝", "螺钉", "螺母", "垫片", "华司", "铜柱", "支柱", "定位孔", "安装孔", "MOUNTINGHOLE", "散热片", "导热垫"]
_TP_PREFIX = ("TP", "JP", "Z_TP", "FID", "MK", "MH")
_TP_KW = ["测试点", "跳线", "FIDUCIAL", "基准", "拼板", "工艺边", "MARK点"]
_VERSION_SENSITIVE_RE = re.compile(r"\b(E?MMC|LP?DDR\d*[A-Z0-9]*)\b|DDR", re.IGNORECASE)


def _looks_like_pcb(row: dict[str, object]) -> bool:
    """裸板特征：印制板/覆铜板/PCB/HDI/任意阶，或“N层”层数描述。"""
    desc = str(row.get("description", ""))
    blob = f"{row.get('part_number','')} {row.get('model','')} {desc}".upper()
    if any(k in blob for k in ["PCB", "HDI"]) or any(k in desc for k in ["印制板", "覆铜板", "任意阶"]):
        return True
    return bool(re.search(r"\d+\s*层", desc))


def _looks_like_shield_bracket(row: dict[str, object]) -> bool:
    refs = [str(ref).upper() for ref in row.get("refs") or []]
    text = f"{row.get('part_number','')} {row.get('model','')} {row.get('description','')} {row.get('name','')}".upper()
    if any(ref.startswith("SH") for ref in refs):
        return True
    return "屏蔽支架" in text or "SHIELD BRACKET" in text


def _version_sensitive_parts(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in rows:
        text = f"{row.get('part_number','')} {row.get('model','')} {row.get('description','')} {row.get('name','')}"
        if _VERSION_SENSITIVE_RE.search(text):
            out.append(row)
    return out


# 位号前缀 -> 期望器件类型（占位换料检查：天线匹配网络常见 C/R 位号换成电感等）
_PREFIX_EXPECT = {"C": "电容", "R": "电阻", "L": "电感"}


_CODE_PREFIX_TYPE = {"L": "电感", "C": "电容", "R": "电阻"}


def _actual_type(desc: str, code: str, model: str) -> str | None:
    # 1) 描述中文类型词（最可靠）
    if "电感" in desc:
        return "电感"
    if "电阻" in desc:
        return "电阻"
    if "电容" in desc:
        return "电容"
    # 2) 料号编码规则前缀（L./C./R. = 电感/电容/电阻），描述为空时的关键判据
    match = re.match(r"^([A-Za-z]+)\.", str(code))
    if match:
        by_code = _CODE_PREFIX_TYPE.get(match.group(1).upper())
        if by_code:
            return by_code
    # 3) 型号单位：nH/uH/mH = 电感；pF/nF/uF = 电容
    if re.search(r"\d\s*[munpμµ]?H\b", str(model)):
        return "电感"
    if re.search(r"\d\s*[munpμµ]?F\b", str(model)):
        return "电容"
    return None


def _type_mismatches(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        actual = _actual_type(str(row.get("description", "")), str(row.get("part_number", "")), str(row.get("model", "")))
        if not actual:
            continue
        for ref in row.get("refs") or []:
            match = re.match(r"^([A-Za-z]+)", ref)
            prefix = match.group(1).upper() if match else ""
            expect = _PREFIX_EXPECT.get(prefix)
            if expect and expect != actual:
                out.append({
                    "ref": ref, "code": row.get("part_number", ""), "desc": row.get("description", ""),
                    "note": f"位号 {prefix}（通常为{expect}）实为{actual}",
                })
    return out


def _risk_check(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    """单份 BOM 的导入前风险自检，输出一组检查项（ok/warn/info）。"""
    from collections import Counter

    def blob(row: dict[str, object]) -> str:
        return f"{row.get('part_number','')} {row.get('model','')} {row.get('description','')}"

    findings: list[dict[str, str]] = []

    pcb = sorted({r["part_number"] for r in rows if _looks_like_pcb(r)})
    findings.append({"name": "PCB 裸板", "status": "ok" if pcb else "warn",
                     "message": "找到 " + ", ".join(pcb) if pcb else "未发现 PCB 裸板项（PCBA BOM 通常应包含裸板）"})

    shield_brackets = sorted({r["part_number"] for r in rows if _looks_like_shield_bracket(r)})
    findings.append({"name": "屏蔽支架", "status": "ok" if shield_brackets else "info",
                     "message": "找到 " + ", ".join(shield_brackets) if shield_brackets else "未发现屏蔽支架（如设计需要请确认）"})

    nc_refs = [rf for r in rows if any(k in blob(r) for k in ["未贴", "不贴", "DNP"]) or _NC_RE.search(blob(r)) for rf in (r.get("refs") or [])]
    findings.append({"name": "NC/未贴器件", "status": "warn" if nc_refs else "ok",
                     "message": f"混入 {len(nc_refs)} 个：" + ",".join(nc_refs[:15]) if nc_refs else "无"})

    mech = sorted({r["part_number"] for r in rows if any(k.upper() in blob(r).upper() for k in _MECH_KW)})
    findings.append({"name": "机构件/螺丝/孔", "status": "warn" if mech else "ok",
                     "message": "混入：" + ", ".join(mech) if mech else "无"})

    tp_refs = sorted({rf for r in rows for rf in (r.get("refs") or []) if rf.upper().startswith(_TP_PREFIX)}) + \
        sorted({r["part_number"] for r in rows if any(k.upper() in blob(r).upper() for k in _TP_KW)})
    findings.append({"name": "测试点/跳线/工艺", "status": "info" if tp_refs else "ok",
                     "message": "发现：" + ", ".join(tp_refs[:15]) if tp_refs else "无"})

    counts = Counter(rf for r in rows for rf in (r.get("refs") or []))
    dup = sorted([rf for rf, n in counts.items() if n > 1])
    findings.append({"name": "重复位号", "status": "warn" if dup else "ok",
                     "message": ", ".join(dup[:15]) if dup else "无"})

    empty = [r for r in rows if (r.get("refs") or []) and not str(r.get("part_number") or "").strip()]
    findings.append({"name": "空编号行", "status": "warn" if empty else "ok",
                     "message": f"{len(empty)} 行有位号但料号为空" if empty else "无"})

    mismatch = [r for r in rows if (r.get("refs") or []) and str(r.get("quantity")).strip() not in ("", str(len(r["refs"])))]
    findings.append({"name": "数量=位号数", "status": "warn" if mismatch else "ok",
                     "message": f"{len(mismatch)} 行不符，例 {mismatch[0]['part_number']}：数量{mismatch[0]['quantity']}≠位号{len(mismatch[0]['refs'])}" if mismatch else "全部一致"})

    mism = _type_mismatches(rows)
    findings.append({"name": "位号/器件类型", "status": "warn" if mism else "ok",
                     "message": (f"{len(mism)} 处位号与器件类型不符（疑似占位换料）：" + ", ".join(m["ref"] for m in mism[:10])) if mism else "无"})

    flagged = [r for r in rows if str(r.get("grade") or "").strip() and str(r.get("grade")).strip() not in ("优选", "正常")]
    if flagged:
        kinds = Counter(str(r.get("grade")).strip() for r in flagged)
        detail = ", ".join(f"{g}×{n}" for g, n in kinds.most_common())
        findings.append({"name": "物料优选等级", "status": "warn", "message": f"{len(flagged)} 项非优选/正常：{detail}"})
    else:
        has_grade = any(str(r.get("grade") or "").strip() for r in rows)
        findings.append({"name": "物料优选等级", "status": "ok" if has_grade else "info",
                         "message": "均为优选/正常" if has_grade else "未提供等级列"})

    sensitive = _version_sensitive_parts(rows)
    if sensitive:
        codes = sorted({str(row.get("part_number") or "").strip() for row in sensitive if str(row.get("part_number") or "").strip()})
        findings.append({"name": "硬件版本敏感物料", "status": "info",
                         "message": "发现 eMMC/DDR 相关物料：" + ", ".join(codes[:10]) + "；请注意核对硬件版本号、容量/速率和替代关系"})
    else:
        findings.append({"name": "硬件版本敏感物料", "status": "ok", "message": "未发现 eMMC/DDR 相关物料"})

    return findings
def _run_bom_risk_check_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    bom, error = _required_file(params, "bom", "BOM 文件")
    if error:
        return _error("bom_risk_check", error)

    rows = _read_bom_rows(bom, require_refs=False)
    findings = _risk_check(rows)
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
        "type_flags": _type_mismatches(rows),
        "review": {"headers": review_headers, "rows": review_rows, "grade_col": 5},
    }
    return result


def run_generic_bom_import(root: Path, params: dict[str, object]) -> dict[str, object]:
    source, error = _required_file(params, "source_bom", "原始 BOM 文件")
    if error:
        return _error("bom_import", error)
    rows = _read_bom_rows(source)
    main_rows = []
    excluded_rows = []
    for row in rows:
        refs = row["refs"]
        text = f"{row.get('description', '')} {row.get('name', '')}"
        value = str(row.get("value", ""))
        reason = ""
        if not row.get("part_number"):
            reason = "子项编码为空"
        elif value.upper().startswith("NC") or "NC/" in text.upper():
            reason = "NC/未贴"
        elif any(ref.upper().startswith(("TP", "Z_TP", "JP", "SH")) for ref in refs):
            reason = "测试点/跳线/非贴装"
        elif any(token in text for token in ["测试点", "跳线", "Test"]):
            reason = "字段包含测试/跳线"

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
def run_bom_risk_check(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_bom_risk_check_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("bom_risk_check", exc)
