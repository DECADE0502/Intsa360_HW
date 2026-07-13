from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.backend.paths import AppPaths
from app.backend.release_manifest import ReleaseManifest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "lifecycle" / "Contract.ps1"
RUNTIME = ROOT / "scripts" / "lifecycle" / "Runtime.ps1"
TCL_SCRIPTS = ROOT / "scripts" / "lib" / "TclScripts.ps1"
PATHS = ROOT / "scripts" / "lib" / "Paths.ps1"


def _manifest() -> dict[str, object]:
    return {
        "schema": 2,
        "product": "Insta360_HW",
        "version": "2.0.0",
        "revision": "a" * 40,
        "published_at": "2026-07-13T00:00:00Z",
        "channel": "stable",
        "minimum_launcher_version": "2.0.0",
        "assets": {
            "runtime": {
                "name": "Insta360_HW_runtime_v2.0.0.zip",
                "url": "https://example.invalid/releases/download/v2.0.0/Insta360_HW_runtime_v2.0.0.zip",
                "sha256": hashlib.sha256(b"runtime").hexdigest(),
                "size_bytes": 7,
            },
            "setup": {
                "name": "Insta360_HW_Setup.exe",
                "url": "https://example.invalid/releases/download/v2.0.0/Insta360_HW_Setup.exe",
                "sha256": hashlib.sha256(b"setup").hexdigest(),
                "size_bytes": 5,
            },
        },
        "notice": {
            "title": "Lifecycle V2",
            "summary": "Complete immutable runtime.",
            "highlights": ["One runtime ZIP"],
        },
    }


class ReleaseManifestContractTests(unittest.TestCase):
    def test_schema_two_manifest_rejects_coercion_and_unknown_fields(self) -> None:
        coerced = _manifest()
        coerced["schema"] = "2"
        with self.assertRaisesRegex(ValueError, "schema"):
            ReleaseManifest.parse(coerced)

        unexpected = _manifest()
        unexpected["source_zip_fallback"] = "https://example.invalid/source.zip"
        with self.assertRaisesRegex(ValueError, "unexpected"):
            ReleaseManifest.parse(unexpected)

    def test_manifest_rejects_source_archives_and_invalid_timestamps(self) -> None:
        source_archive = _manifest()
        asset = dict(source_archive["assets"]["runtime"])  # type: ignore[index]
        asset["url"] = "https://codeload.github.com/DECADE0502/Intsa360_HW/zip/refs/heads/main"
        source_archive["assets"] = {**source_archive["assets"], "runtime": asset}  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "source archive"):
            ReleaseManifest.parse(source_archive)

        invalid_timestamp = _manifest()
        invalid_timestamp["published_at"] = "yesterday"
        with self.assertRaisesRegex(ValueError, "published_at"):
            ReleaseManifest.parse(invalid_timestamp)

    def test_manifest_requires_both_runtime_and_setup_assets(self) -> None:
        missing_setup = _manifest()
        missing_setup["assets"] = {"runtime": missing_setup["assets"]["runtime"]}  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "setup"):
            ReleaseManifest.parse(missing_setup)

        parsed = ReleaseManifest.parse(_manifest())
        self.assertEqual(parsed.setup.name, "Insta360_HW_Setup.exe")


