from __future__ import annotations

import re
from pathlib import Path

from app.backend.parsers.refs import natural_key
from app.backend.tools.common import (
    USER_INPUT_EXCEPTIONS,
    _error,
    _output_dir,
    _parse_part_file,
    _read_bom_rows,
    _required_file,
    _required_folder,
    _result,
    _table,
    _timestamp,
    _user_error,
    _write_table,
)
def _package_tokens(value: str) -> set[str]:
    raw = str(value or "").upper()
    tokens = {token for token in re.split(r"[^A-Z0-9]+", raw) if len(token) >= 2}
    joined = re.sub(r"[^A-Z0-9]", "", raw)
    if joined:
        tokens.add(joined)
    return tokens


_COMMON_PACKAGE_SIZES = {
    "008004", "01005", "0201", "03015", "0402", "0603", "0805", "0806", "1005", "1206", "1210",
    "1608", "2012", "2016", "2520", "3216", "3225", "3528", "4020", "5032", "6032", "7343",
}

_VENDOR_SIZE_PATTERNS = [
    (re.compile(r"\b(CL03|GRM03|GJM03|0201X|RC0201|WR02|RTT01|0201WMF)"), "0201"),
    (re.compile(r"\b(CL05|GRM15[35]|GCM15[35]|GJM15[35]|TDK105|C0402|0402X|RC0402|WR04|RTT02|0402WMF)"), "0402"),
]


def _package_size_codes(value: str) -> set[str]:
    text = str(value or "").upper()
    found = {match.group(1) for match in re.finditer(r"(?<!\d)(\d{4,6})(?!\d)", text) if match.group(1) in _COMMON_PACKAGE_SIZES}
    found.update(match.group(1) for match in re.finditer(r"[CRL](\d{4})(?:[^0-9]|$)", text) if match.group(1) in _COMMON_PACKAGE_SIZES)
    for pattern, size in _VENDOR_SIZE_PATTERNS:
        if pattern.search(text):
            found.add(size)
    return found


def _package_matches(net_package: str, bom_text: str) -> tuple[bool, str]:
    net_sizes = _package_size_codes(net_package)
    bom_sizes = _package_size_codes(bom_text)
    if net_sizes and bom_sizes and not (net_sizes & bom_sizes):
        return False, "封装尺寸码冲突: 网表=" + ",".join(sorted(net_sizes, key=natural_key)) + "; BOM=" + ",".join(sorted(bom_sizes, key=natural_key))

    net_tokens = _package_tokens(net_package)
    bom_tokens = _package_tokens(bom_text)
    if not net_tokens or not bom_tokens:
        return False, "缺少可比对封装信息"
    common = net_tokens & bom_tokens
    if common:
        return True, "匹配到封装关键词: " + ",".join(sorted(common, key=natural_key)[:5])
    long_net = {t for t in net_tokens if len(t) >= 5}
    long_bom = {t for t in bom_tokens if len(t) >= 5}
    for a in long_net:
        for b in long_bom:
            if a in b or b in a:
                return True, f"封装字段近似匹配: {a}/{b}"
    common_sizes = net_sizes & bom_sizes
    if common_sizes:
        return True, "匹配到封装尺寸码: " + ",".join(sorted(common_sizes, key=natural_key)[:5])
    return False, "网表封装未出现在 BOM 描述/名称/封装字段"


_SMT_HIGH_RISK_RE = re.compile(
    r"(^|[^A-Z0-9])(BGA|WLCSP|CSP|QFN|DFN|LGA|QFP|BTB|FPC|FFC|USB|HDMI|TYPEC|EMMC|UFS|DDR|LPDDR|MIPI|CSI|DSI)",
    re.IGNORECASE,
)


def _smt_status_key(status: str) -> str:
    return {
        "通过": "passed",
        "近似通过": "near",
        "需要确认": "manual",
        "BOM 缺位号": "missing_bom",
        "BOM 多余位号": "extra_bom",
        "同料多封装": "multi_package",
        "高风险封装": "high_risk",
        "NC 未贴跳过": "nc_skipped",
        "非贴片对象跳过": "non_smt_skipped",
    }.get(status, "manual")


def _smt_item(
    ref: str,
    status: str,
    net_package: str = "",
    bom_row: dict[str, object] | None = None,
    note: str = "",
    severity: str = "medium",
    part_number: str = "",
) -> dict[str, object]:
    row = bom_row or {}
    return {
        "key": f"{status}:{ref}:{part_number or row.get('part_number', '')}",
        "ref": ref,
        "status": status,
        "kind": _smt_status_key(status),
        "severity": severity,
        "part_number": part_number or str(row.get("part_number", "")),
        "net_package": net_package,
        "bom_package": str(row.get("package", "")),
        "model": str(row.get("model", "")),
        "description": str(row.get("description", "")),
        "name": str(row.get("name", "")),
        "grade": str(row.get("grade", "")),
        "note": note,
    }


