from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts" / "lifecycle" / "Worker.ps1"
RECOVER = ROOT / "scripts" / "lifecycle" / "Recover.ps1"
CONTRACT = ROOT / "scripts" / "lifecycle" / "Contract.ps1"


def _tree_sha256(root: Path) -> str:
    records: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(f"{relative}\t{path.stat().st_size}\t{digest}\n")
    return hashlib.sha256("".join(sorted(records)).encode("utf-8")).hexdigest()


def _runtime(path: Path, version: str, *, product: str = "Insta360_HW", layout: str = "runtime-v2") -> None:
    (path / "app" / "backend").mkdir(parents=True)
    (path / "app" / "backend" / "suite_app.py").write_text("# test runtime\n", encoding="utf-8")
    (path / "Insta360_HW.exe").write_bytes(b"test launcher")
    (path / "VERSION").write_text(version + "\n", encoding="utf-8")
    (path / "install_manifest.json").write_text(
        json.dumps({"schema": 2, "product": product, "version": version, "layout": layout}),
        encoding="utf-8",
    )


def _transaction_paths(install: Path, state: Path, job: str) -> tuple[Path, Path, Path, Path]:
    candidate = install.parent / f".{install.name}.{job}.candidate"
    backup = install.parent / f".{install.name}.{job}.backup"
    failed = install.parent / f".{install.name}.{job}.failed"
    transaction = state / "lifecycle" / "transactions" / job
    return candidate, backup, failed, transaction


def _journal(install: Path, state: Path, job: str, phase: str, *, version: str = "2.0.0") -> Path:
    candidate, backup, _failed, transaction = _transaction_paths(install, state, job)
    transaction.mkdir(parents=True, exist_ok=True)
    path = transaction / "journal.json"
    path.write_text(
        json.dumps(
            {
                "schema": 2,
                "product": "Insta360_HW",
                "job_id": job,
                "phase": phase,
                "install_root": str(install),
                "state_root": str(state),
                "stage_root": str(transaction / "stage"),
                "candidate_root": str(candidate),
                "backup_root": str(backup),
                "expected_version": version,
            }
        ),
        encoding="utf-8",
    )
    return path


