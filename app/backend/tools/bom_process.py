from __future__ import annotations

import re
from collections import Counter, OrderedDict
from pathlib import Path

from app.backend.capture_fields import BOM_OPTIONAL_FIELDS, FIELD_DEFAULTS, PLM_TEMPLATE_HEADERS
from app.backend.parsers._workbook import build_merged_cell_lookup, open_bom_workbook
from app.backend.parsers.bom_table import INHERIT_FIELDS, normalize_header, split_refs
from app.backend.parsers.refs import natural_key

# BOM 处理工具：把 Capture 导出的原始 BOM 处理成可导入的 PLM / OA 成品。
# - 自动定位表头行（Capture 导出前面常有标题块），表头带不带 {} 花括号都能识别
# - 按原样处理：过滤 NC/未贴、测试点 TP、跳线 JP、屏蔽 SH；按料号合并位号、统计数量
#   （从 Capture 按版本导出的 BOM 本身已是该版本的真实器件，无需再做版本换料）
# - 输出 PLM（19 列）和/或 OA（16 列）成品，并可追加 PCB/屏蔽罩等附加物料
# - 同时产出 NC/未贴器件汇总

# 源列别名 -> 规范字段
SRC_ALIASES = {
    "reference": ["Reference", "位号", "Designator", "RefDes"],
    "part_number": ["Part Number", "子项编码", "料号", "物料编码", "PN"],
    "value": ["Value", "值"],
    "model": ["规格型号", "型号", "Model", "MPN"],
    "desc": ["器件描述（新整理）", "器件描述", "内容", "描述", "Description"],
    "name": ["物料名称", "名称", "Part Type", "Name"],
    "grade": ["等级", "物料优选等级", "优选等级"],
    "unit": ["单位", "Unit", "UOM"],
    "remark": ["备注", "Remark", "Note"],
    "grade_remark": ["物料优选等级备注", "等级备注"],
    "alt_group": ["替代组编码"],
    "alt_strategy": ["替代策略"],
    "alt_method": ["替代方式"],
    "alt_priority": ["替代优先级"],
    "issue_method": ["发料方式", "领料方式", "发料"],
    "mrp": ["是否参与MRP运算"],
    "jump_level": ["是否跳层"],
    "pcb_footprint": ["PCB Footprint", "Footprint"],
    "pcb_package": ["PCB封装", "封装"],
    "source_package": ["Source Package"],
    "source_part": ["Source Part"],
    "part_type": ["Part Type"],
    "part_reference": ["Part Reference"],
}

PLM_R1 = ["父项信息", "", "子项信息", "", "", "", "", "", "BOM明细", "", "", "", "", "", "", "", "", "", ""]
PLM_HEADERS = PLM_TEMPLATE_HEADERS
OA_HEADERS = [
    "序号", "编码（父）*##bmf", "描述（父）##msf", "编码（子）*##bm", "描述（子）##ms", "数量*##sl",
    "单位*##dw", "位号##wh", "备注##bz", "替代组编码##tdzbm", "替代策略##tdcl", "发料方式##tdfs",
    "物料优选等级##tdyxj", "领料方式*##flfs", "是否参与MRP运算*##sfcymrpys", "是否跳层*##sftc",
]
NC_HEADERS = ["原始行号", "位号", "子项编码", "物料名称", "型号", "描述", "Value", "过滤原因"]
CONFLICT_FIELDS = ("name", "model", "desc", "grade", "unit")
_NUMERIC_VALUE_RE = re.compile(
    r"^\d+(?:\.\d+)?(?:\s*[RrKkMmGgTtUuNnPpFfHhVv]\d*)?"
    r"\s*(?:Ω|ohms?|%|℃|°C|[VvAaWwFfHh])?$",
    re.IGNORECASE,
)


def _looks_numeric(value: str) -> bool:
    """Return whether a value is a numeric component specification."""
    return bool(_NUMERIC_VALUE_RE.fullmatch(value.strip()))
