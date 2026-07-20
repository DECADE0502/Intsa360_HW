from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _remove_tree_with_retry(path: Path) -> None:
    for attempt in range(8):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 7:
                raise
            time.sleep(0.05 * (attempt + 1))


def _write_payload(root: Path, version: str, revision: str, launcher: bytes) -> None:
    required_files = (
        "launch_tool_suite.ps1",
        "app/backend/suite_app.py",
        "runtime/python/python.exe",
        "scripts/lifecycle_v3/Worker.ps1",
        "scripts/lifecycle_v3/Recover.ps1",
        "scripts/lifecycle_v3/Resume.ps1",
        "scripts/lifecycle_v3/Contract.ps1",
        "scripts/lifecycle_v3/Runtime.ps1",
        "scripts/lifecycle_v3/Install.ps1",
        "scripts/lifecycle_v3/Uninstall.ps1",
        "scripts/lifecycle_v3/SetupRunner.ps1",
        "scripts/lifecycle_v3/SetupRecover.ps1",
        "scripts/lifecycle/Contract.ps1",
        "scripts/lifecycle/Runtime.ps1",
        "scripts/lifecycle/Recover.ps1",
        "scripts/lifecycle/Worker.ps1",
        "scripts/remove_cadence_loader.ps1",
        "scripts/lib/Paths.ps1",
        "cadence/iac_bom_tool.tcl",
        "config/capabilities.json",
        "config/update_public_key.pem",
    )
    root.mkdir(parents=True)
    for relative in required_files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")
    for relative in (
        "scripts/lifecycle/Contract.ps1",
        "scripts/lifecycle/Runtime.ps1",
        "scripts/lifecycle/Recover.ps1",
        "scripts/lifecycle/Worker.ps1",
    ):
        shutil.copyfile(ROOT / relative, root / relative)
    (root / "Insta360_HW.exe").write_bytes(launcher)
    (root / "VERSION").write_text(version, encoding="utf-8")
    (root / "REVISION").write_text(revision, encoding="utf-8")
    (root / "install_manifest.json").write_text(
        json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "layout": "runtime-v3",
                "version": version,
                "revision": revision,
            }
        ),
        encoding="utf-8",
    )


def _write_v2_runtime(root: Path, version: str, marker: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "app" / "backend").mkdir(parents=True, exist_ok=True)
    (root / "app" / "backend" / "suite_app.py").write_text("# legacy fixture\n", encoding="utf-8")
    (root / "Insta360_HW.exe").write_bytes(("launcher-" + marker).encode("ascii"))
    (root / "VERSION").write_text(version, encoding="utf-8")
    (root / "install_manifest.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "product": "Insta360_HW",
                "layout": "runtime-v2",
                "version": version,
            }
        ),
        encoding="utf-8",
    )


def _run_install(
    install_root: Path,
    state_root: Path,
    payload_root: Path,
    action: str,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "lifecycle_v3" / "Install.ps1"),
            "-InstallRoot",
            str(install_root),
            "-StateRoot",
            str(state_root),
            "-PayloadRoot",
            str(payload_root),
            "-Action",
            action,
            "-NoStart",
            "-SkipCadence",
            "-SkipRecoveryRegistration",
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )


def _run_uninstall(
    install_root: Path,
    state_root: Path,
    mode: str,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "lifecycle_v3" / "Uninstall.ps1"),
            "-InstallRoot",
            str(install_root),
            "-StateRoot",
            str(state_root),
            "-Mode",
            mode,
            "-NoStop",
            "-SkipCadence",
            "-SkipRecoveryRegistration",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
    )


def _run_setup_recover(install_root: Path, state_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "lifecycle_v3" / "SetupRecover.ps1"),
            "-InstallRoot",
            str(install_root),
            "-StateRoot",
            str(state_root),
            "-NoRestart",
            "-SkipCadence",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


