from __future__ import annotations

import re
from pathlib import Path

from app.backend.parsers.refs import natural_key
from app.backend.tools.common import (
    USER_INPUT_EXCEPTIONS,
    _error,
    _is_critical_net,
    _natural_join,
    _output_dir,
    _parse_net_file,
    _required_folder,
    _result,
    _table,
    _timestamp,
    _user_error,
    _write_table,
)
_TP_PREFIX = ("TP", "JP", "Z_TP", "FID", "MK", "MH")
_NC_NET_RE = re.compile(r"(^|[^A-Z0-9])(NC|NOCONNECT|NO_CONNECT|DNP)([^A-Z0-9]|$)", re.IGNORECASE)
_POWER_NET_RE = re.compile(r"(^|[^A-Z0-9])(GND|AGND|DGND|PGND|VSS|VDD|VCC|VBAT|VSYS|SYS|POWER|BUCK|LDO|3V3|1V8|5V)([^A-Z0-9]|$)", re.IGNORECASE)
_TEST_NET_RE = re.compile(r"(TP|TEST|PROBE|FID|MARK|JTAG|SWD|UART_DBG|DEBUG)", re.IGNORECASE)
_MECHANICAL_NET_RE = re.compile(r"(HOLE|MOUNT|MTG|SCREW|SHIELD|CHASSIS|GASKET)", re.IGNORECASE)

def _single_network_item(name: str, data: dict[str, list[str]]) -> dict[str, object]:
    refs = data.get("refs", [])
    pins = data.get("pins", [])
    nodes = data.get("nodes", [])
    blob = " ".join([name, *refs, *pins, *nodes]).upper()
    is_nc = bool(_NC_NET_RE.search(blob)) or name.upper().startswith("NC")
    is_single_ref = len(refs) == 1
    is_testpoint = any(str(ref).upper().startswith(_TP_PREFIX) for ref in refs) or bool(_TEST_NET_RE.search(blob))
    is_mechanical = any(str(ref).upper().startswith(("H", "MH", "MTG")) for ref in refs) or bool(_MECHANICAL_NET_RE.search(blob))
    is_power = bool(_POWER_NET_RE.search(blob))
    is_critical = _is_critical_net(name)

    if is_nc:
        category = "NC 网络"
        severity = "medium"
        note = "网络名或节点带 NC/No Connect 特征，确认是否为原理图有意悬空。"
        hint = "重点看该 pin 是否应在符号上标 NC，或是否误漏连。"
        kind = "nc"
    elif is_mechanical:
        category = "机械/安装孔"
        severity = "info"
        note = "安装孔、螺丝孔、屏蔽或结构连接常出现单点网络。"
        hint = "通常只需确认是否为结构连接或接地孔。"
        kind = "mechanical"
    elif is_testpoint:
        category = "测试点/工艺"
        severity = "info"
        note = "测试点、调试点或工艺标记常为单点对象。"
        hint = "确认测试点是否需要保留，是否应连接到目标信号。"
        kind = "testpoint"
    elif is_power:
        category = "电源/地"
        severity = "medium"
        note = "电源或地相关网络只有一个位号，需要确认是否孤岛、拼写错误或局部电源未连接。"
        hint = "优先检查电源符号、跨页端口和电源网络命名。"
        kind = "power"
    elif is_single_ref and is_critical:
        category = "重点复核"
        severity = "high"
        note = "关键网络只有一个位号，可能是悬空引脚、漏连或网络名不一致。"
        hint = "优先回到 Capture/PCB 逐 pin 确认，尤其是存储、高速、时钟、复位、接口网络。"
        kind = "focus"
    elif is_single_ref:
        category = "单一位号网络"
        severity = "medium"
        note = "该网络只连接到一个位号，需确认是否符合设计意图。"
        hint = "检查是否缺少电阻/电容/连接器另一端，或是否应标为 NC。"
        kind = "single_ref"
    else:
        category = "其他"
        severity = "low"
        note = "未命中 NC 或单一位号规则。"
        hint = "通常无需在单网络检查中复核。"
        kind = "other"

    return {
        "key": name,
        "net": name,
        "category": category,
        "kind": kind,
        "severity": severity,
        "refs": refs,
        "pins": pins,
        "nodes": nodes,
        "ref_count": len(refs),
        "pin_count": len(nodes),
        "is_nc": is_nc,
        "is_single_ref": is_single_ref,
        "is_mechanical": is_mechanical,
        "is_testpoint": is_testpoint,
        "is_power": is_power,
        "critical": is_critical,
        "note": note,
        "review_hint": hint,
    }