def _is_high_risk_package(*values: object) -> bool:
    return bool(_SMT_HIGH_RISK_RE.search(" ".join(str(value or "") for value in values)))


def _is_nc_package(value: object) -> bool:
    text = str(value or "").upper()
    return bool(re.search(r"(^|[^A-Z0-9])NC([_/\\\-\s]|$)", text))


def _is_non_smt_netlist_part(ref: object, package: object) -> bool:
    ref_text = str(ref or "").upper()
    pkg = str(package or "").upper()
    if ref_text.startswith(("TP", "JP", "MTG", "MH")):
        return True
    if ref_text.startswith("H") and re.match(r"^H\d+", ref_text):
        return True
    return any(token in pkg for token in ["SHORT", "TP_", "MARK", "FID", "HOLE", "SCREW", "MTG", "MOUNT"])


def _build_smt_package_review(parts: dict[str, str], bom_rows: list[dict[str, object]]) -> dict[str, object]:
    by_ref = {ref: row for row in bom_rows for ref in row["refs"]}
    items: list[dict[str, object]] = []
    rows: list[list[object]] = []
    status_counts = {
        "passed": 0,
        "near": 0,
        "manual": 0,
        "missing_bom": 0,
        "extra_bom": 0,
        "multi_package": 0,
        "high_risk": 0,
        "nc_skipped": 0,
        "non_smt_skipped": 0,
    }

    for ref, package in sorted(parts.items(), key=lambda item: natural_key(item[0])):
        bom_row = by_ref.get(ref)
        if not bom_row:
            if _is_nc_package(package):
                status = "NC 未贴跳过"
                note = "网表中为 NC/未贴器件，最终 PCBA BOM 不包含该位号属于正常情况。"
                item = _smt_item(ref, status, package, None, note, "low")
            elif _is_non_smt_netlist_part(ref, package):
                status = "非贴片对象跳过"
                note = "测试点、短接、安装孔或工艺对象通常不进入最终贴片 BOM，未在 BOM 中出现时不按缺失处理。"
                item = _smt_item(ref, status, package, None, note, "low")
            else:
                status = "BOM 缺位号"
                note = "网表存在该位号，但 BOM 中没有找到。确认是否漏导、未贴或不应进入贴片 BOM。"
                item = _smt_item(ref, status, package, None, note, "high")
                rows.append([ref, package, "", "", "", status, note])
        else:
            desc = str(bom_row.get("description", ""))
            name = str(bom_row.get("name", ""))
            bom_package = str(bom_row.get("package", ""))
            model = str(bom_row.get("model", ""))
            ok, note = _package_matches(package, f"{desc} {name} {bom_package} {model}")
            if ok and note.startswith("封装字段近似匹配"):
                status = "近似通过"
                severity = "low"
            elif ok:
                status = "通过"
                severity = "low"
            else:
                status = "需要确认"
                severity = "medium"
            item = _smt_item(ref, status, package, bom_row, note, severity)
            table_status = "机器初筛通过" if status in {"通过", "近似通过"} else "请人工判断"
            rows.append([ref, package, bom_package or model, desc, name, table_status, note])
        status_counts[_smt_status_key(status)] += 1
        items.append(item)

    for ref in sorted(set(by_ref) - set(parts), key=natural_key):
        bom_row = by_ref[ref]
        note = "BOM 中存在该位号，但 pstxprt.dat 没有找到。确认是否机构/辅料、手工添加、或网表导出不完整。"
        item = _smt_item(ref, "BOM 多余位号", "", bom_row, note, "medium")
        items.append(item)
        status_counts["extra_bom"] += 1

    packages_by_part: dict[str, set[str]] = {}
    refs_by_part: dict[str, list[str]] = {}
    rows_by_part: dict[str, dict[str, object]] = {}
    for ref, package in parts.items():
        row = by_ref.get(ref)
        part_number = str(row.get("part_number", "") if row else "").strip()
        if not part_number:
            continue
        packages_by_part.setdefault(part_number, set()).add(package)
        refs_by_part.setdefault(part_number, []).append(ref)
        rows_by_part.setdefault(part_number, row)
    for part_number, packages in sorted(packages_by_part.items(), key=lambda item: natural_key(item[0])):
        normalized = {re.sub(r"[^A-Z0-9]", "", package.upper()) for package in packages if package}
        if len(normalized) <= 1:
            continue
        refs = sorted(refs_by_part.get(part_number, []), key=natural_key)
        note = "同一个物料编码对应多个网表封装：" + " / ".join(sorted(packages, key=natural_key))
        item = _smt_item(
            ",".join(refs),
            "同料多封装",
            " / ".join(sorted(packages, key=natural_key)),
            rows_by_part.get(part_number),
            note,
            "high",
            part_number,
        )
        item["refs"] = refs
        items.append(item)
        status_counts["multi_package"] += 1

    high_risk_seen: set[str] = set()
    for item in list(items):
        if item["status"] in {"BOM 缺位号", "同料多封装"}:
            continue
        if not _is_high_risk_package(item.get("net_package"), item.get("bom_package"), item.get("model"), item.get("description"), item.get("name")):
            continue
        ref = str(item.get("ref", ""))
        if ref in high_risk_seen:
            continue
        high_risk_seen.add(ref)
        note = "BGA/QFN/连接器/存储/高速相关封装，建议人工确认 footprint、焊盘、硬件版本和替代料一致性。"
        items.append(_smt_item(ref, "高风险封装", str(item.get("net_package", "")), {
            "part_number": item.get("part_number", ""),
            "package": item.get("bom_package", ""),
            "model": item.get("model", ""),
            "description": item.get("description", ""),
            "name": item.get("name", ""),
            "grade": item.get("grade", ""),
        }, note, "medium"))
        status_counts["high_risk"] += 1

    priority = {"high": 0, "medium": 1, "low": 2}
    focus_items = sorted(
        [item for item in items if item["status"] not in {"通过", "近似通过", "高风险封装", "NC 未贴跳过", "非贴片对象跳过"}],
        key=lambda item: (priority.get(str(item.get("severity")), 9), natural_key(str(item.get("ref", ""))), str(item.get("status", ""))),
    )[:500]
    return {
        "items": items,
        "focus_items": focus_items,
        "status_counts": status_counts,
        "table_rows": rows,
        "review_guide": {
            "通过": "网表封装和 BOM 封装/型号/描述中存在明确关键词匹配，通常可快速放行。",
            "近似通过": "封装字段存在包含关系，建议抽查命名是否为同一 footprint。",
            "需要确认": "网表封装没有在 BOM 描述、名称、型号或封装字段中匹配到，需要人工核对。",
            "BOM 缺位号": "pstxprt.dat 中有位号但 BOM 没有，重点确认是否漏导或不应入 BOM。",
            "BOM 多余位号": "BOM 中有位号但网表没有，重点确认手工添加、机构辅料或位号错误。",
            "同料多封装": "同一个物料编码出现在多个 footprint 上，通常需要拆料号或确认封装兼容。",
            "高风险封装": "BGA/QFN/连接器/存储/高速相关物料变更成本高，建议人工二次确认。",
            "NC 未贴跳过": "网表中标为 NC/未贴且最终 PCBA BOM 不包含时，不作为缺失异常处理。",
            "非贴片对象跳过": "测试点、短接、安装孔或工艺对象不进入最终贴片 BOM 时，不作为缺失异常处理。",
        },
    }
