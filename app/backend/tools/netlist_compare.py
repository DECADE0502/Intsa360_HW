from __future__ import annotations

from pathlib import Path

from app.backend.parsers.refs import natural_key
from app.backend.tools.common import (
    USER_INPUT_EXCEPTIONS,
    _compare,
    _error,
    _is_critical_net,
    _natural_join,
    _net_signature,
    _output_dir,
    _parse_net_file,
    _parse_part_file_optional,
    _required_folder,
    _result,
    _table,
    _timestamp,
    _user_error,
    _write_sheets,
)
def _net_item(
    key: str,
    status: str,
    kind: str,
    left: dict[str, object] | None,
    right: dict[str, object] | None,
    diff: list[str],
    message: str,
    severity: str = "medium",
) -> dict[str, object]:
    if status == "关键网络变化":
        severity = "high"
    return {
        "key": key,
        "status": status,
        "kind": kind,
        "left": left,
        "right": right,
        "diff": diff,
        "message": message,
        "severity": severity,
        "critical": _is_critical_net(key) or (left and _is_critical_net(str(left.get("网络", "")))) or (right and _is_critical_net(str(right.get("网络", "")))),
    }


def _build_netlist_review(nets1: dict[str, dict[str, list[str]]], nets2: dict[str, dict[str, list[str]]], package_rows: list[list[object]]) -> dict[str, object]:
    sig1: dict[tuple[str, ...], list[str]] = {}
    sig2: dict[tuple[str, ...], list[str]] = {}
    for name, data in nets1.items():
        sig1.setdefault(_net_signature(data), []).append(name)
    for name, data in nets2.items():
        sig2.setdefault(_net_signature(data), []).append(name)

    left_node_to_net = {node: name for name, data in nets1.items() for node in data.get("nodes", [])}
    right_node_to_net = {node: name for name, data in nets2.items() for node in data.get("nodes", [])}
    covered_left: set[str] = set()
    covered_right: set[str] = set()
    items: list[dict[str, object]] = []
    status_counts = {"rename": 0, "split": 0, "merge": 0, "node_change": 0, "added": 0, "removed": 0, "package": 0, "same": 0}

    def side(name: str, data: dict[str, list[str]]) -> dict[str, object]:
        return {"网络": name, "位号": _natural_join(data.get("refs", [])), "节点": _natural_join(data.get("nodes", [])), "节点数": len(data.get("nodes", []))}

    for signature, left_names in sig1.items():
        right_names = sig2.get(signature, [])
        if len(left_names) == 1 and len(right_names) == 1 and left_names[0] != right_names[0]:
            left_name, right_name = left_names[0], right_names[0]
            covered_left.add(left_name)
            covered_right.add(right_name)
            status_counts["rename"] += 1
            items.append(_net_item(
                f"{left_name} -> {right_name}",
                "网络改名",
                "rename",
                side(left_name, nets1[left_name]),
                side(right_name, nets2[right_name]),
                ["网络名"],
                "节点集合完全一致，仅网络名变化。",
                "low",
            ))

    for left_name, left_data in nets1.items():
        if left_name in covered_left or left_name in nets2:
            continue
        nodes = set(left_data.get("nodes", []))
        targets = sorted({right_node_to_net[node] for node in nodes if node in right_node_to_net}, key=natural_key)
        if len(targets) >= 2 and nodes and all(node in right_node_to_net for node in nodes):
            covered_left.add(left_name)
            covered_right.update(targets)
            status_counts["split"] += 1
            items.append(_net_item(
                left_name,
                "疑似拆网",
                "split",
                side(left_name, left_data),
                {"网络": ",".join(targets), "节点": _natural_join(node for name in targets for node in nets2[name].get("nodes", []))},
                ["节点"],
                "旧版一个网络的节点在新版分散到多个网络。",
                "high",
            ))

    for right_name, right_data in nets2.items():
        if right_name in covered_right or right_name in nets1:
            continue
        nodes = set(right_data.get("nodes", []))
        sources = sorted({left_node_to_net[node] for node in nodes if node in left_node_to_net}, key=natural_key)
        if len(sources) >= 2 and nodes and all(node in left_node_to_net for node in nodes):
            covered_right.add(right_name)
            covered_left.update(sources)
            status_counts["merge"] += 1
            items.append(_net_item(
                right_name,
                "疑似并网",
                "merge",
                {"网络": ",".join(sources), "节点": _natural_join(node for name in sources for node in nets1[name].get("nodes", []))},
                side(right_name, right_data),
                ["节点"],
                "旧版多个网络的节点在新版合并到一个网络。",
                "high",
            ))

    for name in sorted(set(nets1) | set(nets2), key=natural_key):
        if name in covered_left or name in covered_right:
            continue
        in1, in2 = name in nets1, name in nets2
        if in1 and not in2:
            status_counts["removed"] += 1
            items.append(_net_item(name, "网络删除", "removed", side(name, nets1[name]), None, ["节点"], "该网络只存在于网表1。", "medium"))
        elif in2 and not in1:
            status_counts["added"] += 1
            items.append(_net_item(name, "网络新增", "added", None, side(name, nets2[name]), ["节点"], "该网络只存在于网表2。", "medium"))
        else:
            left_nodes = set(nets1[name].get("nodes", []))
            right_nodes = set(nets2[name].get("nodes", []))
            if left_nodes != right_nodes:
                status_counts["node_change"] += 1
                status = "关键网络变化" if _is_critical_net(name) else "节点变化"
                items.append(_net_item(
                    name,
                    status,
                    "node_change",
                    side(name, nets1[name]),
                    side(name, nets2[name]),
                    ["节点"],
                    "同名网络的连接节点发生变化。",
                    "high" if _is_critical_net(name) else "medium",
                ))
            else:
                status_counts["same"] += 1

    for row in package_rows:
        ref = str(row[0])
        status_counts["package"] += 1
        items.append(_net_item(
            f"器件:{ref}",
            "封装变化",
            "package",
            {"位号": ref, "封装": row[1]},
            {"位号": ref, "封装": row[2]},
            ["封装"],
            "同一位号在两版网表中的封装不同。",
            "medium",
        ))

    priority = {"high": 0, "medium": 1, "low": 2}
    focus_items = sorted([item for item in items if item["status"] != "一致"], key=lambda item: (priority.get(str(item.get("severity")), 9), natural_key(str(item.get("key", "")))))[:300]
    return {
        "items": items,
        "focus_items": focus_items,
        "status_counts": status_counts,
        "review_guide": {
            "网络改名": "节点集合一致但网络名变化，通常用于确认命名整理或跨页网络名变更是否符合预期。",
            "节点变化": "同名网络的 pin 连接发生变化，需要确认新增/删除节点是否为设计变更。",
            "关键网络变化": "电源、时钟、复位、高速或存储相关网络发生连接变化，优先人工复核。",
            "疑似拆网": "旧版一个网络在新版拆成多个网络，重点确认是否误断开。",
            "疑似并网": "旧版多个网络在新版合成一个网络，重点确认是否误短接。",
            "封装变化": "同位号封装变化，需要确认 PCB footprint 和 BOM 描述同步。",
        },
    }


