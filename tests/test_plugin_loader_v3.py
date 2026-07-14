from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.backend import plugins as plugins_module


ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = ROOT / "config" / "capabilities.json"
LOADER = ROOT / "cadence" / "iac_bom_tool.tcl"
CADENCE_LIBRARY = ROOT / "scripts" / "lib" / "Cadence.ps1"
POWERSHELL = "powershell.exe"
TCLSH_CANDIDATES = (
    Path(r"D:\CADENCE\Cadence\SPB_17.4\tools\bin\tclsh.exe"),
    Path(r"D:\Cadence\Cadence\SPB_17.4\tools\bin\tclsh.exe"),
)
TCLSH = next((path for path in TCLSH_CANDIDATES if path.is_file()), None)


class PluginLoaderV3Tests(unittest.TestCase):
    def test_every_platform_plugin_has_one_unique_entry_and_lifecycle_contract(self) -> None:
        data = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
        plugins = [item for item in data["capabilities"] if item["type"] == "cadence_tcl"]

        entries = [item.get("entry_script") for item in plugins]
        self.assertEqual(len(entries), len(set(entries)))
        for item in plugins:
            with self.subTest(plugin=item["id"]):
                expected_entry = f"cadence/entries/{item['id']}.tcl"
                self.assertEqual(item.get("entry_script"), expected_entry)
                self.assertEqual(item.get("module"), expected_entry)
                self.assertTrue((ROOT / expected_entry).is_file())
                self.assertEqual(item.get("command"), f"::IACPluginRuntime::invoke {item['id']}")
                self.assertTrue(str(item.get("implementation_command", "")).startswith("::"))
                self.assertEqual(item.get("activate_command"), f"::IACPluginRuntime::activate {item['id']}")
                self.assertEqual(item.get("deactivate_command"), f"::IACPluginRuntime::deactivate {item['id']}")
                expected_activation = "restart" if item["id"] == "cadence_nc_toggle" else "hot_reload"
                self.assertEqual(item.get("activation"), expected_activation)
                self.assertEqual(item.get("compatible_capture_versions"), ["16.6", "17.4"])
                expected_priority = 10 if item["implementation_module"].endswith("enhanced_core_tools.tcl") else 20
                self.assertEqual(item.get("load_priority"), expected_priority)

                entry = (ROOT / expected_entry).read_text(encoding="utf-8")
                self.assertIn('::IAC::SourceModuleOnce "cadence/modules/plugin_runtime.tcl"', entry)
                self.assertIn(f'::IACPluginRuntime::register "{item["id"]}"', entry)
                self.assertIn(f'"{item["implementation_command"]}"', entry)

    def test_loader_deduplicates_modules_and_deactivates_old_plugins_before_reload(self) -> None:
        source = LOADER.read_text(encoding="utf-8")

        self.assertIn("variable LOADED_MODULES", source)
        self.assertIn("proc SourceModuleOnce", source)
        self.assertIn("uplevel #0 [list source $path]", source)
        self.assertIn("proc RegisterPluginLifecycle", source)
        self.assertIn("proc BeginPluginReload", source)
        self.assertIn("::IAC::BeginPluginReload", source)
        self.assertLess(source.index("::IAC::BeginPluginReload"), source.index("# {{CADENCE_SCRIPT_SHORTCUT_ITEMS}}"))

        renderer = CADENCE_LIBRARY.read_text(encoding="utf-8")
        self.assertNotIn("namespace delete", renderer)
        self.assertIn("entry_script", renderer)
        self.assertIn("RegisterPluginLifecycle", renderer)
        self.assertIn("ActivatePlugin", renderer)

    @unittest.skipUnless(sys.platform == "win32", "PowerShell loader renderer")
    def test_renderer_sources_unique_entries_instead_of_shared_implementation_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "runtime"
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "cadence", root / "cadence")
            data = json.loads((root / "config" / "capabilities.json").read_text(encoding="utf-8"))
            enabled_ids = {
                "cadence_ground_name_visible",
                "cadence_ground_name_hidden",
                "cadence_net_name_replace",
            }
            for item in data["capabilities"]:
                if item["id"] in enabled_ids:
                    item["show_in_cadence"] = True
            (root / "config" / "capabilities.json").write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8",
            )
            output = base / "iac_bom_tool.tcl"
            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{CADENCE_LIBRARY}'; "
                f"Write-CadenceLoader -ToolRoot '{root}' -PythonPath '{Path(sys.executable)}' "
                f"-OutputPath '{output}' | Out-Null"
            )
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=os.environ.copy(),
            )
            rendered = output.read_bytes().decode("gbk") if output.exists() else ""

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for plugin_id in enabled_ids:
            entry = f"cadence/entries/{plugin_id}.tcl"
            self.assertEqual(rendered.count(f'::IAC::SourceModuleOnce "$::IAC_ROOT/{entry}"'), 1)
            self.assertIn(f'::IAC::RegisterPluginLifecycle "{plugin_id}"', rendered)
            self.assertIn(f"::IAC::ActivatePlugin {plugin_id}", rendered)
        self.assertNotIn('source "$::IAC_ROOT/cadence/modules/gnd_net_visibility.tcl"', rendered)
        self.assertLess(
            rendered.index("cadence/entries/cadence_net_name_replace.tcl"),
            rendered.index("cadence/entries/cadence_ground_name_visible.tcl"),
        )

    def test_system_script_discovery_covers_c_and_d_style_16_6_and_17_4_roots(self) -> None:
        discover = getattr(plugins_module, "discover_cadence_system_script_dirs", None)
        self.assertTrue(callable(discover))
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            drive_c = base / "drive-c"
            drive_d = base / "drive-d"
            expected = {
                drive_c / "Cadence" / "SPB_16.6" / "tools" / "capture" / "tclscripts" / "capAutoLoad",
                drive_d / "Cadence" / "Cadence" / "SPB_17.4" / "tools" / "capture" / "tclscripts" / "capAutoLoad",
            }
            for path in expected:
                path.mkdir(parents=True)
                (path / "official.tcl").write_text("# official\n", encoding="utf-8")

            actual = set(discover([drive_c, drive_d]))

        self.assertEqual({path.resolve() for path in actual}, {path.resolve() for path in expected})

    @unittest.skipUnless(sys.platform == "win32" and TCLSH is not None, "Cadence Tcl runtime is unavailable")
    def test_rendered_loader_deactivates_removed_plugin_in_same_tcl_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "runtime"
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "cadence", root / "cadence")
            data = json.loads((root / "config" / "capabilities.json").read_text(encoding="utf-8"))
            for item in data["capabilities"]:
                item["show_in_cadence"] = item["id"] == "cadence_ground_name_visible"
            (root / "config" / "capabilities.json").write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8",
            )
            enabled_loader = base / "enabled.tcl"
            disabled_loader = base / "disabled.tcl"

            def render(output: Path) -> None:
                command = (
                    "$ErrorActionPreference='Stop'; "
                    f". '{CADENCE_LIBRARY}'; "
                    f"Write-CadenceLoader -ToolRoot '{root}' -PythonPath '{Path(sys.executable)}' "
                    f"-OutputPath '{output}' | Out-Null"
                )
                result = subprocess.run(
                    [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            render(enabled_loader)
            for item in data["capabilities"]:
                item["show_in_cadence"] = False
            (root / "config" / "capabilities.json").write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8",
            )
            render(disabled_loader)

            harness = base / "lifecycle_harness.tcl"
            harness.write_text(
                "\n".join(
                    [
                        "proc RegisterAction {args} {}",
                        "proc InsertXMLMenu {args} {}",
                        "proc AddAccessoryMenu {args} {}",
                        f"source {{{enabled_loader.as_posix()}}}",
                        "::IAC::addAccessoryMenu",
                        'puts "before=[::IACPluginRuntime::isActive cadence_ground_name_visible]"',
                        f"source {{{disabled_loader.as_posix()}}}",
                        'puts "after=[::IACPluginRuntime::isActive cadence_ground_name_visible]"',
                        'puts "invoke=[::IACPluginRuntime::invoke cadence_ground_name_visible]"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [str(TCLSH), str(harness)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("before=1", result.stdout)
        self.assertIn("after=0", result.stdout)
        self.assertIn("invoke=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
