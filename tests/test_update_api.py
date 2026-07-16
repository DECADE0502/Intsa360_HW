from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from app.backend import lifecycle_update, update_api
from app.backend.release_manifest import ReleaseManifest, compare_versions


ROOT = Path(__file__).resolve().parents[1]


def _installed_runtime(root: Path, version: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "REVISION").write_text("b" * 40 + "\n", encoding="utf-8")
    (root / "install_manifest.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "product": "Insta360_HW",
                "version": version,
                "revision": "b" * 40,
                "layout": "runtime-v2",
            }
        ),
        encoding="utf-8",
    )


def _manifest(
    zip_bytes: bytes,
    version: str = "9.0.0",
    *,
    minimum_launcher_version: str = "0.2.27",
) -> dict[str, object]:
    return {
        "schema": 2,
        "product": "Insta360_HW",
        "version": version,
        "revision": "a" * 40,
        "published_at": "2026-07-13T00:00:00Z",
        "channel": "stable",
        "minimum_launcher_version": minimum_launcher_version,
        "assets": {
            "runtime": {
                "name": f"Insta360_HW_runtime_v{version}.zip",
                "url": "https://example.invalid/runtime.zip",
                "sha256": hashlib.sha256(zip_bytes).hexdigest(),
                "size_bytes": len(zip_bytes),
            },
            "setup": {
                "name": "Insta360_HW_Setup.exe",
                "url": "https://example.invalid/Insta360_HW_Setup.exe",
                "sha256": hashlib.sha256(b"setup").hexdigest(),
                "size_bytes": len(b"setup"),
            },
        },
        "notice": {"title": "Lifecycle V2", "summary": "Transactional update", "highlights": ["Atomic switch"]},
    }


def _runtime_zip(version: str = "9.0.0") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as bundle:
        prefix = "HWAgent_release/"
        bundle.writestr(prefix + "Insta360_HW.exe", b"launcher")
        bundle.writestr(prefix + "VERSION", version + "\n")
        bundle.writestr(prefix + "REVISION", "a" * 40 + "\n")
        bundle.writestr(prefix + "app/backend/suite_app.py", "# runtime\n")
        bundle.writestr(prefix + "app/frontend/index.html", "<!doctype html>\n")
        bundle.writestr(prefix + "launch_tool_suite.ps1", "# launcher\n")
        bundle.writestr(prefix + "scripts/lifecycle/Worker.ps1", "# worker\n")
        bundle.writestr(prefix + "scripts/lifecycle/Recover.ps1", "# recovery\n")
        bundle.writestr(prefix + "scripts/lib/Paths.ps1", "# paths\n")
        bundle.writestr(prefix + "runtime/python/python.exe", b"python")
        bundle.writestr(
            prefix + "install_manifest.json",
            json.dumps(
                {
                    "schema": 2,
                    "product": "Insta360_HW",
                    "version": version,
                    "revision": "a" * 40,
                    "layout": "runtime-v2",
                }
            ),
        )
    return stream.getvalue()


class _Response:
    def __init__(self, data: bytes):
        self._stream = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


