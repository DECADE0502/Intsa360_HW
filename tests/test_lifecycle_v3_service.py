from __future__ import annotations

import base64
import ctypes
import hashlib
import io
import json
import os
import threading
import zipfile
from ctypes import wintypes
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.backend import lifecycle_v3, lifecycle_v3_jobs, lifecycle_v3_process, update_api
from app.backend.lifecycle_v3_archive import REQUIRED_RUNTIME_FILES, runtime_tree_sha256


OLD_VERSION = "0.3.3"
NEW_VERSION = "0.4.0"
OLD_REVISION = "a" * 40
NEW_REVISION = "b" * 40
TEST_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
TEST_TRUST_ANCHOR = TEST_PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("ascii")
ATTACKER_TRUST_ANCHOR = Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65))).public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("ascii")


@pytest.mark.skipif(os.name != "nt", reason="Windows process API contract")
def test_process_probe_uses_pointer_sized_windows_handle_signatures() -> None:
    assert lifecycle_v3_process.process_alive(os.getpid()) is True

    kernel32 = lifecycle_v3_process._kernel32_process_api()
    assert kernel32.OpenProcess.restype is wintypes.HANDLE
    assert kernel32.OpenProcess.argtypes == [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    assert kernel32.GetExitCodeProcess.argtypes == [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    assert kernel32.CloseHandle.argtypes == [wintypes.HANDLE]


def test_v3_state_index_is_isolated_from_legacy_lifecycle_jobs(tmp_path: Path) -> None:
    _, runtime, state_root = _installed_layout(tmp_path)
    legacy_jobs = state_root / "lifecycle" / "jobs"
    legacy_jobs.mkdir(parents=True, exist_ok=True)
    legacy_latest = legacy_jobs / "latest.json"
    legacy_latest.write_text(json.dumps({"schema": 2, "job_id": "legacy-job"}), encoding="utf-8")

    with patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": str(state_root)}):
        assert lifecycle_v3._latest_job_id(runtime) == ""
        job_id = "d" * 32
        lifecycle_v3._write_job(runtime, job_id, phase="queued", progress=0, message="queued")

    assert json.loads(legacy_latest.read_text(encoding="utf-8"))["job_id"] == "legacy-job"
    latest_v3 = state_root / "lifecycle" / "v3" / "jobs" / "latest.json"
    assert json.loads(latest_v3.read_text(encoding="utf-8"))["job_id"] == job_id


def test_v3_job_status_keeps_timestamps_and_distinct_recent_activity(tmp_path: Path) -> None:
    _, runtime, state_root = _installed_layout(tmp_path)
    job_id = "e" * 32

    with patch.dict(os.environ, {"INSTA360_HW_STATE_ROOT": str(state_root)}):
        lifecycle_v3_jobs.write_job(runtime, job_id, phase="queued", progress=0, message="更新任务已创建。")
        lifecycle_v3_jobs.write_job(runtime, job_id, phase="downloading", progress=10, message="正在下载运行包。")
        lifecycle_v3_jobs.write_job(runtime, job_id, phase="downloading", progress=20, message="正在下载运行包。")
        job = lifecycle_v3_jobs.read_job(runtime, job_id)
    assert job is not None
    assert job["started_at"]
    assert job["updated_at"]
    assert job["log_tail"] == ["更新任务已创建。", "正在下载运行包。"]


def test_v3_payload_contract_includes_actual_service_launcher_dependencies() -> None:
    assert "scripts/lifecycle/Contract.ps1" in REQUIRED_RUNTIME_FILES
    assert "scripts/lifecycle/Runtime.ps1" in REQUIRED_RUNTIME_FILES
    assert "scripts/lifecycle_v3/Install.ps1" in REQUIRED_RUNTIME_FILES
    assert "scripts/lifecycle_v3/Uninstall.ps1" in REQUIRED_RUNTIME_FILES
    assert "scripts/lifecycle_v3/SetupRunner.ps1" in REQUIRED_RUNTIME_FILES
    assert "scripts/remove_cadence_loader.ps1" in REQUIRED_RUNTIME_FILES
    assert "cadence/iac_bom_tool.tcl" in REQUIRED_RUNTIME_FILES
    assert "config/capabilities.json" in REQUIRED_RUNTIME_FILES


def _write_runtime(root: Path, version: str, revision: str) -> None:
    files = {
        "VERSION": version + "\n",
        "REVISION": revision + "\n",
        "install_manifest.json": json.dumps(
            {
                "schema": 3,
                "product": "Insta360_HW",
                "layout": "runtime-v3",
                "version": version,
                "revision": revision,
                "build_kind": "published",
            }
        ),
        "launch_tool_suite.ps1": "fixture\n",
        "app/backend/suite_app.py": "fixture\n",
        "app/frontend/index.html": "fixture\n",
        "runtime/python/python.exe": "fixture\n",
        "scripts/lifecycle_v3/Worker.ps1": "fixture\n",
        "scripts/lifecycle_v3/Recover.ps1": "fixture\n",
        "scripts/lifecycle_v3/Resume.ps1": "fixture\n",
        "scripts/lifecycle_v3/Contract.ps1": "fixture\n",
        "scripts/lifecycle_v3/Runtime.ps1": "fixture\n",
        "scripts/lifecycle_v3/Install.ps1": "fixture\n",
        "scripts/lifecycle_v3/Uninstall.ps1": "fixture\n",
        "scripts/lifecycle_v3/SetupRunner.ps1": "fixture\n",
        "scripts/lifecycle_v3/SetupRecover.ps1": "fixture\n",
        "scripts/lifecycle/Contract.ps1": "fixture\n",
        "scripts/lifecycle/Runtime.ps1": "fixture\n",
        "scripts/lifecycle/Recover.ps1": "fixture\n",
        "scripts/lifecycle/Worker.ps1": "fixture\n",
        "scripts/remove_cadence_loader.ps1": "fixture\n",
        "scripts/lib/Paths.ps1": "fixture\n",
        "scripts/lib/Cadence.ps1": "fixture\n",
        "scripts/lib/TclScripts.ps1": "fixture\n",
        "cadence/iac_bom_tool.tcl": "fixture\n",
        "config/capabilities.json": "{}\n",
        "config/update_public_key.pem": TEST_TRUST_ANCHOR,
    }
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _installed_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    install_root = tmp_path / "HWAgent"
    runtime = install_root / "runtime" / f"{OLD_VERSION}+{OLD_REVISION}"
    _write_runtime(runtime, OLD_VERSION, OLD_REVISION)
    install_root.mkdir(parents=True, exist_ok=True)
    (install_root / "Insta360_HW.exe").write_bytes(b"launcher")
    (install_root / "installation.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "product": "Insta360_HW",
                "layout": "versioned-runtime-v3",
                "active_runtime": f"runtime/{OLD_VERSION}+{OLD_REVISION}",
                "previous_runtime": "",
                "generation": 1,
                "updated_at": "2026-07-14T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    state_root = tmp_path / "state"
    return install_root, runtime, state_root


def _runtime_zip(tmp_path: Path, *, trust_anchor: str = TEST_TRUST_ANCHOR) -> bytes:
    payload = tmp_path / "payload"
    _write_runtime(payload, NEW_VERSION, NEW_REVISION)
    (payload / "config" / "update_public_key.pem").write_text(trust_anchor, encoding="utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(payload).as_posix())
    return output.getvalue()


def _signed_manifest(tmp_path: Path, archive: bytes) -> tuple[dict[str, object], Path]:
    public_key = tmp_path / "update_public_key.pem"
    public_key.write_bytes(
        TEST_PRIVATE_KEY.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    raw: dict[str, object] = {
        "schema_version": 3,
        "version": NEW_VERSION,
        "revision": NEW_REVISION,
        "build_kind": "published",
        "published_at": "2026-07-14T00:00:00Z",
        "min_updater_version": "0.3.3",
        "assets": [
            {
                "name": f"Insta360_HW_Runtime_{NEW_VERSION}.zip",
                "url": f"https://github.com/DECADE0502/Intsa360_HW/releases/download/v{NEW_VERSION}/Insta360_HW_Runtime_{NEW_VERSION}.zip",
                "size": len(archive),
                "sha256": hashlib.sha256(archive).hexdigest(),
            }
        ],
        "changelog": ["Atomic update"],
        "signature": "pending",
    }
    raw["signature"] = "ed25519:" + base64.b64encode(
        TEST_PRIVATE_KEY.sign(lifecycle_v3.canonical_manifest_payload(raw))
    ).decode("ascii")
    return raw, public_key


class _Response:
    def __init__(self, payload: bytes):
        self._stream = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


def test_v3_installs_dispatch_to_v3_update_service(tmp_path: Path) -> None:
    _, runtime, state_root = _installed_layout(tmp_path)
    with patch.dict("os.environ", {"INSTA360_HW_STATE_ROOT": str(state_root)}, clear=False):
        with patch.object(lifecycle_v3, "check_update", return_value={"remote_status": "ok", "version": OLD_VERSION}) as check:
            payload = update_api.check_update(runtime)

    check.assert_called_once_with(runtime)
    assert payload["remote_status"] == "ok"


def test_v3_default_manifest_uses_the_git_only_ota_channel() -> None:
    assert lifecycle_v3.DEFAULT_SIGNED_MANIFEST_URL == (
        "https://raw.githubusercontent.com/DECADE0502/Intsa360_HW/"
        "ota/channel/stable/update-manifest-v3.json"
    )


def test_v3_missing_latest_manifest_is_reported_as_not_published(tmp_path: Path) -> None:
    _, runtime, _ = _installed_layout(tmp_path)
    missing_manifest = HTTPError(
        lifecycle_v3.DEFAULT_SIGNED_MANIFEST_URL,
        404,
        "Not Found",
        None,
        None,
    )

    with patch.object(lifecycle_v3, "urlopen", side_effect=missing_manifest):
        payload = update_api.check_update(runtime)

    assert payload["remote_status"] == "not_published"
    assert payload["update_reason"] == "manifest_not_published"
    assert payload["integrity_status"] == "manifest_not_published"
    assert payload["has_update"] is False
    assert payload["can_update"] is False
    assert payload["error"] == ""
    assert "签名" not in payload["message"]
    assert "404" not in payload["message"]


def test_malformed_versioned_layout_is_not_selected_by_directory_shape(tmp_path: Path) -> None:
    install_root = tmp_path / "HWAgent"
    runtime = install_root / "runtime" / f"{OLD_VERSION}+{OLD_REVISION}"
    _write_runtime(runtime, OLD_VERSION, OLD_REVISION)
    (install_root / "installation.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="installation metadata"):
        update_api._update_backend(runtime)


def test_update_trust_anchor_cannot_be_overridden_by_user_environment(tmp_path: Path) -> None:
    _, runtime, _ = _installed_layout(tmp_path)
    attacker_key = tmp_path / "attacker.pem"
    with patch.dict("os.environ", {"INSTA360_HW_UPDATE_PUBLIC_KEY": str(attacker_key)}, clear=False):
        assert lifecycle_v3._public_key_path(runtime) == runtime / "config" / "update_public_key.pem"


def test_prepare_update_verifies_archive_and_hands_off_to_worker(tmp_path: Path) -> None:
    install_root, runtime, state_root = _installed_layout(tmp_path)
    archive = _runtime_zip(tmp_path)
    raw, public_key = _signed_manifest(tmp_path, archive)
    manifest = lifecycle_v3.verify_signed_manifest(raw, public_key)
    job_id = "1" * 32
    cancel = threading.Event()
    captured: dict[str, object] = {}

    def launch(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return 4321

    with patch.dict("os.environ", {"INSTA360_HW_STATE_ROOT": str(state_root)}, clear=False):
        lifecycle_v3._CANCEL_EVENTS[job_id] = cancel
        try:
            with patch.object(lifecycle_v3, "urlopen", return_value=_Response(archive)), patch.object(
                lifecycle_v3, "_launch_worker", side_effect=launch
            ), patch.object(lifecycle_v3, "_wait_for_worker_ack", return_value=True):
                lifecycle_v3._prepare_update(runtime, job_id, manifest)
        finally:
            lifecycle_v3._CANCEL_EVENTS.pop(job_id, None)

    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / f"{job_id}.json").read_text(encoding="utf-8-sig"))
    assert job["phase"] == "awaiting_elevation"
    assert captured["args"][0] == install_root.resolve()
    stage = Path(str(job["stage_root"]))
    assert (stage / "VERSION").read_text(encoding="utf-8").strip() == NEW_VERSION


def test_cancel_before_commit_removes_transaction_without_worker(tmp_path: Path) -> None:
    _, runtime, state_root = _installed_layout(tmp_path)
    archive = _runtime_zip(tmp_path)
    raw, public_key = _signed_manifest(tmp_path, archive)
    manifest = lifecycle_v3.verify_signed_manifest(raw, public_key)
    job_id = "2" * 32
    cancel = threading.Event()
    cancel.set()

    with patch.dict("os.environ", {"INSTA360_HW_STATE_ROOT": str(state_root)}, clear=False):
        lifecycle_v3._CANCEL_EVENTS[job_id] = cancel
        try:
            with patch.object(lifecycle_v3, "urlopen", return_value=_Response(archive)), patch.object(
                lifecycle_v3, "_launch_worker"
            ) as launch:
                lifecycle_v3._prepare_update(runtime, job_id, manifest)
        finally:
            lifecycle_v3._CANCEL_EVENTS.pop(job_id, None)

    launch.assert_not_called()
    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / f"{job_id}.json").read_text(encoding="utf-8-sig"))
    assert job["phase"] == "cancelled"
    assert not (state_root / "lifecycle" / "v3" / "transactions" / job_id).exists()
    assert not list((state_root / "lifecycle" / "v3" / "cache").glob(f"*-{job_id}.zip"))


def test_v3_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "escape.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "blocked")

    with pytest.raises(ValueError, match="escapes staging root"):
        lifecycle_v3._safe_extract(archive, tmp_path / "stage")

    assert not (tmp_path / "outside.txt").exists()


def test_v3_archive_reports_progress_and_hashes_while_extracting(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("one.txt", b"one")
        bundle.writestr("nested/two.bin", b"two-two")
    reports: list[tuple[int, int, int, int]] = []
    stage = tmp_path / "stage"

    extracted_hash = lifecycle_v3._safe_extract(
        archive,
        stage,
        progress=lambda *values: reports.append(values),
    )

    assert extracted_hash == runtime_tree_sha256(stage)
    assert reports[0] == (0, 2, 0, 10)
    assert reports[-1] == (2, 2, 10, 10)


def test_same_size_download_tampering_fails_before_worker(tmp_path: Path) -> None:
    _, runtime, state_root = _installed_layout(tmp_path)
    archive = _runtime_zip(tmp_path)
    raw, public_key = _signed_manifest(tmp_path, archive)
    manifest = lifecycle_v3.verify_signed_manifest(raw, public_key)
    tampered = bytearray(archive)
    tampered[-1] ^= 0x01
    job_id = "6" * 32
    cancel = threading.Event()

    with patch.dict("os.environ", {"INSTA360_HW_STATE_ROOT": str(state_root)}, clear=False):
        lifecycle_v3._CANCEL_EVENTS[job_id] = cancel
        try:
            with patch.object(lifecycle_v3, "urlopen", return_value=_Response(bytes(tampered))), patch.object(
                lifecycle_v3, "_launch_worker"
            ) as launch:
                lifecycle_v3._prepare_update(runtime, job_id, manifest)
        finally:
            lifecycle_v3._CANCEL_EVENTS.pop(job_id, None)

    launch.assert_not_called()
    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / f"{job_id}.json").read_text(encoding="utf-8-sig"))
    assert job["phase"] == "failed"
    assert "SHA256" in job["error"]
    assert not (state_root / "lifecycle" / "v3" / "transactions" / job_id).exists()


def test_candidate_cannot_replace_update_trust_anchor(tmp_path: Path) -> None:
    _, runtime, state_root = _installed_layout(tmp_path)
    archive = _runtime_zip(tmp_path, trust_anchor=ATTACKER_TRUST_ANCHOR)
    raw, public_key = _signed_manifest(tmp_path, archive)
    manifest = lifecycle_v3.verify_signed_manifest(raw, public_key)
    job_id = "7" * 32

    with patch.dict("os.environ", {"INSTA360_HW_STATE_ROOT": str(state_root)}, clear=False):
        lifecycle_v3._CANCEL_EVENTS[job_id] = threading.Event()
        try:
            with patch.object(lifecycle_v3, "urlopen", return_value=_Response(archive)), patch.object(
                lifecycle_v3, "_launch_worker"
            ) as launch:
                lifecycle_v3._prepare_update(runtime, job_id, manifest)
        finally:
            lifecycle_v3._CANCEL_EVENTS.pop(job_id, None)

    launch.assert_not_called()
    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / f"{job_id}.json").read_text(encoding="utf-8-sig"))
    assert job["phase"] == "failed"
    assert "trust anchor" in job["error"]