def _run_smt_package_check_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    netlist, error = _required_folder(params, "netlist", "网表文件夹")
    if error:
        return _error("smt_package_check", error)
    bom, error = _required_file(params, "bom", "BOM 文件")
    if error:
        return _error("smt_package_check", error)
    parts = _parse_part_file(netlist)
    bom_rows = _read_bom_rows(bom)
    review = _build_smt_package_review(parts, bom_rows)
    rows = review["table_rows"]
    headers = ["位号", "网表封装", "BOM封装/型号", "描述", "名称", "状态", "说明"]
    output = _output_dir(params, root, "smt") / f"贴片封装检查结果_{_timestamp()}.xlsx"
    _write_table(output, "封装检查", headers, rows)
    counts = review["status_counts"]
    manual_count = counts["manual"] + counts["missing_bom"] + counts["extra_bom"] + counts["multi_package"]
    passed_count = counts["passed"] + counts["near"]
    table = _table(headers, rows, status_col=5)
    result = _result(
        "smt_package_check",
        [output],
        {
            "total": len(parts),
            "passed_count": passed_count,
            "near_count": counts["near"],
            "manual_count": manual_count,
            "missing_bom": counts["missing_bom"],
            "extra_bom": counts["extra_bom"],
            "multi_package": counts["multi_package"],
            "high_risk": counts["high_risk"],
        },
        table,
    )
    result["smt_package_review"] = {key: value for key, value in review.items() if key != "table_rows"}
    return result
def run_smt_package_check(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_smt_package_check_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("smt_package_check", exc)