class LifecycleV2WorkerTests(unittest.TestCase):
    def test_worker_releases_the_install_tree_as_its_current_directory(self) -> None:
        source = (ROOT / "scripts" / "lifecycle" / "Worker.ps1").read_text(encoding="utf-8")

        self.assertIn("[System.IO.Directory]::SetCurrentDirectory($StateRoot)", source)
        self.assertIn("Set-Location -LiteralPath $StateRoot", source)
        self.assertLess(
            source.index("[System.IO.Directory]::SetCurrentDirectory($StateRoot)"),
            source.index("Move-Item -LiteralPath $InstallRoot -Destination $backup"),
        )

    def _stage(self, state: Path, job: str, version: str = "2.0.0") -> Path:
        stage = state / "lifecycle" / "staging" / job
        _runtime(stage, version)
        return stage

    def _run_worker(
        self,
        install: Path,
        state: Path,
        stage: Path,
        job: str,
        *extra: str,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(WORKER),
                "-InstallRoot",
                str(install),
                "-StateRoot",
                str(state),
                "-StageRoot",
                str(stage),
                "-JobId",
                job,
                "-ExpectedVersion",
                "2.0.0",
                "-NoRestart",
                "-SkipCadence",
                "-SkipRecoveryRegistration",
            ]
        if "-ExpectedTreeSha256" not in extra:
            arguments.extend(["-ExpectedTreeSha256", _tree_sha256(stage)])
        arguments.extend(extra)
        return subprocess.run(
            arguments,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=40,
        )

    def _run_recovery(self, install: Path, state: Path, job: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(WORKER),
                "-Action",
                "Recover",
                "-InstallRoot",
                str(install),
                "-StateRoot",
                str(state),
                "-JobId",
                job,
                "-NoRestart",
                "-SkipCadence",
                "-SkipRecoveryRegistration",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=40,
        )

    def test_complete_candidate_is_switched_as_one_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install, state = base / "HWAgent", base / "state"
            stage = self._stage(state, "success")
            _runtime(install, "1.0.0")
            (install / "data" / "history").mkdir(parents=True)
            (install / "data" / "history" / "kept.json").write_text("{}", encoding="utf-8")
            (install / "unins000.exe").write_bytes(b"uninstaller")

            result = self._run_worker(install, state, stage, "success")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "2.0.0")
            self.assertTrue((install / "unins000.exe").exists())
            self.assertTrue((state / "data" / "history" / "kept.json").exists())
            job = json.loads((state / "lifecycle" / "jobs" / "success.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(job["phase"], "completed")

    def test_candidate_manifest_identity_is_validated_by_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install, state = base / "HWAgent", base / "state"
            stage = state / "lifecycle" / "staging" / "bad-layout"
            _runtime(install, "1.0.0")
            _runtime(stage, "2.0.0", layout="legacy")

            result = self._run_worker(install, state, stage, "bad-layout")

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "1.0.0")
            self.assertIn("layout", result.stdout + result.stderr)

    def test_candidate_tree_is_revalidated_after_elevation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install, state = base / "HWAgent", base / "state"
            stage = self._stage(state, "tampered-tree")
            _runtime(install, "1.0.0")
            expected_tree = _tree_sha256(stage)
            (stage / "app" / "backend" / "suite_app.py").write_text("# tampered\n", encoding="utf-8")

            result = self._run_worker(
                install,
                state,
                stage,
                "tampered-tree",
                "-ExpectedTreeSha256",
                expected_tree,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "1.0.0")
            self.assertIn("integrity", (result.stdout + result.stderr).lower())

    def test_recovery_never_executes_a_worker_from_mutable_state(self) -> None:
        source = RECOVER.read_text(encoding="utf-8-sig")

        self.assertIn('Join-Path $ScriptDir "Worker.ps1"', source)
        self.assertNotIn('Join-Path $item.directory.FullName "worker\\Worker.ps1"', source)
        self.assertIn('Verb = "runas"', source)

    def test_fault_after_backup_restores_previous_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install, state = base / "HWAgent", base / "state"
            stage = self._stage(state, "rollback")
            _runtime(install, "1.0.0")

            result = self._run_worker(install, state, stage, "rollback", "-FaultAt", "old_runtime_backed_up")

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "1.0.0")
            job = json.loads((state / "lifecycle" / "jobs" / "rollback.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(job["phase"], "failed")
            self.assertTrue(job["rolled_back"])

    def test_recovery_after_new_runtime_activation_restores_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install, state, job = base / "HWAgent", base / "state", "recover-active"
            _runtime(install, "2.0.0")
            _candidate, backup, failed, _transaction = _transaction_paths(install, state, job)
            _runtime(backup, "1.0.0")
            journal = _journal(install, state, job, "new_runtime_activated")
            jobs = state / "lifecycle" / "jobs"
            jobs.mkdir(parents=True)
            (jobs / f"{job}.json").write_text(
                json.dumps(
                    {
                        "schema": 2,
                        "job_id": job,
                        "phase": "failed",
                        "recovery_required": True,
                        "running": False,
                    }
                ),
                encoding="utf-8",
            )

            result = self._run_recovery(install, state, job)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "1.0.0")
            self.assertEqual((failed / "VERSION").read_text(encoding="utf-8").strip(), "2.0.0")
            self.assertEqual(json.loads(journal.read_text(encoding="utf-8-sig"))["phase"], "rolled_back")
            recovered_job = json.loads((jobs / f"{job}.json").read_text(encoding="utf-8-sig"))
            self.assertFalse(recovered_job["recovery_required"])

    def test_recovery_after_old_runtime_backup_restores_missing_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install, state, job = base / "HWAgent", base / "state", "recover-missing"
            candidate, backup, _failed, _transaction = _transaction_paths(install, state, job)
            _runtime(candidate, "2.0.0")
            _runtime(backup, "1.0.0")
            _journal(install, state, job, "old_runtime_backed_up")

            result = self._run_recovery(install, state, job)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "1.0.0")
            self.assertFalse(candidate.exists())

    def test_recovery_before_backup_keeps_existing_old_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install, state, job = base / "HWAgent", base / "state", "recover-precommit"
            candidate, _backup, _failed, _transaction = _transaction_paths(install, state, job)
            _runtime(install, "1.0.0")
            _runtime(candidate, "2.0.0")
            _journal(install, state, job, "state_externalized")

            result = self._run_recovery(install, state, job)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "1.0.0")
            self.assertFalse(candidate.exists())

    def test_cleanup_failure_does_not_rollback_verified_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install, state = base / "HWAgent", base / "state"
            stage = self._stage(state, "cleanup-warning")
            _runtime(install, "1.0.0")

            result = self._run_worker(
                install,
                state,
                stage,
                "cleanup-warning",
                "-FaultAt",
                "cleanup_backup",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "2.0.0")
            job = json.loads(
                (state / "lifecycle" / "jobs" / "cleanup-warning.json").read_text(encoding="utf-8-sig")
            )
            self.assertEqual(job["phase"], "completed")
            self.assertTrue(job["cleanup_pending"])

    def test_recover_entrypoint_refuses_to_race_a_live_update_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            install, state, job = base / "HWAgent", base / "state", "live-worker"
            _runtime(install, "1.0.0")
            journal = _journal(install, state, job, "state_externalized")
            sleeper = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f"$worker='Worker.ps1'; $job='{job}'; Start-Sleep -Seconds 20",
                ]
            )
            try:
                jobs = state / "lifecycle" / "jobs"
                jobs.mkdir(parents=True)
                (jobs / f"{job}.json").write_text(
                    json.dumps(
                        {
                            "schema": 2,
                            "job_id": job,
                            "phase": "committing",
                            "worker_pid": sleeper.pid,
                            "running": True,
                        }
                    ),
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(RECOVER),
                        "-InstallRoot",
                        str(install),
                        "-StateRoot",
                        str(state),
                        "-NoRestart",
                    ],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    timeout=20,
                )
            finally:
                sleeper.terminate()
                sleeper.wait(timeout=10)

            self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
            self.assertEqual(json.loads(journal.read_text(encoding="utf-8"))["phase"], "state_externalized")
            self.assertEqual((install / "VERSION").read_text(encoding="utf-8").strip(), "1.0.0")

    def test_runtime_root_guard_rejects_drive_root(self) -> None:
        command = (
            f". '{CONTRACT}'; "
            "try { Assert-HwLifecycleRuntimeRoot -Path $env:SystemDrive -AllowMissing; exit 4 } "
            "catch { exit 0 }"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            timeout=20,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