def test_worker_exit_before_ack_does_not_leave_running_job(tmp_path: Path) -> None:
    _, runtime, state_root = _installed_layout(tmp_path)
    archive = _runtime_zip(tmp_path)
    raw, public_key = _signed_manifest(tmp_path, archive)
    manifest = lifecycle_v3.verify_signed_manifest(raw, public_key)
    job_id = "8" * 32

    with patch.dict("os.environ", {"INSTA360_HW_STATE_ROOT": str(state_root)}, clear=False):
        lifecycle_v3._CANCEL_EVENTS[job_id] = threading.Event()
        try:
            with patch.object(lifecycle_v3, "urlopen", return_value=_Response(archive)), patch.object(
                lifecycle_v3, "_launch_worker", return_value=987654
            ), patch.object(lifecycle_v3, "_process_alive", return_value=False):
                lifecycle_v3._prepare_update(runtime, job_id, manifest)
        finally:
            lifecycle_v3._CANCEL_EVENTS.pop(job_id, None)

    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / f"{job_id}.json").read_text(encoding="utf-8-sig"))
    assert job["phase"] == "failed"
    assert job["running"] is False
    assert "before acknowledging" in job["error"]
    assert not (state_root / "lifecycle" / "v3" / "transactions" / job_id).exists()


