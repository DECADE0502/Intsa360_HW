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

        self.assertEqual({"create_analysis_tools"}, defined)

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

    def test_tool_engines_do_not_import_sibling_engines(self) -> None:
        engine_modules = {
            "bom_compare",
            "bom_risk",
            "netlist_compare",
            "smt_package",
            "single_network",
        }
        tools_dir = ANALYSIS_TOOLS.parent
        for module_name in engine_modules:
            tree = ast.parse((tools_dir / f"{module_name}.py").read_text(encoding="utf-8-sig"))
            imported_siblings = {
                node.module.rsplit(".", 1)[-1]
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("app.backend.tools.")
                and node.module.rsplit(".", 1)[-1] in engine_modules - {module_name}
            }
            self.assertEqual(set(), imported_siblings, f"{module_name} imports sibling engines")


if __name__ == "__main__":
    unittest.main()
