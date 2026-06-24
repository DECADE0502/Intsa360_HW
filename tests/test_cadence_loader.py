from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = "powershell"


class CadenceLoaderGenerationTests(unittest.TestCase):
    def test_cadence_loader_template_uses_ascii_top_menu_and_english_default_items(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Cadence.ps1").read_text(encoding="utf-8")
        template = (ROOT / "cadence" / "iac_bom_tool.tcl").read_text(encoding="utf-8")

        self.assertIn('"insta360_HW"', text)
        self.assertIn('[list "popup" "insta360_HW"', template)
        self.assertIn('"action" "Open Platform"', template)
        self.assertIn('"action" "Export and Process BOM"', template)
        self.assertNotIn('"action" "进入平台"', template)
        self.assertNotIn('"action" "导出并处理BOM"', template)
        self.assertIn('AddAccessoryMenu "insta360_HW" "Open Platform"', text)
        self.assertIn('AddAccessoryMenu "insta360_HW" "Export and Process BOM"', text)
        self.assertNotIn('AddAccessoryMenu "insta360_HW" "选中器件切换NC"', text)

    def test_root_does_not_keep_stale_insta360_bom_loader_copy(self) -> None:
        stale_loader = ROOT / "iac_bom_tool.tcl"

        self.assertFalse(stale_loader.exists())

    def test_generated_loader_is_gbk_encodable_and_uses_hidden_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "iac_bom_tool.tcl"
            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'Cadence.ps1'}'; "
                f"Write-CadenceLoader -ToolRoot '{ROOT}' -PythonPath 'C:/Python/python.exe' -OutputPath '{out}' | Out-Null"
            )

            subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                check=True,
                text=True,
                capture_output=True,
            )

            raw = out.read_bytes()
            self.assertNotEqual(raw[:3], b"\xef\xbb\xbf")
            decoded = raw.decode("gbk")
            self.assertIn('InsertXMLMenu [list [list "IACBOM"]', decoded)
            self.assertIn('"insta360_HW"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "Open Platform"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "Export and Process BOM"', decoded)
            self.assertNotIn('AddAccessoryMenu "insta360_HW" "进入平台"', decoded)
            self.assertNotIn('AddAccessoryMenu "insta360_HW" "导出并处理BOM"', decoded)
            self.assertNotIn('AddAccessoryMenu "insta360_HW" "选中器件切换NC"', decoded)
            self.assertNotIn("orcad_enhanced_tools.tcl", decoded)
            self.assertNotIn("rename RegisterAction", decoded)
            self.assertIn("launch_tool_suite_hidden.vbs", decoded)
            self.assertIn("wscript.exe", decoded)
            self.assertIn("proc ReadParts", decoded)
            self.assertIn("proc PartsToJson", decoded)
            self.assertIn("convert_cadence_bom.py", decoded)
            decoded.encode("gbk")

    def test_generated_loader_can_mount_enabled_tcl_scripts_without_renaming_registeraction(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Cadence.ps1").read_text(encoding="utf-8")

        self.assertIn("show_in_cadence", text)
        self.assertIn("Get-EnabledCadenceMenuItems", text)
        self.assertNotIn("rename RegisterAction", text)

    def test_generated_loader_injects_only_opt_in_cadence_script_menu_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "tool"
            (root / "cadence" / "modules").mkdir(parents=True)
            (root / "config").mkdir()
            (root / "cadence" / "modules" / "demo.tcl").write_text("proc ::Demo::Run {} {}\n", encoding="utf-8")
            (root / "cadence" / "iac_bom_tool.tcl").write_text(
                '\n'.join(
                    [
                        'set ::IAC_ROOT "{{TOOL_ROOT}}"',
                        'set ::IAC_PY   "python"',
                        'proc ::IAC::addAccessoryMenu { args } {',
                        '  AddAccessoryMenu "insta360_HW" "Open Platform" "::IAC::OpenTool"',
                        '  # {{CADENCE_SCRIPT_MENU_ITEMS}}',
                        '}',
                    ]
                ),
                encoding="utf-8",
            )
            (root / "config" / "capabilities.json").write_text(
                """
{
  "platform": {"name": "Insta360硬件提效平台", "cadence_menu": "insta360_HW"},
  "capabilities": [
    {"id": "enabled", "type": "cadence_tcl", "name": "启用脚本", "description": "", "category": "Cadence 脚本", "status": "available", "command": "::Demo::Run", "module": "cadence/modules/demo.tcl", "show_in_platform": true, "show_in_cadence": true},
    {"id": "disabled", "type": "cadence_tcl", "name": "禁用脚本", "description": "", "category": "Cadence 脚本", "status": "disabled", "command": "::Demo::Skip", "show_in_platform": true, "show_in_cadence": false}
  ]
}
""",
                encoding="utf-8",
            )
            out = tmp_path / "iac_bom_tool.tcl"
            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'Cadence.ps1'}'; "
                f"Write-CadenceLoader -ToolRoot '{root}' -PythonPath 'C:/Python/python.exe' -OutputPath '{out}' | Out-Null"
            )

            subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                check=True,
                text=True,
                capture_output=True,
            )

            decoded = out.read_bytes().decode("gbk")
            self.assertIn('source "$::IAC_ROOT/cadence/modules/demo.tcl"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "启用脚本" "::Demo::Run"', decoded)
            self.assertNotIn("禁用脚本", decoded)
            self.assertNotIn("rename RegisterAction", decoded)

    def test_capability_registry_requires_modules_for_enableable_cadence_scripts(self) -> None:
        data = json.loads((ROOT / "config" / "capabilities.json").read_text(encoding="utf-8"))
        for item in data["capabilities"]:
            if item["type"] != "cadence_tcl":
                continue
            if item["id"] in {
                "cadence_nc_toggle",
                "cadence_ground_name_visible",
                "cadence_ground_name_hidden",
                "cadence_reset_net_color",
                "cadence_nc_part_gray",
                "cadence_restore_part_color",
                "cadence_hide_u_value",
                "cadence_show_u_value",
                "cadence_hide_all_value",
                "cadence_show_all_value",
                "cadence_hide_u_pin_names",
                "cadence_net_name_replace",
                "cadence_grayed_part_value_nc",
                "cadence_randomize_net_names",
                "cadence_delete_all_graphic",
                "cadence_delete_text_titleblocks",
                "cadence_required_sanitize",
                "cadence_required_restore",
                "cadence_schematic_obfuscation",
            }:
                self.assertTrue(item["can_enable"])
                self.assertTrue(item["module"].startswith("cadence/modules/"))
            else:
                self.assertFalse(item.get("can_enable", False), item["id"])

    def test_high_risk_enhanced_tools_are_split_into_safe_module(self) -> None:
        data = json.loads((ROOT / "config" / "capabilities.json").read_text(encoding="utf-8"))
        expected = {
            "cadence_net_name_replace": "::capMenuUtil::showNetNameExchangeDialog",
            "cadence_grayed_part_value_nc": "::capMenuUtil::confirmGrayedPartToNC",
            "cadence_randomize_net_names": "::capMenuUtil::confirmRandomizeNetNames",
            "cadence_delete_all_graphic": "::capMenuUtil::confirmDeleteAllGraphic",
            "cadence_delete_text_titleblocks": "::capMenuUtil::confirmDeleteTextTitleblocks",
            "cadence_required_sanitize": "::capRequiredSanitize::sanitizeFromMenu",
            "cadence_required_restore": "::capRequiredSanitize::restoreFromMenu",
            "cadence_schematic_obfuscation": "::capMenuUtil::confirmSchematicObfuscation",
        }

        by_id = {item["id"]: item for item in data["capabilities"]}
        for script_id, command in expected.items():
            item = by_id[script_id]
            self.assertTrue(item["can_enable"], script_id)
            self.assertEqual(item["command"], command)
            self.assertEqual(item["module"], "cadence/modules/enhanced_core_tools.tcl")
            self.assertFalse(item["show_in_cadence"])
            self.assertTrue(item["requires_confirmation"])

        module = (ROOT / "cadence" / "modules" / "enhanced_core_tools.tcl").read_text(encoding="utf-8")
        for command in expected.values():
            proc_name = command.rsplit("::", 1)[-1]
            namespace_name = command.rsplit("::", 1)[0]
            self.assertIn(f"proc {namespace_name}::{proc_name}", module)
        self.assertIn("proc ::capMenuUtil::NetNameExchange", module)
        self.assertIn("proc ::capMenuUtil::RandomizeNetNames", module)
        self.assertIn("namespace eval ::capRequiredSanitize", module)
        self.assertNotIn("RegisterAction", module)
        self.assertNotIn("AddAccessoryMenu", module)

    def test_gnd_net_visibility_module_is_split_without_registeraction(self) -> None:
        module = (ROOT / "cadence" / "modules" / "gnd_net_visibility.tcl").read_text(encoding="utf-8")

        self.assertIn("proc ::capMenuUtil::GroundNameVisible", module)
        self.assertIn("proc ::capMenuUtil::GroundNameHidden", module)
        self.assertNotIn("RegisterAction", module)
        self.assertNotIn("AddAccessoryMenu", module)

    def test_reset_net_color_module_is_split_without_registeraction(self) -> None:
        module = (ROOT / "cadence" / "modules" / "reset_net_color.tcl").read_text(encoding="utf-8")

        self.assertIn("proc ::capMenuUtil::ResetNetnameColor", module)
        self.assertNotIn("RegisterAction", module)
        self.assertNotIn("AddAccessoryMenu", module)

    def test_part_color_module_is_split_without_registeraction(self) -> None:
        module = (ROOT / "cadence" / "modules" / "part_color_tools.tcl").read_text(encoding="utf-8")

        self.assertIn("proc ::capMenuUtil::NcPartGrayed", module)
        self.assertIn("proc ::capMenuUtil::RestorePartDefaultColor", module)
        self.assertIn("Part Number", module)
        self.assertIn("NC/", module)
        self.assertNotIn("RegisterAction", module)
        self.assertNotIn("AddAccessoryMenu", module)

    def test_display_visibility_module_is_split_without_registeraction(self) -> None:
        module = (ROOT / "cadence" / "modules" / "display_visibility_tools.tcl").read_text(encoding="utf-8")

        for proc_name in [
            "confirmHideUcomponent",
            "HideUcomponent",
            "confirmShowUcomponent",
            "ShowUcomponent",
            "confirmHideALLcomponent",
            "HideALLcomponent",
            "confirmShowALLcomponent",
            "ShowALLcomponent",
            "confirmHideUPinNames",
            "HideUPinNames",
        ]:
            self.assertIn(f"proc ::capMenuUtil::{proc_name}", module)
        self.assertIn("SetDisplayType $displayType", module)
        self.assertIn('setPartValueDisplayType "" 1 0', module)
        self.assertIn('setPartValueDisplayType "" 1 1', module)
        self.assertIn('setPartValueDisplayType "" 0 0', module)
        self.assertIn('setPartValueDisplayType "" 0 1', module)
        self.assertIn("NewPinsIter", module)
        self.assertNotIn("RegisterAction", module)
        self.assertNotIn("AddAccessoryMenu", module)

    def test_generated_loader_sources_gnd_module_when_gnd_scripts_are_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "tool"
            (root / "cadence" / "modules").mkdir(parents=True)
            (root / "config").mkdir()
            (root / "cadence" / "iac_bom_tool.tcl").write_text((ROOT / "cadence" / "iac_bom_tool.tcl").read_text(encoding="utf-8"), encoding="utf-8")
            (root / "cadence" / "modules" / "gnd_net_visibility.tcl").write_text("proc ::capMenuUtil::GroundNameVisible {} {}\nproc ::capMenuUtil::GroundNameHidden {} {}\n", encoding="utf-8")
            data = json.loads((ROOT / "config" / "capabilities.json").read_text(encoding="utf-8"))
            for item in data["capabilities"]:
                if item["id"] in {"cadence_ground_name_visible", "cadence_ground_name_hidden"}:
                    item["show_in_cadence"] = True
            (root / "config" / "capabilities.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            out = tmp_path / "iac_bom_tool.tcl"
            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'Cadence.ps1'}'; "
                f"Write-CadenceLoader -ToolRoot '{root}' -PythonPath 'C:/Python/python.exe' -OutputPath '{out}' | Out-Null"
            )

            subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                check=True,
                text=True,
                capture_output=True,
            )

            decoded = out.read_bytes().decode("gbk")
            self.assertIn('source "$::IAC_ROOT/cadence/modules/gnd_net_visibility.tcl"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "显示GND网络名" "::capMenuUtil::GroundNameVisible"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "隐藏GND网络名" "::capMenuUtil::GroundNameHidden"', decoded)
            self.assertNotIn("RegisterAction \"_cdnCapTclAddDesignCustomMenu\" \"::capMenuUtil", decoded)


if __name__ == "__main__":
    unittest.main()

