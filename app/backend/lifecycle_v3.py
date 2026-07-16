from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.backend.config import load_config
from app.backend.contracts.releases import ReleaseManifestV3
from app.backend.lifecycle_v3_archive import (
    CHUNK_SIZE,
    runtime_tree_sha256 as _runtime_tree_sha256,
    safe_extract as _safe_extract,
    validate_payload as _validate_payload,
)
from app.backend.lifecycle_v3_contract import (
    InstallationLayout,
    candidate_install_root as _candidate_install_root,
    canonical_manifest_payload,
    is_versioned_install,
    read_json_object as _read_json_object,
    resolve_installation,
    verify_signed_manifest,
)
from app.backend.lifecycle_v3_jobs import (
    PRECOMMIT_PHASES as _PRECOMMIT_PHASES,
    TERMINAL_PHASES as _TERMINAL_PHASES,
    atomic_json as _atomic_json,
    latest_job_id as _latest_job_id,
    read_job as _read_job,
    valid_job_id as _valid_job_id,
    write_job as _write_job,
)
from app.backend.lifecycle_v3_process import launch_worker as _launch_worker, process_alive as _process_alive
from app.backend.paths import AppPaths
from app.backend.release_manifest import compare_versions


DEFAULT_SIGNED_MANIFEST_URL = (
    "https://raw.githubusercontent.com/DECADE0502/Intsa360_HW/"
    "ota/channel/stable/update-manifest-v3.json"
)
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_RUNTIME_ASSET_BYTES = 2 * 1024 * 1024 * 1024
DOWNLOAD_FREE_SPACE_RESERVE = 512 * 1024 * 1024

_ACTIVE_LOCK = threading.Lock()
_START_LOCK = threading.Lock()
_ACTIVE_THREADS: dict[str, threading.Thread] = {}
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_ACTIVE_WORKER_PIDS: dict[str, int] = {}
_WORKER_PHASES = {"awaiting_elevation", "committing", "switching", "integrating", "verifying_runtime"}


def _read_runtime_text(root: Path, name: str) -> str:
    try:
        return (root / name).read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def _manifest_url(root: Path) -> str:
    configured = ""
    try:
        configured = str(load_config(root).get("update", {}).get("signed_manifest_url") or "").strip()
    except (OSError, ValueError, json.JSONDecodeError, AttributeError):
        pass
    url = os.environ.get("INSTA360_HW_V3_MANIFEST_URL", "").strip() or configured or DEFAULT_SIGNED_MANIFEST_URL
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("signed update manifest URL must use HTTPS")
    return url


def _public_key_path(root: Path) -> Path:
    return root / "config" / "update_public_key.pem"


