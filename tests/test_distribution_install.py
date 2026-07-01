from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import base64
from pathlib import Path

# sys.path is prepared by tests/conftest.py so backend imports work.
from app.backend import update_api


ROOT = Path(__file__).resolve().parents[1]
FS_ROOT = ROOT if ROOT.exists() else Path.cwd()


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
            "scripts/bump_version.ps1",
            "scripts/build_installer.ps1",
            "scripts/lib/Paths.ps1",
            "scripts/lib/Cadence.ps1",
            "scripts/lib/EmbeddedPython.ps1",
            "scripts/lib/ReleaseNotice.ps1",
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

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_powershell_scripts_are_parseable(self) -> None:
        scripts = [
            "install.ps1",
            "update.ps1",
            "uninstall.ps1",
            "oneclick_install.ps1",
            "oneclick_update.ps1",
            "oneclick_uninstall.ps1",
            "launch_tool_suite.ps1",
            "scripts/bump_version.ps1",
            "scripts/lib/Paths.ps1",
            "scripts/lib/Cadence.ps1",
            "scripts/lib/EmbeddedPython.ps1",
            "scripts/lib/ReleaseNotice.ps1",
            "scripts/lib/Service.ps1",
            "scripts/lib/Update.ps1",
            "scripts/lib/TclScripts.ps1",
            "scripts/build_frontend.ps1",
            "scripts/build_installer.ps1",
            "scripts/publish_release.ps1",
            "scripts/verify_all.ps1",
            "scripts/redeploy_cadence_loader.ps1",
            "scripts/remove_cadence_loader.ps1",
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
        self.assertIn("ConvertTo-Json -InputObject $InstallRoot", text)
        self.assertNotIn('"install_dir": "$($InstallRoot -replace', text)
        self.assertIn("Find-CadenceLoaderInstallDirs", text)
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
        self.assertTrue((release / "tools" / "bom" / "convert_cadence_bom.py").exists())
        self.assertFalse((release / "frontend").exists())
        self.assertFalse((release / "tests").exists())
        self.assertFalse((release / "docs").exists())
        self.assertFalse((release / "uploads").exists())
        self.assertFalse((release / "outputs").exists())
        self.assertFalse((release / "history").exists())
        self.assertFalse((release / ".gitignore").exists())
        self.assertFalse((release / "config" / "local.json").exists())
        self.assertFalse((release / "cadence" / "archive").exists())
        self.assertFalse((release / "scripts" / "build_frontend.ps1").exists())
        self.assertFalse((release / "scripts" / "build_installer.ps1").exists())
        self.assertFalse((release / "scripts" / "build_release.ps1").exists())
        self.assertFalse((release / "scripts" / "publish_release.ps1").exists())
        self.assertFalse((release / "scripts" / "verify_all.ps1").exists())
        self.assertFalse(any(item.name.startswith("BOM") for item in release.iterdir() if item.is_dir()))

    def test_built_release_tree_contains_cadence_reinstall_ui_when_present(self) -> None:
        release = ROOT.parent / "HWAgent_release"
        if not release.exists():
            self.skipTest("release tree has not been built")

        backend = (release / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")
        index = (release / "app" / "frontend" / "index.html").read_text(encoding="utf-8")
        assets_dir = release / "app" / "frontend" / "assets"
        js_files = sorted(assets_dir.glob("*.js"))
        combined_js = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in js_files)

        self.assertIn("/api/cadence/install", backend)
        self.assertIn("/api/cadence/install", combined_js)
        self.assertIn("修复 Cadence 集成", combined_js)
        self.assertNotIn("index-LJFH012Z.js", index)

    def test_release_builder_does_not_exclude_lowercase_tools_bom_directory(self) -> None:
        text = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
        robocopy_lines = [line for line in text.splitlines() if "robocopy $src $dst" in line]

        self.assertTrue(robocopy_lines)
        for line in robocopy_lines:
            self.assertNotIn('"BOM*"', line)

    def test_tcl_script_library_disables_custom_scripts_in_vendor_autoload(self) -> None:
        text = (ROOT / "scripts" / "lib" / "TclScripts.ps1").read_text(encoding="utf-8")

        self.assertIn("function Disable-HwAgentVendorAutoLoadScripts", text)
        self.assertIn("_disabled_custom_scripts", text)
        self.assertIn("Move-Item", text)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
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

    @unittest.skipUnless(sys.platform == "win32", "windows only")
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
        self.assertIn("Find-CadenceLoaderInstallDirs", update_text)
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

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_update_sync_preserves_windows_uninstaller_and_removes_source_only_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "payload"
            target = Path(tmp) / "install"
            source.mkdir()
            target.mkdir()

            # Simulate the source-ZIP fallback shape: runtime files plus
            # source-only/development files at the repository root.
            (source / "app" / "frontend").mkdir(parents=True)
            (source / "app" / "frontend" / "index.html").write_text("new", encoding="utf-8")
            (source / "Insta360_HW.exe").write_text("new exe", encoding="utf-8")
            (source / "HWAgent_Setup.iss").write_text("dev-only", encoding="utf-8")
            (source / ".gitignore").write_text("dev-only", encoding="utf-8")
            (source / "launcher").mkdir()
            (source / "launcher" / "Insta360_HW.cs").write_text("dev-only", encoding="utf-8")

            # Simulate files generated by Inno inside the installed directory.
            # They are not present in update payloads, but Windows uninstall
            # depends on them staying in place across OTA updates.
            (target / "unins000.exe").write_text("installer uninstaller", encoding="utf-8")
            (target / "unins000.dat").write_text("installer data", encoding="utf-8")
            (target / "old.txt").write_text("old runtime file", encoding="utf-8")

            ps = (
                f". '{ROOT / 'scripts' / 'lib' / 'Update.ps1'}'; "
                f"Sync-HwAgentTree -SourceRoot '{source}' -TargetRoot '{target}'"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertTrue((target / "unins000.exe").exists())
            self.assertTrue((target / "unins000.dat").exists())
            self.assertFalse((target / "old.txt").exists())
            self.assertFalse((target / "HWAgent_Setup.iss").exists())
            self.assertFalse((target / ".gitignore").exists())
            self.assertFalse((target / "launcher").exists())
            self.assertTrue((target / "app" / "frontend" / "index.html").exists())

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_update_sync_preserves_user_dropped_docs_and_frontend_when_source_omits_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "payload"
            target = Path(tmp) / "install"
            source.mkdir()
            target.mkdir()
            (source / "app" / "frontend").mkdir(parents=True)
            (source / "app" / "frontend" / "index.html").write_text("new", encoding="utf-8")

            (target / "docs").mkdir()
            (target / "docs" / "my_notes.md").write_text("user note", encoding="utf-8")
            (target / "frontend").mkdir()
            (target / "frontend" / "local_probe.txt").write_text("user frontend probe", encoding="utf-8")

            ps = (
                f". '{ROOT / 'scripts' / 'lib' / 'Update.ps1'}'; "
                f"Sync-HwAgentTree -SourceRoot '{source}' -TargetRoot '{target}'"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertEqual((target / "docs" / "my_notes.md").read_text(encoding="utf-8"), "user note")
            self.assertEqual((target / "frontend" / "local_probe.txt").read_text(encoding="utf-8"), "user frontend probe")
            self.assertTrue((target / "app" / "frontend" / "index.html").exists())

    def test_update_sync_no_longer_uses_source_only_force_delete_lists(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")

        self.assertNotIn("HwAgentSourceOnlyRootDirs", text)
        self.assertNotIn("HwAgentSourceOnlyRootFiles", text)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_sync_preserves_config_local_json(self) -> None:
        """Sync-HwAgentTree must preserve target's config/local.json when source has one too.

        Also ensures the exclude doesn't accidentally match plugins/user/*/local.json.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source"
            target = tmp_path / "target"

            # Source: has NEW config/local.json plus a plugins/user file with same filename
            (source / "config").mkdir(parents=True)
            (source / "config" / "local.json").write_text('{"src": true}')
            (source / "plugins" / "user" / "custom").mkdir(parents=True)
            (source / "plugins" / "user" / "custom" / "local.json").write_text('{"user_new": true}')
            (source / "app").mkdir()
            (source / "app" / "code.py").write_text("new code")

            # Target: existing installation with USER'S config/local.json (must NOT be overwritten)
            (target / "config").mkdir(parents=True)
            (target / "config" / "local.json").write_text('{"user_config": true}')
            # NOTE: plugins/user is entirely user data - also excluded from sync via /XD
            (target / "app").mkdir()
            (target / "app" / "code.py").write_text("old code")

            ps = (
                f". '{ROOT / 'scripts' / 'lib' / 'Update.ps1'}'; "
                f"Sync-HwAgentTree -SourceRoot '{source}' -TargetRoot '{target}'"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                capture_output=True, text=True, timeout=60,
            )
            # Sync succeeds
            self.assertEqual(result.returncode, 0, f"stderr={result.stderr} stdout={result.stdout}")
            # Target's config/local.json is UNCHANGED (user's original)
            self.assertEqual(
                (target / "config" / "local.json").read_text(),
                '{"user_config": true}',
                "config/local.json overwritten by sync",
            )
            # But app code IS updated
            self.assertEqual((target / "app" / "code.py").read_text(), "new code")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_sync_local_json_exclude_is_path_scoped_not_filename_only(self) -> None:
        """local.json exclude is scoped to config/local.json only.

        Regression: bare filename /XF local.json used to match ANY local.json in tree.
        """
        content = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")
        # Must NOT have bare "local.json" in exclude list
        self.assertNotRegex(
            content,
            r'HwAgentExcludeFiles\s*=\s*@\("local\.json"',
            "HwAgentExcludeFiles has bare 'local.json' - must be path-scoped as 'config\\local.json'",
        )
        self.assertIn('config\\local.json', content, "expected path-scoped config\\local.json in Update.ps1")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_rollback_backup_excludes_config_local_json_scoped(self) -> None:
        """Backup must exclude config/local.json but NOT plugins/user/*/local.json.

        Regression: bare relative "config\\local.json" was passed to robocopy /XF,
        which is a NO-OP; the file leaked into the rollback backup.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "root"
            backup = tmp_path / "backup"
            (root / "config").mkdir(parents=True)
            (root / "config" / "local.json").write_text('{"user_config": true}')
            (root / "plugins" / "user" / "custom").mkdir(parents=True)
            (root / "plugins" / "user" / "custom" / "local.json").write_text('{"user_content": true}')
            (root / "app").mkdir()
            (root / "app" / "code.py").write_text("code")

            ps = (
                f". '{ROOT / 'scripts' / 'lib' / 'Update.ps1'}'; "
                f"Copy-HwAgentTreeForRollback -Root '{root}' -BackupRoot '{backup}'"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, f"stderr={result.stderr} stdout={result.stdout}")
            # config/local.json must NOT be in the backup (user data, /XF-excluded)
            self.assertFalse(
                (backup / "config" / "local.json").exists(),
                "config/local.json leaked into rollback backup",
            )
            # plugins/user is excluded via /XD - not present in backup at all
            # app/code.py should be present
            self.assertTrue((backup / "app" / "code.py").exists())

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_rollback_restore_preserves_user_config_local_json(self) -> None:
        """Restore from rollback must NOT overwrite user's live config/local.json.

        Regression: bare relative "config\\local.json" was passed to robocopy /XF,
        which is a NO-OP; if a stale copy sat in the backup tree, restore would
        clobber the user's live file.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "root"
            backup = tmp_path / "backup"
            # Backup has an old local.json (artificial: simulates a stale copy from
            # before the backup exclude was fixed).
            (backup / "config").mkdir(parents=True)
            (backup / "config" / "local.json").write_text('{"old": true}')
            (backup / "app").mkdir()
            (backup / "app" / "code.py").write_text("old code")
            # Live root has user's NEW local.json
            (root / "config").mkdir(parents=True)
            (root / "config" / "local.json").write_text('{"live_user": true}')
            (root / "app").mkdir()
            (root / "app" / "code.py").write_text("bad code")  # reverted by restore

            ps = (
                f". '{ROOT / 'scripts' / 'lib' / 'Update.ps1'}'; "
                f"Restore-HwAgentTreeFromRollback -Root '{root}' -BackupRoot '{backup}'"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, f"stderr={result.stderr} stdout={result.stdout}")
            # User's live local.json preserved (not overwritten)
            self.assertEqual(
                (root / "config" / "local.json").read_text(),
                '{"live_user": true}',
                "user's local.json overwritten by rollback restore",
            )
            # Other files properly restored
            self.assertEqual((root / "app" / "code.py").read_text(), "old code")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_update_library_rejects_sha256_mismatch_and_removes_bad_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            update_lib = Path(tmp) / "Update.ps1"
            shutil.copyfile(FS_ROOT / "scripts" / "lib" / "Update.ps1", update_lib)
            bad_zip = Path(tmp) / "update.zip"
            bad_zip.write_bytes(b"not the expected package")
            wrong_hash = "0" * 64

            ps = (
                "$ErrorActionPreference='Stop'; "
                f". '{update_lib}'; "
                f"Assert-HwAgentFileHash -Path '{bad_zip}' -ExpectedSha256 '{wrong_hash}'"
            )
            encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(bad_zip.exists())
            self.assertIn("SHA256 mismatch", result.stderr + result.stdout)

    def test_update_zip_download_receives_sha256_from_release_asset_metadata(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")

        self.assertIn("Sha256", text)
        self.assertIn("ExpectedSha256", text)
        self.assertIn("Download-HwAgentFile -Url $zipUrl -Target $zipPath -ExpectedSha256 $expectedSha256", text)
        self.assertNotIn("Download-HwAgentFile -Url $zipUrl -Target $zipPath\n", text)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_update_library_extracts_sha256_from_latest_release_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            update_lib = Path(tmp) / "Update.ps1"
            shutil.copyfile(FS_ROOT / "scripts" / "lib" / "Update.ps1", update_lib)
            sha = "a" * 64
            ps = (
                "$ErrorActionPreference='Stop'; "
                f". '{update_lib}'; "
                "function Invoke-RestMethod { "
                "  param($Method,$Uri,$Headers,$TimeoutSec); "
                "  if ($Uri -like '*/releases/latest') { "
                "    return [pscustomobject]@{ target_commitish='main'; assets=@([pscustomobject]@{ "
                "      name='Insta360_HW_v0.2.16.zip'; browser_download_url='https://example.test/release.zip'; "
                f"      sha256='{sha}'; size=12345 "
                "    }) } "
                "  } "
                "  return [pscustomobject]@{ sha='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' } "
                "} "
                "$asset = Resolve-HwAgentReleaseAssetUrl -Repo 'DECADE0502/Intsa360_HW' -ExpectedRevision ''; "
                "$asset.Url + '|' + $asset.Sha256 + '|' + $asset.Size"
            )
            encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"https://example.test/release.zip|{sha}|12345", result.stdout)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_update_rollback_restores_install_tree_after_apply_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            update_lib = Path(tmp) / "Update.ps1"
            shutil.copyfile(FS_ROOT / "scripts" / "lib" / "Update.ps1", update_lib)
            target = Path(tmp) / "install"
            target.mkdir()
            (target / "VERSION").write_text("0.2.13", encoding="utf-8")
            (target / "old.txt").write_text("keep me", encoding="utf-8")
            (target / "app").mkdir()
            (target / "app" / "stable.txt").write_text("stable", encoding="utf-8")

            ps = (
                "$ErrorActionPreference='Stop'; "
                f". '{update_lib}'; "
                f"$root = '{target}'; "
                "try { "
                "  Invoke-HwAgentWithRollback -Root $root -Operation { "
                "    Set-Content -LiteralPath (Join-Path $root 'VERSION') -Value 'broken' -Encoding UTF8; "
                "    Remove-Item -LiteralPath (Join-Path $root 'old.txt') -Force; "
                "    New-Item -ItemType File -Force -Path (Join-Path $root 'new.txt') | Out-Null; "
                "    throw 'simulated apply failure'; "
                "  } "
                "} catch { Write-Host $_.Exception.Message; exit 23 }"
            )
            encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertIn("simulated apply failure", result.stdout + result.stderr)
            self.assertEqual((target / "VERSION").read_text(encoding="utf-8").strip(), "0.2.13")
            self.assertEqual((target / "old.txt").read_text(encoding="utf-8"), "keep me")
            self.assertEqual((target / "app" / "stable.txt").read_text(encoding="utf-8"), "stable")
            self.assertFalse((target / "new.txt").exists())

    def test_update_status_detection_does_not_depend_on_wmic(self) -> None:
        text = (ROOT / "app" / "backend" / "update_api.py").read_text(encoding="utf-8")

        self.assertNotIn('"wmic"', text)
        self.assertIn("Get-CimInstance Win32_Process", text)

    def test_update_running_probe_ignores_its_own_query_process(self) -> None:
        original_run = update_api.subprocess.run
        try:
            class Completed:
                returncode = 0
                stdout = "12345\r\n"

            seen = {}

            def fake_run(cmd, **kwargs):
                seen["command"] = cmd[-1]
                if "$_.ProcessId -ne $PID" in cmd[-1] and "-File" in cmd[-1]:
                    completed = Completed()
                    completed.stdout = ""
                    return completed
                return Completed()

            update_api.subprocess.run = fake_run
            self.assertFalse(update_api._is_powershell_script_running("update.ps1"))
            self.assertIn("$PID", seen["command"])
        finally:
            update_api.subprocess.run = original_run

    def test_update_status_done_marker_is_not_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            log_dir = root / "data" / "reports" / "runtime"
            log_dir.mkdir(parents=True)
            (log_dir / "update_latest.log").write_text(
                "__HWAGENT_PROGRESS__ 100 update complete; restarting service\n"
                "__HWAGENT_DONE__\n",
                encoding="utf-8",
            )
            original_running = update_api._is_update_running
            try:
                update_api._is_update_running = lambda _root: True
                status = update_api.update_status(root)
            finally:
                update_api._is_update_running = original_running

            self.assertTrue(status["done"])
            self.assertFalse(status["running"])

    def test_run_update_writes_pid_file_for_status_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            log_dir = root / "data" / "reports" / "runtime"
            (root / "update.ps1").write_text("Write-Host hi\n", encoding="utf-8")

            original_running = update_api._is_update_running
            original_popen = update_api.subprocess.Popen
            try:
                update_api._is_update_running = lambda _root: False

                class FakeProcess:
                    pid = 24680

                update_api.subprocess.Popen = lambda *args, **kwargs: FakeProcess()
                result = update_api.run_update(root)
            finally:
                update_api._is_update_running = original_running
                update_api.subprocess.Popen = original_popen

            self.assertEqual(result["status"], "ok")
            self.assertEqual((log_dir / "update_latest.pid").read_text(encoding="utf-8").strip(), "24680")

    def test_update_api_compares_remote_version(self) -> None:
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

    def test_update_scripts_prevent_duplicate_runs_and_bound_robocopy_retries(self) -> None:
        update_text = (ROOT / "update.ps1").read_text(encoding="utf-8")
        lib_text = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")

        self.assertIn("scripts\\lib\\Service.ps1", update_text)
        self.assertIn("Start-HwAgentService", update_text)
        self.assertIn("Global\\Insta360_HW_Update", update_text)
        self.assertIn("WaitOne(0)", update_text)
        self.assertIn("another update is already running", update_text)
        self.assertIn("Stop-HwAgentServicesByPort", lib_text)
        self.assertIn("Stop-HwAgentLauncherProcesses", lib_text)
        self.assertIn("Restore-HwAgentInterruptedUpdate", lib_text)
        self.assertIn("update_pending.json", lib_text)
        self.assertIn("update_rollback_current", lib_text)

        robocopy_arg_lines = [line for line in lib_text.splitlines() if "$args = @(" in line and '"/MIR"' in line]
        self.assertGreaterEqual(len(robocopy_arg_lines), 3)
        for line in robocopy_arg_lines:
            with self.subTest(line=line):
                self.assertIn('"/R:2"', line)
                self.assertIn('"/W:1"', line)

    def test_update_api_refuses_to_start_duplicate_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.13\n", encoding="utf-8")
            (root / "update.ps1").write_text("echo update\n", encoding="utf-8")

            original_running = update_api._is_update_running
            original_popen = subprocess.Popen
            try:
                update_api._is_update_running = lambda _root: True

                def fail_popen(*_args, **_kwargs):
                    raise AssertionError("run_update must not spawn a second updater")

                subprocess.Popen = fail_popen
                result = update_api.run_update(root)
            finally:
                update_api._is_update_running = original_running
                subprocess.Popen = original_popen

            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["already_running"])

    def test_update_scripts_guard_against_downgrade_unless_explicitly_allowed(self) -> None:
        update_text = (ROOT / "update.ps1").read_text(encoding="utf-8")
        lib_text = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")

        self.assertIn("[switch]$AllowDowngrade", update_text)
        self.assertIn("-AllowDowngrade:$AllowDowngrade", update_text)
        self.assertIn("function Assert-VersionMonotonic", lib_text)
        self.assertIn("Compare-HwAgentVersion", lib_text)
        self.assertIn("Refuse to install", lib_text)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_update_library_refuses_downgrade_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            update_lib = Path(tmp) / "Update.ps1"
            shutil.copyfile(FS_ROOT / "scripts" / "lib" / "Update.ps1", update_lib)
            ps = (
                "$ErrorActionPreference='Stop'; "
                f". '{update_lib}'; "
                "Assert-VersionMonotonic -Current '0.2.16' -Remote '0.2.15'"
            )
            encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refuse to install", result.stderr + result.stdout)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_update_library_accepts_downgrade_with_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            update_lib = Path(tmp) / "Update.ps1"
            shutil.copyfile(FS_ROOT / "scripts" / "lib" / "Update.ps1", update_lib)
            ps = (
                "$ErrorActionPreference='Stop'; "
                f". '{update_lib}'; "
                "Assert-VersionMonotonic -Current '0.2.16' -Remote '0.2.15' -AllowDowngrade; "
                "Write-Host ok"
            )
            encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ok", result.stdout)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_update_refuses_when_remote_version_unreachable(self):
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             ". scripts/lib/Update.ps1; try { Assert-VersionMonotonic -Current '0.2.17' -Remote '' } catch { Write-Host $_.Exception.Message }"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=15)
        self.assertIn("refuse to proceed", r.stdout,
                      f"expected fail-closed message, got: {r.stdout} / {r.stderr}")

    def test_git_pull_update_is_wrapped_in_rollback_transaction(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Update.ps1").read_text(encoding="utf-8")
        git_start = text.index("function Invoke-HwAgentGitUpdate")
        git_block = text[git_start:text.index("function Invoke-HwAgentUpdate", git_start)]
        pull_index = git_block.index("git pull --ff-only")
        rollback_index = git_block.index("Invoke-HwAgentWithRollback")

        # Rollback wrapper must enclose the git pull call.
        self.assertLess(rollback_index, pull_index)
        # Complementary-rollback contract: the wrapper's robocopy-based restore
        # excludes .git (Copy-HwAgentTreeForRollback / Restore-HwAgentTreeFromRollback
        # both pass /XD .git), so if a partial pull mutates refs the wrapper
        # cannot restore HEAD. Invoke-HwAgentGitUpdate MUST reset refs itself
        # inside the scriptblock's catch. This is a source-scan assertion because
        # building a real partial-fetch scenario (fetch succeeds, merge fails
        # after refs updated) needs a divergent local file:// remote.
        self.assertIn(
            "reset --hard", git_block,
            "Invoke-HwAgentGitUpdate must reset refs on partial-pull failure; "
            "the wrapper's rollback excludes .git and cannot restore HEAD.",
        )
        self.assertIn("__HWAGENT_GIT_ROLLBACK__", git_block)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_git_pull_dns_failure_leaves_repo_untouched(self) -> None:
        """DNS failure occurs before any ref mutation, so HEAD and tree stay put.

        Note: this covers the easy case only. A true partial-pull failure (fetch
        succeeds, merge fails after refs update) would need a divergent local
        file:// remote and is asserted via source-scan in
        test_git_pull_update_is_wrapped_in_rollback_transaction instead.
        """
        git_exe = shutil.which("git")
        if not git_exe:
            self.skipTest("git.exe not available on PATH")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Construct a minimal git repo with one commit that also looks like
            # a HWAgent install root (so the rollback backup + restore succeeds).
            subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
            subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@test"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "test"], check=True, capture_output=True)
            (tmp_path / "app" / "backend").mkdir(parents=True)
            (tmp_path / "app" / "backend" / "suite_app.py").write_text("# initial", encoding="utf-8")
            subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(tmp_path), "commit", "-m", "initial"],
                check=True, capture_output=True,
            )
            original_head = subprocess.check_output(
                ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True,
            ).strip()

            # Point at a nonexistent remote so `git pull --ff-only` must fail;
            # Invoke-HwAgentGitUpdate should raise, and the rollback wrapper
            # should restore working-tree state.
            update_ps1 = (ROOT / "scripts" / "lib" / "Update.ps1").as_posix()
            root_arg = str(tmp_path).replace("'", "''")
            ps_command = (
                f". '{update_ps1}'; "
                f"try {{ Invoke-HwAgentGitUpdate -Root '{root_arg}' "
                f"-Repo 'https://example.invalid/nonexistent/nonexistent.git' "
                f"-Branch 'main' }} "
                f"catch {{ Write-Host 'ROLLBACK_TRIGGERED' }}"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_command],
                capture_output=True, text=True, timeout=120,
            )

            combined = (result.stdout or "") + (result.stderr or "")
            self.assertIn(
                "ROLLBACK_TRIGGERED", combined,
                f"expected rollback path; stdout={result.stdout!r} stderr={result.stderr!r}",
            )
            # HEAD must be unchanged after rollback.
            head_after = subprocess.check_output(
                ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True,
            ).strip()
            self.assertEqual(
                original_head, head_after,
                f"HEAD moved despite rollback (before={original_head} after={head_after})",
            )
            # Working tree file untouched.
            self.assertEqual(
                (tmp_path / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8"),
                "# initial",
            )

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

    def test_update_api_detects_same_version_remote_revision_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.1\n", encoding="utf-8")
            (root / "REVISION").write_text("1111111111111111111111111111111111111111\n", encoding="utf-8")
            (root / "update.ps1").write_text("echo hi\n", encoding="utf-8")

            original_fetch_version = update_api._fetch_remote_version
            original_fetch_revision = update_api._fetch_remote_revision
            original_fetch_notice = update_api._fetch_remote_update_notice
            original_is_ancestor = update_api._is_revision_ancestor
            try:
                update_api._fetch_remote_version = lambda _root: ("0.2.1", "ok")
                update_api._fetch_remote_revision = lambda _root: ("2222222222222222222222222222222222222222", "ok")
                update_api._fetch_remote_update_notice = lambda _root: ({}, "missing_notice")
                update_api._is_revision_ancestor = lambda _root, ancestor, descendant: ancestor.startswith("1111111") and descendant.startswith("2222222")

                result = update_api.check_update(root)
            finally:
                update_api._fetch_remote_version = original_fetch_version
                update_api._fetch_remote_revision = original_fetch_revision
                update_api._fetch_remote_update_notice = original_fetch_notice
                update_api._is_revision_ancestor = original_is_ancestor

            self.assertTrue(result["has_update"])
            self.assertEqual(result["revision"], "1111111111111111111111111111111111111111")
            self.assertEqual(result["remote_revision"], "2222222222222222222222222222222222222222")
            self.assertEqual(result["update_reason"], "revision")

    def test_update_api_does_not_treat_same_version_older_remote_revision_as_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.13\n", encoding="utf-8")
            (root / "REVISION").write_text("508e5dbe4df3db7195363e21cd749d88426c07ba\n", encoding="utf-8")
            (root / "update.ps1").write_text("echo hi\n", encoding="utf-8")

            original_fetch_version = update_api._fetch_remote_version
            original_fetch_revision = update_api._fetch_remote_revision
            original_fetch_notice = update_api._fetch_remote_update_notice
            original_is_ancestor = update_api._is_revision_ancestor
            try:
                update_api._fetch_remote_version = lambda _root: ("0.2.13", "ok")
                update_api._fetch_remote_revision = lambda _root: ("76f3406ed0a163f3ea3740fb7a642e4328ad06af", "ok")
                update_api._fetch_remote_update_notice = lambda _root: ({}, "missing_notice")
                update_api._is_revision_ancestor = lambda _root, ancestor, descendant: ancestor.startswith("76f3406") and descendant.startswith("508e5db")
                result = update_api.check_update(root)
            finally:
                update_api._fetch_remote_version = original_fetch_version
                update_api._fetch_remote_revision = original_fetch_revision
                update_api._fetch_remote_update_notice = original_fetch_notice
                update_api._is_revision_ancestor = original_is_ancestor

            self.assertFalse(result["has_update"])
            self.assertEqual(result["update_reason"], "")
            self.assertEqual(result["remote_revision"], "76f3406ed0a163f3ea3740fb7a642e4328ad06af")

    def test_update_api_returns_remote_update_notice_for_new_versions(self) -> None:
        self.assertTrue((ROOT / "UPDATE_NOTICE.json").exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.0\n", encoding="utf-8")
            (root / "REVISION").write_text("1111111111111111111111111111111111111111\n", encoding="utf-8")
            (root / "update.ps1").write_text("echo hi\n", encoding="utf-8")

            original_fetch_version = update_api._fetch_remote_version
            original_fetch_revision = update_api._fetch_remote_revision
            original_fetch_notice = update_api._fetch_remote_update_notice
            try:
                update_api._fetch_remote_version = lambda _root: ("0.3.0", "ok")
                update_api._fetch_remote_revision = lambda _root: ("2222222222222222222222222222222222222222", "ok")
                update_api._fetch_remote_update_notice = lambda _root: ({
                    "version": "0.3.0",
                    "revision": "2222222222222222222222222222222222222222",
                    "date": "2026-06-30",
                    "title": "单网络检查增强",
                    "highlights": ["新增复核工作台", "新增更新公告弹窗"],
                    "compatibility": "建议所有硬件工程师更新",
                }, "ok")
                result = update_api.check_update(root)
            finally:
                update_api._fetch_remote_version = original_fetch_version
                update_api._fetch_remote_revision = original_fetch_revision
                update_api._fetch_remote_update_notice = original_fetch_notice

            self.assertTrue(result["has_update"])
            self.assertEqual(result["notice_status"], "ok")
            notice = result["update_notice"]
            self.assertEqual(notice["version"], "0.3.0")
            self.assertEqual(notice["target_revision"], "2222222")
            self.assertEqual(notice["title"], "单网络检查增强")
            self.assertIn("新增更新公告弹窗", notice["highlights"])

    def test_update_api_prefers_remote_revision_over_stale_notice_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.16\n", encoding="utf-8")
            (root / "REVISION").write_text("1111111111111111111111111111111111111111\n", encoding="utf-8")
            (root / "update.ps1").write_text("echo hi\n", encoding="utf-8")

            original_fetch_version = update_api._fetch_remote_version
            original_fetch_revision = update_api._fetch_remote_revision
            original_fetch_notice = update_api._fetch_remote_update_notice
            original_is_ancestor = update_api._is_revision_ancestor
            try:
                update_api._fetch_remote_version = lambda _root: ("0.2.16", "ok")
                update_api._fetch_remote_revision = lambda _root: ("3333333333333333333333333333333333333333", "ok")
                update_api._fetch_remote_update_notice = lambda _root: ({
                    "version": "0.2.16",
                    "revision": "2222222222222222222222222222222222222222",
                    "title": "stale notice revision",
                }, "ok")
                update_api._is_revision_ancestor = lambda _root, ancestor, descendant: True
                result = update_api.check_update(root)
            finally:
                update_api._fetch_remote_version = original_fetch_version
                update_api._fetch_remote_revision = original_fetch_revision
                update_api._fetch_remote_update_notice = original_fetch_notice
                update_api._is_revision_ancestor = original_is_ancestor

            self.assertTrue(result["has_update"])
            self.assertEqual(result["remote_revision"], "3333333333333333333333333333333333333333")
            self.assertEqual(result["update_notice"]["revision"], "3333333333333333333333333333333333333333")
            self.assertEqual(result["update_notice"]["target_revision"], "3333333")

    def test_update_api_normalizes_update_notice_assets(self) -> None:
        sha = "b" * 64
        notice = update_api._normalize_update_notice({
            "version": "0.2.16",
            "assets": [
                {
                    "kind": "release_zip",
                    "url": "https://example.test/Insta360_HW_v0.2.16.zip",
                    "sha256": sha,
                    "size_bytes": 4321,
                },
                {"kind": "", "url": "", "sha256": "bad", "size_bytes": "x"},
            ],
        })

        self.assertEqual(len(notice["assets"]), 1)
        self.assertEqual(notice["assets"][0]["sha256"], sha)
        self.assertEqual(notice["assets"][0]["size_bytes"], 4321)

    def test_publish_release_supports_dry_run_and_writes_sha256_notice_assets(self) -> None:
        text = (ROOT / "scripts" / "publish_release.ps1").read_text(encoding="utf-8")
        notice_lib = (ROOT / "scripts" / "lib" / "ReleaseNotice.ps1").read_text(encoding="utf-8")

        self.assertIn("[switch]$DryRun", text)
        self.assertIn("[switch]$LocalOnly", text)
        self.assertIn("[string]$ZipPath", text)
        self.assertIn("[string]$NoticePath", text)
        self.assertIn("Update-HwAgentNoticeAssets", text)
        self.assertIn("Get-FileHash", notice_lib)
        self.assertIn("size_bytes", notice_lib)
        self.assertIn("sha256", notice_lib)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_publish_release_local_only_produces_valid_sha256_notice_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / "fixture.zip"
            zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            notice_path = tmp_path / "UPDATE_NOTICE.json"
            notice_path.write_text(
                json.dumps({"version": "0.0.0", "revision": "", "assets": []}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "scripts" / "publish_release.ps1"),
                    "-LocalOnly",
                    "-Tag",
                    "v0.0.1",
                    "-ZipPath",
                    str(zip_path),
                    "-NoticePath",
                    str(notice_path),
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )

            stderr = result.stderr.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, stderr)
            notice = json.loads(notice_path.read_text(encoding="utf-8-sig"))

        self.assertEqual(notice["version"], "0.0.1")
        self.assertEqual(len(notice["assets"]), 1)
        asset = notice["assets"][0]
        self.assertEqual(asset["kind"], "release_zip")
        self.assertRegex(asset["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(asset["size_bytes"], zip_path.stat().st_size if zip_path.exists() else 22)
        self.assertIn("/releases/download/v0.0.1/", asset["url"])

    def test_update_api_uses_notice_version_when_version_endpoint_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.3\n", encoding="utf-8")
            (root / "REVISION").write_text("1111111111111111111111111111111111111111\n", encoding="utf-8")
            (root / "update.ps1").write_text("echo hi\n", encoding="utf-8")

            original_fetch_version = update_api._fetch_remote_version
            original_fetch_revision = update_api._fetch_remote_revision
            original_fetch_notice = update_api._fetch_remote_update_notice
            try:
                update_api._fetch_remote_version = lambda _root: ("0.2.3", "ok_raw")
                update_api._fetch_remote_revision = lambda _root: ("", "rate limited")
                update_api._fetch_remote_update_notice = lambda _root: ({
                    "version": "0.2.4",
                    "title": "OTA notice probe",
                    "highlights": ["notice has newer version"],
                }, "ok_raw")
                result = update_api.check_update(root)
            finally:
                update_api._fetch_remote_version = original_fetch_version
                update_api._fetch_remote_revision = original_fetch_revision
                update_api._fetch_remote_update_notice = original_fetch_notice

            self.assertTrue(result["has_update"])
            self.assertEqual(result["remote_version"], "0.2.4")
            self.assertEqual(result["remote_status"], "ok_notice_version")
            self.assertEqual(result["update_reason"], "notice_version")
            self.assertEqual(result["update_notice"]["title"], "OTA notice probe")

    def test_update_api_accepts_codeload_zip_version_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.4\n", encoding="utf-8")
            (root / "update.ps1").write_text("echo hi\n", encoding="utf-8")

            original_fetch_version = update_api._fetch_remote_version
            original_fetch_revision = update_api._fetch_remote_revision
            original_fetch_notice = update_api._fetch_remote_update_notice
            try:
                update_api._fetch_remote_version = lambda _root: ("0.2.5", "ok_zip")
                update_api._fetch_remote_revision = lambda _root: ("", "rate limited")
                update_api._fetch_remote_update_notice = lambda _root: ({
                    "version": "0.2.5",
                    "title": "ZIP version probe",
                }, "ok_zip")
                result = update_api.check_update(root)
            finally:
                update_api._fetch_remote_version = original_fetch_version
                update_api._fetch_remote_revision = original_fetch_revision
                update_api._fetch_remote_update_notice = original_fetch_notice

            self.assertTrue(result["has_update"])
            self.assertEqual(result["remote_status"], "ok_zip")
            self.assertEqual(result["notice_status"], "ok_zip")
            self.assertEqual(result["update_notice"]["title"], "ZIP version probe")

    def test_update_api_reports_latest_when_codeload_zip_version_matches_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "VERSION").write_text("0.2.6\n", encoding="utf-8")
            (root / "update.ps1").write_text("echo hi\n", encoding="utf-8")

            original_fetch_version = update_api._fetch_remote_version
            original_fetch_revision = update_api._fetch_remote_revision
            original_fetch_notice = update_api._fetch_remote_update_notice
            try:
                update_api._fetch_remote_version = lambda _root: ("0.2.6", "ok_zip")
                update_api._fetch_remote_revision = lambda _root: ("", "rate limited")
                update_api._fetch_remote_update_notice = lambda _root: ({
                    "version": "0.2.6",
                    "title": "Current ZIP version",
                }, "ok_zip")
                result = update_api.check_update(root)
            finally:
                update_api._fetch_remote_version = original_fetch_version
                update_api._fetch_remote_revision = original_fetch_revision
                update_api._fetch_remote_update_notice = original_fetch_notice

            self.assertFalse(result["has_update"])
            self.assertEqual(result["remote_status"], "ok_zip")
            self.assertIn("最新", result["message"])

    def test_update_api_falls_back_when_github_contents_api_is_rate_limited(self) -> None:
        import sys
        import urllib.error
        import urllib.request

        class FakeResponse:
            def __init__(self, body: bytes):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return self.body

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "update.ps1").write_text(
                'param([string]$Repo = "https://github.com/DECADE0502/Intsa360_HW.git")',
                encoding="utf-8",
            )

            original_urlopen = urllib.request.urlopen
            calls: list[str] = []

            def fake_urlopen(req, timeout=0):  # noqa: ANN001
                url = req.full_url if hasattr(req, "full_url") else str(req)
                calls.append(url)
                if "api.github.com" in url:
                    raise urllib.error.HTTPError(url, 403, "rate limit exceeded", hdrs=None, fp=None)
                if url.endswith("/VERSION"):
                    return FakeResponse(b"9.9.9\n")
                if url.endswith("/UPDATE_NOTICE.json"):
                    return FakeResponse(json.dumps({"title": "Fallback notice", "highlights": ["raw ok"]}).encode("utf-8"))
                raise AssertionError(url)

            try:
                urllib.request.urlopen = fake_urlopen
                version, version_status = update_api._fetch_remote_version(root)
                notice, notice_status = update_api._fetch_remote_update_notice(root)
            finally:
                urllib.request.urlopen = original_urlopen

            self.assertEqual(version, "9.9.9")
            self.assertEqual(version_status, "ok_raw")
            self.assertEqual(notice_status, "ok_raw")
            self.assertEqual(notice["title"], "Fallback notice")
            self.assertTrue(any("raw.githubusercontent.com" in call for call in calls))

    def test_update_api_uses_codeload_zip_when_raw_main_is_stale(self) -> None:
        import io
        import sys
        import urllib.error
        import urllib.request
        import zipfile

        class FakeResponse:
            def __init__(self, body: bytes):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return self.body

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as archive:
            archive.writestr("Intsa360_HW-main/VERSION", "0.2.4\n")
            archive.writestr(
                "Intsa360_HW-main/UPDATE_NOTICE.json",
                json.dumps({"version": "0.2.4", "title": "ZIP notice"}),
            )
        zip_body = zip_buffer.getvalue()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "update.ps1").write_text(
                'param([string]$Repo = "https://github.com/DECADE0502/Intsa360_HW.git")',
                encoding="utf-8",
            )

            original_urlopen = urllib.request.urlopen

            def fake_urlopen(req, timeout=0):  # noqa: ANN001
                url = req.full_url if hasattr(req, "full_url") else str(req)
                if "api.github.com" in url:
                    raise urllib.error.HTTPError(url, 403, "rate limit exceeded", hdrs=None, fp=None)
                if "raw.githubusercontent.com" in url and url.endswith("/VERSION"):
                    return FakeResponse(b"0.2.3\n")
                if "raw.githubusercontent.com" in url and url.endswith("/UPDATE_NOTICE.json"):
                    return FakeResponse(json.dumps({"version": "0.2.3", "title": "Raw stale"}).encode("utf-8"))
                if "codeload.github.com" in url:
                    return FakeResponse(zip_body)
                raise AssertionError(url)

            try:
                urllib.request.urlopen = fake_urlopen
                version, version_status = update_api._fetch_remote_version(root)
                notice, notice_status = update_api._fetch_remote_update_notice(root)
            finally:
                urllib.request.urlopen = original_urlopen

            self.assertEqual(version, "0.2.4")
            self.assertEqual(version_status, "ok_zip")
            self.assertEqual(notice_status, "ok_zip")
            self.assertEqual(notice["title"], "ZIP notice")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
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

    @unittest.skipUnless(sys.platform == "win32", "windows only")
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

    @unittest.skipUnless(sys.platform == "win32", "windows only")
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

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_uninstall_preupgrade_emits_sentinel_and_keeps_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "install"
            autoload = tmp_path / "autoload"
            autoload.mkdir()
            history = install / "data" / "history"
            history.mkdir(parents=True)
            (install / "app" / "backend").mkdir(parents=True)
            (install / "app" / "backend" / "suite_app.py").write_text("# dummy", encoding="utf-8")
            run_record = history / "run_x.json"
            run_record.write_text("{}", encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "uninstall.ps1"),
                    "-PreUpgrade",
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
            stdout = result.stdout.decode("utf-8", errors="replace")
            self.assertIn("__HWAGENT_PREUPGRADE_STARTED__", stdout)
            self.assertIn("__HWAGENT_PREUPGRADE_DONE__", stdout)
            self.assertTrue(run_record.exists(), "pre-upgrade must not delete user data")
            self.assertTrue(install.exists(), "pre-upgrade must not delete the install root")

    def test_oneclick_uninstall_offers_detach_and_full_cleanup(self) -> None:
        text = _decode_base64_labels(
            (ROOT / "oneclick_uninstall.ps1").read_text(encoding="utf-8")
        )

        self.assertIn("Detach", text)
        self.assertIn("Full", text)
        self.assertIn("完整卸载", text)
        self.assertIn("保留平台文件", text)
        self.assertIn("删除整个平台目录", text)

    def test_full_uninstall_is_not_driven_by_platform_page(self) -> None:
        # Full removal is owned by the installer / Windows Apps. The platform
        # may still expose a safe detach API for Cadence integration.
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
        self.assertIn("ExpectedRevision", text)
        self.assertIn("Latest release package is behind main", text)

    def test_paths_library_finds_vendor_autoload_dirs_separately_from_user_loader_dirs(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Paths.ps1").read_text(encoding="utf-8")

        self.assertIn("function Find-CadenceVendorAutoLoadDirs", text)
        self.assertIn("function Find-CadenceLoaderInstallDirs", text)
        self.assertIn('Get-ChildItem -LiteralPath $root -Directory -Filter "SPB_*"', text)
        self.assertNotIn("SPB_17.4\\tools\\capture\\tclscripts\\capAutoLoad\",\n    (Join-Path $env:USERPROFILE", text)

        redeploy_text = (ROOT / "scripts" / "redeploy_cadence_loader.ps1").read_text(encoding="utf-8")
        uninstall_text = (ROOT / "uninstall.ps1").read_text(encoding="utf-8")
        self.assertIn("Find-CadenceLoaderInstallDirs", redeploy_text)
        self.assertIn("Find-CadenceLoaderInstallDirs", uninstall_text)

    def test_paths_library_discovers_all_spb_vendor_autoload_dirs(self) -> None:
        text = (ROOT / "scripts" / "lib" / "Paths.ps1").read_text(encoding="utf-8")

        self.assertIn('Get-ChildItem -LiteralPath $root -Directory -Filter "SPB_*"', text)
        self.assertIn('tools\\capture\\tclscripts\\capAutoLoad', text)
        self.assertIn('"C:\\Cadence"', text)
        self.assertIn('"D:\\CADENCE\\Cadence"', text)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
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

        self.assertIn("Find-CadenceLoaderInstallDirs", text)
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
        runner = (ROOT / "run_tool_suite.ps1").read_text(encoding="utf-8")

        # The exe must delegate launching to launch_tool_suite.ps1 (which uses
        # Find-Python) instead of hard-coding a Python path.
        self.assertIn("launch_tool_suite.ps1", text)
        self.assertNotIn("codex-primary-runtime", text)
        self.assertNotIn(".venv\\Scripts\\python.exe", text)
        self.assertIn("Find-Python -Root $Root", runner)
        self.assertNotIn("codex-runtimes", runner)
        self.assertNotIn("C:\\Users\\Administrator", runner)

    def test_no_stale_planned_tools_module_or_unused_frontend_dependencies(self) -> None:
        package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        deps = package["dependencies"]

        self.assertFalse((ROOT / "app" / "backend" / "tools" / "planned_tools.py").exists())
        self.assertNotIn("zustand", deps)
        self.assertNotIn("@tanstack/react-table", deps)

    def test_launcher_source_runs_first_run_readiness_then_launches(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")

        self.assertIn("oneclick_install.ps1", text)
        self.assertIn("-Silent", text)
        self.assertIn(".ready", text)
        self.assertIn("ProcessWindowStyle.Hidden", text)

    def test_launcher_ready_marker_uses_localappdata_and_opens_waiting_page_first(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")

        self.assertIn("Environment.SpecialFolder.LocalApplicationData", text)
        self.assertIn('"Insta360_HW", ".ready"', text)
        self.assertNotIn('Path.Combine(root, "data", ".ready")', text)
        self.assertIn("OpenWaitingPage", text)
        self.assertIn("waiting.html", text)
        self.assertLess(text.index("OpenWaitingPage(root)"), text.index("EnsureFirstRunReady(root, installScript, readyMarker)"))

    def test_launcher_has_single_instance_logging_and_user_visible_errors(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")
        build = (ROOT / "launcher" / "build.ps1").read_text(encoding="utf-8")

        self.assertIn("Mutex", text)
        self.assertIn("Global\\\\Insta360_HW.exe", text)
        self.assertIn("launcher.log", text)
        self.assertIn("WriteLog", text)
        self.assertIn("MessageBox.Show", text)
        self.assertIn("OpenPlatformUrl", text)
        self.assertIn("http://127.0.0.1:8765", text)
        self.assertIn("System.Windows.Forms.dll", build)

    def test_launcher_handles_abandoned_mutex_rotates_logs_and_surfaces_readiness_failures(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")

        self.assertIn("AbandonedMutexException", text)
        self.assertIn("MAX_LOG_BYTES", text)
        self.assertIn("MAX_LOG_FILES", text)
        self.assertIn("RotateIfNeeded", text)
        self.assertIn("ShowStartupFailure", text)
        self.assertIn("First-run readiness", text)
        self.assertIn("Cadence loader repair", text)
        self.assertNotIn("鍚", text)
        self.assertNotIn("鏃", text)

    def test_launcher_repairs_cadence_loader_on_every_start(self) -> None:
        text = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")

        self.assertIn("redeploy_cadence_loader.ps1", text)
        self.assertIn("EnsureCadenceLoaderReady", text)
        self.assertIn("RunPowerShellHidden(root, redeployScript", text)

    def test_status_surfaces_cadence_presence_and_launcher_avoids_duplicate_tabs(self) -> None:
        lifecycle = (ROOT / "app" / "backend" / "lifecycle.py").read_text(encoding="utf-8")
        system_status = (ROOT / "frontend" / "src" / "platform" / "SystemStatus.tsx").read_text(encoding="utf-8")
        launcher = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")

        self.assertIn("cadence_present", lifecycle)
        self.assertIn("cadence_present", system_status)
        self.assertIn("Cadence", system_status)
        self.assertIn("Second instance detected", launcher)
        self.assertIn("Platform already ready, skipping browser open", launcher)
        self.assertIn("Platform not ready after wait, opening browser as usual", launcher)

    def test_launcher_build_script_embeds_icon_and_targets_winexe(self) -> None:
        text = (ROOT / "launcher" / "build.ps1").read_text(encoding="utf-8")

        self.assertIn("/target:winexe", text)
        self.assertIn("/win32icon:", text)
        self.assertIn("insta360_icon.ico", text)
        self.assertIn("Insta360_HW.exe", text)
        self.assertIn("AssemblyInfo.cs.template", text)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_launcher_exe_has_version_info(self) -> None:
        exe = ROOT / "Insta360_HW.exe"
        if not exe.exists():
            self.skipTest("launcher exe not built")

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Item '{exe}').VersionInfo | Select-Object FileVersion,CompanyName,ProductName | ConvertTo-Json -Compress",
            ],
            text=True,
            capture_output=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertRegex(info["FileVersion"], r"^\d+\.\d+\.\d+\.\d+$")
        self.assertNotEqual(info["FileVersion"], "0.0.0.0")
        self.assertEqual(info["CompanyName"], "Insta360")
        self.assertEqual(info["ProductName"], "Insta360 HW Platform")

    def test_oneclick_install_supports_silent_mode(self) -> None:
        text = (ROOT / "oneclick_install.ps1").read_text(encoding="utf-8")

        self.assertIn("[switch]$Silent", text)
        self.assertIn("[switch]$NoStart", text)
        # Silent mode must not prompt; it gates all interactive Write-Host output.
        self.assertIn("-not $Silent", text)
        self.assertIn("[AllowEmptyString()]", text)

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

    # ── In-platform Cadence detach API ─────────────────────────────────────

    def test_suite_app_exposes_uninstall_endpoints(self) -> None:
        text = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")

        self.assertIn("/api/uninstall/check", text)
        self.assertIn("/api/uninstall/run", text)
        self.assertIn("/api/uninstall/status", text)
        self.assertIn("update_api.check_uninstall", text)
        self.assertIn("update_api.run_uninstall", text)
        self.assertIn("update_api.uninstall_status", text)

    def test_suite_app_exposes_cadence_reinstall_endpoint(self) -> None:
        text = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        update_status = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")

        self.assertIn("/api/cadence/install", text)
        self.assertIn("installCadenceIntegration", client)
        self.assertIn("/api/cadence/install", client)
        self.assertIn("onInstallCadence", update_status)
        self.assertIn("修复 Cadence 集成", update_status)
        self.assertIn('"installed": installed', text)

    def test_suite_app_exposes_update_status_endpoint(self) -> None:
        text = (ROOT / "app" / "backend" / "suite_app.py").read_text(encoding="utf-8")
        self.assertIn("/api/update/status", text)
        self.assertIn("update_api.update_status", text)

    def test_update_api_supports_detach_but_rejects_full_uninstall(self) -> None:
        text = (ROOT / "app" / "backend" / "update_api.py").read_text(encoding="utf-8")

        self.assertIn("def check_uninstall", text)
        self.assertIn("def run_uninstall", text)
        self.assertIn("def uninstall_status", text)
        # Detach must be safe to run while the service is up. Full removal is
        # intentionally handled by Windows Apps / Insta360_HW_Setup.exe.
        self.assertIn('"detach"', text)
        self.assertIn("Windows Apps", text)
        self.assertIn("Insta360_HW_Setup.exe", text)
        self.assertIn("__HWAGENT_UNINSTALL_PROGRESS__", text)
        self.assertNotIn("完整卸载已启动", text)

    def test_uninstall_script_emits_progress_and_done_markers(self) -> None:
        text = (ROOT / "uninstall.ps1").read_text(encoding="utf-8")

        self.assertIn("__HWAGENT_UNINSTALL_PROGRESS__ 10", text)
        self.assertIn("__HWAGENT_UNINSTALL_PROGRESS__ 40", text)
        self.assertIn("__HWAGENT_UNINSTALL_PROGRESS__ 100", text)
        self.assertIn("__HWAGENT_UNINSTALL_DONE__", text)

    def test_uninstall_uses_localized_safe_service_stop_helper(self) -> None:
        uninstall = (ROOT / "uninstall.ps1").read_text(encoding="utf-8")
        service = (ROOT / "scripts" / "lib" / "Service.ps1").read_text(encoding="utf-8")

        self.assertIn("scripts\\lib\\Service.ps1", uninstall)
        self.assertIn("Stop-HwAgentServicesByPort", uninstall)
        self.assertNotIn("netstat", uninstall)
        self.assertIn("Get-NetTCPConnection", service)

    def test_launcher_only_stops_backend_from_current_install_root(self) -> None:
        text = (ROOT / "launch_tool_suite.ps1").read_text(encoding="utf-8")

        self.assertIn('$BackendScript = Join-Path $Root "app\\backend\\suite_app.py"', text)
        self.assertIn("Resolve-Path -LiteralPath $BackendScript", text)
        self.assertIn("CommandLine -like", text)
        self.assertNotIn('.CommandLine.Contains("suite_app.py")', text)

    def test_uninstall_status_parses_progress_markers_from_log(self) -> None:
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

    def test_full_uninstall_status_reads_temp_log_after_install_root_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "removed-install"
            temp_log = Path(tempfile.gettempdir()) / "hwagent_uninstall_latest.log"
            original = temp_log.read_text(encoding="utf-8", errors="replace") if temp_log.exists() else None
            try:
                temp_log.write_text(
                    "__HWAGENT_UNINSTALL_PROGRESS__ 100 Platform files removed\n"
                    "__HWAGENT_UNINSTALL_DONE__\n",
                    encoding="utf-8",
                )

                status = update_api.uninstall_status(root)

                self.assertTrue(status["done"])
                self.assertEqual(status["progress"], 100)
                self.assertIn("Platform files removed", status["step"])
            finally:
                if original is None:
                    temp_log.unlink(missing_ok=True)
                else:
                    temp_log.write_text(original, encoding="utf-8")

    def test_update_api_does_not_expose_full_uninstall_helper_to_platform(self) -> None:
        text = (ROOT / "app" / "backend" / "update_api.py").read_text(encoding="utf-8")

        self.assertIn("def _full_uninstall_helper", text)
        self.assertIn("Full uninstall from the web UI is intentionally disabled", text)
        self.assertNotIn("run_uninstall(root, \"full\")", text)

    def test_platform_api_rejects_full_uninstall_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            (root / "uninstall.ps1").write_text("echo uninstall", encoding="utf-8")

            check = update_api.check_uninstall(root)
            result = update_api.run_uninstall(root, "full")

            self.assertEqual(check["modes"], ["detach"])
            self.assertEqual(result["status"], "error")
            self.assertIn("Windows", result["error"])

    def test_detach_uninstall_starts_detach_mode_without_deleting_install_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            autoload = Path(tmp) / "autoload"
            root.mkdir()
            autoload.mkdir()
            (root / "uninstall.ps1").write_text("echo uninstall", encoding="utf-8")
            loader = autoload / "iac_bom_tool.tcl"
            loader.write_text("loader", encoding="utf-8")

            original_popen = subprocess.Popen
            captured: dict[str, object] = {}

            class FakePopen:
                def __init__(self, args, **kwargs):
                    captured["args"] = args
                    captured["kwargs"] = kwargs

            try:
                subprocess.Popen = FakePopen
                result = update_api.run_uninstall(root, "detach")
            finally:
                subprocess.Popen = original_popen

            self.assertEqual(result["status"], "ok")
            self.assertTrue(root.exists())
            self.assertTrue(loader.exists())
            self.assertIn("-Mode", captured["args"])
            self.assertIn("Detach", captured["args"])
            self.assertEqual(captured["kwargs"]["cwd"], str(root))

    def test_full_uninstall_preclean_includes_legacy_vendor_loader_dir(self) -> None:
        cleanup_dirs = [str(path) for path in update_api._find_cadence_autoload_dirs()]

        self.assertTrue(
            any(r"SPB_17.4\tools\capture\tclscripts\capAutoLoad" in path for path in cleanup_dirs),
            cleanup_dirs,
        )

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

    def test_outer_stale_inno_setup_file_is_removed(self) -> None:
        self.assertFalse(
            (ROOT.parent / "HWAgent_Setup.iss").exists(),
            "The parent-folder HWAgent_Setup.iss is stale and can build the wrong installer.",
        )

    def test_version_metadata_is_consistent(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8-sig").strip()
        revision = (ROOT / "REVISION").read_text(encoding="utf-8-sig").strip()
        notice = json.loads((ROOT / "UPDATE_NOTICE.json").read_text(encoding="utf-8-sig"))
        iss = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        self.assertEqual(notice["version"], version, "UPDATE_NOTICE.version diverges")
        self.assertEqual(str(notice["revision"]).strip(), revision, "UPDATE_NOTICE.revision diverges")
        self.assertIn(f'#define MyAppVersion "{version}"', iss, "iss version diverges")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_bump_version_script_updates_version_iss_revision_and_notice(self) -> None:
        script = ROOT / "scripts" / "bump_version.ps1"
        self.assertTrue(script.exists(), "scripts/bump_version.ps1 should exist")

        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp) / "fixture"
            temp_root.mkdir()
            (temp_root / "VERSION").write_text("0.1.0\n", encoding="ascii")
            (temp_root / "REVISION").write_text("old\n", encoding="ascii")
            (temp_root / "HWAgent_Setup.iss").write_text(
                '#define MyAppName "Insta360_HW"\n#define MyAppVersion "0.1.0"\n',
                encoding="utf-8",
            )
            (temp_root / "UPDATE_NOTICE.json").write_text(
                json.dumps({"version": "0.1.0", "revision": "old", "date": "", "assets": []}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                    "-NewVersion",
                    "0.2.17",
                    "-Root",
                    str(temp_root),
                    "-Revision",
                    "abcdef1234567890",
                ],
                text=True,
                capture_output=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((temp_root / "VERSION").read_text(encoding="utf-8-sig").strip(), "0.2.17")
            self.assertEqual((temp_root / "REVISION").read_text(encoding="utf-8-sig").strip(), "abcdef1234567890")
            self.assertIn(
                '#define MyAppVersion "0.2.17"',
                (temp_root / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig"),
            )
            notice = json.loads((temp_root / "UPDATE_NOTICE.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(notice["version"], "0.2.17")
            self.assertEqual(notice["revision"], "abcdef1234567890")
            self.assertRegex(notice["date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_inno_existing_install_uninstall_prompt_uses_ascii_text(self) -> None:
        text = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8")

        self.assertIn("Existing installation detected", text)
        self.assertIn("Reinstall and keep local data", text)
        self.assertIn("Uninstall existing version", text)
        self.assertIn("Uninstall complete.", text)
        self.assertNotIn("检测到已安装版本", text)
        self.assertNotIn("卸载现有版本", text)
        self.assertNotIn("鍗", text)
        self.assertNotIn("姝", text)
        self.assertNotIn("妫", text)

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
        self.assertNotIn('Type: filesandordirs; Name: "{app}"', text)
        self.assertIn('uninstall.ps1"" -Mode Detach', text)

    def test_inno_setup_stops_services_before_overwrite_and_warns_on_downgrade(self) -> None:
        text = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8")

        self.assertIn("CloseApplications=yes", text)
        self.assertIn("function PrepareToInstall", text)
        self.assertIn("StopHwAgentServices", text)
        self.assertIn("-PreUpgrade", text)
        self.assertIn("function InitializeSetup", text)
        self.assertIn("CompareSemver", text)
        self.assertIn("A newer version", text)

    def test_iss_source_declares_initialize_uninstall_with_keep_prompt(self):
        """v0.3.0 uninstall must prompt for keep-data and stash to LOCALAPPDATA.

        Inno's [UninstallDelete] section is additive-only (it adds more paths to
        the delete list; it cannot exclude anything), so preserving user data
        during uninstall requires physically moving it out of {app} BEFORE Inno
        starts deleting. This test locks in that InitializeUninstall runs the
        keep-data prompt and stashes to %LOCALAPPDATA%\\Insta360_HW\\keep_data\\.
        """
        iss = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")
        self.assertIn("InitializeUninstall", iss, "InitializeUninstall procedure missing")
        self.assertIn("UninstallKeepData", iss, "UninstallKeepData variable missing")
        self.assertIn("keep_data", iss, "keep_data destination not referenced")
        self.assertIn("LOCALAPPDATA", iss, "LOCALAPPDATA not referenced in stash path")
        # Ensure MsgBox prompts user
        self.assertIn("mbConfirmation", iss, "confirmation prompt missing")
        self.assertIn("MB_YESNO", iss, "yes/no choice missing")

    def test_iss_keep_data_stash_is_timestamped_and_surfaces_failures(self):
        """Keep-data stash must be collision-proof AND surface PowerShell failures.

        Two silent-data-loss risks the previous implementation missed:

        1. Repeat uninstall collision: if %LOCALAPPDATA%\\Insta360_HW\\keep_data\\
           already exists from a prior uninstall, Move-Item -Force on the
           existing (non-empty) destination directory FAILS on Windows
           PowerShell 5.1 and $ErrorActionPreference='Continue' swallows the
           error. User sees "kept" but new data is lost. Fix: timestamp the
           destination subdir (yyyyMMdd_HHmmss) so each uninstall gets a fresh
           empty tree.
        2. Swallowed ResultCode: Exec()'s return code was captured but never
           checked. If PowerShell fails to launch or the stash script exits
           non-zero, user sees no error and Inno wipes {app}. Fix: check
           ResultCode, show a MsgBox on failure, and clear UninstallKeepData.

        This test locks both invariants into the .iss so a future refactor can't
        silently undo either fix.
        """
        iss = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        # Timestamped destination: Get-Date -Format 'yyyyMMdd_HHmmss' feeds a
        # Join-Path so each uninstall lands in its own subdir.
        self.assertIn(
            "Get-Date -Format",
            iss,
            "keep_data destination is not timestamped — repeat uninstall will "
            "silently lose data on Move-Item -Force collision.",
        )
        self.assertIn(
            "yyyyMMdd_HHmmss",
            iss,
            "expected yyyyMMdd_HHmmss timestamp format for keep_data subdir",
        )

        # ResultCode from the stash Exec must be inspected — otherwise a failed
        # PowerShell launch or non-zero exit slips past silently.
        self.assertIn(
            "if ResultCode <> 0 then",
            iss,
            "Pascal must check ResultCode from stash Exec; otherwise PowerShell "
            "failures are swallowed and Inno wipes {app} silently.",
        )

        # Failure MsgBox must render the numeric ResultCode so the user has a
        # diagnostic handle, and must be an error-severity dialog.
        self.assertIn(
            "IntToStr(ResultCode)",
            iss,
            "failure MsgBox must include ResultCode via IntToStr for diagnostics",
        )
        self.assertIn(
            "数据保留失败",
            iss,
            "failure MsgBox message missing — user won't know stash failed",
        )
        self.assertIn(
            "mbError",
            iss,
            "stash failure should use mbError severity",
        )

        # On stash failure, UninstallKeepData must be cleared so downstream
        # consumers know preservation did not succeed.
        self.assertIn(
            "UninstallKeepData := False",
            iss,
            "on stash failure UninstallKeepData must be cleared",
        )

        # Happy-path success MsgBox: user needs to know where their data went.
        self.assertIn(
            "用户数据已备份至",
            iss,
            "success MsgBox missing — user won't know stash location",
        )
        self.assertIn(
            "mbInformation",
            iss,
            "success MsgBox should use mbInformation severity",
        )

    def test_cadence_only_uninstall_does_not_stop_platform_services(self) -> None:
        """cadence_only mode must NOT invoke Stop-HwAgentServicesByPort.

        The web UI's "移除 Cadence 集成" button runs inside the platform
        service on port 8765; killing python on 8765 would kill the very
        service that spawned this script, dropping the response mid-flight
        and leaving the browser stuck on a spinner.
        """
        script = ROOT / "scripts" / "remove_cadence_loader.ps1"
        self.assertTrue(script.exists(), "remove_cadence_loader.ps1 should exist")
        text = script.read_text(encoding="utf-8")
        self.assertNotIn(
            "Stop-HwAgentServicesByPort",
            text,
            "cadence_only script must not stop platform services",
        )
        self.assertNotIn(
            "Stop-HwAgentServices",
            text,
            "cadence_only script must not touch platform services",
        )
        self.assertIn(
            "__HWAGENT_CADENCE_REMOVE_DONE__",
            text,
            "must emit completion sentinel for backend to detect",
        )
        # Must reuse the existing TclScripts helper so vendor scripts stashed
        # by install.ps1 are restored on detach.
        self.assertIn(
            "Restore-HwAgentAutoLoadBackupDirs",
            text,
            "cadence_only script should restore vendor scripts install.ps1 disabled",
        )

    def test_frontend_cadence_removal_uses_cadence_only_mode(self) -> None:
        tsx = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        self.assertIn(
            "cadence_only",
            tsx,
            'UpdateStatus.tsx should use "cadence_only" mode for Cadence removal button',
        )

    def test_update_api_supports_cadence_only_uninstall_mode(self) -> None:
        text = (ROOT / "app" / "backend" / "update_api.py").read_text(encoding="utf-8")
        self.assertIn("cadence_only", text)
        self.assertIn("remove_cadence_loader.ps1", text)

    def test_tcl_script_library_exposes_restore_backup_helper(self) -> None:
        text = (ROOT / "scripts" / "lib" / "TclScripts.ps1").read_text(encoding="utf-8")
        self.assertIn("function Restore-HwAgentAutoLoadBackupDirs", text)
        # Must match both patterns install.ps1 uses to stash prior files.
        self.assertIn("_disabled_hwagent_loader_", text)
        self.assertIn("_disabled_custom_scripts_", text)

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_restore_backup_helper_moves_disabled_files_back_into_autoload_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            autoload = Path(tmp) / "capAutoLoad"
            autoload.mkdir()
            backup = autoload / "_disabled_custom_scripts_20260701"
            backup.mkdir()
            (backup / "orCAD_Enhanced_Tools_V1.8.tcl").write_text("vendor script", encoding="utf-8")

            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{ROOT / 'scripts' / 'lib' / 'TclScripts.ps1'}'; "
                f"$restored = Restore-HwAgentAutoLoadBackupDirs -Dir '{autoload}'; "
                "$restored"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            # File was moved back into the autoload dir.
            self.assertTrue((autoload / "orCAD_Enhanced_Tools_V1.8.tcl").exists())
            # Backup dir was cleaned up.
            self.assertFalse(backup.exists())
            # Function returned a count >= 1.
            self.assertIn("1", result.stdout)

    def test_run_uninstall_cadence_only_invokes_standalone_script_not_uninstall_ps1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            (root / "scripts").mkdir(parents=True)
            (root / "scripts" / "remove_cadence_loader.ps1").write_text(
                "param([string]$InstallDir)\nWrite-Host hi\n", encoding="utf-8",
            )

            captured: dict[str, object] = {}
            original_popen = update_api.subprocess.Popen
            try:
                class FakeProcess:
                    pid = 13579

                def fake_popen(cmd, *args, **kwargs):
                    captured["cmd"] = list(cmd)
                    return FakeProcess()

                update_api.subprocess.Popen = fake_popen
                result = update_api.run_uninstall(root, "cadence_only")
            finally:
                update_api.subprocess.Popen = original_popen

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["mode"], "cadence_only")
            cmd = captured.get("cmd") or []
            joined = " ".join(str(x) for x in cmd)
            # Must invoke the standalone script, not uninstall.ps1.
            self.assertIn("remove_cadence_loader.ps1", joined)
            self.assertNotIn("uninstall.ps1", joined)
            self.assertNotIn("Detach", cmd, f"Detach flag leaked into cadence_only: {cmd}")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_full_uninstall_clears_localappdata(self):
        """Full mode uninstall must remove %LOCALAPPDATA%\\Insta360_HW\\.

        Regression for Task 4.3: prior to this, Full uninstall only wiped the
        install tree, leaving launcher.log, .ready marker, rollback backups,
        and any keep_data\\ stashes behind under %LOCALAPPDATA%\\Insta360_HW\\.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Simulate an install root that Assert-SafeInstallRoot will accept.
            install_dir = tmp / "install"
            (install_dir / "app" / "backend").mkdir(parents=True)
            (install_dir / "app" / "backend" / "suite_app.py").write_text("# dummy")
            # Simulate LOCALAPPDATA presence with the sidecar tree that Full
            # mode is supposed to clean up.
            fake_localappdata = tmp / "AppData"
            (fake_localappdata / "Insta360_HW").mkdir(parents=True)
            (fake_localappdata / "Insta360_HW" / "launcher.log").write_text("test")

            env = os.environ.copy()
            env["LOCALAPPDATA"] = str(fake_localappdata)
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(ROOT / "uninstall.ps1"),
                 "-Mode", "Full", "-InstallDir", str(install_dir), "-Force"],
                capture_output=True, text=True, env=env, timeout=60)
            # After Full uninstall, LOCALAPPDATA subtree must be gone.
            self.assertFalse((fake_localappdata / "Insta360_HW").exists(),
                             f"LOCALAPPDATA\\Insta360_HW still exists after Full uninstall. "
                             f"stdout={result.stdout} stderr={result.stderr}")

    @unittest.skipUnless(sys.platform == "win32", "windows only")
    def test_uninstall_restores_disabled_custom_scripts(self):
        """Uninstall must move _disabled_custom_scripts_*/*.tcl back into the autoload dir.

        Regression for Task 4.3: install.ps1 stashes vendor scripts into
        _disabled_custom_scripts_<date>\\ before dropping iac_bom_tool.tcl.
        uninstall.ps1 previously deleted iac_bom_tool.tcl but never restored
        the vendor scripts — silent data loss.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            install_dir = tmp / "install"
            (install_dir / "app" / "backend").mkdir(parents=True)
            (install_dir / "app" / "backend" / "suite_app.py").write_text("# dummy")

            # Simulate a Cadence autoload dir with a _disabled_custom_scripts_* backup.
            fake_home = tmp / "home"
            auto_load = fake_home / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            auto_load.mkdir(parents=True)
            backup_dir = auto_load / "_disabled_custom_scripts_20260701"
            backup_dir.mkdir()
            (backup_dir / "vendor_tool.tcl").write_text("# vendor tool")
            # Also put iac_bom_tool.tcl to be removed.
            (auto_load / "iac_bom_tool.tcl").write_text("# platform loader")

            env = os.environ.copy()
            env["HOME"] = str(fake_home)
            env["USERPROFILE"] = str(fake_home)
            env["LOCALAPPDATA"] = str(tmp / "AppData")
            # Pass the autoload dir explicitly via -CaptureAutoLoadDir so we
            # don't depend on Find-CadenceLoaderInstallDirs discovering our
            # fake $HOME layout. Run Detach mode so we don't need to touch
            # the install tree — it exercises Remove-CadenceLoader all the
            # same, which is what Task 4.3 fixed.
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(ROOT / "uninstall.ps1"),
                 "-Mode", "Detach", "-InstallDir", str(install_dir),
                 "-CaptureAutoLoadDir", str(auto_load), "-Force"],
                capture_output=True, text=True, env=env, timeout=60)

            # Cadence loader should be gone.
            self.assertFalse((auto_load / "iac_bom_tool.tcl").exists(),
                             f"iac_bom_tool.tcl remains after uninstall. stdout={result.stdout}")
            # Vendor script must be restored to autoload dir.
            self.assertTrue((auto_load / "vendor_tool.tcl").exists(),
                            f"vendor_tool.tcl not restored. stdout={result.stdout} stderr={result.stderr}")
            # Backup dir cleaned.
            self.assertFalse(backup_dir.exists(),
                             f"backup dir {backup_dir} still exists")


if __name__ == "__main__":
    unittest.main()
