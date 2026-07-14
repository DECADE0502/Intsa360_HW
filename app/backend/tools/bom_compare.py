from __future__ import annotations

from pathlib import Path

from app.backend.parsers.refs import natural_key
from app.backend.tools.bom_risk import _risk_check
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
def _run_bom_compare_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
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
        "left": _risk_check(rows1),
        "right": _risk_check(rows2),
    }
    return result
def run_bom_compare(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_bom_compare_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("bom_compare", exc)