def test_handoff_metadata_failure_does_not_delete_live_worker_stage(tmp_path: Path) -> None:
    _, runtime, state_root = _installed_layout(tmp_path)
    archive = _runtime_zip(tmp_path)
    raw, public_key = _signed_manifest(tmp_path, archive)
    manifest = lifecycle_v3.verify_signed_manifest(raw, public_key)
    job_id = "a" * 32

    with patch.dict("os.environ", {"INSTA360_HW_STATE_ROOT": str(state_root)}, clear=False):
        lifecycle_v3._CANCEL_EVENTS[job_id] = threading.Event()
        try:
            with patch.object(lifecycle_v3, "urlopen", return_value=_Response(archive)), patch.object(
                lifecycle_v3, "_launch_worker", return_value=123456
            ), patch.object(lifecycle_v3, "_atomic_json", side_effect=OSError("handoff disk error")), patch.object(
                lifecycle_v3, "_wait_for_worker_ack", return_value=True
            ):
                lifecycle_v3._prepare_update(runtime, job_id, manifest)
        finally:
            lifecycle_v3._CANCEL_EVENTS.pop(job_id, None)

    job = json.loads((state_root / "lifecycle" / "v3" / "jobs" / f"{job_id}.json").read_text(encoding="utf-8-sig"))
    assert job["phase"] == "awaiting_elevation"
    assert (state_root / "lifecycle" / "v3" / "transactions" / job_id / "stage").is_dir()