GRADE_RANK = {"优选": 5, "正常": 4, "限选": 3, "验证中": 2, "": 0}


def normalize_ref(ref: str) -> str:
    match = re.fullmatch(r"(U\d+)[A-Z]", ref)
    return match.group(1) if match else ref


def detect_header(ws) -> tuple[int, dict[str, int]]:
    """扫描前若干行，定位含 Reference + Part Number 的表头行，返回行号与字段列映射。"""
    alias_norm = {key: [normalize_header(a) for a in names] for key, names in SRC_ALIASES.items()}
    best_row, best_map, best_score = 1, {}, -1
    for row in range(1, min(ws.max_row, 40) + 1):
        values = [normalize_header(ws.cell(row, col).value) for col in range(1, ws.max_column + 1)]
        mapping: dict[str, int] = {}
        for key, names in alias_norm.items():
            for alias in names:
                for idx, value in enumerate(values, start=1):
                    if value and value == alias:
                        mapping[key] = idx
                        break
                if key in mapping:
                    break
        score = sum(1 for k in ("reference", "part_number") if k in mapping) * 10 + len(mapping)
        if score > best_score:
            best_row, best_map, best_score = row, mapping, score
    if "reference" not in best_map or "part_number" not in best_map:
        raise ValueError("表头识别失败：未找到 Reference / Part Number 列，请确认按导出配置生成的原始 BOM。")
    return best_row, best_map


def _cell(
    ws,
    row: int,
    mapping: dict[str, int],
    key: str,
    merged_lookup: dict[tuple[int, int], object] | None = None,
) -> str:
    col = mapping.get(key)
    if not col:
        return ""
    raw_value = ws.cell(row, col).value
    source_field = {
        "desc": "description",
        "part_type": "name",
        "pcb_footprint": "package",
        "pcb_package": "package",
        "source_package": "package",
    }.get(key, key)
    if raw_value is None and merged_lookup is not None and source_field in INHERIT_FIELDS:
        raw_value = merged_lookup.get((row, col))
    return str(raw_value or "").strip()


def has_shield_refs(refs: list[str]) -> bool:
    return any(ref.upper().startswith("SH") for ref in refs)


def _normalize_shield_row(row: dict[str, str], refs: list[str]) -> None:
    if not has_shield_refs(refs):
        return
    if not row.get("name", "").strip():
        row["name"] = "屏蔽支架"
    if not row.get("desc", "").strip():
        row["desc"] = row.get("value", "").strip() or "屏蔽支架"


def exclusion_reason(row: dict[str, str], refs: list[str], include_shields: bool = False) -> str | None:
    if not row.get("part_number"):
        return "子项编码为空"
    upper = [r.upper() for r in refs]
    if any(r.startswith("SH") for r in upper):
        if include_shields:
            return None
        return "屏蔽支架 SH*"
    value = row.get("value", "")
    upper_value = value.upper()
    if upper_value == "NC" or upper_value.startswith("NC/") or upper_value == "DNP":
        return "NC/未贴"
    upper = [r.upper() for r in refs]
    if any(r.startswith("JP") for r in upper):
        return "跳线 JP*"
    if any(r.startswith(("TP", "Z_TP")) for r in upper):
        return "测试点 TP*/Z_TP*"
    if any(r.startswith("SH") for r in upper) and not include_shields:
        return "屏蔽/非贴装 SH*"
    text = " ".join(str(v) for v in row.values())
    for token in ("Test", "测试点", "跳线"):
        if token in text:
            return f"字段包含 {token}"
    return None


