from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DistributionInstallTests(unittest.TestCase):
    def test_distribution_scripts_and_libraries_exist(self) -> None:
        expected = [
            "install.ps1",
            "update.ps1",
            "scripts/lib/Paths.ps1",
            "scripts/lib/Cadence.ps1",
            "scripts/lib/Service.ps1",
            "scripts/lib/Update.ps1",
            "scripts/lib/TclScripts.ps1",
            "scripts/redeploy_cadence_loader.ps1",
            "scripts/diagnose_platform.ps1",
            "scripts/verify_capture_runtime.ps1",
        ]

        for relative in expected:
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).exists(), f"{relative} should exist")

    def test_powershell_scripts_are_parseable(self) -> None:
        scripts = [
            "install.ps1",
            "update.ps1",
            "launch_tool_suite.ps1",
            "scripts/lib/Paths.ps1",
            "scripts/lib/Cadence.ps1",
            "scripts/lib/Service.ps1",
            "scripts/lib/Update.ps1",
            "scripts/lib/TclScripts.ps1",
            "scripts/build_frontend.ps1",
            "scripts/verify_all.ps1",
            "scripts/redeploy_cadence_loader.ps1",
            "scripts/diagnose_platform.ps1",
            "scripts/verify_capture_runtime.ps1",
        ]
        for relative in scripts:
            with self.subTest(relative=relative):
                parser = (
                    f"$path={json.dumps(relative)}; "
                    "$errors=$null; "
                    "$text=Get-Content -LiteralPath $path -Raw -Encoding UTF8; "
                    "[System.Management.Automation.PSParser]::Tokenize($text, [ref]$errors) | Out-Null; "
                    "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", parser],
                    cwd=ROOT,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=20,
                )

    def test_install_script_uses_helpers_preserves_local_config_and_installs_cadence(self) -> None:
        text = (ROOT / "install.ps1").read_text(encoding="utf-8")

        self.assertIn("scripts\\lib\\Paths.ps1", text)
        self.assertIn("scripts\\lib\\Cadence.ps1", text)
        self.assertIn("scripts\\lib\\Service.ps1", text)
        self.assertIn("scripts\\lib\\TclScripts.ps1", text)
        self.assertIn("config\\local.json", text)
        self.assertIn("Test-Path -LiteralPath $LocalConfig", text)
        self.assertIn("Install-CadenceLoader", text)
        self.assertIn("Find-Python", text)
        self.assertIn("Find-CadenceAutoLoadDirs", text)
        self.assertIn("Find-CadenceVendorAutoLoadDirs", text)
        self.assertIn("Disable-HwAgentVendorAutoLoadScripts", text)
        self.assertIn("robocopy", text)
        self.assertIn("build_frontend.ps1", text)

    def test_tcl_script_library_disables_custom_scripts_in_vendor_autoload(self) -> None:
        text = (ROOT / "scripts" / "lib" / "TclScripts.ps1").read_text(encoding="utf-8")

        self.assertIn("function Disable-HwAgentVendorAutoLoadScripts", text)
        self.assertIn("_disabled_custom_scripts", text)
        self.assertIn("Move-Item", text)

    def test_tcl_script_library_moves_enhanced_tool_backups_but_keeps_vendor_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autoload = Path(tmp) / "capAutoLoad"
            autoload.mkdir()
            active = autoload / "orCAD_Enhanced_Tools_V1.8.tcl"
            backup = autoload / "orCAD_Enhanced_Tools_V1.3.tcl.bak_before_update"
            vendor = autoload / "capAutoPDFExport.tcl"
            active.write_text("RegisterAction bad", encoding="utf-8")
            backup.write_text("RegisterAction old", encoding="utf-8")
            vendor.write_text("official script", encoding="utf-8")

            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'TclScripts.ps1'}'; "
                f"$moved = Disable-HwAgentVendorAutoLoadScripts -VendorAutoLoadDir '{autoload}'; "
                "$moved | ConvertTo-Json -Compress"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(active.exists())
            self.assertFalse(backup.exists())
            self.assertTrue(vendor.exists())
            disabled_dirs = list(autoload.glob("_disabled_custom_scripts_*"))
            self.assertEqual(len(disabled_dirs), 1)
            self.assertTrue((disabled_dirs[0] / active.name).exists())
            self.assertTrue((disabled_dirs[0] / backup.name).exists())

    def test_tcl_script_library_moves_disabled_backup_dirs_outside_autoload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autoload = Path(tmp) / "capAutoLoad"
            autoload.mkdir()
            backup = autoload / "_disabled_hwagent_loader_20260623_231552"
            backup.mkdir()
            (backup / "iac_bom_tool.tcl").write_text("old loader", encoding="utf-8")
            active_loader = autoload / "iac_bom_tool.tcl"
            active_loader.write_text("current loader", encoding="utf-8")

            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'TclScripts.ps1'}'; "
                f"$moved = Move-HwAgentAutoLoadBackupDirs -AutoLoadDir '{autoload}'; "
                "$moved | ConvertTo-Json -Compress"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(active_loader.exists())
            self.assertFalse(backup.exists())
            archived = list(autoload.parent.glob("_hwagent_disabled_autoload_backups/*/_disabled_hwagent_loader_20260623_231552"))
            self.assertEqual(len(archived), 1)
            self.assertTrue((archived[0] / "iac_bom_tool.tcl").exists())

    def test_active_cadence_modules_do_not_include_full_legacy_enhanced_script(self) -> None:
        legacy_module = ROOT / "cadence" / "modules" / "orcad_enhanced_tools.tcl"

        self.assertFalse(legacy_module.exists())

    def test_update_script_preserves_user_data_and_handles_empty_repo(self) -> None:
        update_text = (ROOT / "update.ps1").read_text(encoding="utf-8")
        lib_text = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")
        combined = update_text + "\n" + lib_text

        for protected in ["data", "uploads", "outputs", "history", "config/local.json"]:
            with self.subTest(protected=protected):
                self.assertIn(protected, combined)

        self.assertIn("Invoke-HwAgentGitUpdate", combined)
        self.assertIn("git pull", combined)
        self.assertIn("build_frontend.ps1", combined)
        self.assertIn("verify_all.ps1", combined)
        self.assertIn("empty_repo", combined)
        self.assertIn("scripts\\lib\\Cadence.ps1", update_text)
        self.assertIn("scripts\\lib\\TclScripts.ps1", update_text)
        self.assertIn("Find-Python", update_text)
        self.assertIn("Find-CadenceAutoLoadDirs", update_text)
        self.assertIn("Find-CadenceVendorAutoLoadDirs", update_text)
        self.assertIn("Disable-HwAgentVendorAutoLoadScripts", update_text)
        self.assertIn("Install-CadenceLoader", update_text)

    def test_update_library_can_update_plain_folder_from_git_repo(self) -> None:
        git = subprocess.run(
            ["git", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if git.returncode != 0:
            self.skipTest("git is not available")

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            install = Path(tmp) / "install"
            source.mkdir()
            install.mkdir()

            (source / "VERSION").write_text("2.0.0\n", encoding="utf-8")
            (source / "scripts").mkdir()
            (source / "scripts" / "from_repo.txt").write_text("new", encoding="utf-8")
            subprocess.run(["git", "init", "-b", "main"], cwd=source, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
            subprocess.run(["git", "add", "."], cwd=source, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
            subprocess.run(["git", "commit", "-m", "seed"], cwd=source, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)

            (install / "VERSION").write_text("1.0.0\n", encoding="utf-8")
            (install / "stale.txt").write_text("remove me", encoding="utf-8")
            (install / "data").mkdir()
            (install / "data" / "keep.txt").write_text("keep", encoding="utf-8")
            (install / "config").mkdir()
            (install / "config" / "local.json").write_text('{"install_dir":"local"}', encoding="utf-8")

            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'Update.ps1'}'; "
                f"Invoke-HwAgentGitUpdate -Root '{install}' -Repo '{source}' -Branch main | ConvertTo-Json -Compress"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )

            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "2.0.0")
            self.assertTrue((install / "scripts" / "from_repo.txt").exists())
            self.assertFalse((install / "stale.txt").exists())
            self.assertTrue((install / "data" / "keep.txt").exists())
            self.assertEqual((install / "config" / "local.json").read_text(encoding="utf-8"), '{"install_dir":"local"}')
            self.assertFalse((install / ".git").exists())

    def test_paths_library_finds_vendor_autoload_dirs_separately_from_user_loader_dirs(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Paths.ps1").read_text(encoding="utf-8")

        self.assertIn("function Find-CadenceVendorAutoLoadDirs", text)
        self.assertIn("SPB_17.4\\tools\\capture\\tclscripts\\capAutoLoad", text)
        self.assertNotIn("SPB_17.4\\tools\\capture\\tclscripts\\capAutoLoad\",\n    (Join-Path $env:USERPROFILE", text)

    def test_redeploy_cadence_loader_script_runs_with_windows_powershell_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "autoload"
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "scripts" / "redeploy_cadence_loader.ps1"),
                    "-CaptureAutoLoadDir",
                    str(target),
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertTrue((target / "iac_bom_tool.tcl").exists())

    def test_diagnose_platform_script_checks_cadence_and_runtime_health(self) -> None:
        script = ROOT / "scripts" / "diagnose_platform.ps1"
        text = script.read_text(encoding="utf-8")

        self.assertIn("Find-CadenceAutoLoadDirs", text)
        self.assertIn("Find-CadenceVendorAutoLoadDirs", text)
        self.assertIn("Disable-HwAgentVendorAutoLoadScripts", text)
        self.assertIn("GetEncoding(936)", text)
        self.assertIn("[System.Text.Encoding]::UTF8", text)
        self.assertIn("function U", text)
        self.assertIn("AddAccessoryMenu", text)
        self.assertIn("OpenLine", text)
        self.assertIn("ExportLine", text)
        self.assertIn("cadence_loader_probe.log", text)
        self.assertIn("orcad_enhanced_tools.tcl", text)
        self.assertIn("rename RegisterAction", text)
        self.assertIn("/api/platform/status", text)
        self.assertIn("launcher_latest.log", text)
        self.assertIn("exit 1", text)

    def test_capture_runtime_verifier_waits_for_loader_probe(self) -> None:
        text = (ROOT / "scripts" / "verify_capture_runtime.ps1").read_text(encoding="utf-8")

        self.assertIn("Capture.exe", text)
        self.assertIn("cadence_loader_probe.log", text)
        self.assertIn("RegisterAction=available", text)
        self.assertIn("InsertXMLMenu=available", text)
        self.assertIn("AddAccessoryMenu=available", text)
        self.assertIn("CloseMainWindow", text)
        self.assertIn("exit 1", text)


if __name__ == "__main__":
    unittest.main()
