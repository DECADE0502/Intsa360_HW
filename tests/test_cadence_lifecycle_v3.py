from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / "scripts" / "lib" / "CadenceDiscovery.ps1"
PATHS = ROOT / "scripts" / "lib" / "Paths.ps1"
CADENCE = ROOT / "scripts" / "lib" / "Cadence.ps1"
TCL_SCRIPTS = ROOT / "scripts" / "lib" / "TclScripts.ps1"
REMOVE = ROOT / "scripts" / "remove_cadence_loader.ps1"
LEGACY_INSTALL = ROOT / "cadence" / "install_cadence_integration.ps1"
UPDATE_WORKER = ROOT / "scripts" / "lifecycle" / "Worker.ps1"
LOADER_MARKER = "# Insta360_HW Cadence Loader | schema=2 | managed=true"


def _quote(path: Path) -> str:
    return str(path).replace("'", "''")


def _run_powershell(command: str, *, env: dict[str, str] | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


@unittest.skipUnless(os.name == "nt", "Windows Cadence integration")
class CadenceLifecycleV3Tests(unittest.TestCase):
    def test_legacy_install_entry_delegates_to_the_owned_repair_flow(self) -> None:
        source = LEGACY_INSTALL.read_text(encoding="utf-8")

        self.assertIn("redeploy_cadence_loader.ps1", source)
        self.assertNotIn("WriteAllText", source)
        self.assertNotIn("PLMMenu.tcl", source)
        self.assertNotIn("Get-ChildItem C:\\", source)

    def test_update_reloads_cadence_libraries_after_runtime_activation(self) -> None:
        source = UPDATE_WORKER.read_text(encoding="utf-8-sig")
        activated = source.index('Write-Journal -Phase "new_runtime_activated"')
        reloaded = source.index('Join-Path $InstallRoot "scripts\\lib\\Cadence.ps1"', activated)
        deployed = source.index("Install-CadenceLoader", reloaded)

        self.assertLess(activated, reloaded)
        self.assertLess(reloaded, deployed)

    def test_discovery_path_normalization_preserves_drive_roots(self) -> None:
        command = (
            f". '{_quote(DISCOVERY)}'; "
            "@(ConvertTo-HwAgentUniqueFullPaths -Paths @('C:\\','D:\\')) | ConvertTo-Json -Compress"
        )
        result = _run_powershell(command)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        roots = json.loads(result.stdout.strip())
        self.assertEqual([value.upper() for value in roots], ["C:\\", "D:\\"])

    def test_discovery_finds_user_and_only_supported_vendor_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            user_root = base / "SPB_Data"
            user_auto_load = user_root / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            vendor_166 = base / "drive-c" / "Cadence" / "SPB_16.6" / "tools" / "capture" / "tclscripts" / "capAutoLoad"
            vendor_174 = base / "drive-d" / "Cadence" / "Cadence" / "SPB_17.4" / "tools" / "capture" / "tclscripts" / "capAutoLoad"
            unsupported = base / "drive-d" / "Cadence" / "SPB_18.1" / "tools" / "capture" / "tclscripts" / "capAutoLoad"
            for path in (user_auto_load, vendor_166, vendor_174, unsupported):
                path.mkdir(parents=True)

            command = (
                f". '{_quote(DISCOVERY)}'; "
                "$result=Get-HwAgentCadenceDiscovery "
                f"-DriveRoots @('{_quote(base / 'drive-c')}','{_quote(base / 'drive-d')}') "
                f"-UserRoots @('{_quote(user_root)}','{_quote(user_root)}'); "
                "$result | ConvertTo-Json -Depth 6 -Compress"
            )
            result = _run_powershell(command)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip())
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual([Path(item).resolve() for item in payload["user_autoload_dirs"]], [user_auto_load.resolve()])
        installations = payload["vendor_installations"]
        self.assertEqual({item["version"] for item in installations}, {"16.6", "17.4"})
        self.assertEqual(
            {Path(item["autoload_dir"]).resolve() for item in installations},
            {vendor_166.resolve(), vendor_174.resolve()},
        )
        self.assertNotIn(str(unsupported.resolve()), json.dumps(payload))

    def test_discovery_accepts_cdsroot_style_tools_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vendor_root = Path(tmp) / "SPB_17.4"
            auto_load = vendor_root / "tools" / "capture" / "tclscripts" / "capAutoLoad"
            auto_load.mkdir(parents=True)
            command = (
                f". '{_quote(DISCOVERY)}'; "
                "$result=Get-HwAgentCadenceDiscovery -DriveRoots @() -UserRoots @() "
                f"-VendorRoots @('{_quote(vendor_root / 'tools')}'); "
                "$result | ConvertTo-Json -Depth 6 -Compress"
            )
            result = _run_powershell(command)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip())
        self.assertEqual(len(payload["vendor_installations"]), 1)
        self.assertEqual(payload["vendor_installations"][0]["version"], "17.4")
        self.assertEqual(Path(payload["vendor_installations"][0]["autoload_dir"]).resolve(), auto_load.resolve())

    def test_repair_is_idempotent_and_records_one_owned_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = base / "state"
            auto_load = base / "SPB_Data" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            auto_load.mkdir(parents=True)
            (auto_load / "PLMTools.tcl").write_text("# third-party\n", encoding="utf-8")
            env = {**os.environ, "INSTA360_HW_STATE_ROOT": str(state)}
            command = (
                f". '{_quote(PATHS)}'; . '{_quote(CADENCE)}'; . '{_quote(TCL_SCRIPTS)}'; "
                f"$dir='{_quote(auto_load)}'; "
                f"$python='{_quote(Path(os.sys.executable))}'; "
                f"$first=@(Install-CadenceLoader -ToolRoot '{_quote(ROOT)}' -PythonPath $python -AutoLoadDirs @($dir)); "
                "Set-HwAgentCadenceOwnershipManifest -LoaderPaths $first | Out-Null; "
                "$loader=Join-Path $dir 'iac_bom_tool.tcl'; $ticks=(Get-Item -LiteralPath $loader).LastWriteTimeUtc.Ticks; "
                "Start-Sleep -Milliseconds 1100; "
                f"$second=@(Install-CadenceLoader -ToolRoot '{_quote(ROOT)}' -PythonPath $python -AutoLoadDirs @($dir)); "
                "Set-HwAgentCadenceOwnershipManifest -LoaderPaths $second | Out-Null; "
                "$manifest=Get-HwAgentCadenceOwnershipManifest; "
                "[pscustomobject]@{same_timestamp=((Get-Item -LiteralPath $loader).LastWriteTimeUtc.Ticks -eq $ticks); "
                "owned_count=@($manifest.owned_files).Count; loader=$manifest.owned_files[0].path} | ConvertTo-Json -Compress"
            )
            result = _run_powershell(command, env=env, timeout=40)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertTrue(payload["same_timestamp"])
            self.assertEqual(payload["owned_count"], 1)
            self.assertEqual(Path(payload["loader"]).resolve(), (auto_load / "iac_bom_tool.tcl").resolve())
            self.assertTrue((auto_load / "PLMTools.tcl").exists())

    def test_remove_cleans_all_owned_copies_and_preserves_unknown_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = base / "state"
            user_dir = base / "SPB_Data" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            vendor_dir = base / "Cadence" / "SPB_17.4" / "tools" / "capture" / "tclscripts" / "capAutoLoad"
            unknown_dir = base / "other" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            for path in (user_dir, vendor_dir, unknown_dir):
                path.mkdir(parents=True)
                (path / "PLMTools.tcl").write_text("# preserve me\n", encoding="utf-8")
            for path in (user_dir / "iac_bom_tool.tcl", vendor_dir / "iac_bom_tool.tcl"):
                path.write_text(LOADER_MARKER + "\n", encoding="utf-8")
            unknown_loader = unknown_dir / "iac_bom_tool.tcl"
            unknown_loader.write_text("# third-party loader\n", encoding="utf-8")
            env = {**os.environ, "INSTA360_HW_STATE_ROOT": str(state)}

            prepare = (
                f". '{_quote(PATHS)}'; . '{_quote(TCL_SCRIPTS)}'; "
                f"Set-HwAgentCadenceIntegrationState -Enabled:$true -LoaderPaths @('{_quote(user_dir)}') | Out-Null; "
                f"Set-HwAgentCadenceOwnershipManifest -LoaderPaths @('{_quote(user_dir / 'iac_bom_tool.tcl')}',"
                f"'{_quote(vendor_dir / 'iac_bom_tool.tcl')}') | Out-Null"
            )
            prepared = _run_powershell(prepare, env=env)
            self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)

            removed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(REMOVE),
                    "-InstallDir",
                    str(ROOT),
                    "-AutoLoadDirs",
                    str(user_dir),
                    str(unknown_dir),
                    "-SkipDiscovery",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=env,
            )

            self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
            self.assertFalse((user_dir / "iac_bom_tool.tcl").exists())
            self.assertFalse((vendor_dir / "iac_bom_tool.tcl").exists())
            self.assertTrue(unknown_loader.exists())
            self.assertTrue((user_dir / "PLMTools.tcl").exists())
            self.assertTrue((vendor_dir / "PLMTools.tcl").exists())
            self.assertTrue((unknown_dir / "PLMTools.tcl").exists())

            inspect = (
                f". '{_quote(PATHS)}'; . '{_quote(TCL_SCRIPTS)}'; "
                "$state=Get-HwAgentCadenceIntegrationState; $manifest=Get-HwAgentCadenceOwnershipManifest; "
                "[pscustomobject]@{enabled=$state.enabled; owned_count=@($manifest.owned_files).Count} | ConvertTo-Json -Compress"
            )
            inspected = _run_powershell(inspect, env=env)
            self.assertEqual(inspected.returncode, 0, inspected.stdout + inspected.stderr)
            payload = json.loads(inspected.stdout.strip())
            self.assertFalse(payload["enabled"])
            self.assertEqual(payload["owned_count"], 0)

    def test_deployment_transaction_restores_ownership_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = base / "state"
            old_dir = base / "old" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            new_dir = base / "new" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            for path in (old_dir, new_dir):
                path.mkdir(parents=True)
                (path / "iac_bom_tool.tcl").write_text(LOADER_MARKER + "\n", encoding="utf-8")
            env = {**os.environ, "INSTA360_HW_STATE_ROOT": str(state)}
            command = (
                f". '{_quote(PATHS)}'; . '{_quote(TCL_SCRIPTS)}'; "
                f"$old='{_quote(old_dir / 'iac_bom_tool.tcl')}'; $new='{_quote(new_dir / 'iac_bom_tool.tcl')}'; "
                "Set-HwAgentCadenceOwnershipManifest -LoaderPaths @($old) | Out-Null; "
                f"$snapshot=Start-HwAgentCadenceDeploymentTransaction -AutoLoadDirs @('{_quote(old_dir)}','{_quote(new_dir)}'); "
                "Set-HwAgentCadenceOwnershipManifest -LoaderPaths @($new) | Out-Null; "
                "Restore-HwAgentCadenceDeploymentTransaction -SnapshotRoot $snapshot; "
                "$manifest=Get-HwAgentCadenceOwnershipManifest; "
                "[pscustomobject]@{count=@($manifest.owned_files).Count; path=$manifest.owned_files[0].path} | ConvertTo-Json -Compress; "
                "Complete-HwAgentCadenceDeploymentTransaction -SnapshotRoot $snapshot"
            )
            result = _run_powershell(command, env=env)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[0])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(Path(payload["path"]).resolve(), (old_dir / "iac_bom_tool.tcl").resolve())


if __name__ == "__main__":
    unittest.main()