@unittest.skipUnless(os.name == "nt", "Windows lifecycle scripts")
class SetupLifecycleV3Tests(unittest.TestCase):
    def test_fresh_install_creates_one_versioned_runtime_and_stable_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root, payload = base / "install", base / "state", base / "payload"
            revision = "1" * 40
            _write_payload(payload, "1.2.3", revision, b"launcher-v1")

            result = _run_install(install_root, state_root, payload, "Install")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            metadata = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(metadata["schema_version"], 3)
            self.assertEqual(metadata["layout"], "versioned-runtime-v3")
            self.assertEqual(metadata["active_runtime"], f"runtime/1.2.3+{revision}")
            self.assertEqual(metadata["active_version"], "1.2.3")
            self.assertEqual(metadata["generation"], 1)
            self.assertEqual((install_root / "Insta360_HW.exe").read_bytes(), b"launcher-v1")
            self.assertTrue((install_root / metadata["active_runtime"] / "app/backend/suite_app.py").is_file())

    def test_repair_rebuilds_when_active_runtime_directory_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root, payload = base / "install", base / "state", base / "payload"
            revision = "b" * 40
            _write_payload(payload, "1.2.3", revision, b"launcher-v1")
            installed = _run_install(install_root, state_root, payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            metadata = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            shutil.rmtree(install_root / metadata["active_runtime"])

            repaired = _run_install(install_root, state_root, payload, "Repair")

            self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
            rebuilt = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(rebuilt["active_runtime"], f"runtime/1.2.3+{revision}")
            self.assertTrue((install_root / rebuilt["active_runtime"] / "app/backend/suite_app.py").is_file())

    def test_repair_rebuilds_when_active_manifest_is_corrupt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root, payload = base / "install", base / "state", base / "payload"
            revision = "c" * 40
            _write_payload(payload, "1.2.3", revision, b"launcher-v1")
            installed = _run_install(install_root, state_root, payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            metadata = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            active_runtime = install_root / metadata["active_runtime"]
            (active_runtime / "install_manifest.json").write_bytes(b"not-json")

            repaired = _run_install(install_root, state_root, payload, "Repair")

            self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
            rebuilt = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(rebuilt["active_runtime"], f"runtime/1.2.3+{revision}")
            manifest = json.loads(
                (install_root / rebuilt["active_runtime"] / "install_manifest.json").read_text(encoding="utf-8-sig")
            )
            self.assertEqual(manifest["version"], "1.2.3")

    def test_install_action_still_refuses_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root, payload = base / "install", base / "state", base / "payload"
            _write_payload(payload, "1.2.3", "d" * 40, b"launcher-v1")
            installed = _run_install(install_root, state_root, payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            metadata = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            shutil.rmtree(install_root / metadata["active_runtime"])

            duplicate = _run_install(install_root, state_root, payload, "Install")

            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("cannot replace an existing installation", duplicate.stdout + duplicate.stderr)

    def test_upgrade_still_refuses_downgrade_when_active_runtime_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root = base / "install", base / "state"
            current, older = base / "current", base / "older"
            _write_payload(current, "2.0.0", "e" * 40, b"launcher-current")
            _write_payload(older, "1.9.9", "f" * 40, b"launcher-older")
            installed = _run_install(install_root, state_root, current, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            metadata = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            shutil.rmtree(install_root / metadata["active_runtime"])

            downgrade = _run_install(install_root, state_root, older, "Upgrade")

            self.assertNotEqual(downgrade.returncode, 0)
            self.assertIn("downgrade", (downgrade.stdout + downgrade.stderr).lower())
            preserved = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(preserved["active_version"], "2.0.0")
            self.assertEqual((install_root / "Insta360_HW.exe").read_bytes(), b"launcher-current")

    def test_install_rejects_unsupported_destination_length_before_copy(self) -> None:
        base = Path(tempfile.mkdtemp())
        try:
            install_root = base / ("long-install-root-" + "x" * 120)
            state_root, payload = base / "state", base / "payload"
            _write_payload(payload, "1.2.3", "9" * 40, b"launcher-v1")

            result = _run_install(install_root, state_root, payload, "Install")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Selected installation directory is too long", result.stdout + result.stderr)
            self.assertFalse(install_root.exists())
        finally:
            _remove_tree_with_retry(base)

    def test_failed_upgrade_restores_pointer_launcher_and_old_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root = base / "install", base / "state"
            old_payload, new_payload = base / "old", base / "new"
            old_revision, new_revision = "2" * 40, "3" * 40
            _write_payload(old_payload, "1.0.0", old_revision, b"launcher-old")
            _write_payload(new_payload, "1.1.0", new_revision, b"launcher-new")
            first = _run_install(install_root, state_root, old_payload, "Install")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            failed = _run_install(
                install_root,
                state_root,
                new_payload,
                "Upgrade",
                "-FaultAt",
                "pointer_committed",
            )

            self.assertNotEqual(failed.returncode, 0)
            metadata = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(metadata["active_runtime"], f"runtime/1.0.0+{old_revision}")
            self.assertEqual((install_root / "Insta360_HW.exe").read_bytes(), b"launcher-old")
            self.assertTrue((install_root / metadata["active_runtime"]).is_dir())
            self.assertFalse((install_root / f"runtime/1.1.0+{new_revision}").exists())

    def test_upgrade_refuses_implicit_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root = base / "install", base / "state"
            current, older = base / "current", base / "older"
            current_revision, older_revision = "4" * 40, "5" * 40
            _write_payload(current, "2.0.0", current_revision, b"launcher-current")
            _write_payload(older, "1.9.9", older_revision, b"launcher-older")
            first = _run_install(install_root, state_root, current, "Install")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            result = _run_install(install_root, state_root, older, "Upgrade")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("downgrade", (result.stdout + result.stderr).lower())
            metadata = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(metadata["active_runtime"], f"runtime/2.0.0+{current_revision}")
            self.assertEqual((install_root / "Insta360_HW.exe").read_bytes(), b"launcher-current")

    def test_reinstall_keeps_the_previous_runtime_rollback_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root = base / "install", base / "state"
            old_payload, current_payload = base / "old", base / "current"
            old_revision, current_revision = "9" * 40, "a" * 40
            _write_payload(old_payload, "1.0.0", old_revision, b"launcher-old")
            _write_payload(current_payload, "1.1.0", current_revision, b"launcher-current")
            first = _run_install(install_root, state_root, old_payload, "Install")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            upgraded = _run_install(install_root, state_root, current_payload, "Upgrade")
            self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)

            reinstalled = _run_install(install_root, state_root, current_payload, "Reinstall")

            self.assertEqual(reinstalled.returncode, 0, reinstalled.stdout + reinstalled.stderr)
            metadata = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(metadata["active_runtime"], f"runtime/1.1.0+{current_revision}")
            self.assertEqual(metadata["previous_runtime"], f"runtime/1.0.0+{old_revision}")

    def test_install_recovers_interrupted_v2_setup_before_migrating_user_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root, payload = base / "install", base / "state", base / "payload"
            transaction = state_root / "lifecycle" / "setup" / "active"
            backup = transaction / "backup"
            legacy_history = backup / "data" / "history" / "legacy.json"
            legacy_history.parent.mkdir(parents=True)
            legacy_history.write_text('{"kept": true}', encoding="utf-8")
            (backup / "install_manifest.json").write_text(
                json.dumps(
                    {
                        "schema": 2,
                        "product": "Insta360_HW",
                        "layout": "runtime-v2",
                        "version": "0.3.3",
                        "revision": "b" * 40,
                    }
                ),
                encoding="utf-8",
            )
            transaction.mkdir(parents=True, exist_ok=True)
            (transaction / "journal.json").write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "product": "Insta360_HW",
                        "phase": "replacing",
                        "install_root": str(install_root),
                        "state_root": str(state_root),
                        "backup_root": str(backup),
                        "had_existing_runtime": True,
                    }
                ),
                encoding="utf-8",
            )
            install_root.mkdir(parents=True)
            (install_root / "partial-new-file.txt").write_text("partial", encoding="utf-8")
            _write_payload(payload, "0.4.0", "c" * 40, b"launcher-v3")

            result = _run_install(install_root, state_root, payload, "Upgrade")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            migrated = state_root / "data" / "history" / "legacy.json"
            self.assertEqual(migrated.read_text(encoding="utf-8"), '{"kept": true}')
            self.assertFalse(transaction.exists())
            self.assertFalse((install_root / "partial-new-file.txt").exists())

    def test_install_recovers_interrupted_v2_update_before_v3_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root, payload = base / "legacy install", base / "state", base / "payload"
            job_id = "1" * 32
            backup = install_root.parent / f".{install_root.name}.{job_id}.backup"
            candidate = install_root.parent / f".{install_root.name}.{job_id}.candidate"
            failed = install_root.parent / f".{install_root.name}.{job_id}.failed"
            _write_v2_runtime(install_root, "0.3.3", "interrupted-new")
            _write_v2_runtime(backup, "0.3.2", "restored-old")
            legacy_history = backup / "data" / "history" / "from-backup.json"
            legacy_history.parent.mkdir(parents=True)
            legacy_history.write_text('{"source": "backup"}', encoding="utf-8")
            transaction = state_root / "lifecycle" / "transactions" / job_id
            transaction.mkdir(parents=True)
            (transaction / "journal.json").write_text(
                json.dumps(
                    {
                        "schema": 2,
                        "product": "Insta360_HW",
                        "job_id": job_id,
                        "phase": "new_runtime_activated",
                        "install_root": str(install_root),
                        "state_root": str(state_root),
                        "stage_root": "",
                        "candidate_root": str(candidate),
                        "backup_root": str(backup),
                        "failed_root": str(failed),
                        "expected_version": "0.3.3",
                        "expected_tree_sha256": "",
                        "cadence_snapshot": "",
                        "worker_path": "",
                        "run_once_name": f"Insta360_HW_Recovery_{job_id}",
                        "updated_at": "2026-07-14T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            _write_payload(payload, "0.4.0", "2" * 40, b"launcher-v3")

            result = _run_install(install_root, state_root, payload, "Upgrade")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            migrated = state_root / "data" / "history" / "from-backup.json"
            self.assertEqual(migrated.read_text(encoding="utf-8"), '{"source": "backup"}')
            self.assertFalse(transaction.exists())
            self.assertFalse(failed.exists())

    def test_interrupted_upgrade_is_rolled_back_by_setup_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root = base / "install", base / "state"
            old_payload, new_payload = base / "old", base / "new"
            old_revision, new_revision = "d" * 40, "e" * 40
            _write_payload(old_payload, "1.0.0", old_revision, b"launcher-old")
            _write_payload(new_payload, "1.1.0", new_revision, b"launcher-new")
            installed = _run_install(install_root, state_root, old_payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)

            interrupted = _run_install(
                install_root,
                state_root,
                new_payload,
                "Upgrade",
                "-CrashAt",
                "pointer_committed",
            )

            self.assertNotEqual(interrupted.returncode, 0)
            current = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(current["active_runtime"], f"runtime/1.1.0+{new_revision}")
            recovered = _run_setup_recover(install_root, state_root)
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            restored = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(restored["active_runtime"], f"runtime/1.0.0+{old_revision}")
            self.assertEqual((install_root / "Insta360_HW.exe").read_bytes(), b"launcher-old")
            self.assertFalse((install_root / f"runtime/1.1.0+{new_revision}").exists())
            setup_root = state_root / "lifecycle" / "v3" / "setup"
            self.assertFalse(setup_root.exists() and any(setup_root.iterdir()))

    def test_recovery_handles_pointer_write_before_commit_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root = base / "install", base / "state"
            old_payload, new_payload = base / "old", base / "new"
            old_revision, new_revision = "5" * 40, "6" * 40
            _write_payload(old_payload, "1.0.0", old_revision, b"launcher-old")
            _write_payload(new_payload, "1.1.0", new_revision, b"launcher-new")
            installed = _run_install(install_root, state_root, old_payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)

            interrupted = _run_install(
                install_root,
                state_root,
                new_payload,
                "Upgrade",
                "-CrashAt",
                "pointer_written_unjournaled",
            )

            self.assertNotEqual(interrupted.returncode, 0)
            current = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(current["active_runtime"], f"runtime/1.1.0+{new_revision}")
            recovered = _run_setup_recover(install_root, state_root)
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            restored = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(restored["active_runtime"], f"runtime/1.0.0+{old_revision}")
            self.assertTrue((install_root / f"runtime/1.0.0+{old_revision}").is_dir())
            self.assertFalse((install_root / f"runtime/1.1.0+{new_revision}").exists())

    def test_setup_rerun_recovers_interrupted_upgrade_and_finishes_in_one_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root = base / "install", base / "state"
            old_payload, new_payload = base / "old", base / "new"
            old_revision, new_revision = "3" * 40, "4" * 40
            _write_payload(old_payload, "1.0.0", old_revision, b"launcher-old")
            _write_payload(new_payload, "1.1.0", new_revision, b"launcher-new")
            installed = _run_install(install_root, state_root, old_payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            interrupted = _run_install(
                install_root,
                state_root,
                new_payload,
                "Upgrade",
                "-CrashAt",
                "pointer_committed",
            )
            self.assertNotEqual(interrupted.returncode, 0)

            rerun = _run_install(install_root, state_root, new_payload, "Repair")

            self.assertEqual(rerun.returncode, 0, rerun.stdout + rerun.stderr)
            metadata = json.loads((install_root / "installation.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(metadata["active_runtime"], f"runtime/1.1.0+{new_revision}")
            self.assertEqual(metadata["previous_runtime"], f"runtime/1.0.0+{old_revision}")

    def test_interrupted_same_runtime_reinstall_restores_moved_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root, payload = base / "install", base / "state", base / "payload"
            revision = "f" * 40
            _write_payload(payload, "1.0.0", revision, b"launcher")
            installed = _run_install(install_root, state_root, payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            runtime = install_root / f"runtime/1.0.0+{revision}"
            (runtime / "preserved.txt").write_text("old runtime", encoding="utf-8")

            interrupted = _run_install(
                install_root,
                state_root,
                payload,
                "Reinstall",
                "-CrashAt",
                "same_runtime_moved",
            )

            self.assertNotEqual(interrupted.returncode, 0)
            self.assertFalse(runtime.exists())
            recovered = _run_setup_recover(install_root, state_root)
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertEqual((runtime / "preserved.txt").read_text(encoding="utf-8"), "old runtime")

    def test_recovery_handles_same_runtime_move_before_moved_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root, payload = base / "install", base / "state", base / "payload"
            revision = "7" * 40
            _write_payload(payload, "1.0.0", revision, b"launcher")
            installed = _run_install(install_root, state_root, payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            runtime = install_root / f"runtime/1.0.0+{revision}"
            (runtime / "preserved.txt").write_text("old runtime", encoding="utf-8")

            interrupted = _run_install(
                install_root,
                state_root,
                payload,
                "Reinstall",
                "-CrashAt",
                "same_runtime_moved_unjournaled",
            )

            self.assertNotEqual(interrupted.returncode, 0)
            self.assertFalse(runtime.exists())
            recovered = _run_setup_recover(install_root, state_root)
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertEqual((runtime / "preserved.txt").read_text(encoding="utf-8"), "old runtime")

    def test_setup_uses_v3_staging_and_exposes_all_maintenance_actions(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        self.assertIn(r"{tmp}\Insta360_HW_payload", setup)
        self.assertIn(r"scripts\lifecycle_v3\Install.ps1", setup)
        self.assertIn(r"scripts\lifecycle_v3\Uninstall.ps1", setup)
        self.assertIn(r"scripts\lifecycle_v3\SetupRecover.ps1", setup)
        self.assertIn("升级到", setup)
        self.assertIn("修复当前安装", setup)
        self.assertIn("重新安装", setup)
        self.assertIn("卸载 Insta360硬件提效平台", setup)
        self.assertIn("installation.json", setup)
        self.assertIn("CompareSemanticVersion", setup)
        self.assertNotIn("SetupTransaction.ps1", setup)
        self.assertNotIn(r"scripts\lifecycle\Install.ps1", setup)
        launcher = (ROOT / "launcher" / "Insta360_HW.cs").read_text(encoding="utf-8")
        self.assertIn("SetupRecover.ps1", launcher)

    def test_setup_silent_action_resolution_exists(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")

        self.assertIn("ResolveSilentInstallAction", setup)
        self.assertIn("{param:ACTION|}", setup)
        self.assertIn("WizardSilent", setup)
        self.assertIn("SilentActionResolutionFailed", setup)
        self.assertIn("SilentUninstallRequested", setup)
        self.assertIn("SILENT_DOWNGRADE_REJECTED", setup)
        self.assertIn("RaiseException(SilentActionError)", setup)

    def test_uninstall_defaults_to_purge_and_preserve_is_explicit(self) -> None:
        setup = (ROOT / "HWAgent_Setup.iss").read_text(encoding="utf-8-sig")
        uninstaller = (ROOT / "scripts" / "lifecycle_v3" / "Uninstall.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("PreserveRequested", setup)
        self.assertIn("PreserveUserData := False", setup)
        self.assertNotIn("PreserveRequested or UninstallSilent", setup)
        self.assertIn('[string]$Mode = "PurgeData"', uninstaller)
        self.assertIn("Insta360_HW_Recovery_", uninstaller)
        self.assertIn("scripts\\remove_cadence_loader.ps1", uninstaller)
        self.assertIn("Restore-HwV2InterruptedSetup", uninstaller)

    def test_v3_restart_reclaims_only_the_exact_owned_backend(self) -> None:
        runtime = (ROOT / "scripts" / "lifecycle_v3" / "Runtime.ps1").read_text(encoding="utf-8-sig")

        self.assertIn("Get-HwV3RuntimeBackendProcesses", runtime)
        self.assertIn(r"runtime\python\python.exe", runtime)
        self.assertIn(r"app\backend\suite_app.py", runtime)
        self.assertIn("remaining owned backend process", runtime)

    def test_preserve_uninstall_keeps_user_files_but_removes_lifecycle_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install_root, state_root, payload = base / "install", base / "state", base / "payload"
            _write_payload(payload, "1.0.0", "6" * 40, b"launcher")
            installed = _run_install(install_root, state_root, payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            user_file = state_root / "data" / "history" / "kept.json"
            user_file.parent.mkdir(parents=True)
            user_file.write_text("{}", encoding="utf-8")
            lifecycle_file = state_root / "lifecycle" / "v3" / "jobs" / "old.json"
            lifecycle_file.parent.mkdir(parents=True)
            lifecycle_file.write_text("{}", encoding="utf-8")

            result = _run_uninstall(install_root, state_root, "PreserveData")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(user_file.is_file())
            self.assertFalse((state_root / "lifecycle" / "v3").exists())
            self.assertTrue(install_root.exists(), "Inno Setup owns final program-directory deletion")

    def test_purge_uninstall_removes_only_exact_local_appdata_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            local_app_data = base / "LocalAppData"
            install_root, state_root, payload = (
                base / "install",
                local_app_data / "Insta360_HW",
                base / "payload",
            )
            env = {**os.environ, "LOCALAPPDATA": str(local_app_data)}
            _write_payload(payload, "1.0.0", "7" * 40, b"launcher")
            installed = _run_install(install_root, state_root, payload, "Install")
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            (state_root / "data" / "private.txt").parent.mkdir(parents=True, exist_ok=True)
            (state_root / "data" / "private.txt").write_text("delete", encoding="utf-8")

            result = _run_uninstall(install_root, state_root, "PurgeData", env=env)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(state_root.exists())
            self.assertTrue(local_app_data.exists())

    def test_setup_runner_preserves_arguments_with_spaces_and_reports_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "directory with spaces"
            install_root, state_root, payload = base / "installed app", base / "user state", base / "payload files"
            result_path, progress_path = base / "result.txt", base / "progress.json"
            _write_payload(payload, "1.0.0", "8" * 40, b"launcher")
            command = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts" / "lifecycle_v3" / "SetupRunner.ps1"),
                "-Operation",
                "Install",
                "-EntryPath",
                str(ROOT / "scripts" / "lifecycle_v3" / "Install.ps1"),
                "-InstallRoot",
                str(install_root),
                "-StateRoot",
                str(state_root),
                "-PayloadRoot",
                str(payload),
                "-Action",
                "Install",
                "-ResultPath",
                str(result_path),
                "-ProgressPath",
                str(progress_path),
                "-NoStart",
                "-SkipCadence",
                "-SkipRecoveryRegistration",
            ]

            runner = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )

            self.assertEqual(runner.returncode, 0, runner.stdout + runner.stderr)
            self.assertTrue(result_path.is_file(), runner.stdout + runner.stderr)
            self.assertEqual(result_path.read_text(encoding="utf-8"), "0")
            self.assertTrue((install_root / "installation.json").is_file())

    def test_setup_runner_waits_only_for_the_lifecycle_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            entry = base / "spawn-service.ps1"
            child_pid_path = base / "service.pid"
            result_path, progress_path = base / "result.txt", base / "progress.json"
            entry.write_text(
                """
param(
  [string]$InstallRoot,
  [string]$StateRoot,
  [string]$ProgressPath,
  [string]$PayloadRoot,
  [string]$Action
)
$powershell = Join-Path $env:SystemRoot "System32\\WindowsPowerShell\\v1.0\\powershell.exe"
$service = Start-Process -FilePath $powershell `
  -ArgumentList @("-NoProfile", "-Command", "Start-Sleep -Seconds 60") `
  -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $env:HWAGENT_TEST_SERVICE_PID -Value $service.Id
exit 0
""".strip()
                + "\n",
                encoding="utf-8",
            )
            env = {**os.environ, "HWAGENT_TEST_SERVICE_PID": str(child_pid_path)}
            command = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts" / "lifecycle_v3" / "SetupRunner.ps1"),
                "-Operation",
                "Install",
                "-EntryPath",
                str(entry),
                "-InstallRoot",
                str(base / "install"),
                "-StateRoot",
                str(base / "state"),
                "-PayloadRoot",
                str(base / "payload"),
                "-Action",
                "Install",
                "-ResultPath",
                str(result_path),
                "-ProgressPath",
                str(progress_path),
            ]
            started = time.monotonic()
            runner = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            timed_out = False
            try:
                stdout, stderr = runner.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                timed_out = True
                runner.kill()
                stdout, stderr = runner.communicate(timeout=5)
            finally:
                if child_pid_path.is_file():
                    child_pid = child_pid_path.read_text(encoding="utf-8-sig").strip()
                    subprocess.run(
                        ["taskkill.exe", "/PID", child_pid, "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )

            self.assertFalse(timed_out, stdout + stderr)
            self.assertLess(time.monotonic() - started, 8)
            self.assertTrue(result_path.is_file(), stdout + stderr)
            self.assertEqual(result_path.read_text(encoding="utf-8"), "0")


if __name__ == "__main__":
    unittest.main()
