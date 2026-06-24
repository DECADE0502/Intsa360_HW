from __future__ import annotations

from app.backend.tool_registry import Tool


def planned_tools() -> list[Tool]:
    return [
        Tool(
            id="bom_compare",
            name="BOM 差异比较",
            description="比较两个 BOM Excel，输出位号、编号、描述、数量差异报告。",
            status="planned",
            category="BOM",
        ),
        Tool(
            id="netlist_compare",
            name="网表差异比较",
            description="比较两个网表文件夹中的网络节点和器件信息。",
            status="planned",
            category="Netlist",
        ),
        Tool(
            id="smt_package_check",
            name="贴片封装检查",
            description="检查网表封装信息与 BOM 描述/名称的一致性。",
            status="planned",
            category="SMT",
        ),
        Tool(
            id="single_network_check",
            name="单网络检查",
            description="提取 NC 网络和只有单一位号的网络，辅助硬件检查。",
            status="planned",
            category="Netlist",
        ),
    ]
