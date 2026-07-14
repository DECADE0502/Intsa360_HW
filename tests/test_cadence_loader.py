from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = "powershell"


class CadenceLoaderGenerationTests(unittest.TestCase):
    def test_cadence_loader_and_modules_avoid_tcl85_only_constructs_for_capture_166(self) -> None:
        forbidden_literals = {
            "dict ": "Tcl dict requires Tcl 8.5 and is unsafe for older Capture 16.6 runtimes",
            "{*}": "argument expansion requires Tcl 8.5 and is unsafe for older Capture 16.6 runtimes",
        }
        forbidden_commands = {
            "try": "try requires newer Tcl and is unsafe for older Capture 16.6 runtimes",
            "throw": "throw requires newer Tcl and is unsafe for older Capture 16.6 runtimes",
            "lmap": "lmap requires newer Tcl and is unsafe for older Capture 16.6 runtimes",
            "apply": "apply requires newer Tcl and is unsafe for older Capture 16.6 runtimes",
            "chan": "chan requires newer Tcl and is unsafe for older Capture 16.6 runtimes",
        }
        paths = [ROOT / "cadence" / "iac_bom_tool.tcl", *sorted((ROOT / "cadence" / "modules").glob("*.tcl"))]

        for path in paths:
            text = path.read_text(encoding="utf-8")
            padded = f" {text} "
            for token, reason in forbidden_literals.items():
                self.assertNotIn(token, padded, f"{path.relative_to(ROOT)} uses {token!r}: {reason}")
            for command, reason in forbidden_commands.items():
                self.assertIsNone(
                    re.search(rf"(?m)^\s*{re.escape(command)}\b", text),
                    f"{path.relative_to(ROOT)} uses Tcl command {command!r}: {reason}",
                )

    def test_cadence_runtime_tcl_files_are_ascii_safe_for_capture_166_and_174(self) -> None:
        paths = [ROOT / "cadence" / "iac_bom_tool.tcl", *sorted((ROOT / "cadence" / "modules").glob("*.tcl"))]

        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                try:
                    path.read_bytes().decode("ascii")
                except UnicodeDecodeError as exc:
                    self.fail(
                        f"{path.relative_to(ROOT)} contains non-ASCII byte at offset {exc.start}; "
                        "Capture loads Tcl scripts through the local ANSI codepage, so runtime Tcl text must use "
                        "ASCII messages and Tcl \\uXXXX escapes for required Chinese property names."
                    )

    def test_loader_property_names_do_not_use_multiline_command_substitution(self) -> None:
        text = (ROOT / "cadence" / "iac_bom_tool.tcl").read_text(encoding="utf-8")

        self.assertNotRegex(
            text,
            r"variable\s+PROP_NAMES\s+\[list\s*(?:\r?\n)",
            "Tcl treats the newline after [list as a command separator, so Capture fails before registering "
            "the insta360_HW menu.",
        )

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_generated_cadence_loader_menu_items_are_ascii_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "tool"
            (root / "cadence" / "modules").mkdir(parents=True)
            (root / "config").mkdir()
            (root / "cadence" / "modules" / "demo.tcl").write_text("proc ::Demo::Run {} {}\n", encoding="ascii")
            (root / "cadence" / "iac_bom_tool.tcl").write_text(
                '\n'.join(
                    [
                        'set ::IAC_ROOT "{{TOOL_ROOT}}"',
                        'set ::IAC_PY   "python"',
                        'proc ::IAC::addAccessoryMenu { args } {',
                        '  # {{CADENCE_SCRIPT_MENU_ITEMS}}',
                        '}',
                    ]
                ),
                encoding="ascii",
            )
            (root / "config" / "capabilities.json").write_text(
                json.dumps(
                    {
                        "platform": {"name": "Insta360硬件提效平台", "cadence_menu": "insta360_HW"},
                        "capabilities": [
                            {
                                "id": "enabled",
                                "type": "cadence_tcl",
                                "name": "中文脚本名",
                                "cadence_name": "English Script Name",
                                "description": "",
                                "category": "Cadence 脚本",
                                "status": "available",
                                "command": "::Demo::Run",
                                "module": "cadence/modules/demo.tcl",
                                "show_in_platform": True,
                                "show_in_cadence": True,
                            },
                            {
                                "id": "user.ascii_fallback",
                                "type": "cadence_tcl",
                                "name": "未配置英文名",
                                "description": "",
                                "category": "Cadence 脚本",
                                "status": "available",
                                "command": "::Demo::Run",
                                "module": "cadence/modules/demo.tcl",
                                "show_in_platform": True,
                                "show_in_cadence": True,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
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
            self.assertIn('AddAccessoryMenu "insta360_HW" "English Script Name" "::Demo::Run"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "user.ascii_fallback" "::Demo::Run"', decoded)
            self.assertNotIn("中文脚本名", decoded)
            self.assertNotIn("未配置英文名", decoded)
            decoded.encode("ascii")

    def test_every_cadence_capability_points_to_existing_module_proc(self) -> None:
        data = json.loads((ROOT / "config" / "capabilities.json").read_text(encoding="utf-8"))
        for item in data["capabilities"]:
            if item.get("type") != "cadence_tcl":
                continue
            module = item.get("module")
            command = item.get("command", "")
            self.assertTrue(module, item["id"])
            module_path = ROOT / module
            self.assertTrue(module_path.exists(), f"{item['id']} missing module {module}")
            text = module_path.read_text(encoding="utf-8")
            self.assertIn(f"proc {command}", text, f"{item['id']} command {command} is not defined by {module}")

    def test_cadence_modules_do_not_pass_literal_plib_to_implementation(self) -> None:
        for path in sorted((ROOT / "cadence" / "modules").glob("*.tcl")):
            text = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(), start=1):
                if line.lstrip().startswith("proc "):
                    continue
                self.assertIsNone(
                    re.search(r"::[A-Za-z0-9_:]+\s+\{pLib\}", line),
                    f"{path.relative_to(ROOT)}:{line_number} passes literal pLib instead of the Capture argument",
                )

    def test_cadence_loader_template_uses_ascii_top_menu_and_english_default_items(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Cadence.ps1").read_text(encoding="utf-8")
        template = (ROOT / "cadence" / "iac_bom_tool.tcl").read_text(encoding="utf-8")

        self.assertIn('"insta360_HW"', text)
        self.assertIn('[list "popup" "insta360_HW"', template)
        self.assertIn('InsertXMLMenu [list [list "insta360_HW"]', template)
        self.assertIn('InsertXMLMenu [list [list "insta360_HW" "Open"]', template)
        self.assertIn('InsertXMLMenu [list [list "insta360_HW" "Export"]', template)
        self.assertNotIn('InsertXMLMenu [list [list "IACBOM"', template)
        self.assertIn('"action" "Open Platform"', template)
        self.assertIn('"action" "Export and Process BOM"', template)
        self.assertNotIn('"action" "进入平台"', template)
        self.assertNotIn('"action" "导出并处理BOM"', template)
        self.assertNotIn('AddAccessoryMenu "insta360_HW" "Open Platform"', template)
        self.assertNotIn('AddAccessoryMenu "insta360_HW" "Export and Process BOM"', template)
        self.assertNotIn('AddAccessoryMenu "insta360_HW" "选中器件切换NC"', text)

    def test_root_does_not_keep_stale_insta360_bom_loader_copy(self) -> None:
        stale_loader = ROOT / "iac_bom_tool.tcl"

        self.assertFalse(stale_loader.exists())

    def test_root_does_not_keep_unrendered_tool_root_directory(self) -> None:
        self.assertFalse((ROOT / "{{TOOL_ROOT}}").exists())

    def test_loader_template_aborts_when_placeholders_are_unrendered(self) -> None:
        template = (ROOT / "cadence" / "iac_bom_tool.tcl").read_text(encoding="utf-8")
        header = "\n".join(template.splitlines()[:12])

        self.assertIn('set ::IAC_ROOT "{{TOOL_ROOT}}"', header)
        self.assertIn('set ::IAC_PY   "{{PYTHON_PATH}}"', header)
        self.assertRegex(header, r'string match "\*\\\{\\\{\*\\\}\\\}\*" \$::IAC_ROOT')
        self.assertIn("unrendered template", header)
        self.assertIn("return", header)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_write_cadence_loader_rejects_leftover_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "tool"
            (root / "cadence").mkdir(parents=True)
            (root / "config").mkdir()
            (root / "cadence" / "iac_bom_tool.tcl").write_text(
                '\n'.join(
                    [
                        'set ::IAC_ROOT "{{TOOL_ROOT}}"',
                        'set ::IAC_PY   "{{PYTHON_PATH}}"',
                        'set ::IAC_BAD "{{UNKNOWN_PLACEHOLDER}}"',
                    ]
                ),
                encoding="utf-8",
            )
            (root / "config" / "capabilities.json").write_text('{"capabilities":[]}', encoding="utf-8")
            out = tmp_path / "iac_bom_tool.tcl"
            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'Cadence.ps1'}'; "
                f"Write-CadenceLoader -ToolRoot '{root}' -PythonPath 'C:/Python/python.exe' -OutputPath '{out}' | Out-Null"
            )

            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unrendered placeholder", result.stderr + result.stdout)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
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
            self.assertNotRegex(decoded, r"\{\{[A-Z_]+\}\}")
            self.assertNotIn("codex-runtimes", decoded)
            self.assertIn('set ::IAC_PY   "C:/Python/python.exe"', decoded)
            self.assertIn('InsertXMLMenu [list [list "insta360_HW"]', decoded)
            self.assertNotIn('InsertXMLMenu [list [list "IACBOM"', decoded)
            self.assertIn('"insta360_HW"', decoded)
            self.assertNotIn('AddAccessoryMenu "insta360_HW" "Open Platform"', decoded)
            self.assertNotIn('AddAccessoryMenu "insta360_HW" "Export and Process BOM"', decoded)
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

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_generated_loader_keeps_capture_property_unicode_escapes_unmodified(self) -> None:
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

            decoded = out.read_bytes().decode("gbk")
            prop_block = decoded[decoded.index("variable PROP_NAMES"):decoded.index("proc shouldProcess")]
            self.assertIn('"PCB\\u5c01\\u88c5"', prop_block)
            self.assertIn('"\\u7b49\\u7ea7"', prop_block)
            self.assertIn('"\\u89c4\\u683c\\u578b\\u53f7"', prop_block)
            self.assertIn('"\\u5668\\u4ef6\\u63cf\\u8ff0\\uff08\\u65b0\\u6574\\u7406\\uff09"', prop_block)
            self.assertIn('"\\u7269\\u6599\\u540d\\u79f0"', prop_block)
            self.assertNotIn("PCBCancel", prop_block)
            self.assertNotIn("CancelCancel", prop_block)
            self.assertNotIn("Net name randomization completed.", prop_block)

    def test_capture_runtime_visible_messages_are_english_ascii(self) -> None:
        paths = [ROOT / "cadence" / "iac_bom_tool.tcl", *sorted((ROOT / "cadence" / "modules").glob("*.tcl"))]
        visible_message_pattern = re.compile(r"\b(tk_messageBox|puts|error|label|button)\b|\bwm\s+title\b")

        for path in paths:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if "\\u" in line and visible_message_pattern.search(line):
                    self.fail(
                        f"{path.relative_to(ROOT)}:{line_number} emits Tcl Unicode escapes in a Capture-visible "
                        "message. Keep Capture-side logs/dialogs in English ASCII; reserve \\uXXXX for property names."
                    )

    def test_generated_loader_can_mount_enabled_tcl_scripts_without_renaming_registeraction(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Cadence.ps1").read_text(encoding="utf-8")

        self.assertIn("show_in_cadence", text)
        self.assertIn("Get-EnabledCadenceMenuItems", text)
        self.assertIn("shortcut", text)
        self.assertNotIn("rename RegisterAction", text)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
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
            self.assertIn('AddAccessoryMenu "insta360_HW" "enabled" "::Demo::Run"', decoded)
            self.assertNotIn('AddAccessoryMenu "insta360_HW" "Open Platform"', decoded)
            self.assertNotIn('AddAccessoryMenu "insta360_HW" "Export and Process BOM"', decoded)
            self.assertNotIn("禁用脚本", decoded)
            self.assertNotIn("rename RegisterAction", decoded)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_generated_loader_injects_enabled_user_plugin_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "tool"
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "cadence", root / "cadence")
            (root / "plugins" / "user" / "scripts").mkdir(parents=True)
            (root / "plugins" / "user" / "scripts" / "demo.tcl").write_text("proc ::Demo::Run {} {}\n", encoding="utf-8")
            (root / "plugins" / "user" / "demo.json").write_text(
                json.dumps(
                    {
                        "id": "user.demo",
                        "name": "User Demo",
                        "type": "cadence_tcl",
                        "command": "::Demo::Run",
                        "script": "scripts/demo.tcl",
                        "show_in_platform": True,
                        "show_in_cadence": True,
                    }
                ),
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
            self.assertIn('source "$::IAC_ROOT/plugins/user/scripts/demo.tcl"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "User Demo" "::Demo::Run"', decoded)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_local_appdata_plugin_state_override_changes_rendered_loader_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "runtime"
            local_app_data = tmp_path / "local-app-data"
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "cadence", root / "cadence")
            (root / "install_manifest.json").write_text(
                json.dumps({"schema": 2, "product": "Insta360_HW", "layout": "runtime-v2"}),
                encoding="utf-8",
            )
            state_path = local_app_data / "Insta360_HW" / "config" / "plugin_state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(
                json.dumps({"schema_version": 1, "plugins": {"cadence_nc_toggle": {"enabled": True}}}),
                encoding="utf-8",
            )
            enabled_loader = tmp_path / "enabled.tcl"
            disabled_loader = tmp_path / "disabled.tcl"
            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'Cadence.ps1'}'; "
                f"Write-CadenceLoader -ToolRoot '{root}' -PythonPath 'C:/Python/python.exe' -OutputPath '{enabled_loader}' | Out-Null"
            )
            environment = {**os.environ, "LOCALAPPDATA": str(local_app_data)}

            subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                check=True,
                text=True,
                capture_output=True,
                env=environment,
            )

            state_path.write_text(
                json.dumps({"schema_version": 1, "plugins": {"cadence_nc_toggle": {"enabled": False}}}),
                encoding="utf-8",
            )
            disabled_command = command.replace(str(enabled_loader), str(disabled_loader))
            subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", disabled_command],
                check=True,
                text=True,
                capture_output=True,
                env=environment,
            )

            enabled = enabled_loader.read_bytes().decode("gbk")
            disabled = disabled_loader.read_bytes().decode("gbk")
            self.assertIn('source "$::IAC_ROOT/cadence/modules/nc_toggle_selected.tcl"', enabled)
            self.assertIn('AddAccessoryMenu "insta360_HW" "Toggle Selected NC (Ctrl+Q)"', enabled)
            self.assertIn('::IAC::SetShortcut "cadence_nc_toggle" 1', enabled)
            self.assertIn('::IAC::SetShortcut "cadence_nc_toggle" 0', disabled)
            self.assertNotIn('AddAccessoryMenu "insta360_HW" "Toggle Selected NC (Ctrl+Q)"', disabled)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_malformed_user_manifest_does_not_block_loader_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "tool"
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "cadence", root / "cadence")
            scripts = root / "plugins" / "user" / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "demo.tcl").write_text("proc ::Demo::Run {} {}\n", encoding="utf-8")
            (root / "plugins" / "user" / "demo.json").write_text(
                json.dumps(
                    {
                        "id": "user.demo",
                        "name": "User Demo",
                        "type": "cadence_tcl",
                        "command": "::Demo::Run",
                        "script": "scripts/demo.tcl",
                        "show_in_platform": True,
                        "show_in_cadence": True,
                    }
                ),
                encoding="utf-8",
            )
            (root / "plugins" / "user" / "broken.json").write_text("{not json", encoding="utf-8")
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
            self.assertIn('source "$::IAC_ROOT/plugins/user/scripts/demo.tcl"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "User Demo" "::Demo::Run"', decoded)

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

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_nc_toggle_shortcut_is_declared_in_registry_and_generated_by_loader(self) -> None:
        data = json.loads((ROOT / "config" / "capabilities.json").read_text(encoding="utf-8"))
        item = next(item for item in data["capabilities"] if item["id"] == "cadence_nc_toggle")
        module = (ROOT / "cadence" / "modules" / "nc_toggle_selected.tcl").read_text(encoding="utf-8")

        self.assertEqual(item["shortcut"], "Ctrl+Q")
        self.assertEqual(item["shortcut_context"], "Schematic")
        self.assertEqual(item["enabled_command"], "::capNCToggleSelected::enabled")
        self.assertEqual(item["shortcut_action"], "insta360_HW_nc_toggle")
        self.assertEqual(item["shortcut_command"], "::capNCToggleSelected::toggleImpl")
        self.assertIn("proc ::capNCToggleSelected::toggleImpl", module)
        self.assertIn("proc ::capNCToggleSelected::isMounted", module)
        self.assertIn("::IAC::ShortcutEnabled cadence_nc_toggle", module)
        self.assertNotIn("RegisterAction", module)
        self.assertNotIn("AddAccessoryMenu", module)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "tool"
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "cadence", root / "cadence")
            data = json.loads((root / "config" / "capabilities.json").read_text(encoding="utf-8"))
            for capability in data["capabilities"]:
                if capability["id"] == "cadence_nc_toggle":
                    capability["show_in_cadence"] = True
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
            self.assertIn('source "$::IAC_ROOT/cadence/modules/nc_toggle_selected.tcl"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW"', decoded)
            self.assertIn('"Toggle Selected NC (Ctrl+Q)"', decoded)
            self.assertIn('"::capNCToggleSelected::toggleFromMenu"', decoded)
            self.assertIn("proc RunShortcut", decoded)
            self.assertIn('::IAC::SetShortcut "cadence_nc_toggle" 1', decoded)
            self.assertIn('RegisterAction "insta360_HW_nc_toggle"', decoded)
            self.assertNotIn('RegisterAction "cadence_nc_toggle_shortcut" "::IAC::shouldProcess" "" "" ""', decoded)
            self.assertNotIn('RegisterAction "NC Toggle Selected Parts"', decoded)
            self.assertNotIn('RegisterAction "NC Toggle Selected Parts" "::IAC::shouldProcess" "" "" ""', decoded)
            self.assertIn('::IAC::SetShortcut "cadence_nc_toggle" 1 "::capNCToggleSelected::toggleImpl"', decoded)
            self.assertIn('"::IAC::ShortcutEnabled cadence_nc_toggle" "Ctrl+Q" "::IAC::RunShortcut cadence_nc_toggle" "Schematic"', decoded)
            self.assertIn("shortcut registered: insta360_HW_nc_toggle Ctrl+Q", decoded)
            shortcut_index = decoded.index('RegisterAction "insta360_HW_nc_toggle"')
            dynamic_menu_index = decoded.index("proc ::IAC::addAccessoryMenu")
            self.assertLess(shortcut_index, dynamic_menu_index)
            dynamic_menu_body = decoded[dynamic_menu_index:]
            self.assertNotIn('RegisterAction "NC Toggle Selected Parts"', dynamic_menu_body)
            self.assertNotIn('RegisterAction "cadence_nc_toggle_shortcut"', dynamic_menu_body)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_nc_shortcut_disabled_state_keeps_dispatcher_hot_reloadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "tool"
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "cadence", root / "cadence")
            data = json.loads((root / "config" / "capabilities.json").read_text(encoding="utf-8"))
            for capability in data["capabilities"]:
                if capability["id"] == "cadence_nc_toggle":
                    capability["show_in_cadence"] = False
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
            self.assertIn('::IAC::SetShortcut "cadence_nc_toggle" 0', decoded)
            self.assertIn('RegisterAction "insta360_HW_nc_toggle"', decoded)
            self.assertNotIn('RegisterAction "NC Toggle Selected Parts"', decoded)
            self.assertIn('"::IAC::ShortcutEnabled cadence_nc_toggle" "Ctrl+Q" "::IAC::RunShortcut cadence_nc_toggle" "Schematic"', decoded)
            self.assertNotIn('RegisterAction "NC Toggle Selected Parts" "::IAC::shouldProcess" "" "" ""', decoded)
            self.assertIn('source "$::IAC_ROOT/cadence/modules/nc_toggle_selected.tcl"', decoded.split("proc ::IAC::addAccessoryMenu", 1)[0])

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_installed_loader_reads_user_plugins_from_external_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "runtime"
            local_app_data = tmp_path / "local"
            state_root = local_app_data / "Insta360_HW"
            user_dir = state_root / "plugins" / "user"
            user_dir.mkdir(parents=True)
            (state_root / "config").mkdir(parents=True)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "cadence", root / "cadence")
            (root / "install_manifest.json").write_text(
                json.dumps({"product": "Insta360_HW", "schema": 2, "layout": "runtime-v2"}),
                encoding="utf-8",
            )
            script = user_dir / "external_tool.tcl"
            script.write_text("proc ::externalTool::run {} { return 1 }\n", encoding="utf-8")
            (user_dir / "external_tool.json").write_text(
                json.dumps(
                    {
                        "id": "external_tool",
                        "name": "External Tool",
                        "type": "cadence_tcl",
                        "command": "::externalTool::run",
                        "script": script.name,
                        "show_in_cadence": False,
                    }
                ),
                encoding="utf-8",
            )
            (state_root / "config" / "plugin_state.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "plugins": {"external_tool": {"enabled": True}},
                    }
                ),
                encoding="utf-8",
            )
            out = tmp_path / "iac_bom_tool.tcl"
            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'Cadence.ps1'}'; "
                f"Write-CadenceLoader -ToolRoot '{root}' -PythonPath 'C:/Python/python.exe' -OutputPath '{out}' | Out-Null"
            )
            env = os.environ.copy()
            env["LOCALAPPDATA"] = str(local_app_data)

            subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                check=True,
                text=True,
                capture_output=True,
                env=env,
            )

            decoded = out.read_bytes().decode("gbk")
            expected_script = script.resolve().as_posix()
            self.assertIn(f'::IAC::SourceModule "{expected_script}"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "External Tool" "::externalTool::run"', decoded)
            self.assertNotIn('$::IAC_ROOT/plugins/user/external_tool.tcl', decoded)

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

    @unittest.skipUnless(sys.platform == "win32", "windows only")
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
            self.assertIn('AddAccessoryMenu "insta360_HW" "Show GND Net Names" "::capMenuUtil::GroundNameVisible"', decoded)
            self.assertIn('AddAccessoryMenu "insta360_HW" "Hide GND Net Names" "::capMenuUtil::GroundNameHidden"', decoded)
            self.assertNotIn("RegisterAction \"_cdnCapTclAddDesignCustomMenu\" \"::capMenuUtil", decoded)


if __name__ == "__main__":
    unittest.main()

