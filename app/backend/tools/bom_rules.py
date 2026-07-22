from __future__ import annotations

import re
from collections import Counter

from app.backend.tools.common import qty_matches
from app.backend.tools.bom_classify import default_nc_value_re


_NC_RE = re.compile(r"(^|[,/\s（(])(?:NC|DNP|DNI|NO\s*LOAD|NOFIT|不贴|未贴|空贴)([,/\s）)]|$)", re.IGNORECASE)
NC_VALUE_RE = default_nc_value_re()
_MECH_KW = ["螺丝", "螺钉", "螺母", "垫片", "华司", "铜柱", "支柱", "定位孔", "安装孔", "MOUNTINGHOLE", "散热片", "导热垫"]
_TP_PREFIX = ("TP", "JP", "Z_TP", "FID", "MK", "MH")
_TP_KW = ["测试点", "跳线", "FIDUCIAL", "基准", "拼板", "工艺边", "MARK点"]
_VERSION_SENSITIVE_RE = re.compile(r"\b(E?MMC|LP?DDR\d*[A-Z0-9]*)\b|DDR", re.IGNORECASE)
_PREFIX_EXPECT = {"C": "电容", "R": "电阻", "L": "电感"}
_CODE_PREFIX_TYPE = {"L": "电感", "C": "电容", "R": "电阻"}


def _quantity_mismatch(row: dict[str, object]) -> bool:
    return not qty_matches(row.get("quantity"), len(row.get("refs") or []))


def _nc_row(row: dict[str, object]) -> bool:
    value = str(row.get("value") or "").strip()
    if NC_VALUE_RE.fullmatch(value):
        return True
    text = " ".join(
        str(row.get(field) or "")
        for field in ("part_number", "model", "description", "name")
    )
    upper_text = text.upper()
    return any(key in upper_text for key in ("未贴", "不贴", "DNP")) or bool(_NC_RE.search(text))


def _looks_like_pcb(row: dict[str, object]) -> bool:
    desc = str(row.get("description", ""))
    blob = f"{row.get('part_number','')} {row.get('model','')} {desc}".upper()
    if any(key in blob for key in ["PCB", "HDI"]) or any(key in desc for key in ["印制板", "覆铜板", "任意阶"]):
        return True
    return bool(re.search(r"\d+\s*层", desc))


def _looks_like_shield_bracket(row: dict[str, object]) -> bool:
    refs = [str(ref).upper() for ref in row.get("refs") or []]
    text = f"{row.get('part_number','')} {row.get('model','')} {row.get('description','')} {row.get('name','')}".upper()
    return any(ref.startswith("SH") for ref in refs) or "屏蔽支架" in text or "SHIELD BRACKET" in text


def _version_sensitive_parts(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row
        for row in rows
        if _VERSION_SENSITIVE_RE.search(
            f"{row.get('part_number','')} {row.get('model','')} {row.get('description','')} {row.get('name','')}"
        )
    ]


def _actual_type(desc: str, code: str, model: str) -> str | None:
    if "电感" in desc:
        return "电感"
    if "电阻" in desc:
        return "电阻"
    if "电容" in desc:
        return "电容"
    match = re.match(r"^([A-Za-z]+)\.", str(code))
    if match:
        by_code = _CODE_PREFIX_TYPE.get(match.group(1).upper())
        if by_code:
            return by_code
    if re.search(r"\d\s*[munpμµ]?H\b", str(model)):
        return "电感"
    if re.search(r"\d\s*[munpμµ]?F\b", str(model)):
        return "电容"
    return None