class PathAndWorkerContractTests(unittest.TestCase):
    def test_global_lifecycle_mutex_rejects_a_second_owner(self) -> None:
        holder_command = (
            f". '{CONTRACT}'; "
            "$m=Enter-HwLifecycleMutex -TimeoutMilliseconds 0; "
            "try { [Console]::Out.WriteLine('READY'); [Console]::Out.Flush(); Start-Sleep -Seconds 20 } "
            "finally { Exit-HwLifecycleMutex -Mutex $m }"
        )
        holder = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", holder_command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "READY")
            contender_command = (
                f". '{CONTRACT}'; "
                "try { $m=Enter-HwLifecycleMutex -TimeoutMilliseconds 0; "
                "Exit-HwLifecycleMutex -Mutex $m; exit 4 } catch { exit 0 }"
            )
            contender = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", contender_command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            self.assertEqual(contender.returncode, 0, contender.stdout + contender.stderr)
        finally:
            holder.terminate()
            holder.wait(timeout=10)

    def test_malformed_install_manifest_is_not_treated_as_a_runtime_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "install_manifest.json").write_text(json.dumps({"product": "other"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "install manifest"):
                _ = AppPaths(root).state_root

    def test_powershell_contract_rejects_unknown_job_phases_and_malformed_worker_handoffs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            command = (
                f". '{CONTRACT}'; "
                "try { Set-HwLifecycleJobPhase -StateRoot '"
                + str(state)
                + "' -JobId '../escape' -Phase 'not_a_phase' -Progress 1 -Message 'bad' | Out-Null; exit 4 } "
                "catch {}; "
                "if (Test-HwLifecycleWorkerHandoff -InstallRoot 'C:\\runtime' -StateRoot 'C:\\state' -StageRoot 'C:\\stage' -JobId '../escape' -ExpectedVersion '2.0.0') { exit 5 }; "
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

    def test_powershell_contract_keeps_state_external_and_staging_under_state(self) -> None:
        command = (
            f". '{CONTRACT}'; "
            "if (Test-HwLifecycleWorkerHandoff -InstallRoot 'C:\\runtime' -StateRoot 'C:\\runtime\\data' -StageRoot 'C:\\runtime\\data\\lifecycle\\transactions\\job\\payload' -JobId 'job' -ExpectedVersion '2.0.0') { exit 4 }; "
            "if (Test-HwLifecycleWorkerHandoff -InstallRoot 'C:\\runtime' -StateRoot 'C:\\state' -StageRoot 'C:\\stage' -JobId 'job' -ExpectedVersion '2.0.0') { exit 5 }; "
            "if (-not (Test-HwLifecycleWorkerHandoff -InstallRoot 'C:\\runtime' -StateRoot 'C:\\state' -StageRoot 'C:\\state\\lifecycle\\transactions\\job\\payload' -JobId 'job' -ExpectedVersion '2.0.0')) { exit 6 }; "
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

    def test_destructive_lifecycle_operations_reject_active_or_recoverable_updates(self) -> None:
        self.assertIn("function Assert-HwLifecycleQuiescent", CONTRACT.read_text(encoding="utf-8-sig"))
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            jobs = state / "lifecycle" / "jobs"
            jobs.mkdir(parents=True)
            job_id = "a" * 32
            (jobs / "latest.json").write_text(json.dumps({"job_id": job_id}), encoding="utf-8")
            (jobs / f"{job_id}.json").write_text(
                json.dumps({"job_id": job_id, "phase": "downloading", "running": True}),
                encoding="utf-8",
            )
            command = (
                f". '{CONTRACT}'; "
                "try { Assert-HwLifecycleQuiescent -StateRoot '"
                + str(state)
                + "'; exit 4 } catch {}; exit 0"
            )
            active = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            self.assertEqual(active.returncode, 0, active.stdout + active.stderr)

            (jobs / f"{job_id}.json").write_text(
                json.dumps({"job_id": job_id, "phase": "failed", "running": False}),
                encoding="utf-8",
            )
            transaction = state / "lifecycle" / "transactions" / job_id
            transaction.mkdir(parents=True)
            (transaction / "journal.json").write_text(
                json.dumps({"job_id": job_id, "phase": "new_runtime_activated"}),
                encoding="utf-8",
            )
            recoverable = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            self.assertEqual(recoverable.returncode, 0, recoverable.stdout + recoverable.stderr)

            (transaction / "journal.json").write_text(
                json.dumps({"job_id": job_id, "phase": "rolled_back"}),
                encoding="utf-8",
            )
            settled_command = (
                f". '{CONTRACT}'; Assert-HwLifecycleQuiescent -StateRoot '{state}'; Write-Output 'QUIET'"
            )
            settled = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", settled_command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            self.assertEqual(settled.returncode, 0, settled.stdout + settled.stderr)
            self.assertEqual(settled.stdout.strip(), "QUIET")

    def test_terminal_runtime_cleanup_removes_only_journal_owned_trees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install = base / "HWAgent"
            state = base / "state"
            install.mkdir()
            job_id = "cleanup-job"
            transaction = state / "lifecycle" / "transactions" / job_id
            transaction.mkdir(parents=True)
            backup = base / f".{install.name}.{job_id}.backup"
            backup.mkdir()
            (backup / "install_manifest.json").write_text(
                json.dumps({"schema": 2, "product": "Insta360_HW", "layout": "runtime-v2"}),
                encoding="utf-8",
            )
            unrelated = base / f".{install.name}.{job_id}.backup-unrelated"
            unrelated.mkdir()
            (transaction / "journal.json").write_text(
                json.dumps(
                    {
                        "schema": 2,
                        "product": "Insta360_HW",
                        "job_id": job_id,
                        "phase": "completed",
                        "install_root": str(install),
                        "backup_root": str(backup),
                    }
                ),
                encoding="utf-8",
            )
            command = (
                f". '{CONTRACT}'; "
                f"Remove-HwLifecycleTerminalRuntimeTrees -RuntimeRoot '{install}' -StateRoot '{state}'"
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
            self.assertFalse(backup.exists())
            self.assertFalse(transaction.exists())
            self.assertTrue(unrelated.exists())

    def test_exact_service_identity_requires_executable_root_token_version_and_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            state = Path(tmp) / "state"
            executable = root / "runtime" / "python" / "python.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"python")
            (root / "VERSION").write_text("2.0.0\n", encoding="utf-8")
            command = (
                f". '{CONTRACT}'; . '{RUNTIME}'; "
                "$missing = [pscustomobject]@{ schema = 2; product = 'Insta360_HW'; pid = 41; port = 8765; root = '"
                + str(root)
                + "'; state_root = '"
                + str(state)
                + "'; instance_token = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' }; "
                "if (Test-HwLifecycleServiceIdentity -Identity $missing -RuntimeRoot '"
                + str(root)
                + "' -StateRoot '"
                + str(state)
                + "') { exit 4 }; "
                "$complete = [pscustomobject]@{ schema = 2; product = 'Insta360_HW'; pid = 41; port = 8765; executable = '"
                + str(executable)
                + "'; root = '"
                + str(root)
                + "'; state_root = '"
                + str(state)
                + "'; version = '2.0.0'; instance_token = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' }; "
                "if (-not (Test-HwLifecycleServiceIdentity -Identity $complete -RuntimeRoot '"
                + str(root)
                + "' -StateRoot '"
                + str(state)
                + "')) { exit 5 }; exit 0"
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

    def test_legacy_service_stop_requires_exact_backend_process_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "runtime"
            state = base / "state"
            backend = root / "app" / "backend" / "suite_app.py"
            backend.parent.mkdir(parents=True)
            backend.write_text("# legacy service\n", encoding="utf-8")
            (root / "VERSION").write_text("0.2.27\n", encoding="utf-8")
            powershell = Path(shutil.which("powershell.exe") or "powershell.exe")
            sleeper = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f"$backend='{backend}'; Start-Sleep -Seconds 20",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                service_path = state / "runtime" / "service.json"
                service_path.parent.mkdir(parents=True)
                service_path.write_text(
                    json.dumps(
                        {
                            "pid": sleeper.pid,
                            "port": 8765,
                            "executable": str(powershell),
                            "root": str(root),
                        }
                    ),
                    encoding="utf-8",
                )
                command = (
                    f". '{CONTRACT}'; . '{RUNTIME}'; "
                    "Stop-HwLifecycleService -RuntimeRoot '"
                    + str(root)
                    + "' -StateRoot '"
                    + str(state)
                    + "' -AllowLegacyIdentity"
                )
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                )
                sleeper.wait(timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(service_path.exists())
            finally:
                if sleeper.poll() is None:
                    sleeper.terminate()
                    sleeper.wait(timeout=10)


class CadenceOwnershipContractTests(unittest.TestCase):
    def test_cadence_path_discovery_prefers_an_existing_spb_data_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home = base / "generic-home"
            spb = base / "SPB_Data"
            home.mkdir()
            expected = spb / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            expected.mkdir(parents=True)
            env = {**os.environ, "HOME": str(home), "SPB_DATA": str(spb), "CDS_DATA": ""}
            command = f". '{PATHS}'; @(Find-CadenceAutoLoadDirs)[0]"
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
        self.assertEqual(Path(result.stdout.strip()), expected)

    def test_cadence_state_round_trips_managed_autoload_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "local"
            first = Path(tmp) / "one" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            second = Path(tmp) / "two" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            env = {**os.environ, "LOCALAPPDATA": str(local)}
            command = (
                f". '{TCL_SCRIPTS}'; "
                "Set-HwAgentCadenceIntegrationState -Enabled:$true -LoaderPaths @('"
                + str(first)
                + "','"
                + str(second)
                + "') | Out-Null; "
                "$paths=@(Get-HwAgentRecordedCadenceAutoLoadDirs); "
                "if ($paths.Count -ne 2 -or $paths[0] -notlike '*one*' -or $paths[1] -notlike '*two*') { exit 4 }; exit 0"
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

    def test_cadence_state_uses_the_lifecycle_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "local"
            state_root = Path(tmp) / "explicit-state"
            env = {
                **os.environ,
                "LOCALAPPDATA": str(local),
                "INSTA360_HW_STATE_ROOT": str(state_root),
            }
            command = (
                f". '{TCL_SCRIPTS}'; "
                "Set-HwAgentCadenceIntegrationState -Enabled:$true -LoaderPaths @() | Out-Null; "
                "(Get-HwAgentCadenceStatePath)"
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
        self.assertEqual(Path(result.stdout.strip()), state_root / "cadence_integration.json")

    def test_cadence_deployment_transaction_restores_integration_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "local"
            old_dir = Path(tmp) / "old" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            new_dir = Path(tmp) / "new" / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
            env = {**os.environ, "LOCALAPPDATA": str(local)}
            command = (
                f". '{TCL_SCRIPTS}'; "
                "Set-HwAgentCadenceIntegrationState -Enabled:$true -LoaderPaths @('"
                + str(old_dir)
                + "') | Out-Null; "
                "$snapshot=Start-HwAgentCadenceDeploymentTransaction -AutoLoadDirs @(); "
                "Set-HwAgentCadenceIntegrationState -Enabled:$false -LoaderPaths @('"
                + str(new_dir)
                + "') | Out-Null; "
                "Restore-HwAgentCadenceDeploymentTransaction -SnapshotRoot $snapshot; "
                "$state=Get-HwAgentCadenceIntegrationState; "
                "if (-not $state.enabled -or @($state.loader_paths).Count -ne 1 -or $state.loader_paths[0] -notlike '*old*') { exit 4 }; exit 0"
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

    def test_cadence_cleanup_only_removes_marked_product_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto_load = Path(tmp) / "capAutoLoad"
            auto_load.mkdir()
            loader = auto_load / "iac_bom_tool.tcl"
            loader.write_text("# third-party loader\n", encoding="utf-8")
            command = (
                f". '{TCL_SCRIPTS}'; "
                "Remove-HwAgentCadenceArtifacts -AutoLoadDir '"
                + str(auto_load)
                + "'; "
                "if (-not (Test-Path -LiteralPath '"
                + str(loader)
                + "')) { exit 4 }; "
                "Set-Content -LiteralPath '"
                + str(loader)
                + "' -Value '# Insta360_HW Cadence Loader | schema=2 | managed=true'; "
                "Remove-HwAgentCadenceArtifacts -AutoLoadDir '"
                + str(auto_load)
                + "'; "
                "if (Test-Path -LiteralPath '"
                + str(loader)
                + "') { exit 5 }; exit 0"
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


if __name__ == "__main__":
    unittest.main()
