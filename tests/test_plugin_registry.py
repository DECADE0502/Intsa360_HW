from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.backend.plugins import load_plugins, set_plugin_cadence_menu_visibility


ROOT = Path(__file__).resolve().parents[1]


def _copy_minimal_root() -> Path:
    root = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "config", root / "config")
    (root / "plugins" / "user" / "scripts").mkdir(parents=True)
    return root


def _write_demo_user_plugin(root: Path) -> Path:
    (root / "plugins" / "user" / "scripts" / "demo.tcl").write_text(
        "proc ::Demo::Run {} {}\n",
        encoding="utf-8",
    )
    manifest = root / "plugins" / "user" / "demo.json"
    manifest.write_text(
        json.dumps(
            {
                "id": "user.demo",
                "name": "Demo Script",
                "description": "A user script",
                "type": "cadence_tcl",
                "category": "User Script",
                "status": "disabled",
                "command": "::Demo::Run",
                "script": "scripts/demo.tcl",
                "show_in_platform": True,
                "show_in_cadence": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


class PluginRegistryTests(unittest.TestCase):
    def test_load_plugins_separates_cadence_official_platform_and_user_scripts(self) -> None:
        root = _copy_minimal_root()
        official_dir = root / "fake-cadence" / "capAutoLoad"
        official_dir.mkdir(parents=True)
        (official_dir / "capAutoPDFExport.tcl").write_text("# official\n", encoding="utf-8")
        _write_demo_user_plugin(root)
        try:
            plugins = load_plugins(root, system_script_dirs=[official_dir])

            system = plugins["groups"]["system"]
            platform = plugins["groups"]["platform"]
            user = plugins["groups"]["user"]

            self.assertEqual([item["id"] for item in system], ["cadence_official.capAutoPDFExport"])
            self.assertEqual(system[0]["source"], "system")
            self.assertTrue(system[0]["readonly"])
            self.assertFalse(system[0]["manageable"])
            self.assertEqual(system[0]["path"], str(official_dir / "capAutoPDFExport.tcl"))

            platform_ids = {item["id"] for item in platform}
            self.assertIn("cadence_nc_toggle", platform_ids)
            nc_toggle = [item for item in platform if item["id"] == "cadence_nc_toggle"][0]
            self.assertEqual(nc_toggle["source"], "platform")
            self.assertFalse(nc_toggle["readonly"])
            self.assertTrue(nc_toggle["manageable"])
            self.assertEqual(nc_toggle["menu"], "insta360_HW")

            self.assertEqual(user[0]["id"], "user.demo")
            self.assertEqual(user[0]["source"], "user")
            self.assertFalse(user[0]["readonly"])
            self.assertTrue(user[0]["manageable"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_load_plugins_discovers_user_manifest_scripts_as_manageable_plugins(self) -> None:
        root = _copy_minimal_root()
        try:
            _write_demo_user_plugin(root)

            plugins = load_plugins(root, system_script_dirs=[])
            user = plugins["groups"]["user"]

            self.assertEqual(len(user), 1)
            self.assertEqual(user[0]["id"], "user.demo")
            self.assertEqual(user[0]["source"], "user")
            self.assertFalse(user[0]["readonly"])
            self.assertTrue(user[0]["manageable"])
            self.assertEqual(user[0]["module"], "plugins/user/scripts/demo.tcl")
            self.assertEqual(user[0]["menu"], "insta360_HW")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_platform_capability_plugin_toggle_persists_to_mutable_overrides(self) -> None:
        root = _copy_minimal_root()
        try:
            updated = set_plugin_cadence_menu_visibility(root, "cadence_nc_toggle", True)
            overrides = json.loads((root / "config" / "capability_overrides.json").read_text(encoding="utf-8"))
            reloaded = load_plugins(root, system_script_dirs=[])
            enabled = [item for item in reloaded["groups"]["platform"] if item["id"] == "cadence_nc_toggle"][0]

            self.assertEqual(updated["id"], "cadence_nc_toggle")
            self.assertEqual(updated["source"], "platform")
            self.assertTrue(updated["show_in_cadence"])
            self.assertTrue(overrides["cadence_nc_toggle"])
            self.assertTrue(enabled["show_in_cadence"])
            self.assertEqual(enabled["status"], "available")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_official_cadence_plugins_cannot_be_toggled_through_plugin_api(self) -> None:
        root = _copy_minimal_root()
        official_dir = root / "fake-cadence" / "capAutoLoad"
        official_dir.mkdir(parents=True)
        (official_dir / "capAutoPDFExport.tcl").write_text("# official\n", encoding="utf-8")
        try:
            with self.assertRaises(PermissionError):
                set_plugin_cadence_menu_visibility(
                    root,
                    "cadence_official.capAutoPDFExport",
                    True,
                    system_script_dirs=[official_dir],
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_user_plugin_toggle_persists_to_manifest(self) -> None:
        root = _copy_minimal_root()
        try:
            manifest = _write_demo_user_plugin(root)

            updated = set_plugin_cadence_menu_visibility(root, "user.demo", True)
            saved = json.loads(manifest.read_text(encoding="utf-8"))

            self.assertTrue(updated["show_in_cadence"])
            self.assertEqual(updated["status"], "available")
            self.assertTrue(saved["show_in_cadence"])
            self.assertEqual(saved["status"], "available")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
