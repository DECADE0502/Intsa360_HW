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
        Tool("bom_process", "BOM 处理", "Capture 原始 BOM 转为可导入 PLM/OA 的成品 BOM，并输出 NC 与非贴片汇总。", "available", "BOM", lambda params=None: run_bom_process(root, params or {})),
        Tool("bom_compare", "BOM 差异比较", "从实际贴装、替代关系、原始行和元数据四层比较两份 BOM。", "available", "BOM", lambda params=None: run_bom_compare(root, params or {})),
        Tool("bom_risk_check", "BOM 风险检查", "检查单份 BOM 的位号、数量、物料属性、优选等级和高风险器件。", "available", "BOM", lambda params=None: run_bom_risk_check(root, params or {})),
        Tool("netlist_compare", "网表差异比较", "比较两个网表目录中的网络节点和器件连接。", "available", "Netlist", lambda params=None: run_netlist_compare(root, params or {})),
        Tool("smt_package_check", "贴片封装检查", "对照 Allegro 网表和已处理 BOM 检查封装一致性。", "available", "SMT", lambda params=None: run_smt_package_check(root, params or {})),
        Tool("single_network_check", "单网络检查", "提取 NC 网络和只有单一位号的网络，辅助原理图检查。", "available", "Netlist", lambda params=None: run_single_network_check(root, params or {})),
        Tool("smt_view", "贴片位号视图", "用 XY 坐标叠加成品 BOM 的贴装、NC、非贴片和资料差异状态。", "available", "SMT"),
    ]