def _fetch_manifest(root: Path) -> tuple[ReleaseManifestV3, dict[str, object]]:
    request = Request(
        _manifest_url(root),
        headers={"User-Agent": "Insta360-HWAgent-Lifecycle/3", "Accept": "application/json"},
    )
    with urlopen(request, timeout=8.0) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_MANIFEST_BYTES:
            raise ValueError("signed update manifest exceeds the 1 MiB limit")
        content = response.read(MAX_MANIFEST_BYTES + 1)
    if len(content) > MAX_MANIFEST_BYTES:
        raise ValueError("signed update manifest exceeds the 1 MiB limit")
    try:
        raw = json.loads(content.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("signed update manifest is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("signed update manifest must be an object")
    manifest = verify_signed_manifest(raw, _public_key_path(root))
    paths = AppPaths(root)
    paths.lifecycle_v3_cache_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(paths.lifecycle_v3_cache_dir / "remote-manifest-v3.json", raw)
    return manifest, raw


def _runtime_asset(manifest: ReleaseManifestV3):
    expected = f"Insta360_HW_Runtime_{manifest.version}.zip"
    matches = [asset for asset in manifest.assets if asset.name == expected]
    if len(matches) != 1:
        raise ValueError(f"signed manifest must contain exactly one {expected} asset")
    if matches[0].size > MAX_RUNTIME_ASSET_BYTES:
        raise ValueError("runtime asset exceeds the 2 GiB download limit")
    return matches[0]


def _cleanup_precommit(transaction: Path, download: Path) -> None:
    try:
        download.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        if transaction.is_dir():
            shutil.rmtree(transaction)
    except OSError:
        pass


def _worker_handoff_path(root: Path, job_id: str) -> Path:
    return AppPaths(root).lifecycle_v3_transactions_dir / job_id / "worker-handoff.json"


def _read_worker_handoff(root: Path, job_id: str) -> dict[str, object] | None:
    try:
        raw = json.loads(_worker_handoff_path(root, job_id).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or raw.get("schema") != 3 or raw.get("job_id") != job_id:
        return None
    return raw


def _wait_for_worker_ack(root: Path, job_id: str, process_id: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = _read_job(root, job_id) or {}
        phase = str(job.get("phase") or "awaiting_elevation")
        worker_pid = job.get("worker_pid")
        if phase != "awaiting_elevation" and isinstance(worker_pid, int) and worker_pid == process_id:
            return True
        if not _process_alive(process_id):
            raise RuntimeError("elevated lifecycle worker exited before acknowledging the handoff")
        time.sleep(0.1)
    return False


def _prepare_update(root: Path, job_id: str, manifest: ReleaseManifestV3) -> None:
    paths = AppPaths(root)
    cancel = _CANCEL_EVENTS[job_id]
    layout = resolve_installation(root)
    asset = _runtime_asset(manifest)
    transaction = paths.lifecycle_v3_transactions_dir / job_id
    stage = transaction / "stage"
    download = paths.lifecycle_v3_cache_dir / f"{manifest.version}-{job_id}.zip"
    handed_off = False
    try:
        transaction.mkdir(parents=True, exist_ok=True)
        paths.lifecycle_v3_cache_dir.mkdir(parents=True, exist_ok=True)
        free_bytes = shutil.disk_usage(paths.lifecycle_v3_cache_dir).free
        if free_bytes < asset.size + DOWNLOAD_FREE_SPACE_RESERVE:
            raise ValueError("insufficient free disk space for the verified runtime download")
        if cancel.is_set():
            raise InterruptedError("更新已在提交前取消")
        _write_job(
            root,
            job_id,
            phase="downloading",
            progress=2,
            message="正在下载已签名发布清单指定的运行包。",
            version=manifest.version,
            revision=manifest.revision.lower(),
            bytes_total=asset.size,
            bytes_downloaded=0,
            cancellable=True,
            archive_path=str(download),
        )
        request = Request(str(asset.url), headers={"User-Agent": "Insta360-HWAgent-Lifecycle/3"})
        digest = hashlib.sha256()
        downloaded = 0
        started = time.monotonic()
        last_report = 0.0
        with urlopen(request, timeout=30.0) as response, download.open("wb") as output:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) != asset.size:
                raise ValueError("download Content-Length does not match the signed manifest")
            while True:
                if cancel.is_set():
                    raise InterruptedError("更新已在提交前取消")
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if downloaded > asset.size:
                    raise ValueError("download exceeds the size declared by the signed manifest")
                now = time.monotonic()
                if now - last_report >= 0.2:
                    elapsed = max(now - started, 0.001)
                    _write_job(
                        root,
                        job_id,
                        phase="downloading",
                        progress=2 + int(min(downloaded / asset.size, 1.0) * 52),
                        message="正在下载已签名发布清单指定的运行包。",
                        bytes_total=asset.size,
                        bytes_downloaded=downloaded,
                        bytes_per_second=int(downloaded / elapsed),
                        cancellable=True,
                    )
                    last_report = now
        if downloaded != asset.size:
            raise ValueError(f"download size mismatch: expected {asset.size}, got {downloaded}")
        if cancel.is_set():
            raise InterruptedError("更新已在提交前取消")

        _write_job(
            root,
            job_id,
            phase="verifying",
            progress=57,
            message="正在校验运行包 SHA256。",
            bytes_total=asset.size,
            bytes_downloaded=downloaded,
            cancellable=True,
        )
        if digest.hexdigest().lower() != asset.sha256.lower():
            raise ValueError("downloaded runtime SHA256 does not match the signed manifest")
        if cancel.is_set():
            raise InterruptedError("更新已在提交前取消")

        _write_job(root, job_id, phase="staging", progress=62, message="正在安全展开并验证候选运行时。", cancellable=True)
        if stage.exists():
            shutil.rmtree(stage)
        _safe_extract(download, stage, cancel)
        _validate_payload(stage, manifest)
        current_key = _public_key_path(root)
        candidate_key = stage / "config" / "update_public_key.pem"
        if candidate_key.read_bytes() != current_key.read_bytes():
            raise ValueError("candidate runtime attempts to replace the update trust anchor")
        tree_sha256 = _runtime_tree_sha256(stage)
        with _ACTIVE_LOCK:
            if cancel.is_set():
                raise InterruptedError("更新已在提交前取消")
            _write_job(
                root,
                job_id,
                phase="awaiting_elevation",
                progress=68,
                message="候选版本已验证，正在请求系统授权完成原子切换。",
                cancellable=False,
                stage_root=str(stage),
                tree_sha256=tree_sha256,
            )
            _CANCEL_EVENTS.pop(job_id, None)
        worker_pid = _launch_worker(
            layout.install_root,
            root,
            paths.state_root,
            job_id,
            stage,
            manifest,
            tree_sha256,
        )
        handed_off = True
        with _ACTIVE_LOCK:
            _ACTIVE_WORKER_PIDS[job_id] = worker_pid
        try:
            _atomic_json(
                _worker_handoff_path(root, job_id),
                {
                    "schema": 3,
                    "job_id": job_id,
                    "worker_pid": worker_pid,
                    "worker_path": str(root / "scripts" / "lifecycle_v3" / "Worker.ps1"),
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )
        except OSError:
            # The worker owns the transaction as soon as process creation succeeds.
            # Its first durable job update carries the same PID and remains a status fallback.
            pass
        try:
            _wait_for_worker_ack(root, job_id, worker_pid)
        except RuntimeError:
            handed_off = False
            raise
    except InterruptedError as exc:
        _write_job(
            root, job_id, phase="cancelled", progress=100, message=str(exc),
            cancellable=False, error="",
        )
    except Exception as exc:  # noqa: BLE001
        _write_job(
            root,
            job_id,
            phase="failed",
            progress=100,
            message=f"更新准备失败：{exc}",
            cancellable=False,
            error=str(exc),
            rolled_back=True,
            recovery_required=False,
        )
    finally:
        if not handed_off:
            _cleanup_precommit(transaction, download)
        with _ACTIVE_LOCK:
            _ACTIVE_THREADS.pop(job_id, None)
            _CANCEL_EVENTS.pop(job_id, None)
            if not handed_off:
                _ACTIVE_WORKER_PIDS.pop(job_id, None)


def _compare_semver(left: str, right: str) -> int:
    return compare_versions(left.split("+", 1)[0], right.split("+", 1)[0])


def _evaluate_update(root: Path, manifest: ReleaseManifestV3) -> dict[str, object]:
    layout = resolve_installation(root)
    local_manifest = _read_json_object(
        layout.active_runtime / "install_manifest.json", label="runtime install manifest"
    )
    local_version = _read_runtime_text(root, "VERSION") or "0.0.0"
    local_revision = _read_runtime_text(root, "REVISION").lower()
    local_build_kind = str(local_manifest.get("build_kind") or "published")
    comparison = _compare_semver(manifest.version, local_version)
    updater_ok = _compare_semver(local_version, manifest.min_updater_version) >= 0
    has_update = comparison > 0

    if comparison < 0:
        reason = "remote_older"
        message = "远端版本低于当前版本，已拒绝降级。"
    elif comparison == 0 and manifest.revision.lower() == local_revision:
        has_update = False
        reason = "up_to_date"
        message = "当前已经是最新版本。"
    elif comparison == 0 and local_build_kind == "dev" and manifest.build_kind.value == "published":
        has_update = True
        reason = "canonical_published_revision"
        message = "发现同版本的正式发布构建，可以更新。"
    elif comparison == 0:
        has_update = False
        reason = "integrity_conflict"
        message = "同版本对应了不同提交，已拒绝不具备单调版本号的更新。"
    elif not updater_ok:
        reason = "updater_too_old"
        message = "当前稳定启动器过旧，请使用新版 Setup 升级。"
    else:
        reason = "newer_version"
        message = "发现新的已签名版本，可以开始更新。"
    return {
        "local_version": local_version,
        "local_revision": local_revision,
        "has_update": has_update,
        "can_update": has_update and updater_ok,
        "update_reason": reason,
        "message": message,
        "installed_runtime": True,
        "minimum_launcher_version": manifest.min_updater_version,
    }


def _check_payload(root: Path, manifest: ReleaseManifestV3) -> dict[str, object]:
    evaluation = _evaluate_update(root, manifest)
    asset = _runtime_asset(manifest)
    return {
        "status": "ok",
        "version": evaluation["local_version"],
        "revision": evaluation["local_revision"],
        "remote_version": manifest.version,
        "remote_revision": manifest.revision.lower(),
        "display_remote": manifest.version,
        "has_update": evaluation["has_update"],
        "can_update": evaluation["can_update"],
        "installed_runtime": True,
        "minimum_launcher_version": manifest.min_updater_version,
        "update_reason": evaluation["update_reason"],
        "remote_status": "ok",
        "remote_revision_status": "ok",
        "notice_status": "ok",
        "update_notice": {
            "version": manifest.version,
            "revision": manifest.revision.lower(),
            "date": manifest.published_at.isoformat(),
            "title": f"Insta360 硬件提效平台 {manifest.version}",
            "summary": manifest.changelog[0] if manifest.changelog else "已签名正式版本",
            "highlights": list(manifest.changelog),
            "trace": {"source": "signed_release_manifest_v3"},
        },
        "expected_sha256": asset.sha256.lower(),
        "integrity_verified": True,
        "integrity_status": "manifest_signature_verified",
        "download_strategy": "release_runtime_zip",
        "message": evaluation["message"],
        "error": "",
    }


def _manifest_failure_payload(
    runtime: Path,
    *,
    remote_status: str,
    update_reason: str,
    integrity_status: str,
    message: str,
    error: str = "",
) -> dict[str, object]:
    return {
        "status": "ok" if remote_status == "not_published" else "error",
        "version": _read_runtime_text(runtime, "VERSION") or "0.0.0",
        "revision": _read_runtime_text(runtime, "REVISION"),
        "remote_version": "",
        "remote_revision": "",
        "display_remote": "",
        "has_update": False,
        "can_update": False,
        "installed_runtime": _candidate_install_root(runtime) is not None,
        "minimum_launcher_version": "",
        "update_reason": update_reason,
        "remote_status": remote_status,
        "remote_revision_status": remote_status,
        "notice_status": remote_status,
        "update_notice": {},
        "expected_sha256": "",
        "integrity_verified": False,
        "integrity_status": integrity_status,
        "download_strategy": "none",
        "message": message,
        "error": error,
    }


def check_update(root: Path) -> dict[str, object]:
    runtime = Path(root).resolve()
    try:
        manifest, _ = _fetch_manifest(runtime)
        return _check_payload(runtime, manifest)
    except HTTPError as exc:
        if exc.code == 404:
            return _manifest_failure_payload(
                runtime,
                remote_status="not_published",
                update_reason="manifest_not_published",
                integrity_status="manifest_not_published",
                message="当前仓库尚未发布与此客户端兼容的更新清单。",
            )
        return _manifest_failure_payload(
            runtime,
            remote_status="error",
            update_reason="manifest_unavailable",
            integrity_status="manifest_invalid",
            message="无法读取或验证已签名更新清单。",
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        return _manifest_failure_payload(
            runtime,
            remote_status="error",
            update_reason="manifest_unavailable",
            integrity_status="manifest_invalid",
            message="无法读取或验证已签名更新清单。",
            error=str(exc),
        )


def _prune_cache(paths: AppPaths) -> None:
    cutoff = time.time() - 7 * 24 * 60 * 60
    if not paths.lifecycle_v3_cache_dir.is_dir():
        return
    for path in paths.lifecycle_v3_cache_dir.iterdir():
        try:
            if path.is_file() and path.name != "remote-manifest-v3.json" and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def run_update(root: Path) -> dict[str, object]:
    runtime = Path(root).resolve()
    with _START_LOCK:
        current = update_status(runtime)
        if current.get("running"):
            return {"status": "error", "error": "已有更新任务正在运行", "job_id": current.get("job_id", "")}
        if current.get("recovery_required"):
            return {"status": "error", "error": "上一次更新仍需恢复，不能启动新的更新", "job_id": current.get("job_id", "")}
        try:
            manifest, _ = _fetch_manifest(runtime)
            evaluation = _evaluate_update(runtime, manifest)
            if not evaluation["can_update"]:
                return {"status": "error", "error": str(evaluation["message"])}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "error": f"无法启动可信更新：{exc}"}

        paths = AppPaths(runtime)
        paths.ensure_runtime_dirs()
        _prune_cache(paths)
        job_id = uuid.uuid4().hex
        cancel = threading.Event()
        _write_job(
            runtime, job_id, phase="queued", progress=0, message="更新任务已创建。",
            version=manifest.version, revision=manifest.revision.lower(), cancellable=True,
        )
        thread = threading.Thread(
            target=_prepare_update,
            args=(runtime, job_id, manifest),
            daemon=True,
            name=f"hw-v3-update-{job_id[:8]}",
        )
        with _ACTIVE_LOCK:
            _ACTIVE_THREADS[job_id] = thread
            _CANCEL_EVENTS[job_id] = cancel
        thread.start()
        return {
            "status": "ok", "job_id": job_id, "message": "已开始下载并验证更新。",
            "version": manifest.version,
        }


def cancel_update(root: Path, job_id: str = "") -> dict[str, object]:
    runtime = Path(root).resolve()
    target = job_id or _latest_job_id(runtime)
    if not target:
        return {"status": "error", "error": "没有可取消的更新任务"}
    if not _valid_job_id(target):
        return {"status": "error", "error": "更新任务编号无效"}
    job = _read_job(runtime, target)
    if not job:
        return {"status": "error", "error": "更新任务不存在"}
    phase = str(job.get("phase") or "")
    if phase in _TERMINAL_PHASES:
        return {"status": "error", "error": "更新任务已经结束"}
    if phase not in _PRECOMMIT_PHASES or not job.get("cancellable"):
        return {"status": "error", "error": "更新已进入提交阶段，不能取消"}
    with _ACTIVE_LOCK:
        event = _CANCEL_EVENTS.get(target)
        if event is None:
            return {"status": "error", "error": "更新准备进程已中断，无法发送取消请求"}
        event.set()
    return {"status": "ok", "job_id": target, "message": "正在取消更新"}


def _cleanup_terminal_artifacts(root: Path, job: dict[str, object]) -> None:
    paths = AppPaths(root)
    archive_value = job.get("archive_path")
    if isinstance(archive_value, str) and archive_value:
        try:
            archive = Path(archive_value).resolve()
            archive.relative_to(paths.lifecycle_v3_cache_dir.resolve())
            archive.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
    job_id = str(job.get("job_id") or "")
    if not _valid_job_id(job_id):
        return
    transaction = (paths.lifecycle_v3_transactions_dir / job_id).resolve()
    try:
        transaction.relative_to(paths.lifecycle_v3_transactions_dir.resolve())
    except ValueError:
        return
    for child_name in ("stage", "extracted"):
        child = transaction / child_name
        try:
            if child.is_dir():
                shutil.rmtree(child)
        except OSError:
            pass
    try:
        _worker_handoff_path(root, job_id).unlink(missing_ok=True)
    except OSError:
        pass


def update_status(root: Path) -> dict[str, object]:
    runtime = Path(root).resolve()
    job_id = _latest_job_id(runtime)
    if not job_id:
        return {
            "status": "ok", "job_id": "", "running": False, "done": False,
            "failed": False, "phase": "idle", "progress": 0,
            "message": "暂无更新任务。", "step": "idle", "log_tail": [],
        }
    job = _read_job(runtime, job_id) or {}
    phase = str(job.get("phase") or "queued")
    if phase in _PRECOMMIT_PHASES:
        with _ACTIVE_LOCK:
            thread = _ACTIVE_THREADS.get(job_id)
        if thread is None or not thread.is_alive():
            job = _write_job(
                runtime,
                job_id,
                phase="failed",
                progress=100,
                message="更新准备进程意外中断，尚未修改当前安装。",
                error="pre-commit update process was interrupted",
                interrupted=True,
                rolled_back=True,
                recovery_required=False,
                cancellable=False,
            )
            _cleanup_precommit(
                AppPaths(runtime).lifecycle_v3_transactions_dir / job_id,
                AppPaths(runtime).lifecycle_v3_cache_dir / f"{job.get('version', '')}-{job_id}.zip",
            )
            phase = "failed"
    elif phase in _WORKER_PHASES:
        handoff = _read_worker_handoff(runtime, job_id)
        with _ACTIVE_LOCK:
            in_memory_pid = _ACTIVE_WORKER_PIDS.get(job_id)
        worker_pid = (handoff or {}).get("worker_pid") or job.get("worker_pid") or in_memory_pid
        if isinstance(worker_pid, int) and worker_pid > 0 and not _process_alive(worker_pid):
            before_worker_ack = phase == "awaiting_elevation"
            try:
                pointer_unchanged = resolve_installation(runtime).active_runtime == runtime
            except ValueError:
                pointer_unchanged = False
            safe_without_recovery = before_worker_ack or pointer_unchanged
            job = _write_job(
                runtime,
                job_id,
                phase="failed",
                progress=100,
                message=(
                    "更新 Worker 在接管安装前退出，当前安装未修改。"
                    if safe_without_recovery
                    else "更新 Worker 意外退出，需要先恢复上一次事务。"
                ),
                error="lifecycle worker exited unexpectedly",
                interrupted=True,
                rolled_back=safe_without_recovery,
                recovery_required=not safe_without_recovery,
                cancellable=False,
            )
            if safe_without_recovery:
                archive = Path(str(job.get("archive_path") or ""))
                _cleanup_precommit(AppPaths(runtime).lifecycle_v3_transactions_dir / job_id, archive)
            phase = "failed"
    if phase in _TERMINAL_PHASES and not job.get("recovery_required"):
        _cleanup_terminal_artifacts(runtime, job)
        with _ACTIVE_LOCK:
            _ACTIVE_WORKER_PIDS.pop(job_id, None)
    job.setdefault("status", "ok")
    job.setdefault("step", phase)
    job.setdefault("log_tail", [])
    return job


__all__ = [
    "InstallationLayout",
    "canonical_manifest_payload",
    "verify_signed_manifest",
    "resolve_installation",
    "is_versioned_install",
    "check_update",
    "run_update",
    "cancel_update",
    "update_status",
]
