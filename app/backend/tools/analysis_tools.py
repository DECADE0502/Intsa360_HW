from __future__ import annotations

from pathlib import Path

from app.backend.tool_registry import Tool
from app.backend.tools.bom_compare import run_bom_compare
from app.backend.tools.bom_process_adapter import run_bom_process
from app.backend.tools.bom_risk import run_bom_risk_check, run_generic_bom_import
from app.backend.tools.common import _parse_net_file, _parse_part_file
from app.backend.tools.netlist_compare import run_netlist_compare
from app.backend.tools.single_network import run_single_network_check
from app.backend.tools.smt_package import _package_matches, run_smt_package_check


def create_analysis_tools(root: Path) -> list[Tool]:
    return [
        Tool("bom_process", "BOM 处理", "Capture 原始 BOM → 可导入 PLM/OA 成品（过滤、合并、可加 PCB/屏蔽支架等附加物料）。", "available", "BOM", lambda params=None: run_bom_process(root, params or {})),
        Tool("bom_compare", "BOM 差异比较", "比较两个 BOM Excel，输出位号、编号、描述、数量差异报告。", "available", "BOM", lambda params=None: run_bom_compare(root, params or {})),
        Tool("bom_risk_check", "BOM 风险检查", "单份 BOM 导入前体检：PCB/屏蔽支架/NC 未贴/机构件/测试点/重复位号/数量一致性/eMMC-DDR 版本提醒。", "available", "BOM", lambda params=None: run_bom_risk_check(root, params or {})),
        Tool("netlist_compare", "网表差异比较", "比较两个网表文件夹中的网络节点和器件信息。", "available", "Netlist", lambda params=None: run_netlist_compare(root, params or {})),
        Tool("smt_package_check", "贴片封装检查", "选择 Allegro 目录和已处理后的 PLM/OA 成品 BOM，检查网表封装与 BOM 型号/描述的一致性。", "available", "SMT", lambda params=None: run_smt_package_check(root, params or {})),
        Tool("single_network_check", "单网络检查", "提取 NC 网络和只有单一位号的网络，辅助硬件检查。", "available", "Netlist", lambda params=None: run_single_network_check(root, params or {})),
    ]
