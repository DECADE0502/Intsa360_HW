from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _minimal_runtime(root: Path, version: str = "0.3.0") -> None:
    (root / "app" / "backend").mkdir(parents=True)
    (root / "app" / "frontend").mkdir(parents=True)
    (root / "runtime" / "python").mkdir(parents=True)
    (root / "scripts" / "lib").mkdir(parents=True)
    shutil.copytree(ROOT / "scripts" / "lifecycle", root / "scripts" / "lifecycle")
    shutil.copy2(ROOT / "scripts" / "lib" / "Paths.ps1", root / "scripts" / "lib" / "Paths.ps1")
    (root / "app" / "backend" / "suite_app.py").write_text("# runtime\n", encoding="utf-8")
    (root / "app" / "frontend" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (root / "runtime" / "python" / "python.exe").write_bytes(b"python")
    (root / "Insta360_HW.exe").write_bytes(b"launcher")
    (root / "VERSION").write_text(version, encoding="utf-8")
    (root / "REVISION").write_text("a" * 40, encoding="utf-8")
    (root / "install_manifest.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "product": "Insta360_HW",
                "version": version,
                "revision": "a" * 40,
                "layout": "runtime-v2",
            }
        ),
        encoding="utf-8",
    )


class DistributionLifecycleV2Tests(unittest.TestCase):
    def test_runtime_has_one_visible_launcher_and_standard_setup(self) -> None:
        self.assertTrue((ROOT / "Insta360_HW.exe").exists())
        self.assertTrue((ROOT.parent / "Insta360_HW_Setup.exe").exists() or (ROOT / "HWAgent_Setup.iss").exists())
        source = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8")
        self.assertIn("Insta360_HW.exe", source)
        self.assertIn("InitializeUninstall", source)
        self.assertIn("CurUninstallStepChanged", source)
        self.assertIn("PreserveData", source)
        self.assertIn("PurgeData", source)
        self.assertIn("NextButtonClick", source)
        self.assertIn("CancelButtonClick", source)
        self.assertNotIn("/VERYSILENT", source)

    def test_old_update_and_port_kill_libraries_are_removed(self) -> None:
        self.assertFalse((ROOT / "scripts" / "lib" / "Update.ps1").exists())
        self.assertFalse((ROOT / "scripts" / "lib" / "Service.ps1").exists())
        production = "\n".join(
            path.read_text(encoding="utf-8-sig", errors="replace")
            for path in [
                ROOT / "app" / "backend" / "update_api.py",
                ROOT / "app" / "backend" / "lifecycle_update.py",
                ROOT / "launch_tool_suite.ps1",
                ROOT / "update.ps1",
            ]
        )
        self.assertNotIn("source_zip_fallback", production)
        self.assertNotIn("codeload.github", production)
        self.assertNotIn("Stop-HwAgentServicesByPort", production)

    def test_lifecycle_v2_files_are_packaged_by_release_builder(self) -> None:
        builder = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
        self.assertIn('layout = "runtime-v2"', builder)
        self.assertIn('state_root = "%LOCALAPPDATA%\\Insta360_HW"', builder)
        self.assertIn('foreach ($d in @("runtime"))', builder)
        self.assertIn('"data"', builder)
        for name in ("Contract.ps1", "Runtime.ps1", "Worker.ps1", "Install.ps1", "Uninstall.ps1", "Recover.ps1"):
            self.assertTrue((ROOT / "scripts" / "lifecycle" / name).exists(), name)

    def test_install_update_and_uninstall_share_one_lifecycle_mutex(self) -> None:
        contract = (ROOT / "scripts" / "lifecycle" / "Contract.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Enter-HwLifecycleMutex", contract)
        for name in ("Install.ps1", "Worker.ps1", "Uninstall.ps1"):
            source = (ROOT / "scripts" / "lifecycle" / name).read_text(encoding="utf-8-sig")
            self.assertIn("Enter-HwLifecycleMutex", source, name)
            self.assertIn("Exit-HwLifecycleMutex", source, name)
        for name in ("Install.ps1", "Uninstall.ps1"):
            source = (ROOT / "scripts" / "lifecycle" / name).read_text(encoding="utf-8-sig")
            self.assertIn("Assert-HwLifecycleQuiescent", source, name)

    def test_cadence_uninstall_uses_shared_cleanup_directory_discovery(self) -> None:
        remover = (ROOT / "scripts" / "remove_cadence_loader.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-HwAgentCadenceCleanupAutoLoadDirs", remover)
        self.assertNotIn(
            "(Get-HwAgentRecordedCadenceAutoLoadDirs) + (Find-CadenceAutoLoadDirs) + "
            "(Find-CadenceVendorAutoLoadDirs)",
            remover,
        )

    @unittest.skipUnless(os.name == "nt", "Windows lifecycle scripts")
    def test_cadence_cleanup_directory_discovery_keeps_each_result_separate(self) -> None:
        library = ROOT / "scripts" / "lib" / "TclScripts.ps1"
        command = (
            ". '" + str(library).replace("'", "''") + "'; "
            "function Get-HwAgentManagedCadenceAutoLoadDirs { @('C:\\work\\cdssetup\\OrCAD_Capture\\tclscripts\\capAutoLoad',"
            "'D:\\work\\cdssetup\\OrCAD_Capture\\tclscripts\\capAutoLoad') }; "
            "function Find-CadenceVendorAutoLoadDirs { @('C:\\Cadence\\SPB_17.4\\tools\\capture\\tclscripts\\capAutoLoad',"
            "'D:\\Cadence\\SPB_16.6\\tools\\capture\\tclscripts\\capAutoLoad') }; "
            "$paths=@(Get-HwAgentCadenceCleanupAutoLoadDirs); "
            "if($paths.Count -ne 4){Write-Error ('count=' + $paths.Count);exit 2}; "
            "if($paths | Where-Object { $_ -match 'capAutoLoad[A-Z]:' }){Write-Error 'concatenated path';exit 3}; "
            "exit 0"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_release_manifest_is_the_only_production_update_source(self) -> None:
        backend = (ROOT / "app" / "backend" / "lifecycle_update.py").read_text(encoding="utf-8")
        contract = (ROOT / "app" / "backend" / "release_manifest.py").read_text(encoding="utf-8")
        self.assertIn("releases/latest/download/update-manifest.json", contract)
        self.assertIn("ReleaseManifest.parse", backend)
        self.assertIn("manifest.runtime.sha256", backend)
        self.assertIn("download size mismatch", backend)
        self.assertNotIn("git merge-base", backend)

    def test_release_workflow_builds_on_windows_when_version_changes(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("windows-latest", workflow)
        self.assertIn("- VERSION", workflow)
        self.assertIn("publish_release.ps1", workflow)
        self.assertIn("contents: write", workflow)

    def test_publish_script_uploads_runtime_setup_and_strict_manifest(self) -> None:
        publish = (ROOT / "scripts" / "publish_release.ps1").read_text(encoding="utf-8")
        self.assertIn('schema = 2', publish)
        self.assertIn('product = "Insta360_HW"', publish)
        self.assertIn("Get-FileHash", publish)
        self.assertIn("update-manifest.json", publish)
        self.assertIn("Insta360_HW_Setup.exe", publish)
        self.assertIn('minimum_launcher_version = "0.3.0"', publish)
        self.assertNotIn("source ZIP", publish)

    def test_publish_timestamp_is_portable_rfc3339_utc(self) -> None:
        publish = (ROOT / "scripts" / "publish_release.ps1").read_text(encoding="utf-8")

        self.assertIn('ToString("yyyy-MM-ddTHH:mm:ssZ")', publish)
        self.assertNotIn('ToString("o")', publish)

    def test_publish_repair_is_revision_safe_and_verifies_latest_with_retry(self) -> None:
        publish = (ROOT / "scripts" / "publish_release.ps1").read_text(encoding="utf-8")

        self.assertIn("Resolve-GitHubTagRevision", publish)
        self.assertIn("does not point to current revision", publish)
        self.assertIn("Assert-ReleaseManifest", publish)
        self.assertIn("Invoke-PublicVerificationWithRetry", publish)
        self.assertIn("expected manifest SHA256", publish)
        self.assertIn("status --porcelain --untracked-files=normal", publish)
        self.assertIn("Publish-StagedAsset", publish)
        self.assertIn("Promote-StagedAsset", publish)
        self.assertLess(
            publish.index('Promote-StagedAsset -Asset $stagedRuntime'),
            publish.index('Promote-StagedAsset -Asset $stagedManifest'),
        )

    def test_release_workflow_can_repair_an_existing_release(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        self.assertNotIn("release_check.outputs.exists", workflow)
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("group: insta360-hw-release", workflow)
        self.assertIn("cancel-in-progress: false", workflow)

    def test_launcher_uses_registered_identity_and_real_port(self) -> None:
        launcher = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")
        self.assertIn('"runtime", "service.json"', launcher)
        self.assertIn("InstanceToken", launcher)
        self.assertIn("identity.Port", launcher)
        self.assertIn("/api/health", launcher)
        self.assertIn("RunRecovery", launcher)
        self.assertNotIn("const string PlatformUrl", launcher)
        self.assertNotIn("EnsureCadenceLoaderReady", launcher)
        self.assertNotIn("EnsureFirstRunReady", launcher)

    def test_service_launcher_records_exact_process_identity(self) -> None:
        script = (ROOT / "launch_tool_suite.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-HwLifecycleServiceStatePath", script)
        self.assertIn("instance_token", script)
        self.assertIn("schema = 2", script)
        self.assertIn("executable = $Python", script)
        self.assertIn("version = $Version", script)
        self.assertIn("-PassThru", script)
        self.assertIn("Test-HwLifecycleService", script)
        self.assertNotIn("Get-NetTCPConnection", script)
        self.assertNotIn("Stop-HwAgentServicesByPort", script)

    def test_setup_text_is_readable_chinese_and_uses_external_state(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        self.assertIn("Insta360硬件提效平台", setup)
        self.assertIn("{localappdata}\\Insta360_HW", setup)
        self.assertIn("卸载完成", setup)
        self.assertIn('Root: HKLM; Subkey: "Software\\Classes\\insta360-hw"', setup)
        self.assertIn('ValueName: "Owner"; ValueData: "Insta360_HW"', setup)
        self.assertNotIn('Root: HKCU; Subkey: "Software\\Classes\\insta360-hw"', setup)
        for mojibake in ("纭欢", "鍗歌浇", "姝ｅ湪", "鏄惁"):
            self.assertNotIn(mojibake, setup)

    def test_setup_uses_a_vendored_simplified_chinese_language_file(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")
        language = ROOT / "installer" / "ChineseSimplified.isl"

        self.assertIn('MessagesFile: "installer\\ChineseSimplified.isl"', setup)
        self.assertTrue(language.is_file())
        translated = language.read_text(encoding="utf-8-sig")
        self.assertIn("[LangOptions]", translated)
        self.assertIn("LanguageID=$0804", translated)

    def test_setup_surfaces_existing_install_and_broken_runtime_as_repair(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        self.assertIn("ExistingInstallPage", setup)
        self.assertIn("TInputOptionWizardPage", setup)
        self.assertIn("CreateInputOptionPage", setup)
        self.assertIn("DisplayVersion", setup)
        self.assertIn("已检测到已安装版本", setup)
        self.assertIn("安装记录存在，但程序文件不完整", setup)
        self.assertIn("修复/重装", setup)
        self.assertIn("卸载 Insta360硬件提效平台", setup)
        self.assertIn("取消，不做任何更改", setup)
        self.assertIn("SelectedValueIndex := MAINTENANCE_REPAIR", setup)
        self.assertIn("function ShouldSkipPage", setup)

    def test_setup_maintenance_uninstall_repairs_before_launching_fresh_uninstaller(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")
        next_start = setup.index("function NextButtonClick")
        next_end = setup.index("procedure CancelButtonClick", next_start)
        next_block = setup[next_start:next_end]
        uninstall_start = next_block.index("MAINTENANCE_UNINSTALL:")
        uninstall_end = next_block.index("MAINTENANCE_CANCEL:", uninstall_start)
        uninstall_block = next_block[uninstall_start:uninstall_end]
        deinit_start = setup.index("procedure DeinitializeSetup")
        deinit_end = setup.index("function HasUninstallParameter", deinit_start)
        deinit_block = setup[deinit_start:deinit_end]

        self.assertIn("MaintenanceUninstallRequested := True", next_block)
        self.assertNotIn("ExistingUninstaller", uninstall_block)
        self.assertNotIn("WizardForm.Close", uninstall_block)
        self.assertIn("SetupLifecycleSucceeded and MaintenanceUninstallRequested", deinit_block)
        self.assertIn("ExpandConstant('{uninstallexe}')", deinit_block)
        self.assertIn("ewNoWait", deinit_block)
        self.assertIn("function ShouldLaunchPlatform", setup)
        self.assertIn("Check: ShouldLaunchPlatform", setup)
        self.assertIn("先修复卸载组件", setup)
        self.assertLess(setup.index("function NextButtonClick"), setup.index("function PrepareToInstall"))

    def test_setup_registers_one_standard_windows_and_geek_uninstaller(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")
        registry_section = setup.split("[Registry]", 1)[1].split("[Icons]", 1)[0]

        self.assertIn("AppId={{B7F3AC9E-2D5E-4A8C-9F6E-1A3D4E5F6B72}", setup)
        self.assertIn("Uninstallable=yes", setup)
        self.assertIn("CreateUninstallRegKey=yes", setup)
        self.assertIn("UninstallDisplayName={#MyAppName}", setup)
        self.assertIn("UninstallDisplayIcon={app}\\{#MyAppExeName}", setup)
        self.assertNotIn("UninstallString", registry_section)
        self.assertNotIn("QuietUninstallString", registry_section)
        self.assertIn("ExistingUninstaller := AddBackslash(ExistingInstallDir) + 'unins000.exe'", setup)

    def test_uninstall_command_line_modes_are_explicit_and_silent_defaults_to_preserve(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        self.assertIn("function HasUninstallParameter", setup)
        self.assertIn("ParamCount", setup)
        self.assertIn("ParamStr(Index)", setup)
        self.assertIn("'/PURGEDATA'", setup)
        self.assertIn("'/PRESERVEDATA'", setup)
        self.assertIn("if PurgeRequested and PreserveRequested", setup)
        self.assertIn("else if PurgeRequested then", setup)
        self.assertIn("else if PreserveRequested or UninstallSilent then", setup)

    def test_setup_never_predeletes_the_previous_runtime_before_install_commits(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        self.assertNotIn("[InstallDelete]", setup)
        self.assertNotIn('Type: filesandordirs; Name: "{app}\\app"', setup)
        self.assertNotIn('Type: filesandordirs; Name: "{app}\\runtime"', setup)

    @unittest.skipUnless(os.name == "nt", "PowerShell setup transaction")
    def test_setup_transaction_restores_previous_runtime_after_failed_install(self) -> None:
        transaction = ROOT / "scripts" / "lifecycle" / "SetupTransaction.ps1"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root = base / "installed"
            state_root = base / "state"
            install_root.mkdir()
            marker = install_root / "marker.txt"
            marker.write_text("old-runtime", encoding="utf-8")

            begin = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(transaction),
                    "-Action", "Begin", "-InstallRoot", str(install_root), "-StateRoot", str(state_root),
                    "-SkipRunOnce",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            self.assertEqual(begin.returncode, 0, begin.stdout + begin.stderr)

            prepare = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(transaction),
                    "-Action", "PrepareReplace", "-InstallRoot", str(install_root), "-StateRoot", str(state_root),
                    "-SkipRunOnce",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            self.assertEqual(prepare.returncode, 0, prepare.stdout + prepare.stderr)
            self.assertFalse(marker.exists())

            marker.write_text("new-runtime", encoding="utf-8")
            new_file = install_root / "new-only.txt"
            new_file.write_text("new", encoding="utf-8")
            rollback = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(transaction),
                    "-Action", "Rollback", "-InstallRoot", str(install_root), "-StateRoot", str(state_root),
                    "-SkipRunOnce",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )

            self.assertEqual(rollback.returncode, 0, rollback.stdout + rollback.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "old-runtime")
            self.assertFalse(new_file.exists())
            self.assertFalse((state_root / "lifecycle" / "setup" / "active").exists())

    @unittest.skipUnless(os.name == "nt", "PowerShell setup transaction")
    def test_setup_transaction_commit_keeps_new_runtime_and_cleans_backup(self) -> None:
        transaction = ROOT / "scripts" / "lifecycle" / "SetupTransaction.ps1"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root = base / "installed"
            state_root = base / "state"
            install_root.mkdir()
            marker = install_root / "marker.txt"
            marker.write_text("old-runtime", encoding="utf-8")
            obsolete = install_root / "obsolete-module.txt"
            obsolete.write_text("old-only", encoding="utf-8")
            legacy_history = install_root / "data" / "history" / "board.json"
            legacy_history.parent.mkdir(parents=True)
            legacy_history.write_text("legacy-history", encoding="utf-8")
            legacy_plugin = install_root / "plugins" / "user" / "scripts" / "custom.tcl"
            legacy_plugin.parent.mkdir(parents=True)
            legacy_plugin.write_text("legacy-plugin", encoding="utf-8")
            legacy_config = install_root / "config" / "local.json"
            legacy_config.parent.mkdir(parents=True)
            legacy_config.write_text('{"source":"legacy"}', encoding="utf-8")
            current_history = state_root / "data" / "history" / "board.json"
            current_history.parent.mkdir(parents=True)
            current_history.write_text("current-history", encoding="utf-8")
            common = [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(transaction),
                "-InstallRoot", str(install_root), "-StateRoot", str(state_root), "-SkipRunOnce",
            ]

            begin = subprocess.run(
                [*common, "-Action", "Begin"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
            )
            self.assertEqual(begin.returncode, 0, begin.stdout + begin.stderr)
            prepare = subprocess.run(
                [*common, "-Action", "PrepareReplace"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
            )
            self.assertEqual(prepare.returncode, 0, prepare.stdout + prepare.stderr)
            marker.write_text("new-runtime", encoding="utf-8")
            commit = subprocess.run(
                [*common, "-Action", "Commit"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
            )

            self.assertEqual(commit.returncode, 0, commit.stdout + commit.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "new-runtime")
            self.assertFalse(obsolete.exists())
            self.assertEqual(current_history.read_text(encoding="utf-8"), "current-history")
            self.assertEqual(
                (state_root / "plugins" / "user" / "scripts" / "custom.tcl").read_text(encoding="utf-8"),
                "legacy-plugin",
            )
            self.assertEqual(
                (state_root / "config" / "local.json").read_text(encoding="utf-8"),
                '{"source":"legacy"}',
            )
            recovered = list((state_root / "recovered").rglob("board.json"))
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0].read_text(encoding="utf-8"), "legacy-history")
            self.assertFalse((state_root / "lifecycle" / "setup" / "active").exists())

    def test_setup_wires_transaction_recovery_begin_commit_and_rollback(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        self.assertIn("SetupTransaction.ps1", setup)
        self.assertIn("ExtractTemporaryFile", setup)
        self.assertIn("RunSetupTransaction('Recover')", setup)
        self.assertIn("RunSetupTransaction('Begin')", setup)
        self.assertIn("RunSetupTransaction('PrepareReplace')", setup)
        self.assertIn("RunSetupTransaction('Commit')", setup)
        self.assertIn("RunSetupTransaction('Rollback')", setup)
        self.assertIn("procedure DeinitializeSetup", setup)
        self.assertLess(setup.index("RunSetupTransaction('Recover')"), setup.index("RunSetupTransaction('Begin')"))
        self.assertLess(setup.index("RunSetupTransaction('Begin')"), setup.index("-PrepareUpgrade"))
        self.assertLess(setup.index("-PrepareUpgrade"), setup.index("RunSetupTransaction('PrepareReplace')"))

    def test_setup_recovers_interrupted_update_before_upgrade_or_uninstall(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        self.assertIn("ExistingRecovery", setup)
        self.assertIn("UninstallRecovery", setup)
        self.assertLess(setup.index("if FileExists(ExistingRecovery)"), setup.index("if FileExists(ExistingLifecycle)"))
        self.assertIn("-NoRestart", setup)

    def test_setup_postinstall_starts_and_health_checks_the_backend(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")
        start = setup.index("if CurStep = ssPostInstall")
        end = setup.index("function InitializeUninstall", start)
        postinstall = setup[start:end]

        self.assertIn("Install.ps1", postinstall)
        self.assertIn("if MaintenanceUninstallRequested then", postinstall)
        self.assertIn("Parameters := Parameters + ' -NoStart -SkipCadence'", postinstall)

    def test_protocol_registration_has_one_installer_owned_authority(self) -> None:
        launcher = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")
        uninstaller = (ROOT / "scripts" / "lifecycle" / "Uninstall.ps1").read_text(encoding="utf-8")

        self.assertNotIn("EnsureReconnectProtocolReady", launcher)
        self.assertNotIn("Registry.CurrentUser", launcher)
        self.assertIn('HKLM:\\Software\\Classes\\insta360-hw', uninstaller)
        self.assertIn('HKCU:\\Software\\Classes\\insta360-hw', uninstaller)
        self.assertIn("Remove-OwnedProtocolRegistrationAtPath", uninstaller)

    def test_lifecycle_wrappers_never_return_stale_native_exit_codes(self) -> None:
        for name in ("install.ps1", "uninstall.ps1", "oneclick_install.ps1"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("exit $LASTEXITCODE", text, name)
            self.assertIn("exit 0", text, name)

    def test_release_root_exposes_only_the_main_application_entry(self) -> None:
        builder = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
        keep_block = builder.split("$keepFiles = @(", 1)[1].split(")", 1)[0]

        self.assertIn('"Insta360_HW.exe"', keep_block)
        for obsolete in (
            "run_tool_suite.ps1",
            "install.ps1",
            "uninstall.ps1",
            "update.ps1",
            "oneclick_install.ps1",
            "oneclick_uninstall.ps1",
            "oneclick_update.ps1",
        ):
            self.assertNotIn(f'"{obsolete}"', keep_block)
        self.assertIn("Remove-Item -LiteralPath $Release -Recurse -Force", builder)
        self.assertIn('"bump_version.ps1"', builder)
        self.assertIn('"pre_release_check.ps1"', builder)
        self.assertIn('"scripts\\lib\\EmbeddedPython.ps1"', builder)
        self.assertIn('-Filter "__pycache__" -Recurse', builder)

    def test_pre_release_gate_rejects_python_cache_artifacts(self) -> None:
        gate = (ROOT / "scripts" / "pre_release_check.ps1").read_text(encoding="utf-8")

        self.assertIn('-Filter "__pycache__"', gate)
        self.assertIn('-Filter "*.pyc"', gate)
        self.assertIn("Release payload contains Python cache artifact", gate)

    def test_embedded_runtime_download_cache_is_verified_before_reuse(self) -> None:
        library = ROOT / "scripts" / "lib" / "EmbeddedPython.ps1"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out_file = base / "copied.bin"
            env = {**os.environ, "LOCALAPPDATA": str(base / "local")}
            command = (
                f". '{library}'; "
                "$bytes=[Text.Encoding]::UTF8.GetBytes('cached-runtime'); "
                "$sha=([BitConverter]::ToString((New-Object Security.Cryptography.SHA256Managed).ComputeHash($bytes))).Replace('-','').ToLowerInvariant(); "
                "$url='https://example.invalid/runtime.bin'; "
                "$cache=Get-HwAgentDownloadCachePath -Url $url -Sha256 $sha; "
                "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $cache) | Out-Null; "
                "[IO.File]::WriteAllBytes($cache,$bytes); "
                "Invoke-HwAgentDownload -Url $url -OutFile '"
                + str(out_file)
                + "' -Sha256 $sha; "
                "if ([Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes('"
                + str(out_file)
                + "')) -ne 'cached-runtime') { exit 4 }; exit 0"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                env=env,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cadence_detach_removes_only_owned_loader(self) -> None:
        remover = (ROOT / "scripts" / "remove_cadence_loader.ps1").read_text(encoding="utf-8")
        paths = (ROOT / "scripts" / "lib" / "Paths.ps1").read_text(encoding="utf-8")
        install_dirs = paths.split("function Find-CadenceLoaderInstallDirs", 1)[1].split("function ", 1)[0]

        self.assertIn("Remove-HwAgentOwnedCadenceLoader", remover)
        self.assertNotIn("Remove-Item -Force -LiteralPath $loader", remover)
        self.assertIn("Find-CadenceAutoLoadDirs", install_dirs)
        self.assertNotIn("Find-CadenceVendorAutoLoadDirs", install_dirs)

    @unittest.skipUnless(os.name == "nt", "Windows lifecycle scripts")
    def test_install_migrates_mutable_state_and_keeps_runtime_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime, state = base / "HWAgent", base / "state"
            _minimal_runtime(runtime)
            (runtime / "data" / "history").mkdir(parents=True)
            (runtime / "data" / "history" / "run.json").write_text("{}", encoding="utf-8")
            (runtime / "plugins" / "user").mkdir(parents=True)
            (runtime / "plugins" / "user" / "custom.tcl").write_text("# user", encoding="utf-8")
            (runtime / "config").mkdir(exist_ok=True)
            (runtime / "config" / "local.json").write_text("{}", encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "scripts" / "lifecycle" / "Install.ps1"),
                    "-InstallRoot", str(runtime), "-StateRoot", str(state), "-NoStart", "-SkipCadence",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=40,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((state / "data" / "history" / "run.json").exists())
            self.assertTrue((state / "plugins" / "user" / "custom.tcl").exists())
            self.assertTrue((state / "config" / "local.json").exists())
            identity = json.loads((state / "runtime" / "install.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(identity["product"], "Insta360_HW")

    @unittest.skipUnless(os.name == "nt", "Windows lifecycle scripts")
    def test_install_rejects_non_v2_runtime_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime, state = base / "HWAgent", base / "state"
            _minimal_runtime(runtime)
            manifest_path = runtime / "install_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["layout"] = "legacy"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "scripts" / "lifecycle" / "Install.ps1"),
                    "-InstallRoot", str(runtime), "-StateRoot", str(state), "-NoStart", "-SkipCadence",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("runtime-v2", result.stdout + result.stderr)
            log_path = state / "logs" / "install_latest.log"
            self.assertTrue(log_path.exists())
            log_text = log_path.read_text(encoding="utf-8-sig")
            self.assertIn("stage=validating_runtime", log_text)
            self.assertIn("runtime-v2", log_text)

    def test_install_retries_transactional_cadence_deployment_and_commits_identity_last(self) -> None:
        installer = (ROOT / "scripts" / "lifecycle" / "Install.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("function Invoke-CadenceDeploymentAttempt", installer)
        self.assertIn("foreach ($attempt in 1..2)", installer)
        self.assertIn("Restore-HwAgentCadenceDeploymentTransaction", installer)
        self.assertIn('"cadence attempt " + $attempt + " failed:', installer)
        self.assertLess(installer.index("Start-HwLifecycleService"), installer.index('runtime\\install.json'))
        self.assertLess(installer.index("Invoke-CadenceDeploymentAttempt"), installer.rindex('runtime\\install.json'))

    @unittest.skipUnless(os.name == "nt", "Windows lifecycle scripts")
    def test_install_deduplicates_single_discovered_and_recorded_cadence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime, state = base / "HWAgent", base / "state"
            auto_load = base / "SPB_Data" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            auto_load.mkdir(parents=True)
            _minimal_runtime(runtime)
            shutil.copy2(ROOT / "scripts" / "lib" / "Cadence.ps1", runtime / "scripts" / "lib" / "Cadence.ps1")
            shutil.copy2(ROOT / "scripts" / "lib" / "TclScripts.ps1", runtime / "scripts" / "lib" / "TclScripts.ps1")
            shutil.copytree(ROOT / "cadence", runtime / "cadence")
            state.mkdir(parents=True)
            (state / "cadence_integration.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "enabled": True,
                        "loader_paths": [str(auto_load)],
                    }
                ),
                encoding="utf-8",
            )
            env = {
                **os.environ,
                "HOME": str(base / "SPB_Data"),
                "SPB_DATA": str(base / "SPB_Data"),
                "CDS_DATA": "",
                "LOCALAPPDATA": str(base / "local"),
                "INSTA360_HW_STATE_ROOT": str(state),
            }

            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(runtime / "scripts" / "lifecycle" / "Install.ps1"),
                    "-InstallRoot", str(runtime), "-StateRoot", str(state), "-NoStart",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=40,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((auto_load / "iac_bom_tool.tcl").exists())

    def test_install_and_update_share_managed_cadence_directory_discovery(self) -> None:
        for name in ("Install.ps1", "Worker.ps1"):
            source = (ROOT / "scripts" / "lifecycle" / name).read_text(encoding="utf-8-sig")
            self.assertIn("Get-HwAgentManagedCadenceAutoLoadDirs", source, name)
            self.assertNotIn("(Find-CadenceLoaderInstallDirs) + (Get-HwAgentRecordedCadenceAutoLoadDirs)", source, name)

    @unittest.skipUnless(os.name == "nt", "Windows lifecycle scripts")
    def test_preserve_uninstall_keeps_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime, state = base / "HWAgent", base / "state"
            _minimal_runtime(runtime)
            (state / "data" / "history").mkdir(parents=True)
            (state / "data" / "history" / "kept.json").write_text("{}", encoding="utf-8")
            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "scripts" / "lifecycle" / "Uninstall.ps1"),
                    "-InstallRoot", str(runtime), "-StateRoot", str(state), "-Mode", "PreserveData", "-NoStop",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((state / "data" / "history" / "kept.json").exists())
            self.assertTrue(runtime.exists(), "Inno owns final runtime deletion")
            self.assertFalse((runtime / "data").exists(), "runtime junction must not keep the install directory alive")

    @unittest.skipUnless(os.name == "nt", "Windows lifecycle scripts")
    def test_failed_uninstall_records_the_exact_stage_and_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime, state = base / "HWAgent", base / "state"
            _minimal_runtime(runtime)
            remover = runtime / "scripts" / "remove_cadence_loader.ps1"
            remover.write_text("throw 'forced cadence cleanup failure'\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "scripts" / "lifecycle" / "Uninstall.ps1"),
                    "-InstallRoot", str(runtime), "-StateRoot", str(state), "-Mode", "PreserveData", "-NoStop",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            log_path = state / "logs" / "uninstall_latest.log"
            self.assertTrue(log_path.exists())
            log = log_path.read_text(encoding="utf-8-sig")
            self.assertIn("FAILED stage=removing_cadence_integration", log)
            self.assertIn("forced cadence cleanup failure", log)

    def test_inno_uninstall_failure_names_the_diagnostic_log(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8")
        self.assertIn(
            r"%LOCALAPPDATA%\Insta360_HW\logs\uninstall_latest.log",
            setup,
        )

    @unittest.skipUnless(os.name == "nt", "Windows lifecycle scripts")
    def test_purge_uninstall_only_deletes_exact_local_app_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime = base / "HWAgent"
            local = base / "LocalAppData"
            state = local / "Insta360_HW"
            _minimal_runtime(runtime)
            (state / "data").mkdir(parents=True)
            (state / "data" / "private.txt").write_text("delete", encoding="utf-8")
            env = os.environ.copy()
            env["LOCALAPPDATA"] = str(local)
            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "scripts" / "lifecycle" / "Uninstall.ps1"),
                    "-InstallRoot", str(runtime), "-StateRoot", str(state), "-Mode", "PurgeData", "-NoStop",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(state.exists())
            self.assertTrue(local.exists())

    def test_all_shipped_powershell_scripts_parse(self) -> None:
        scripts = [
            path for path in ROOT.rglob("*.ps1")
            if "node_modules" not in path.parts and "data" not in path.parts
        ]
        command = (
            "$failed=$false; $files=@(" + ",".join("'" + str(path).replace("'", "''") + "'" for path in scripts) + "); "
            "foreach($f in $files){$t=$null;$e=$null;"
            "[System.Management.Automation.Language.Parser]::ParseFile($f,[ref]$t,[ref]$e)|Out-Null;"
            "if($e.Count){$failed=$true;$e|%{Write-Error ($f+': '+$_.Message)}}};if($failed){exit 1}"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_non_ascii_powershell_scripts_use_utf8_bom_for_windows_powershell(self) -> None:
        invalid = []
        for path in ROOT.rglob("*.ps1"):
            if "node_modules" in path.parts or "data" in path.parts:
                continue
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
            if any(ord(char) > 127 for char in text) and not raw.startswith(b"\xef\xbb\xbf"):
                invalid.append(str(path.relative_to(ROOT)))

        self.assertEqual(
            invalid,
            [],
            "PowerShell 5 reads UTF-8 without BOM as the local ANSI code page: "
            + ", ".join(invalid),
        )

    def test_platform_does_not_offer_full_self_uninstall(self) -> None:
        api = (ROOT / "app" / "backend" / "update_api.py").read_text(encoding="utf-8")
        frontend = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        self.assertIn('"can_uninstall": False', api)
        self.assertIn("Windows 设置", frontend)
        self.assertNotIn('runUninstall("full")', frontend)

    def test_update_and_check_buttons_are_separate_and_update_is_gated(self) -> None:
        source = (ROOT / "frontend" / "src" / "components" / "UpdateStatus.tsx").read_text(encoding="utf-8")
        self.assertIn("检查更新", source)
        self.assertIn("更新到", source)
        self.assertIn("disabled={!canUpdate}", source)
        self.assertIn("cancelUpdate", source)
        self.assertIn("bytes_per_second", (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
