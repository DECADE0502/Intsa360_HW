from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.backend.capabilities import PluginStateRepository, load_capabilities
from app.backend.tool_registry import build_registry


ROOT = Path(__file__).resolve().parents[1]


class CapabilitiesRegistryTests(unittest.TestCase):
    def test_registry_contains_platform_name_and_existing_web_tools(self) -> None:
        data = load_capabilities(ROOT)

        self.assertEqual(data["platform"]["name"], "Insta360硬件提效平台")
        self.assertEqual(data["platform"]["cadence_menu"], "insta360_HW")
        web_ids = [item["id"] for item in data["capabilities"] if item["type"] == "web_tool"]
        self.assertEqual(
            web_ids,
            [
                "bom_process",
                "bom_compare",
                "bom_risk_check",
                "netlist_compare",
                "smt_package_check",
                "single_network_check",
            ],
        )

    def test_cadence_scripts_are_registered_but_disabled_for_capture_menu_by_default(self) -> None:
        data = load_capabilities(ROOT)
        scripts = [item for item in data["capabilities"] if item["type"] == "cadence_tcl"]

        self.assertGreaterEqual(len(scripts), 10)
        self.assertTrue(all("command" in item for item in scripts))
        self.assertTrue(all(item["show_in_platform"] is True for item in scripts))
        self.assertTrue(all(item["show_in_cadence"] is False for item in scripts))

    def test_build_registry_uses_capability_metadata_for_existing_runners(self) -> None:
        tools = build_registry(ROOT).list_tools()

        self.assertEqual(tools[0]["id"], "bom_process")
        self.assertEqual(tools[0]["name"], "BOM 处理")
        self.assertTrue(all(tool["status"] == "available" for tool in tools))

    def test_loading_capabilities_reads_plugin_state_once(self) -> None:
        original = PluginStateRepository._load
        calls = 0

        def counting_load(repository: PluginStateRepository):
            nonlocal calls
            calls += 1
            return original(repository)

        with patch.object(PluginStateRepository, "_load", autospec=True, side_effect=counting_load):
            load_capabilities(ROOT)

        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