class UpdateApiV2Tests(unittest.TestCase):
    def test_public_lifecycle_fallback_messages_remain_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(lifecycle_update, "check_update", side_effect=RuntimeError("network down")):
                checked = update_api.check_update(root)

            idle = update_api._update_status_payload({"phase": "idle"})
            removal = update_api.run_uninstall(root, "cadence_only")

        self.assertEqual(checked["message"], "无法读取更新清单。")
        self.assertEqual(idle["message"], "当前没有正在执行的更新任务。")
        self.assertIn("Cadence", removal["error"])
        self.assertIn("缺少", removal["error"])

    def test_atomic_json_retries_transient_replace_access_denial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state" / "job.json"
            original_replace = Path.replace
            attempts = 0

            def flaky_replace(source: Path, destination: Path) -> Path:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError(13, "simulated transient access denial", str(source))
                return original_replace(source, destination)

            with patch.object(Path, "replace", new=flaky_replace):
                lifecycle_update._atomic_json(target, {"status": "ok"})

            self.assertEqual(attempts, 3)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"status": "ok"})

    def test_release_manifest_cli_uses_the_same_strict_contract_as_the_client(self) -> None:
        archive = _runtime_zip()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "update-manifest.json"
            valid = _manifest(archive)
            path.write_text(json.dumps(valid), encoding="utf-8")
            command = [sys.executable, str(ROOT / "app" / "backend" / "release_manifest.py"), str(path)]

            accepted = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

            del valid["assets"]["setup"]
            path.write_text(json.dumps(valid), encoding="utf-8")
            rejected = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("setup", rejected.stderr)

    def test_manifest_requires_complete_release_asset_integrity(self) -> None:
        archive = _runtime_zip()
        parsed = ReleaseManifest.parse(_manifest(archive))
        self.assertEqual(parsed.version, "9.0.0")
        broken = _manifest(archive)
        broken["assets"]["runtime"]["sha256"] = ""
        with self.assertRaisesRegex(ValueError, "SHA256"):
            ReleaseManifest.parse(broken)

    def test_version_comparison_is_monotonic_and_same_version_is_equal(self) -> None:
        self.assertGreater(compare_versions("0.3.0", "0.2.27"), 0)
        self.assertEqual(compare_versions("0.3.0", "0.3.0"), 0)
        self.assertLess(compare_versions("0.3.0-rc.1", "0.3.0"), 0)

    def test_check_update_reads_one_manifest_and_never_uses_source_zip(self) -> None:
        archive = _runtime_zip("0.3.0")
        body = json.dumps(_manifest(archive, "0.3.0")).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "runtime"
            state = base / "state"
            _installed_runtime(root, "0.2.27")
            (root / "config").mkdir()
            (root / "config" / "default.json").write_text("{}", encoding="utf-8")
            calls: list[str] = []

            def fake_open(request, timeout=0):
                calls.append(request.full_url)
                return _Response(body)

            with (
                patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": str(state)}, clear=False),
                patch.object(lifecycle_update, "urlopen", fake_open),
            ):
                result = update_api.check_update(root)

            self.assertTrue(result["has_update"])
            self.assertEqual(result["download_strategy"], "release_runtime_zip")
            self.assertEqual(len(calls), 1)
            self.assertIn("update-manifest.json", calls[0])

    def test_legacy_latest_release_without_manifest_is_not_reported_as_a_network_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _installed_runtime(root, "0.3.0")
            missing_manifest = HTTPError(
                "https://github.com/DECADE0502/Intsa360_HW/releases/download/v0.2.27/update-manifest.json",
                404,
                "Not Found",
                None,
                None,
            )

            with patch.object(lifecycle_update, "urlopen", side_effect=missing_manifest):
                result = update_api.check_update(root)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["remote_status"], "not_published")
        self.assertEqual(result["update_reason"], "manifest_not_published")
        self.assertEqual(result["remote_version"], "0.2.27")
        self.assertFalse(result["has_update"])
        self.assertFalse(result["can_update"])
        self.assertEqual(result["download_strategy"], "none")
        self.assertNotIn("HTTP Error", result["message"])
        self.assertNotIn("404", result["message"])

    def test_unrelated_manifest_404_remains_a_configuration_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _installed_runtime(root, "0.3.0")
            missing_manifest = HTTPError(
                "https://example.invalid/wrong-manifest.json",
                404,
                "Not Found",
                None,
                None,
            )

            with patch.object(lifecycle_update, "urlopen", side_effect=missing_manifest):
                result = update_api.check_update(root)

        self.assertEqual(result["remote_status"], "error")
        self.assertEqual(result["update_reason"], "manifest_unavailable")
        self.assertEqual(result["download_strategy"], "none")

    def test_same_version_matching_published_revision_is_up_to_date(self) -> None:
        archive = _runtime_zip("0.3.0")
        parsed = ReleaseManifest.parse(_manifest(archive, "0.3.0"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _installed_runtime(root, "0.3.0")
            (root / "REVISION").write_text(parsed.revision + "\n", encoding="utf-8")
            install_manifest = json.loads((root / "install_manifest.json").read_text(encoding="utf-8"))
            install_manifest["revision"] = parsed.revision
            (root / "install_manifest.json").write_text(json.dumps(install_manifest), encoding="utf-8")
            with patch.object(lifecycle_update, "_fetch_manifest", return_value=(parsed, {})):
                result = update_api.check_update(root)
        self.assertFalse(result["has_update"])
        self.assertEqual(result["update_reason"], "up_to_date")

    def test_minimum_launcher_version_blocks_unsafe_in_app_update(self) -> None:
        archive = _runtime_zip("9.0.0")
        parsed = ReleaseManifest.parse(
            _manifest(archive, "9.0.0", minimum_launcher_version="2.0.0")
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _installed_runtime(root, "1.0.0")
            with patch.object(lifecycle_update, "_fetch_manifest", return_value=(parsed, {})):
                checked = update_api.check_update(root)
                started = update_api.run_update(root)

        self.assertTrue(checked["has_update"])
        self.assertFalse(checked["can_update"])
        self.assertEqual(checked["update_reason"], "launcher_too_old")
        self.assertEqual(started["status"], "error")
        self.assertIn("安装包", started["error"])

    def test_download_verify_stage_and_worker_handoff_are_structured(self) -> None:
        archive = _runtime_zip("9.0.0")
        parsed = ReleaseManifest.parse(_manifest(archive, "9.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root, state = base / "runtime", base / "state"
            _installed_runtime(root, "1.0.0")
            (root / "scripts").mkdir()
            shutil.copytree(ROOT / "scripts" / "lifecycle", root / "scripts" / "lifecycle")
            handed_off: list[tuple[Path, Path, str, str, str, bool]] = []

            def fake_worker(runtime, worker, state_root, job_id, stage, version, tree_sha256):
                handed_off.append(
                    (
                        worker,
                        stage,
                        version,
                        tree_sha256,
                        lifecycle_update._runtime_tree_sha256(stage),
                        (stage / "app" / "backend" / "suite_app.py").exists(),
                    )
                )
                lifecycle_update._write_job(
                    runtime,
                    job_id,
                    phase="completed",
                    progress=100,
                    message="test worker complete",
                    version=version,
                )
                return os.getpid()

            with (
                patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": str(state)}, clear=False),
                patch.object(lifecycle_update, "_fetch_manifest", return_value=(parsed, {})),
                patch.object(lifecycle_update, "urlopen", return_value=_Response(archive)),
                patch.object(lifecycle_update, "_launch_worker", side_effect=fake_worker),
            ):
                result = update_api.run_update(root)
                self.assertEqual(result["status"], "ok")
                deadline = time.time() + 10
                while time.time() < deadline:
                    status = update_api.update_status(root)
                    with lifecycle_update._ACTIVE_LOCK:
                        preparer_alive = any(thread.is_alive() for thread in lifecycle_update._ACTIVE_THREADS.values())
                    if (status.get("done") or status.get("failed")) and not preparer_alive:
                        break
                    time.sleep(0.05)

            self.assertTrue(status["done"], status)
            self.assertEqual(status["phase"], "completed")
            self.assertEqual(handed_off[0][0], root / "scripts" / "lifecycle" / "Worker.ps1")
            self.assertEqual(handed_off[0][2], "9.0.0")
            self.assertEqual(handed_off[0][3], handed_off[0][4])
            self.assertTrue(handed_off[0][5])

    def test_concurrent_update_requests_create_only_one_job(self) -> None:
        archive = _runtime_zip("9.0.0")
        parsed = ReleaseManifest.parse(_manifest(archive, "9.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root, state = base / "runtime", base / "state"
            _installed_runtime(root, "1.0.0")
            release_preparer = threading.Event()
            callers_ready = threading.Barrier(3)
            results: list[dict[str, object]] = []
            fetch_count = 0
            fetch_lock = threading.Lock()

            def fake_fetch(_root):
                nonlocal fetch_count
                with fetch_lock:
                    fetch_count += 1
                time.sleep(0.15)
                return parsed, {}

            def fake_prepare(runtime, job_id, _manifest):
                try:
                    release_preparer.wait(timeout=5)
                    lifecycle_update._write_job(
                        runtime,
                        job_id,
                        phase="completed",
                        progress=100,
                        message="test complete",
                        cancellable=False,
                    )
                finally:
                    with lifecycle_update._ACTIVE_LOCK:
                        lifecycle_update._ACTIVE_THREADS.pop(job_id, None)
                        lifecycle_update._CANCEL_EVENTS.pop(job_id, None)

            def invoke_update():
                callers_ready.wait(timeout=5)
                results.append(lifecycle_update.run_update(root))

            with (
                patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": str(state)}, clear=False),
                patch.object(lifecycle_update, "_fetch_manifest", side_effect=fake_fetch),
                patch.object(lifecycle_update, "_prepare_update", side_effect=fake_prepare),
            ):
                callers = [threading.Thread(target=invoke_update) for _ in range(2)]
                for caller in callers:
                    caller.start()
                callers_ready.wait(timeout=5)
                for caller in callers:
                    caller.join(timeout=5)
                release_preparer.set()
                with lifecycle_update._ACTIVE_LOCK:
                    preparers = list(lifecycle_update._ACTIVE_THREADS.values())
                for preparer in preparers:
                    preparer.join(timeout=5)

            self.assertEqual(sum(result["status"] == "ok" for result in results), 1, results)
            self.assertEqual(sum(result["status"] == "error" for result in results), 1, results)
            self.assertEqual(fetch_count, 1)

    def test_idle_and_cancelled_statuses_are_terminal_for_the_web_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            idle = update_api.update_status(root)
            self.assertEqual(idle["phase"], "idle")
            self.assertFalse(idle["running"])
            self.assertFalse(idle["cancelled"])

            job_id = "c" * 32
            lifecycle_update._write_job(
                root,
                job_id,
                phase="cancelled",
                progress=100,
                message="已取消",
                cancellable=False,
            )
            cancelled = update_api.update_status(root)
            self.assertEqual(cancelled["phase"], "cancelled")
            self.assertFalse(cancelled["running"])
            self.assertTrue(cancelled["cancelled"])

    def test_update_check_preserves_install_and_launcher_eligibility(self) -> None:
        archive = _runtime_zip("9.0.0")
        parsed = ReleaseManifest.parse(_manifest(archive, "9.0.0", minimum_launcher_version="2.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _installed_runtime(root, "1.0.0")
            with patch.object(lifecycle_update, "_fetch_manifest", return_value=(parsed, {})):
                checked = update_api.check_update(root)

        self.assertFalse(checked["can_update"])
        self.assertTrue(checked["installed_runtime"])
        self.assertEqual(checked["minimum_launcher_version"], "2.0.0")

    def test_elevated_worker_uses_native_shell_execute_and_preserves_spaced_paths(self) -> None:
        arguments = [
            "-NoProfile",
            "-File",
            r"C:\Program Files\Insta360\HWAgent\Worker.ps1",
            "-InstallRoot",
            r"C:\Program Files\Insta360\HWAgent",
        ]
        command_line = lifecycle_update._windows_argument_line(arguments)
        source = (ROOT / "app" / "backend" / "lifecycle_update.py").read_text(encoding="utf-8")

        self.assertIn('"C:\\Program Files\\Insta360\\HWAgent\\Worker.ps1"', command_line)
        self.assertIn("ShellExecuteExW", source)
        self.assertIn("subprocess.list2cmdline", source)
        self.assertNotIn("$p=Start-Process", source)

    def test_update_worker_launches_outside_the_replaceable_install_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "Program Files" / "Insta360" / "HWAgent"
            worker = root / "scripts" / "lifecycle" / "Worker.ps1"
            state = base / "LocalAppData" / "Insta360_HW"
            stage = state / "lifecycle" / "transactions" / ("a" * 32) / "extracted" / "HWAgent_release"
            worker.parent.mkdir(parents=True)
            state.mkdir(parents=True)

            with (
                patch.object(lifecycle_update, "_is_admin", return_value=True),
                patch.object(lifecycle_update.subprocess, "Popen") as popen,
            ):
                popen.return_value.pid = 4321
                pid = lifecycle_update._launch_worker(
                    root,
                    worker,
                    state,
                    "a" * 32,
                    stage,
                    "0.3.3",
                    "b" * 64,
                )

            self.assertEqual(pid, 4321)
            self.assertEqual(Path(popen.call_args.kwargs["cwd"]), state)

    def test_terminal_job_cleanup_removes_only_its_staged_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root, state = base / "runtime", base / "state"
            root.mkdir()
            job_id = "d" * 32
            transaction = state / "lifecycle" / "transactions" / job_id
            transaction.mkdir(parents=True)
            (transaction / "payload.bin").write_bytes(b"payload")
            unrelated = state / "lifecycle" / "transactions" / "keep-me"
            unrelated.mkdir(parents=True)
            with patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": str(state)}, clear=False):
                lifecycle_update._write_job(
                    root,
                    job_id,
                    phase="completed",
                    progress=100,
                    message="完成",
                    worker_pid=99999999,
                )
                status = lifecycle_update.update_status(root)

            self.assertEqual(status["phase"], "completed")
            self.assertFalse(transaction.exists())
            self.assertTrue(unrelated.exists())

    def test_cleanup_pending_job_keeps_transaction_journal_for_elevated_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root, state = base / "runtime", base / "state"
            root.mkdir()
            job_id = "f" * 32
            transaction = state / "lifecycle" / "transactions" / job_id
            transaction.mkdir(parents=True)
            (transaction / "journal.json").write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": str(state)}, clear=False):
                lifecycle_update._write_job(
                    root,
                    job_id,
                    phase="completed",
                    progress=100,
                    message="新版本已生效，旧版本清理待重试",
                    cleanup_pending=True,
                    worker_pid=99999999,
                )
                status = lifecycle_update.update_status(root)

            self.assertTrue(status["cleanup_pending"])
            self.assertTrue(transaction.exists())

    def test_reused_worker_pid_is_not_reported_as_a_running_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root, state = base / "runtime", base / "state"
            root.mkdir()
            job_id = "e" * 32
            transaction = state / "lifecycle" / "transactions" / job_id
            transaction.mkdir(parents=True)
            (transaction / "journal.json").write_text(
                json.dumps({"schema": 2, "job_id": job_id, "phase": "new_runtime_activated"}),
                encoding="utf-8",
            )
            with (
                patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": str(state)}, clear=False),
                patch.object(lifecycle_update, "_process_creation_token", return_value=222),
            ):
                lifecycle_update._write_job(
                    root,
                    job_id,
                    phase="committing",
                    progress=72,
                    message="切换中",
                    worker_pid=os.getpid(),
                    worker_creation_time=111,
                    cancellable=False,
                )
                status = lifecycle_update.update_status(root)

            self.assertEqual(status["phase"], "failed")
            self.assertTrue(status["recovery_required"])
            self.assertFalse(status["running"])
            self.assertTrue(transaction.exists())
            self.assertTrue((transaction / "journal.json").is_file())

    def test_archive_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.txt", "bad")
            with self.assertRaisesRegex(ValueError, "escapes"):
                lifecycle_update._safe_extract(archive, Path(tmp) / "out")

    def test_archive_symbolic_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "link.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                info = zipfile.ZipInfo("payload/link")
                info.create_system = 3
                info.external_attr = 0o120777 << 16
                bundle.writestr(info, "../outside")
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                lifecycle_update._safe_extract(archive, Path(tmp) / "out")

    def test_archive_extraction_honours_precommit_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "cancel.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("payload/file.bin", b"x" * 1024)
            cancelled = threading.Event()
            cancelled.set()
            with self.assertRaises(InterruptedError):
                lifecycle_update._safe_extract(archive, Path(tmp) / "out", cancelled)

    def test_payload_requires_complete_runtime_inventory(self) -> None:
        archive = _runtime_zip("9.0.0")
        parsed = ReleaseManifest.parse(_manifest(archive, "9.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "payload"
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                bundle.extractall(payload)
            root = payload / "HWAgent_release"
            (root / "runtime" / "python" / "python.exe").unlink()
            with self.assertRaisesRegex(ValueError, "runtime/python/python.exe"):
                lifecycle_update._validate_payload(root, parsed)

    def test_payload_install_manifest_identity_is_strict(self) -> None:
        archive = _runtime_zip("9.0.0")
        parsed = ReleaseManifest.parse(_manifest(archive, "9.0.0"))
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "payload"
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                bundle.extractall(payload)
            root = payload / "HWAgent_release"
            manifest_path = root / "install_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["layout"] = "legacy"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "layout"):
                lifecycle_update._validate_payload(root, parsed)

    def test_invalid_cancel_job_id_cannot_escape_jobs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = update_api.cancel_update(root, "../outside")
            self.assertEqual(result["status"], "error")
            self.assertIn("任务编号", result["error"])

    def test_orphaned_precommit_job_is_normalized_after_backend_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_id = "a" * 32
            lifecycle_update._write_job(
                root,
                job_id,
                phase="downloading",
                progress=24,
                message="downloading",
                cancellable=True,
            )

            status = update_api.update_status(root)

            self.assertEqual(status["phase"], "failed")
            self.assertFalse(status["running"])
            self.assertIn("中断", status["message"])


if __name__ == "__main__":
    unittest.main()