def _run_netlist_compare_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    net1, error = _required_folder(params, "netlist1", "网表1文件夹")
    if error:
        return _error("netlist_compare", error)
    net2, error = _required_folder(params, "netlist2", "网表2文件夹")
    if error:
        return _error("netlist_compare", error)
    nets1 = _parse_net_file(net1)
    nets2 = _parse_net_file(net2)
    parts1, part_warning1 = _parse_part_file_optional(net1)
    parts2, part_warning2 = _parse_part_file_optional(net2)
    warnings = [warning for warning in [part_warning1, part_warning2] if warning]

    rows = []
    package_rows = []
    compare_items: list[dict[str, object]] = []

    def net_side(refs: str, nodes: str) -> dict[str, object]:
        return {"位号": refs, "节点": nodes}

    for name in sorted(set(nets1) | set(nets2)):
        in1, in2 = name in nets1, name in nets2
        left_refs = _natural_join(nets1.get(name, {}).get("refs", []))
        right_refs = _natural_join(nets2.get(name, {}).get("refs", []))
        left_nodes = _natural_join(nets1.get(name, {}).get("nodes", []))
        right_nodes = _natural_join(nets2.get(name, {}).get("nodes", []))
        if not in1:
            status, kind, diff = "仅网表2存在", "only_right", ["位号", "节点"]
        elif not in2:
            status, kind, diff = "仅网表1存在", "only_left", ["位号", "节点"]
        elif left_nodes != right_nodes:
            status, kind, diff = "网络节点差异", "diff", ["节点"]
            if left_refs != right_refs:
                diff.insert(0, "位号")
        else:
            status, kind, diff = "一致", "same", []
        rows.append([name, left_refs, left_nodes, right_nodes, right_refs, status])
        compare_items.append(
            {
                "key": name,
                "status": status,
                "kind": kind,
                "left": net_side(left_refs, left_nodes) if in1 else None,
                "right": net_side(right_refs, right_nodes) if in2 else None,
                "diff": diff,
            }
        )

    for ref in sorted(set(parts1) | set(parts2)):
        if parts1.get(ref) != parts2.get(ref):
            in1, in2 = ref in parts1, ref in parts2
            if not in1:
                kind = "only_right"
            elif not in2:
                kind = "only_left"
            else:
                kind = "diff"
            package_rows.append([ref, parts1.get(ref, ""), parts2.get(ref, ""), "封装差异"])
            compare_items.append(
                {
                    "key": f"器件:{ref}",
                    "status": "封装差异",
                    "kind": kind,
                    "left": {"封装": parts1[ref]} if in1 else None,
                    "right": {"封装": parts2[ref]} if in2 else None,
                    "diff": ["封装"] if kind == "diff" else [],
                }
            )

    headers = ["网络", "网表1位号", "网表1节点", "网表2节点", "网表2位号", "状态"]
    package_headers = ["位号", "网表1封装", "网表2封装", "状态"]
    output = _output_dir(params, root, "netlist") / f"网表比较差异_{_timestamp()}.xlsx"
    _write_sheets(output, [("网络节点差异", headers, rows), ("器件封装差异", package_headers, package_rows)])
    diff_count = sum(1 for row in rows if row[-1] != "一致")
    table = _table(headers, rows, status_col=5, diff_pairs=[[2, 3]])
    package_table = _table(package_headers, package_rows, status_col=3, diff_pairs=[[1, 2]])
    compare = _compare("对象", "网表1", "网表2", ["节点", "封装"], compare_items)
    review = _build_netlist_review(nets1, nets2, package_rows)
    result = _result(
        "netlist_compare",
        [output],
        {
            "diff_count": diff_count + len(package_rows),
            "node_diffs": diff_count,
            "package_diffs": len(package_rows),
            "package_check": "skipped" if warnings else "ok",
            "critical_changes": sum(1 for item in review["items"] if item.get("critical") and item.get("status") != "一致"),
        },
        table,
        compare,
    )
    result["package_table"] = package_table
    result["netlist_review"] = review
    result["warnings"] = warnings
    return result
def run_netlist_compare(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_netlist_compare_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("netlist_compare", exc)