def load_source(path: Path, include_shields: bool = False) -> tuple[list[dict[str, str]], list[list[object]]]:
    with open_bom_workbook(path, data_only=True) as wb:
        ws = wb.active
        merged_lookup = build_merged_cell_lookup(ws)
        header_row, mapping = detect_header(ws)
        rows: list[dict[str, str]] = []
        excluded: list[list[object]] = []
        for row_num in range(header_row + 1, ws.max_row + 1):
            row = {key: _cell(ws, row_num, mapping, key, merged_lookup) for key in SRC_ALIASES}
            if not row.get("name"):
                row["name"] = row.get("part_type") or ""
            if not row.get("model"):
                row["model"] = row.get("value") or row.get("pcb_package") or row.get("pcb_footprint") or ""
            if not row.get("desc"):
                row["desc"] = row.get("value") or ""
            if not any(row.values()):
                continue
            refs = [normalize_ref(r) for r in split_refs(row.get("reference"))]
            _normalize_shield_row(row, refs)
            reason = exclusion_reason(row, refs, include_shields=include_shields)
            if reason:
                excluded.append([row_num, ",".join(refs), row.get("part_number"), row.get("name"),
                                 row.get("model"), row.get("desc"), row.get("value"), reason])
                continue
            rows.append(row)
        return rows, excluded