def test_dead_acknowledged_worker_requires_recovery_and_blocks_next_update(tmp_path: Path) -> None:
    install_root, runtime, state_root = _installed_layout(tmp_path)
    job_id = "9" * 32
    new_runtime = install_root / "runtime" / f"{NEW_VERSION}+{NEW_REVISION}"
    _write_runtime(new_runtime, NEW_VERSION, NEW_REVISION)
    installation = install_root / "installation.json"
    current = json.loads(installation.read_text(encoding="utf-8"))
    installation.write_text(
        json.dumps(
            {
                **current,
                "active_runtime": f"runtime/{NEW_VERSION}+{NEW_REVISION}",
                "previous_runtime": f"runtime/{OLD_VERSION}+{OLD_REVISION}",
                "generation": 2,
            }
        ),
        encoding="utf-8",
    )
    with patch.dict("os.environ", {"INSTA360_HW_STATE_ROOT": str(state_root)}, clear=False):
        lifecycle_v3._write_job(
            runtime,
            job_id,
            phase="committing",
            progress=70,
            message="worker active",
            worker_pid=987654,
            cancellable=False,
        )
        with patch.object(lifecycle_v3, "_process_alive", return_value=False):
            status = lifecycle_v3.update_status(runtime)
            with patch.object(lifecycle_v3, "_fetch_manifest") as fetch:
                next_update = lifecycle_v3.run_update(runtime)

    assert status["phase"] == "failed"
    assert status["recovery_required"] is True
    assert next_update["status"] == "error"
    assert "恢复" in next_update["error"]
    fetch.assert_not_called()
