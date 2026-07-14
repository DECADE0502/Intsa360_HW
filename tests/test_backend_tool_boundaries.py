from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_TOOLS = ROOT / "app" / "backend" / "tools" / "analysis_tools.py"


class BackendToolBoundaryTests(unittest.TestCase):
    def test_analysis_tools_is_only_a_compatibility_facade(self) -> None:
        tree = ast.parse(ANALYSIS_TOOLS.read_text(encoding="utf-8-sig"))
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        implementation_functions = {
            "_read_bom_rows",
            "_run_bom_compare_impl",
            "_risk_check",
            "_run_bom_risk_check_impl",
            "_parse_net_file",
            "_build_netlist_review",
            "_build_smt_package_review",
            "_build_single_network_review",
        }
        self.assertTrue(
            implementation_functions.isdisjoint(defined),
            f"analysis_tools.py still owns tool implementations: "
            f"{sorted(implementation_functions & defined)}",
        )

    def test_each_tool_has_an_independent_module(self) -> None:
        expected = {
            "common.py",
            "bom_compare.py",
            "bom_risk.py",
            "bom_process_adapter.py",
            "netlist_compare.py",
            "smt_package.py",
            "single_network.py",
        }
        tools_dir = ANALYSIS_TOOLS.parent
        present = {path.name for path in tools_dir.glob("*.py")}
        self.assertTrue(expected.issubset(present), sorted(expected - present))


if __name__ == "__main__":
    unittest.main()