def detect_shield_candidates(source_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    candidates = []
    for row in source_rows:
        refs = sorted({normalize_ref(r) for r in split_refs(row.get("reference"))}, key=natural_key)
        shield_refs = [ref for ref in refs if ref.upper().startswith("SH")]
        if not shield_refs:
            continue
        candidates.append(
            {
                "code": row.get("part_number", "").strip(),
                "name": row.get("name", "").strip() or "屏蔽支架",
                "model": row.get("model", "").strip(),
                "desc": row.get("desc", "").strip() or "屏蔽支架",
                "grade": row.get("grade", "").strip(),
                "refs": shield_refs,
                "count": len(shield_refs),
            }
        )
    return candidates


def _grade_rank(value: str) -> int:
    return GRADE_RANK.get(str(value or "").strip(), 1)


def _representative(values: list[str], field: str) -> str:
    non_empty = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not non_empty:
        return ""
    if field == "grade":
        return max(non_empty, key=lambda value: (_grade_rank(value), -non_empty.index(value)))
    counts = Counter(non_empty)
    return max(non_empty, key=lambda value: (counts[value], -non_empty.index(value)))


def _row_signature(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return tuple(row.get(field, "").strip() for field in CONFLICT_FIELDS)


def _signature_payload(signature: tuple[str, str, str, str, str]) -> dict[str, str]:
    return dict(zip(CONFLICT_FIELDS, signature))


def _fallback_recommendation(
    variants: list[dict[str, object]],
    signatures: list[tuple[str, str, str, str, str]],
    reason: str,
) -> dict[str, object]:
    # Low-confidence recommendations still select one intact source variant.
    # Richer text wins first, then completeness, grade, affected count, and source order.
    index = max(
        range(len(variants)),
        key=lambda item: (
            sum(len(value.strip()) for value in signatures[item]),
            sum(1 for value in signatures[item] if value.strip()),
            _grade_rank(signatures[item][CONFLICT_FIELDS.index("grade")]),
            int(variants[item].get("count") or 0),
            -item,
        ),
    )
    return {
        "confidence": "low",
        "reason": reason,
        "high_confidence": False,
        "manual_choice_required": True,
        "recommended_index": index,
        "recommended_signature": _signature_payload(signatures[index]),
    }


def _conflict_recommendation(variants: list[dict[str, object]]) -> dict[str, object]:
    signatures = [tuple(str(variant.get(field) or "") for field in CONFLICT_FIELDS) for variant in variants]

    core_without_grade = [
        tuple(value for field, value in zip(CONFLICT_FIELDS, signature) if field != "grade")
        for signature in signatures
    ]
    grades = {signature[CONFLICT_FIELDS.index("grade")] for signature in signatures}
    if len(set(core_without_grade)) == 1 and len(grades) > 1:
        index = max(
            range(len(variants)),
            key=lambda item: (
                _grade_rank(signatures[item][CONFLICT_FIELDS.index("grade")]),
                int(variants[item].get("count") or 0),
                -item,
            ),
        )
        return {
            "confidence": "high",
            "reason": "grade_only_conflict",
            "high_confidence": True,
            "manual_choice_required": False,
            "recommended_index": index,
            "recommended_signature": _signature_payload(signatures[index]),
        }

    non_empty_by_field = [
        {signature[index] for signature in signatures if signature[index]}
        for index in range(len(CONFLICT_FIELDS))
    ]
    has_blank = any(not value for signature in signatures for value in signature)
    if has_blank and all(len(values) <= 1 for values in non_empty_by_field):
        target = tuple(next(iter(values), "") for values in non_empty_by_field)
        complete = [index for index, signature in enumerate(signatures) if signature == target]
        if len(complete) == 1:
            index = complete[0]
            return {
                "confidence": "high",
                "reason": "blank_completion",
                "high_confidence": True,
                "manual_choice_required": False,
                "recommended_index": index,
                "recommended_signature": _signature_payload(signatures[index]),
            }
        return _fallback_recommendation(variants, signatures, "complementary_incomplete_candidates")

    dominant: list[int] = []
    has_numeric_conflict = False
    for candidate_index, candidate in enumerate(signatures):
        dominates_all = True
        has_strict_prefix = False
        for other_index, other in enumerate(signatures):
            if candidate_index == other_index:
                continue
            for candidate_value, other_value in zip(candidate, other):
                if candidate_value == other_value:
                    continue
                if not candidate_value or not other_value:
                    dominates_all = False
                    break
                if _looks_numeric(candidate_value) and _looks_numeric(other_value):
                    has_numeric_conflict = True
                    dominates_all = False
                    break
                if not candidate_value.startswith(other_value):
                    dominates_all = False
                    break
                extension = candidate_value[len(other_value):]
                if extension and extension[0].isdigit():
                    has_numeric_conflict = True
                    dominates_all = False
                    break
                has_strict_prefix = True
            if not dominates_all:
                break
        if dominates_all and has_strict_prefix:
            dominant.append(candidate_index)
    if len(dominant) == 1:
        index = dominant[0]
        return {
            "confidence": "high",
            "reason": "truncation_prefix_completion",
            "high_confidence": True,
            "manual_choice_required": False,
            "recommended_index": index,
            "recommended_signature": _signature_payload(signatures[index]),
        }

    all_complete = all(all(value for value in signature) for signature in signatures)
    return _fallback_recommendation(
        variants,
        signatures,
        "multiple_complete_candidates" if all_complete and not has_numeric_conflict else "conflicting_candidate_values",
    )


def detect_part_conflicts(source_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    by_code: "OrderedDict[str, list[dict[str, str]]]" = OrderedDict()
    for row in source_rows:
        code = row.get("part_number", "").strip()
        if code:
            by_code.setdefault(code, []).append(row)

    conflicts: list[dict[str, object]] = []
    for code, rows in by_code.items():
        variants: "OrderedDict[tuple[str, str, str, str, str], dict[str, object]]" = OrderedDict()
        for row in rows:
            refs = sorted({normalize_ref(r) for r in split_refs(row.get("reference"))}, key=natural_key)
            signature = _row_signature(row)
            if signature not in variants:
                variants[signature] = {
                    "name": signature[0],
                    "model": signature[1],
                    "desc": signature[2],
                    "grade": signature[3],
                    "unit": signature[4],
                    "refs": [],
                    "count": 0,
                }
            variants[signature]["refs"].extend(refs)
            variants[signature]["count"] += len(refs) or 1
        if len(variants) > 1:
            variant_list = [
                {
                    **variant,
                    "refs": sorted(set(variant["refs"]), key=natural_key)[:30],
                }
                for variant in variants.values()
            ]
            conflicts.append(
                {
                    "code": code,
                    "total_refs": sum(int(v["count"]) for v in variants.values()),
                    "variants": variant_list,
                    **_conflict_recommendation(variant_list),
                }
            )
    return conflicts


def conflict_summary(source_rows: list[dict[str, str]], limit: int = 50) -> list[dict[str, object]]:
    conflicts = detect_part_conflicts(source_rows)
    return conflicts[:limit]


def _selected_signature(
    code: str,
    source_rows: list[dict[str, str]],
    conflict_choices: dict[str, object] | None,
) -> tuple[str, str, str, str, str] | None:
    if not conflict_choices or code not in conflict_choices:
        return None
    raw_choice = conflict_choices.get(code)
    if isinstance(raw_choice, bool):
        return None
    if isinstance(raw_choice, int):
        choice = raw_choice
    elif isinstance(raw_choice, str) and raw_choice.isdigit():
        choice = int(raw_choice)
    else:
        return None
    signatures: list[tuple[str, str, str, str, str]] = []
    for row in source_rows:
        if row.get("part_number", "").strip() != code:
            continue
        signature = _row_signature(row)
        if signature not in signatures:
            signatures.append(signature)
    if 0 <= choice < len(signatures):
        return signatures[choice]
    return None


def unresolved_part_conflicts(
    source_rows: list[dict[str, str]],
    conflict_choices: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    unresolved = []
    for conflict in detect_part_conflicts(source_rows):
        code = str(conflict["code"])
        if conflict.get("high_confidence"):
            continue
        if _selected_signature(code, source_rows, conflict_choices) is None:
            unresolved.append(conflict)
    return unresolved


def build_records(
    path: Path,
    merge_conflicts: bool = False,
    conflict_choices: dict[str, object] | None = None,
    include_shields: bool = False,
) -> list[dict[str, object]]:
    groups: "OrderedDict[tuple, dict[str, object]]" = OrderedDict()
    source_rows, _ = load_source(path, include_shields=include_shields)
    conflicts_by_code = {str(conflict["code"]): conflict for conflict in detect_part_conflicts(source_rows)}
    selected_by_code: dict[str, tuple[str, str, str, str, str]] = {}
    if merge_conflicts:
        for code, conflict in conflicts_by_code.items():
            selected = _selected_signature(code, source_rows, conflict_choices)
            if selected is None and conflict.get("high_confidence"):
                recommended = conflict.get("recommended_signature")
                if isinstance(recommended, dict):
                    selected = tuple(str(recommended.get(field) or "") for field in CONFLICT_FIELDS)
            if selected is not None:
                selected_by_code[code] = selected
    for row in source_rows:
        refs = sorted({normalize_ref(r) for r in split_refs(row.get("reference"))}, key=natural_key)
        code = row.get("part_number", "").strip()
        signature = _row_signature(row)
        if merge_conflicts and (code not in conflicts_by_code or code in selected_by_code):
            key = (code,)
        else:
            key = (code, *signature)
        if key not in groups:
            groups[key] = {
                "code": code,
                "refs": set(),
                **{field: [] for field in (*CONFLICT_FIELDS, *BOM_OPTIONAL_FIELDS)},
            }
        for field in CONFLICT_FIELDS:
            groups[key][field].append(row.get(field, "").strip())
        for field in BOM_OPTIONAL_FIELDS:
            if field not in CONFLICT_FIELDS:
                groups[key][field].append(row.get(field, "").strip())
        groups[key]["refs"].update(refs)
    records = []
    for group in groups.values():
        refs = sorted(group["refs"], key=natural_key)
        selected = selected_by_code.get(str(group["code"])) if merge_conflicts else None
        record = {
            "code": group["code"],
            "name": selected[0] if selected else _representative(group["name"], "name"),
            "model": selected[1] if selected else _representative(group["model"], "model"),
            "desc": selected[2] if selected else _representative(group["desc"], "desc"),
            "grade": selected[3] if selected else _representative(group["grade"], "grade"),
            "refs": refs,
            "qty": len(refs),
        }
        for field in BOM_OPTIONAL_FIELDS:
            if selected is not None and field in CONFLICT_FIELDS:
                record[field] = selected[CONFLICT_FIELDS.index(field)]
            else:
                record[field] = _representative(group[field], field)
        records.append(record)
    return records


def _extra_records(extras: list[dict[str, object]] | None) -> list[dict[str, object]]:
    out = []
    for extra in extras or []:
        code = str(extra.get("code") or "").strip()
        if not code:
            continue
        refs = sorted({normalize_ref(r) for r in split_refs(extra.get("refs"))}, key=natural_key)
        qty_raw = str(extra.get("qty") or "").strip()
        qty = int(qty_raw) if qty_raw.isdigit() else (len(refs) if refs else 1)
        out.append({
            "code": code, "name": str(extra.get("name") or "").strip(), "model": str(extra.get("model") or "").strip(),
            "desc": str(extra.get("desc") or "").strip(), "grade": "", "refs": refs, "qty": qty,
            **{field: FIELD_DEFAULTS.get(field, "") for field in BOM_OPTIONAL_FIELDS},
        })
    return out


def _autosize(ws) -> None:
    for column in ws.columns:
        width = min(max((len(str(cell.value or "")) for cell in column), default=4) + 2, 60)
        ws.column_dimensions[column[0].column_letter].width = width


def _sheet_title(name: str, suffix: str) -> str:
    base = re.sub(r'[\\/*?:\[\]]', "_", name or "BOM")
    return (base + suffix)[:31] or "BOM"


def _safe_filename_component(value: str) -> str:
    text = str(value or "BOM").strip()
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", text)
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text or "BOM"


def _rec_value(rec: dict[str, object], key: str) -> object:
    value = rec.get(key)
    if value is None or value == "":
        return FIELD_DEFAULTS.get(key, "")
    return value


def _plm_row(rec: dict[str, object], parent_code: str, parent_desc: str) -> list[object]:
    return [
        parent_code,
        parent_desc,
        rec["code"],
        rec["name"],
        rec["model"],
        rec["desc"],
        _rec_value(rec, "unit"),
        rec["qty"],
        ",".join(rec["refs"]),
        _rec_value(rec, "remark"),
        rec["grade"],
        _rec_value(rec, "grade_remark"),
        _rec_value(rec, "alt_group"),
        _rec_value(rec, "alt_strategy"),
        _rec_value(rec, "alt_method"),
        _rec_value(rec, "alt_priority"),
        _rec_value(rec, "issue_method"),
        _rec_value(rec, "mrp"),
        _rec_value(rec, "jump_level"),
    ]


def write_plm(
    path: Path,
    records: list[dict[str, object]],
    parent_code: str,
    parent_desc: str,
    name: str,
    template: Path | None = None,
) -> None:
    """优先复制 PLM 模板（保留合并表头、配色、边框、默认值），把数据套用数据行样式填入。"""
    from copy import copy
    from openpyxl import Workbook
    from openpyxl.styles import Font

    rows_data = [_plm_row(rec, parent_code, parent_desc) for rec in records]

    if template and Path(template).exists():
        with open_bom_workbook(template) as wb:
            ws = wb.worksheets[0]
            # 捕获模板首个数据行（第3行）每列样式，用于新数据行
            styles: dict[int, tuple] = {}
            if ws.max_row >= 3:
                for col in range(1, ws.max_column + 1):
                    cell = ws.cell(3, col)
                    styles[col] = (copy(cell.font), copy(cell.fill), copy(cell.border), copy(cell.alignment), cell.number_format)
                ws.delete_rows(3, ws.max_row - 2)  # 删除模板自带示例数据 + 脚注，保留 1-2 行表头
            for i, values in enumerate(rows_data):
                for col, val in enumerate(values, start=1):
                    cell = ws.cell(3 + i, col, val)
                    style = styles.get(col)
                    if style:
                        cell.font, cell.fill, cell.border, cell.alignment, cell.number_format = (
                            copy(style[0]), copy(style[1]), copy(style[2]), copy(style[3]), style[4],
                        )
            try:
                ws.title = _sheet_title(name, "")
            except Exception:
                pass
            wb.save(path)
        return

    # 无模板时从零生成（降级）
    wb = Workbook()
    try:
        ws = wb.active
        ws.title = _sheet_title(name, "")
        ws.append(PLM_R1)
        ws.append(PLM_HEADERS)
        for values in rows_data:
            ws.append(values)
        for cell in ws[2]:
            cell.font = Font(bold=True)
        _autosize(ws)
        wb.save(path)
    finally:
        wb.close()


def write_oa(path: Path, records: list[dict[str, object]], parent_code: str, parent_desc: str, name: str) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    try:
        ws = wb.active
        ws.title = _sheet_title(name, "_OA")
        ws.append(OA_HEADERS)
        for rec in records:
            ws.append([
                "",
                parent_code,
                parent_desc,
                rec["code"],
                rec["desc"],
                rec["qty"],
                _rec_value(rec, "unit"),
                ",".join(rec["refs"]),
                _rec_value(rec, "remark"),
                _rec_value(rec, "alt_group"),
                _rec_value(rec, "alt_strategy"),
                _rec_value(rec, "alt_method"),
                rec["grade"],
                _rec_value(rec, "issue_method"),
                _rec_value(rec, "mrp"),
                _rec_value(rec, "jump_level"),
            ])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        _autosize(ws)
        wb.save(path)
    finally:
        wb.close()


def write_nc_summary(path: Path, excluded: list[list[object]], name: str) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    try:
        ws = wb.active
        ws.title = _sheet_title(name, "_NC")
        ws.append(NC_HEADERS)
        for row in excluded:
            ws.append(row)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        _autosize(ws)
        wb.save(path)
    finally:
        wb.close()


def process(
    source_path: Path,
    formats: list[str],
    parent_code: str,
    parent_desc: str,
    name: str,
    extras: list[dict[str, object]] | None,
    out_dir: Path,
    stamp: str,
    template: Path | None = None,
    merge_conflicts: bool = False,
    conflict_choices: dict[str, object] | None = None,
    confirm_shields: bool = False,
) -> dict[str, object]:
    name = (name or source_path.stem).strip() or "BOM"
    parent_code = (parent_code or "").strip()
    parent_desc = (parent_desc or name).strip()

    source_rows_for_checks, _ = load_source(source_path, include_shields=True)
    shield_candidates = detect_shield_candidates(source_rows_for_checks)
    source_rows, excluded = load_source(source_path, include_shields=confirm_shields)
    conflicts = detect_part_conflicts(source_rows)
    unresolved_conflicts = (
        unresolved_part_conflicts(source_rows, conflict_choices)
        if merge_conflicts
        else []
    )
    records = _extra_records(extras) + build_records(
        source_path,
        merge_conflicts=merge_conflicts,
        conflict_choices=conflict_choices,
        include_shields=confirm_shields,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    base = _safe_filename_component(f"{name}_{stamp}")
    outputs: list[Path] = []
    if "plm" in formats:
        plm = out_dir / f"{base}_PLM_BOM.xlsx"
        write_plm(plm, records, parent_code, parent_desc, name, template)
        outputs.append(plm)
    if "oa" in formats:
        oa = out_dir / f"{base}_OA_BOM.xlsx"
        write_oa(oa, records, parent_code, parent_desc, name)
        outputs.append(oa)
    nc = out_dir / f"{base}_NC未贴汇总.xlsx"
    write_nc_summary(nc, excluded, name)

    return {
        "outputs": outputs,
        "nc_summary": nc,
        "records": records,
        "summary": {
            "name": name,
            "parent_code": parent_code or "(未填)",
            "records": len(records),
            "total_positions": sum(rec["qty"] for rec in records),
            "excluded": len(excluded),
            "extras": len(_extra_records(extras)),
            "conflicts": len(conflicts),
            "recommended_conflicts": sum(1 for conflict in conflicts if conflict.get("high_confidence")),
            "unresolved_conflicts": len(unresolved_conflicts),
            "merge_conflicts": merge_conflicts,
            "shield_candidates": len(shield_candidates),
            "confirm_shields": confirm_shields,
        },
        "conflicts": conflicts,
        "unresolved_conflicts": unresolved_conflicts,
        "shield_candidates": shield_candidates,
    }