def find_type_mismatches(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    mismatches: list[dict[str, str]] = []
    for row in rows:
        actual = _actual_type(str(row.get("description", "")), str(row.get("part_number", "")), str(row.get("model", "")))
        if not actual:
            continue
        for ref in row.get("refs") or []:
            match = re.match(r"^([A-Za-z]+)", ref)
            prefix = match.group(1).upper() if match else ""
            expected = _PREFIX_EXPECT.get(prefix)
            if expected and expected != actual:
                mismatches.append({
                    "ref": ref,
                    "code": row.get("part_number", ""),
                    "desc": row.get("description", ""),
                    "note": f"位号 {prefix}（通常为{expected}）实为{actual}",
                })
    return mismatches


def evaluate_bom_risks(
    rows: list[dict[str, object]],
    review_summary: dict[str, object] | None = None,
) -> list[dict[str, str]]:
    """Evaluate reusable BOM risk rules without depending on a tool engine."""

    def blob(row: dict[str, object]) -> str:
        return f"{row.get('part_number','')} {row.get('model','')} {row.get('description','')}"

    findings: list[dict[str, str]] = []
    pcb = sorted({row["part_number"] for row in rows if _looks_like_pcb(row)})
    findings.append({"name": "PCB 裸板", "status": "ok" if pcb else "warn", "message": "找到 " + ", ".join(pcb) if pcb else "未发现 PCB 裸板项（PCBA BOM 通常应包含裸板）"})

    brackets = sorted({row["part_number"] for row in rows if _looks_like_shield_bracket(row)})
    findings.append({"name": "屏蔽支架", "status": "ok" if brackets else "info", "message": "找到 " + ", ".join(brackets) if brackets else "未发现屏蔽支架（如设计需要请确认）"})

    nc_refs = [ref for row in rows if _nc_row(row) for ref in (row.get("refs") or [])]
    findings.append({"name": "NC/未贴器件", "status": "warn" if nc_refs else "ok", "message": f"混入 {len(nc_refs)} 个：" + ",".join(nc_refs[:15]) if nc_refs else "无"})

    mechanical = sorted({row["part_number"] for row in rows if any(key.upper() in blob(row).upper() for key in _MECH_KW)})
    findings.append({"name": "机构件/螺丝/孔", "status": "warn" if mechanical else "ok", "message": "混入：" + ", ".join(mechanical) if mechanical else "无"})

    test_points = sorted({ref for row in rows for ref in (row.get("refs") or []) if ref.upper().startswith(_TP_PREFIX)}) + sorted({row["part_number"] for row in rows if any(key.upper() in blob(row).upper() for key in _TP_KW)})
    findings.append({"name": "测试点/跳线/工艺", "status": "info" if test_points else "ok", "message": "发现：" + ", ".join(test_points[:15]) if test_points else "无"})

    counts = Counter(ref for row in rows for ref in (row.get("refs") or []))
    duplicates = sorted(ref for ref, count in counts.items() if count > 1)
    findings.append({"name": "重复位号", "status": "warn" if duplicates else "ok", "message": ", ".join(duplicates[:15]) if duplicates else "无"})

    empty_codes = [row for row in rows if (row.get("refs") or []) and not str(row.get("part_number") or "").strip()]
    findings.append({"name": "空编号行", "status": "warn" if empty_codes else "ok", "message": f"{len(empty_codes)} 行有位号但料号为空" if empty_codes else "无"})

    quantity_mismatches = [row for row in rows if (row.get("refs") or []) and _quantity_mismatch(row)]
    findings.append({"name": "数量=位号数", "status": "warn" if quantity_mismatches else "ok", "message": f"{len(quantity_mismatches)} 行不符，例 {quantity_mismatches[0]['part_number']}：数量{quantity_mismatches[0]['quantity']}≠位号{len(quantity_mismatches[0]['refs'])}" if quantity_mismatches else "全部一致"})

    type_mismatches = find_type_mismatches(rows)
    findings.append({"name": "位号/器件类型", "status": "warn" if type_mismatches else "ok", "message": f"{len(type_mismatches)} 处位号与器件类型不符（疑似占位换料）：" + ", ".join(item["ref"] for item in type_mismatches[:10]) if type_mismatches else "无"})

    flagged = [row for row in rows if str(row.get("grade") or "").strip() and str(row.get("grade")).strip() not in ("优选", "正常")]
    if flagged:
        kinds = Counter(str(row.get("grade")).strip() for row in flagged)
        detail = ", ".join(f"{grade}×{count}" for grade, count in kinds.most_common())
        findings.append({"name": "物料优选等级", "status": "warn", "message": f"{len(flagged)} 项非优选/正常：{detail}"})
    else:
        has_grade = any(str(row.get("grade") or "").strip() for row in rows)
        findings.append({"name": "物料优选等级", "status": "ok" if has_grade else "info", "message": "均为优选/正常" if has_grade else "未提供等级列"})

    sensitive = _version_sensitive_parts(rows)
    if sensitive:
        codes = sorted({str(row.get("part_number") or "").strip() for row in sensitive if str(row.get("part_number") or "").strip()})
        findings.append({"name": "硬件版本敏感物料", "status": "info", "message": "发现 eMMC/DDR 相关物料：" + ", ".join(codes[:10]) + "；请注意核对硬件版本号、容量/速率和替代关系"})
    else:
        findings.append({"name": "硬件版本敏感物料", "status": "ok", "message": "未发现 eMMC/DDR 相关物料"})
    if review_summary:
        kept = int(review_summary.get("kept_groups") or 0)
        excluded = int(review_summary.get("excluded_groups") or 0)
        findings.append({
            "name": "装机人工审查",
            "status": "info",
            "message": f"已人工确认纳入 {kept} 组、确认不装 {excluded} 组；这些决议不再作为空编码风险重复报警。",
        })
    return findings
