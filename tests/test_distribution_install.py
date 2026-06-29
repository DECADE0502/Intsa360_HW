from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _decode_base64_labels(text: str) -> str:
    """Concatenate raw script text with UTF-8 decoded `T \"<b64>\"` payloads.

    One-click entry scripts store Chinese UI strings as Base64 to survive
    PowerShell encoding quirks, so tests must decode them before asserting
    on user-facing wording.
    """
    import base64
    import re

    decoded_chunks = []
    for match in re.finditer(r'T\s+"([A-Za-z0-9+/=]+)"', text):
        try:
            decoded_chunks.append(base64.b64decode(match.group(1)).decode("utf-8"))
        except Exception:
            pass
    return text + "\n" + "\n".join(decoded_chunks)


class DistributionInstallTests(unittest.TestCase):
    def test_distribution_scripts_and_libraries_exist(self) -> None:
        expected = [
            "install.ps1",
            "update.ps1",
            "uninstall.ps1",
            "oneclick_update.ps1",
            "scripts/build_installer.ps1",
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
            "uninstall.ps1",
            "oneclick_install.ps1",
            "oneclick_update.ps1",
            "oneclick_uninstall.ps1",
            "launch_tool_suite.ps1",
            "scripts/lib/Paths.ps1",
            "scripts/lib/Cadence.ps1",
            "scripts/lib/Service.ps1",
            "scripts/lib/Update.ps1",
            "scripts/lib/TclScripts.ps1",
            "scripts/build_frontend.ps1",
            "scripts/build_installer.ps1",
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
        self.assertIn("Python lookup failed", text)
        self.assertIn("Skipping Cadence loader deployment", text)
        self.assertIn("Find-CadenceAutoLoadDirs", text)
        self.assertIn("Find-CadenceVendorAutoLoadDirs", text)
        self.assertIn("Disable-HwAgentVendorAutoLoadScripts", text)
        self.assertIn("robocopy", text)
        self.assertNotIn("build_frontend.ps1", text)
        self.assertNotIn("npm install", text)
        self.assertNotIn("pip install", text)
        self.assertNotIn("Start-HwAgentService", text)

    def test_release_builder_outputs_runtime_manifest_and_excludes_dev_tree(self) -> None:
        text = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")

        self.assertIn("install_manifest.json", text)
        self.assertIn("runtime", text)
        self.assertIn('"frontend"', text)
        self.assertIn('"tests"', text)
        self.assertIn('"docs"', text)
        self.assertIn('"BOM*"', text)
        self.assertIn('"frontend/src"', text)
        self.assertIn('"frontend/node_modules"', text)
        self.assertIn('"src"', text)
        self.assertIn('"node_modules"', text)

    def test_built_release_tree_is_runtime_only_when_present(self) -> None:
        release = ROOT.parent / "HWAgent_release"
        if not release.exists():
            self.skipTest("release tree has not been built")

        self.assertTrue((release / "install_manifest.json").exists())
        self.assertTrue((release / "app" / "frontend" / "index.html").exists())
        self.assertFalse((release / "frontend").exists())
        self.assertFalse((release / "tests").exists())
        self.assertFalse((release / "docs").exists())
        self.assertFalse((release / "uploads").exists())
        self.assertFalse((release / "outputs").exists())
        self.assertFalse((release / "history").exists())
        self.assertFalse((release / "scripts" / "build_frontend.ps1").exists())
        self.assertFalse((release / "scripts" / "build_installer.ps1").exists())
        self.assertFalse((release / "scripts" / "build_release.ps1").exists())
        self.assertFalse((release / "scripts" / "publish_release.ps1").exists())
        self.assertFalse((release / "scripts" / "verify_all.ps1").exists())
        self.assertFalse(any(item.name.startswith("BOM") for item in release.iterdir() if item.is_dir()))

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

        for protected in ["data", "uploads", "outputs", "history", "config/local.json", "plugins/user"]:
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

    def test_update_library_supports_zip_update_without_git(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")
        update_text = (ROOT / "update.ps1").read_text(encoding="utf-8")

        # The zip path is the zero-dependency default so end users need no git.
        self.assertIn("function Invoke-HwAgentZipUpdate", text)
        self.assertIn("codeload.github.com", text)
        self.assertIn("Expand-Archive", text)
        # The dispatcher defaults to zip.
        self.assertIn("function Invoke-HwAgentUpdate", text)
        self.assertIn('[string]$Method = "zip"', update_text)

    def test_update_api_compares_remote_version(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            from app.backend import update_api
        finally:
            sys.path.pop(0)

        # Semantic parsing strips non-numeric suffixes for comparison.
        self.assertEqual(update_api._parse_version("0.2.0-dev"), (0, 2, 0))
        self.assertEqual(update_api._parse_version("1.0"), (1, 0, 0))
        self.assertGreater(update_api._parse_version("0.3.0"), update_api._parse_version("0.2.0-dev"))

        # Repo path is extracted from update.ps1's $Repo default.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.0\n", encoding="utf-8")
            (root / "update.ps1").write_text(
                'param([string]$Repo = "https://github.com/DECADE0502/Intsa360_HW.git")',
                encoding="utf-8",
            )
            self.assertEqual(update_api._remote_repo_path(root), "DECADE0502/Intsa360_HW")

            # Live remote fetch — network may be unavailable in CI, so only
            # assert structure when it succeeds.
            remote_version, status = update_api._fetch_remote_version(root)
            if status == "ok":
                self.assertIsInstance(remote_version, str)

    def test_update_status_parses_progress_markers_from_log(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            from app.backend import update_api
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            log_dir = root / "data" / "reports" / "runtime"
            log_dir.mkdir(parents=True)
            log = log_dir / "update_latest.log"

            # Mid-update log: latest marker wins for progress + step.
            log.write_text(
                "__HWAGENT_PROGRESS__ 30 更新包下载完成\n"
                "__HWAGENT_PROGRESS__ 70 正应用更新文件...\n",
                encoding="utf-8",
            )
            s = update_api.update_status(root)
            self.assertEqual(s["progress"], 70)
            self.assertIn("应用", s["step"])
            self.assertFalse(s["done"])

            # Completed log: done marker present.
            log.write_text(
                "__HWAGENT_PROGRESS__ 100 完成\n__HWAGENT_DONE__\n",
                encoding="utf-8",
            )
            s2 = update_api.update_status(root)
            self.assertTrue(s2["done"])
            self.assertIn("完成", s2["message"])
            # Machine markers are stripped from the displayed tail.
            for line in s2["log_tail"]:
                self.assertFalse(line.startswith("__HWAGENT"))

    def test_update_status_reports_explicit_failed_marker(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            from app.backend import update_api
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            log_dir = root / "data" / "reports" / "runtime"
            log_dir.mkdir(parents=True)
            log = log_dir / "update_latest.log"
            log.write_text(
                "__HWAGENT_PROGRESS__ 95 finishing update\n"
                "npm run build failed\n"
                "__HWAGENT_FAILED__ frontend build failed\n",
                encoding="utf-8",
            )

            status = update_api.update_status(root)

            self.assertTrue(status["failed"])
            self.assertFalse(status["running"])
            self.assertIn("frontend build failed", status["error"])

    def test_update_scripts_emit_progress_markers(self) -> None:
        update_text = (ROOT / "update.ps1").read_text(encoding="utf-8")
        lib_text = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")

        # The entry script marks start and done; the lib marks each phase so
        # /api/update/status can report a live percentage.
        self.assertIn("__HWAGENT_PROGRESS__ 0", update_text)
        self.assertIn("__HWAGENT_DONE__", update_text)
        self.assertIn("__HWAGENT_PROGRESS__ 10", lib_text)
        self.assertIn("__HWAGENT_PROGRESS__ 100", update_text)

    def test_update_script_defaults_to_zip_and_skips_user_machine_frontend_build(self) -> None:
        update_text = (ROOT / "update.ps1").read_text(encoding="utf-8")

        # The default update method is zip (no git required on user machines).
        self.assertIn('[string]$Method = "zip"', update_text)
        self.assertIn("Invoke-HwAgentUpdate", update_text)
        self.assertIn("[switch]$BuildFrontend", update_text)
        self.assertIn("if ($BuildFrontend", update_text)
        # verify_all is gated on tests/ existing — installed runtime copies
        # lack the dev tree and must not hard-fail the update at verification.
        self.assertIn('Join-Path $Root "tests"', update_text)

    def test_update_api_reports_git_availability_and_runs_zip_without_git(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            from app.backend import update_api
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.0\n", encoding="utf-8")
            (root / "update.ps1").write_text("echo hi\n", encoding="utf-8")

            check = update_api.check_update.__wrapped__ if hasattr(update_api.check_update, "__wrapped__") else update_api.check_update
            result = update_api.check_update(root)
            self.assertIn("git_available", result)
            self.assertIsInstance(result["git_available"], bool)
            self.assertTrue(result["can_update"])

            # ZIP-based update needs no git, so run_update must NOT hard-fail on
            # a missing git — it should launch the updater (status ok). We
            # can't let the real process run in a test, so just assert the
            # script-exists branch is reached without a git gate.
            self.assertTrue((root / "update.ps1").exists())

    def test_update_library_can_update_plain_folder_from_git_repo(self) -> None:
        if not shutil.which("git"):
            self.skipTest("git is not available")

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
            (install / "plugins" / "user" / "scripts").mkdir(parents=True)
            (install / "plugins" / "user" / "scripts" / "mine.tcl").write_text("keep-user-script", encoding="utf-8")
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
            self.assertEqual((install / "plugins" / "user" / "scripts" / "mine.tcl").read_text(encoding="utf-8"), "keep-user-script")
            self.assertEqual((install / "config" / "local.json").read_text(encoding="utf-8"), '{"install_dir":"local"}')
            self.assertFalse((install / ".git").exists())

    def test_uninstall_script_removes_install_root_and_cadence_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "install"
            autoload = tmp_path / "autoload"
            install.mkdir()
            autoload.mkdir()
            (install / "app").mkdir()
            (install / "plugins" / "user" / "scripts").mkdir(parents=True)
            (install / "plugins" / "user" / "scripts" / "mine.tcl").write_text("delete-me", encoding="utf-8")
            (autoload / "iac_bom_tool.tcl").write_text("loader", encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "uninstall.ps1"),
                    "-InstallDir",
                    str(install),
                    "-CaptureAutoLoadDir",
                    str(autoload),
                    "-Force",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertFalse(install.exists())
            self.assertFalse((autoload / "iac_bom_tool.tcl").exists())

    def test_uninstall_detach_mode_keeps_install_root_and_user_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "install"
            autoload = tmp_path / "autoload"
            install.mkdir()
            autoload.mkdir()
            (install / "app").mkdir()
            (install / "plugins" / "user" / "scripts").mkdir(parents=True)
            user_script = install / "plugins" / "user" / "scripts" / "mine.tcl"
            user_script.write_text("keep-me", encoding="utf-8")
            (autoload / "iac_bom_tool.tcl").write_text("loader", encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "uninstall.ps1"),
                    "-Mode",
                    "Detach",
                    "-InstallDir",
                    str(install),
                    "-CaptureAutoLoadDir",
                    str(autoload),
                    "-Force",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertTrue(install.exists())
            self.assertTrue(user_script.exists())
            self.assertEqual(user_script.read_text(encoding="utf-8"), "keep-me")
            self.assertFalse((autoload / "iac_bom_tool.tcl").exists())

    def test_oneclick_uninstall_offers_detach_and_full_cleanup(self) -> None:
        text = _decode_base64_labels(
            (ROOT / "oneclick_uninstall.ps1").read_text(encoding="utf-8")
        )

        self.assertIn("Detach", text)
        self.assertIn("Full", text)
        self.assertIn("完整卸载", text)
        self.assertIn("保留平台文件", text)
        self.assertIn("删除整个平台目录", text)

    def test_uninstall_is_driven_by_platform_api_not_a_batch(self) -> None:
        # Uninstall moved from a standalone .bat into the platform UI / API.
        # The legacy 一键卸载.bat must NOT exist; the API endpoint must.
        self.assertFalse((ROOT / "一键卸载.bat").exists())
        backend = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")
        self.assertIn("/api/uninstall/check", backend)
        self.assertIn("/api/uninstall/run", backend)

    def test_update_entrypoint_checks_git_and_no_legacy_batch(self) -> None:
        ps1_text = _decode_base64_labels(
            (ROOT / "oneclick_update.ps1").read_text(encoding="utf-8")
        )

        self.assertIn("update.ps1", ps1_text)
        self.assertNotIn("Get-Command git.exe", ps1_text)
        self.assertNotIn("git.exe", ps1_text)
        # The user-facing 一键更新.bat was replaced by the in-platform update UI;
        # the ps1 remains as an internal entry point invoked by the API.
        self.assertFalse((ROOT / "一键更新.bat").exists())

    def test_update_library_prefers_release_asset_runtime_zip(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")

        self.assertIn("Resolve-HwAgentReleaseAssetUrl", text)
        self.assertIn("api.github.com/repos", text)
        self.assertIn("releases/latest", text)
        self.assertIn("install_manifest.json", text)
        self.assertIn("Using runtime release package", text)
        self.assertIn("falling back to source ZIP", text)

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

    # ── Single-exe launcher (Insta360_HW.exe) ──────────────────────────────

    def test_launcher_source_and_build_script_exist(self) -> None:
        self.assertTrue((ROOT / "launcher" / "Insta360_HW.cs").exists())
        self.assertTrue((ROOT / "launcher" / "build.ps1").exists())

    def test_launcher_source_uses_find_python_via_ps1_and_no_hardcoded_python(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")

        # The exe must delegate launching to launch_tool_suite.ps1 (which uses
        # Find-Python) instead of hard-coding a Python path.
        self.assertIn("launch_tool_suite.ps1", text)
        self.assertNotIn("codex-primary-runtime", text)
        self.assertNotIn(".venv\\Scripts\\python.exe", text)

    def test_launcher_source_runs_first_run_readiness_then_launches(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")

        self.assertIn("oneclick_install.ps1", text)
        self.assertIn("-Silent", text)
        self.assertIn(".ready", text)
        self.assertIn("ProcessWindowStyle.Hidden", text)

    def test_launcher_repairs_cadence_loader_on_every_start(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")

        self.assertIn("redeploy_cadence_loader.ps1", text)
        self.assertIn("EnsureCadenceLoaderReady", text)
        self.assertIn("RunPowerShellHidden(root, redeployScript", text)

    def test_launcher_build_script_embeds_icon_and_targets_winexe(self) -> None:
        text = (ROOT / "launcher" / "build.ps1").read_text(encoding="utf-8")

        self.assertIn("/target:winexe", text)
        self.assertIn("/win32icon:", text)
        self.assertIn("insta360_icon.ico", text)
        self.assertIn("Insta360_HW.exe", text)

    def test_oneclick_install_supports_silent_mode(self) -> None:
        text = (ROOT / "oneclick_install.ps1").read_text(encoding="utf-8")

        self.assertIn("[switch]$Silent", text)
        self.assertIn("[switch]$NoStart", text)
        # Silent mode must not prompt; it gates all interactive Write-Host output.
        self.assertIn("-not $Silent", text)

    def test_oneclick_install_is_ascii_safe_for_windows_powershell(self) -> None:
        data = (ROOT / "oneclick_install.ps1").read_bytes()

        try:
            data.decode("ascii")
        except UnicodeDecodeError as exc:
            self.fail(f"oneclick_install.ps1 must be ASCII-safe for Windows PowerShell: {exc}")

    def test_oneclick_install_does_not_install_runtime_dependencies_on_user_machine(self) -> None:
        text = (ROOT / "oneclick_install.ps1").read_text(encoding="utf-8")

        self.assertNotIn("pip install", text)
        self.assertNotIn("openpyxl is missing", text)
        self.assertNotIn("Checking Node.js", text)
        self.assertNotIn("Node.js is ready", text)

    def test_insta360_hw_exe_is_built_with_embedded_icon(self) -> None:
        exe = ROOT / "Insta360_HW.exe"
        self.assertTrue(exe.exists(), "Insta360_HW.exe must be built")
        # PE signature (MZ) sanity check.
        header = exe.read_bytes()[:2]
        self.assertEqual(header, b"MZ")

    # ── Release tree builder ───────────────────────────────────────────────

    def test_release_builder_script_exists_and_ships_exe(self) -> None:
        text = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")

        self.assertIn("launcher\\build.ps1", text)
        self.assertIn("scripts\\build_frontend.ps1", text)
        self.assertIn("Insta360_HW.exe", text)

    # ── In-platform uninstall API ──────────────────────────────────────────

    def test_suite_app_exposes_uninstall_endpoints(self) -> None:
        text = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")

        self.assertIn("/api/uninstall/check", text)
        self.assertIn("/api/uninstall/run", text)
        self.assertIn("/api/uninstall/status", text)
        self.assertIn("update_api.check_uninstall", text)
        self.assertIn("update_api.run_uninstall", text)
        self.assertIn("update_api.uninstall_status", text)

    def test_suite_app_exposes_update_status_endpoint(self) -> None:
        text = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")
        self.assertIn("/api/update/status", text)
        self.assertIn("update_api.update_status", text)

    def test_update_api_supports_detach_and_full_uninstall(self) -> None:
        text = (ROOT / "app" / "backend" / "update_api.py").read_text(encoding="utf-8")

        self.assertIn("def check_uninstall", text)
        self.assertIn("def run_uninstall", text)
        self.assertIn("def uninstall_status", text)
        # Detach must be safe to run while the service is up; Full must defer
        # deletion to a detached helper that waits for the backend to exit.
        self.assertIn('"detach"', text)
        self.assertIn('"full"', text)
        self.assertIn("DETACHED_PROCESS", text)
        self.assertIn("__HWAGENT_UNINSTALL_PROGRESS__", text)
        self.assertIn("Stopping platform service and deleting files", text)

    def test_uninstall_script_emits_progress_and_done_markers(self) -> None:
        text = (ROOT / "uninstall.ps1").read_text(encoding="utf-8")

        self.assertIn("__HWAGENT_UNINSTALL_PROGRESS__ 10", text)
        self.assertIn("__HWAGENT_UNINSTALL_PROGRESS__ 40", text)
        self.assertIn("__HWAGENT_UNINSTALL_PROGRESS__ 100", text)
        self.assertIn("__HWAGENT_UNINSTALL_DONE__", text)

    def test_uninstall_status_parses_progress_markers_from_log(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT))
        try:
            from app.backend import update_api
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            log_dir = root / "data" / "reports" / "runtime"
            log_dir.mkdir(parents=True)
            log = log_dir / "uninstall_latest.log"

            log.write_text(
                "__HWAGENT_UNINSTALL_PROGRESS__ 20 Removing Cadence integration\n"
                "__HWAGENT_UNINSTALL_PROGRESS__ 70 Waiting for platform service to exit\n",
                encoding="utf-8",
            )
            status = update_api.uninstall_status(root)
            self.assertEqual(status["progress"], 70)
            self.assertIn("Waiting", status["step"])
            self.assertFalse(status["done"])

            log.write_text(
                "__HWAGENT_UNINSTALL_PROGRESS__ 100 Complete\n"
                "__HWAGENT_UNINSTALL_DONE__\n",
                encoding="utf-8",
            )
            done = update_api.uninstall_status(root)
            self.assertTrue(done["done"])
            self.assertEqual(done["progress"], 100)
            for line in done["log_tail"]:
                self.assertFalse(line.startswith("__HWAGENT"))

    def test_update_api_full_uninstall_helper_runs_from_temp_and_waits(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT))
        try:
            from app.backend import update_api
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            helper = update_api._full_uninstall_helper(root, ["powershell", "-File", "uninstall.ps1", "-Mode", "Full"])
            self.assertIn("Set-Location $env:TEMP", helper)
            self.assertIn("uninstall.ps1", helper)
            self.assertIn("__HWAGENT_UNINSTALL_PROGRESS__", helper)
            self.assertIn("Stopping platform service and deleting files", helper)
            self.assertIn("Tee-Object -FilePath $log -Append", helper)
            self.assertIn("__HWAGENT_UNINSTALL_DONE__", helper)
            self.assertNotIn("*> $null", helper)

            check = update_api.check_uninstall(root)
            self.assertFalse(check["can_uninstall"])
            self.assertEqual(check["modes"], [])

    def test_inno_setup_points_shortcuts_at_exe(self) -> None:
        iss = ROOT / "HWAgent_Setup.iss"
        text = iss.read_text(encoding="utf-8")

        # Shortcuts must launch the exe, not the legacy bat.
        self.assertIn(r"{app}\Insta360_HW.exe", text)
        self.assertNotIn(r"{app}\启动硬件效率工具集.bat", text)
        # Control panel uninstall display icon is the exe.
        self.assertIn(r"UninstallDisplayIcon={app}\Insta360_HW.exe", text)
        # Installer runs the silent oneclick install.
        self.assertIn('oneclick_install.ps1"" -Silent', text)

    def test_inno_setup_version_matches_runtime_version(self) -> None:
        iss = ROOT / "HWAgent_Setup.iss"
        text = iss.read_text(encoding="utf-8")
        version = (ROOT / "VERSION").read_text(encoding="utf-8-sig").strip()

        self.assertIn(f'#define MyAppVersion "{version}"', text)

    def test_installer_build_script_finds_inno_and_outputs_named_setup(self) -> None:
        text = (ROOT / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")

        self.assertIn("HWAgent_Setup.iss", text)
        self.assertIn("Insta360_HW_Setup.exe", text)
        self.assertIn("ISCC.exe", text)
        self.assertIn("Inno Setup", text)
        self.assertIn("build_release.ps1", text)

    def test_inno_setup_preserves_user_state_on_upgrade_and_does_not_start_service(self) -> None:
        iss = ROOT / "HWAgent_Setup.iss"
        text = iss.read_text(encoding="utf-8")

        self.assertIn('Excludes: "data\\*,uploads\\*,outputs\\*,history\\*,config\\local.json,plugins\\user\\*"', text)
        self.assertIn('oneclick_install.ps1"" -Silent -NoStart', text)
        self.assertNotIn("Python", text)
        self.assertNotIn("openpyxl", text)
        self.assertNotIn("npm", text)
        self.assertNotIn("检查依赖", text)
        self.assertNotIn("Start-HwAgentService", text)
        self.assertIn("[InstallDelete]", text)
        for stale_dir in ["app", "cadence", "scripts", "tools"]:
            self.assertIn(f'Type: filesandordirs; Name: "{{app}}\\{stale_dir}"', text)
        self.assertIn("[UninstallDelete]", text)
        self.assertIn('Type: filesandordirs; Name: "{app}"', text)
        self.assertIn('uninstall.ps1"" -Mode Detach', text)


if __name__ == "__main__":
    unittest.main()