def _build_single_network_review(nets: dict[str, dict[str, list[str]]]) -> dict[str, object]:
    items: list[dict[str, object]] = []
    status_counts = {
        "focus": 0,
        "single_ref": 0,
        "nc": 0,
        "power": 0,
        "testpoint": 0,
        "mechanical": 0,
        "other": 0,
    }
    for name, data in sorted(nets.items(), key=lambda item: natural_key(item[0])):
        item = _single_network_item(name, data)
        if item["is_nc"] or item["is_single_ref"]:
            items.append(item)
            kind = str(item["kind"])
            status_counts[kind if kind in status_counts else "other"] += 1

    priority = {"high": 0, "medium": 1, "info": 2, "low": 3}
    focus_items = sorted(
        [
            item
            for item in items
            if item["kind"] in {"focus", "single_ref", "nc", "power"}
        ],
        key=lambda item: (priority.get(str(item.get("severity")), 9), natural_key(str(item.get("net", "")))),
    )[:500]
    return {
        "items": items,
        "focus_items": focus_items,
        "status_counts": status_counts,
        "review_guide": {
            "重点复核": "存储、高速、时钟、复位、接口等关键网络只有一个位号时，优先确认是否漏连或网络名不一致。",
            "单一位号网络": "普通网络只连到一个位号，常见于悬空脚、预留脚、孤立网络或漏连，需要人工确认。",
            "NC 网络": "NC/No Connect 网络需要确认是否为设计意图，避免把应连接的 pin 错标为 NC。",
            "电源/地": "电源或地网络单点连接可能是局部电源孤岛、跨页端口拼写问题或设计预留。",
            "测试点/工艺": "测试点、调试点、拼板基准点常出现单点对象，通常按工艺需求确认即可。",
            "机械/安装孔": "安装孔、螺丝、屏蔽或结构连接可能是单点网络，通常不按电气漏连处理。",
        },
    }
def _run_single_network_check_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    netlist, error = _required_folder(params, "netlist", "网表文件夹")
    if error:
        return _error("single_network_check", error)
    nets = _parse_net_file(netlist)
    review = _build_single_network_review(nets)
    rows = [
        [
            item["net"],
            item["category"],
            _natural_join(item.get("refs") or []),
            _natural_join(item.get("nodes") or []),
            item["ref_count"],
            item["pin_count"],
            item["severity"],
            item["note"],
        ]
        for item in review["items"]
    ]
    headers = ["网络", "类型", "位号", "节点/Pin", "位号数", "节点数", "优先级", "说明"]
    output = _output_dir(params, root, "netlist") / f"单网络检查结果_{_timestamp()}.xlsx"
    _write_table(output, "单网络检查", headers, rows)
    table = _table(headers, rows, status_col=1)
    counts = review["status_counts"]
    result = _result(
        "single_network_check",
        [output],
        {
            "total_nets": len(nets),
            "matched_count": len(rows),
            "focus_count": len(review["focus_items"]),
            "nc_count": counts["nc"],
            "single_ref_count": counts["single_ref"] + counts["focus"] + counts["power"],
            "mechanical_count": counts["mechanical"],
            "testpoint_count": counts["testpoint"],
        },
        table,
    )
    result["single_network_review"] = review
    return result
def run_single_network_check(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_single_network_check_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("single_network_check", exc)
