from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.backend.config import load_config
from app.backend.paths import AppPaths
from app.backend.release_manifest import (
    DEFAULT_MANIFEST_URL,
    PRODUCT,
    ReleaseManifest,
    compare_versions,
)


MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARCHIVE_ENTRIES = 50_000
MAX_UNCOMPRESSED_BYTES = 3 * 1024 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_RELEASE_MANIFEST_URL_RE = re.compile(
    r"/releases/download/v(?P<version>[^/]+)/update-manifest\.json(?:$|[?#])",
    re.IGNORECASE,
)
_TERMINAL_PHASES = {"completed", "failed", "cancelled"}
_PREPARER_PHASES = {"queued", "downloading", "verifying", "staging"}
_WORKER_PHASES = {"awaiting_elevation", "committing", "switching", "integrating", "verifying_runtime"}
_REQUIRED_RUNTIME_FILES = (
    "Insta360_HW.exe",
    "VERSION",
    "REVISION",
    "install_manifest.json",
    "launch_tool_suite.ps1",
    "app/backend/suite_app.py",
    "app/frontend/index.html",
    "scripts/lifecycle/Worker.ps1",
    "scripts/lifecycle/Recover.ps1",
    "scripts/lib/Paths.ps1",
    "runtime/python/python.exe",
)

_ACTIVE_LOCK = threading.Lock()
_JOB_LOCK = threading.Lock()
_START_LOCK = threading.Lock()
_ACTIVE_THREADS: dict[str, threading.Thread] = {}
_CANCEL_EVENTS: dict[str, threading.Event] = {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def _manifest_url(root: Path) -> str:
    try:
        configured = str(load_config(root).get("update", {}).get("manifest_url") or "").strip()
    except (OSError, ValueError, json.JSONDecodeError):
        configured = ""
    return configured or os.environ.get("INSTA360_HW_MANIFEST_URL", "").strip() or DEFAULT_MANIFEST_URL


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for attempt in range(8):
            try:
                temp.replace(path)
                break
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.025 * (attempt + 1))
    finally:
        temp.unlink(missing_ok=True)


def _valid_job_id(job_id: str) -> bool:
    return bool(_JOB_ID_RE.fullmatch(job_id))


def _job_path(root: Path, job_id: str) -> Path:
    if not _valid_job_id(job_id):
        raise ValueError("更新任务编号无效")
    return AppPaths(root).lifecycle_jobs_dir / f"{job_id}.json"


def _latest_path(root: Path) -> Path:
    return AppPaths(root).lifecycle_jobs_dir / "latest.json"


def _write_job(root: Path, job_id: str, **updates: object) -> dict[str, object]:
    path = _job_path(root, job_id)
    with _JOB_LOCK:
        try:
            current = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            current = {}
        if not isinstance(current, dict):
            current = {}
        current.update(
            {
                "schema": 2,
                "job_id": job_id,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **updates,
            }
        )
        phase = str(current.get("phase") or "queued")
        current["running"] = phase not in _TERMINAL_PHASES
        current["done"] = phase == "completed"
        current["failed"] = phase == "failed"
        _atomic_json(path, current)
        _atomic_json(_latest_path(root), {"job_id": job_id})
        return current


def _read_job(root: Path, job_id: str) -> dict[str, object] | None:
    try:
        value = json.loads(_job_path(root, job_id).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _latest_job_id(root: Path) -> str:
    try:
        value = json.loads(_latest_path(root).read_text(encoding="utf-8-sig"))
        job_id = str(value.get("job_id") or "")
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""
    return job_id if _valid_job_id(job_id) else ""


def _fetch_manifest(root: Path) -> tuple[ReleaseManifest, dict[str, object]]:
    url = _manifest_url(root)
    request = Request(url, headers={"User-Agent": "Insta360-HWAgent-Lifecycle/2", "Accept": "application/json"})
    with urlopen(request, timeout=6.0) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_MANIFEST_BYTES:
            raise ValueError("update manifest exceeds the 1 MiB limit")
        data = response.read(MAX_MANIFEST_BYTES + 1)
    if len(data) > MAX_MANIFEST_BYTES:
        raise ValueError("update manifest exceeds the 1 MiB limit")
    raw = json.loads(data.decode("utf-8-sig"))
    manifest = ReleaseManifest.parse(raw)
    _atomic_json(AppPaths(root).lifecycle_cache_dir / "remote-manifest.json", raw)
    return manifest, raw


def _installed_runtime_status(root: Path, local_version: str) -> tuple[bool, str]:
    try:
        raw = json.loads((root / "install_manifest.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False, "当前目录不是由 Setup 安装的运行环境"
    if not isinstance(raw, dict):
        return False, "本地安装清单格式无效"
    if raw.get("schema") != 2 or raw.get("product") != PRODUCT or raw.get("layout") != "runtime-v2":
        return False, "本地安装清单不属于 Lifecycle V2"
    if str(raw.get("version") or "") != local_version:
        return False, "本地安装清单与 VERSION 不一致"
    return True, ""


def _evaluate_update(root: Path, manifest: ReleaseManifest) -> dict[str, object]:
    local_version = _read_text(root / "VERSION") or "0.0.0"
    comparison = compare_versions(manifest.version, local_version)
    has_update = comparison > 0
    installed, install_error = _installed_runtime_status(root, local_version)
    launcher_ok = compare_versions(local_version, manifest.minimum_launcher_version) >= 0

    if comparison < 0:
        reason = "remote_older"
        message = "远端版本低于当前版本，未执行更新。"
    elif comparison == 0:
        reason = "up_to_date"
        message = "当前已是最新版本。"
    elif not installed:
        reason = "development_mode"
        message = f"{install_error}，应用内更新已禁用，请使用 Setup 安装包。"
    elif not launcher_ok:
        reason = "launcher_too_old"
        message = "当前启动器版本过旧，请使用最新 Setup 安装包升级。"
    else:
        reason = "newer_version"
        message = "发现新版本，可以开始更新。"

    return {
        "local_version": local_version,
        "has_update": has_update,
        "can_update": has_update and installed and launcher_ok,
        "update_reason": reason,
        "message": message,
        "installed_runtime": installed,
        "minimum_launcher_version": manifest.minimum_launcher_version,
    }


def _release_version_from_missing_manifest(exc: HTTPError) -> str:
    url = str(getattr(exc, "filename", "") or "")
    if not url:
        try:
            url = str(exc.geturl() or "")
        except (AttributeError, KeyError):
            url = ""
    match = _RELEASE_MANIFEST_URL_RE.search(url)
    if not match:
        return ""
    version = match.group("version")
    try:
        compare_versions(version, version)
    except ValueError:
        return ""
    return version


def _manifest_not_published_result(root: Path, exc: HTTPError) -> dict[str, object]:
    local_version = _read_text(root / "VERSION") or "0.0.0"
    local_revision = _read_text(root / "REVISION")
    remote_version = _release_version_from_missing_manifest(exc)
    installed, _ = _installed_runtime_status(root, local_version)

    if remote_version:
        comparison = compare_versions(remote_version, local_version)
        if comparison < 0:
            message = (
                f"当前版本 {local_version} 高于仓库已发布版本 {remote_version}。"
                "正式更新清单尚未发布，请等待下一次 Release。"
            )
        elif comparison == 0:
            message = f"版本 {remote_version} 尚未提供可信更新包，请稍后重试。"
        else:
            message = f"仓库版本 {remote_version} 尚未提供可信更新包，请等待维护人员补充 Release 资产。"
    else:
        message = "仓库最新 Release 尚未提供可信更新包，请稍后重试。"

    return {
        "status": "ok",
        "version": local_version,
        "revision": local_revision,
        "remote_version": remote_version,
        "remote_revision": "",
        "display_remote": remote_version,
        "has_update": False,
        "can_update": False,
        "update_reason": "manifest_not_published",
        "remote_status": "not_published",
        "remote_revision_status": "not_published",
        "notice_status": "not_published",
        "update_notice": {},
        "expected_sha256": "",
        "integrity_verified": False,
        "integrity_status": "manifest_not_published",
        "download_strategy": "none",
        "minimum_launcher_version": "",
        "installed_runtime": installed,
        "message": message,
        "error": "",
    }


def check_update(root: Path) -> dict[str, object]:
    local_version = _read_text(root / "VERSION") or "0.0.0"
    local_revision = _read_text(root / "REVISION")
    try:
        manifest, _ = _fetch_manifest(root)
        evaluation = _evaluate_update(root, manifest)
        return {
            "status": "ok",
            "version": local_version,
            "revision": local_revision,
            "remote_version": manifest.version,
            "remote_revision": manifest.revision,
            "display_remote": manifest.version,
            "has_update": evaluation["has_update"],
            "can_update": evaluation["can_update"],
            "update_reason": evaluation["update_reason"],
            "remote_status": "ok",
            "remote_revision_status": "ok",
            "notice_status": "ok",
            "update_notice": manifest.update_notice(),
            "expected_sha256": manifest.runtime.sha256,
            "integrity_verified": True,
            "integrity_status": "manifest_sha256_required",
            "download_strategy": "release_runtime_zip",
            "minimum_launcher_version": manifest.minimum_launcher_version,
            "installed_runtime": evaluation["installed_runtime"],
            "message": evaluation["message"],
        }
    except HTTPError as exc:
        if exc.code == 404 and _release_version_from_missing_manifest(exc):
            return _manifest_not_published_result(root, exc)
        return {
            "status": "error",
            "version": local_version,
            "revision": local_revision,
            "remote_version": "",
            "remote_revision": "",
            "display_remote": "",
            "has_update": False,
            "can_update": False,
            "update_reason": "manifest_unavailable",
            "remote_status": "error",
            "remote_revision_status": "error",
            "notice_status": "error",
            "integrity_verified": False,
            "integrity_status": "manifest_invalid",
            "download_strategy": "none",
            "message": f"无法读取可信更新清单：HTTP {exc.code}",
            "error": f"HTTP {exc.code}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "version": local_version,
            "revision": local_revision,
            "remote_version": "",
            "remote_revision": "",
            "display_remote": "",
            "has_update": False,
            "can_update": False,
            "update_reason": "manifest_unavailable",
            "remote_status": "error",
            "remote_revision_status": "error",
            "notice_status": "error",
            "integrity_verified": False,
            "integrity_status": "manifest_invalid",
            "download_strategy": "none",
            "message": f"无法读取可信更新清单：{exc}",
            "error": str(exc),
        }


def _safe_extract(archive: Path, destination: Path, cancel: threading.Event | None = None) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise ValueError("runtime archive contains too many entries")
        if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("runtime archive expands beyond the 3 GiB limit")

        targets: set[str] = set()
        planned: list[tuple[zipfile.ZipInfo, Path]] = []
        for info in infos:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("update cancelled before commit")
            unix_mode = info.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise ValueError(f"runtime archive contains a symbolic link: {info.filename}")
            target = (destination / info.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"runtime archive path escapes staging root: {info.filename}") from exc
            key = str(target).casefold()
            if key in targets:
                raise ValueError(f"runtime archive contains a duplicate path: {info.filename}")
            targets.add(key)
            planned.append((info, target))

        for info, target in planned:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("update cancelled before commit")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("wb") as output:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError("update cancelled before commit")
                    chunk = source.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)


def _payload_root(extracted: Path) -> Path:
    def identifiable(path: Path) -> bool:
        return all(
            (path / relative).is_file()
            for relative in ("Insta360_HW.exe", "VERSION", "install_manifest.json", "app/backend/suite_app.py")
        )

    if identifiable(extracted):
        return extracted
    children = [item for item in extracted.iterdir() if item.is_dir()]
    matches = [item for item in children if identifiable(item)]
    if len(matches) != 1:
        raise ValueError("runtime ZIP does not contain one complete HWAgent payload")
    return matches[0]


def _validate_payload(path: Path, manifest: ReleaseManifest) -> None:
    for relative in _REQUIRED_RUNTIME_FILES:
        if not (path / relative).is_file():
            raise ValueError(f"runtime payload is incomplete; missing {relative}")

    version = _read_text(path / "VERSION")
    if version != manifest.version:
        raise ValueError(f"payload VERSION mismatch: expected {manifest.version}, got {version or '<empty>'}")
    revision = _read_text(path / "REVISION").lower()
    if revision != manifest.revision:
        raise ValueError("payload REVISION does not match the release manifest")
    try:
        install_manifest = json.loads((path / "install_manifest.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("payload install_manifest.json is invalid") from exc
    if not isinstance(install_manifest, dict):
        raise ValueError("payload install_manifest.json must be an object")
    if install_manifest.get("schema") != 2:
        raise ValueError("payload install manifest schema must be 2")
    if install_manifest.get("product") != PRODUCT:
        raise ValueError("payload install manifest product is invalid")
    if install_manifest.get("layout") != "runtime-v2":
        raise ValueError("payload install manifest layout must be runtime-v2")
    if str(install_manifest.get("version")) != manifest.version:
        raise ValueError("payload install manifest version does not match the release manifest")
    if str(install_manifest.get("revision") or "").lower() != manifest.revision:
        raise ValueError("payload install manifest revision does not match the release manifest")


def _runtime_tree_sha256(root: Path) -> str:
    records: list[str] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"runtime payload contains a symbolic link: {path}")
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK_SIZE):
                digest.update(chunk)
        relative = path.relative_to(root).as_posix()
        records.append(f"{relative}\t{path.stat().st_size}\t{digest.hexdigest()}\n")
    payload = "".join(sorted(records)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _windows_argument_line(arguments: list[str]) -> str:
    return subprocess.list2cmdline(arguments)


class _ShellExecuteInfoW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _launch_elevated_process(executable: str, arguments: list[str], working_directory: Path) -> int:
    if os.name != "nt":
        raise RuntimeError("提权更新仅支持 Windows")

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfoW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    info = _ShellExecuteInfoW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = _windows_argument_line(arguments)
    info.lpDirectory = str(working_directory)
    info.nShow = 0  # SW_HIDE applies to the worker, not the UAC consent UI.

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == 1223:
            raise RuntimeError("用户取消了更新所需的系统授权")
        raise OSError(error, "无法启动提权更新进程")
    if not info.hProcess:
        raise RuntimeError("系统授权成功，但未返回更新工作进程")
    try:
        process_id = int(kernel32.GetProcessId(info.hProcess))
        if process_id <= 0:
            raise OSError(ctypes.get_last_error(), "无法读取更新工作进程编号")
        return process_id
    finally:
        kernel32.CloseHandle(info.hProcess)


def _launch_worker(
    root: Path,
    worker: Path,
    state_root: Path,
    job_id: str,
    stage: Path,
    version: str,
    tree_sha256: str,
) -> int:
    arguments = [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(worker),
        "-InstallRoot",
        str(root),
        "-StateRoot",
        str(state_root),
        "-JobId",
        job_id,
        "-StageRoot",
        str(stage),
        "-ExpectedVersion",
        version,
        "-ExpectedTreeSha256",
        tree_sha256,
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if os.environ.get("INSTA360_HW_NO_ELEVATION") == "1" or _is_admin():
        process = subprocess.Popen(
            ["powershell.exe", *arguments],
            cwd=str(worker.parent),
            creationflags=creationflags,
        )
        return process.pid

    return _launch_elevated_process("powershell.exe", arguments, worker.parent)


def _cleanup_precommit(transaction: Path, download: Path) -> None:
    try:
        download.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        if transaction.exists():
            shutil.rmtree(transaction)
    except OSError:
        pass


def _prepare_update(root: Path, job_id: str, manifest: ReleaseManifest) -> None:
    paths = AppPaths(root)
    cancel = _CANCEL_EVENTS[job_id]
    transaction = paths.lifecycle_transactions_dir / job_id
    download = paths.lifecycle_cache_dir / f"{manifest.version}-{job_id}.zip"
    extract_root = transaction / "extracted"
    handed_off = False
    try:
        transaction.mkdir(parents=True, exist_ok=True)
        paths.lifecycle_cache_dir.mkdir(parents=True, exist_ok=True)
        _write_job(
            root,
            job_id,
            phase="downloading",
            progress=2,
            message="正在下载完整运行包。",
            version=manifest.version,
            bytes_total=manifest.runtime.size_bytes,
            bytes_downloaded=0,
            cancellable=True,
        )
        request = Request(manifest.runtime.url, headers={"User-Agent": "Insta360-HWAgent-Lifecycle/2"})
        digest = hashlib.sha256()
        downloaded = 0
        started = time.monotonic()
        last_report = 0.0
        with urlopen(request, timeout=30.0) as response, download.open("wb") as handle:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) != manifest.runtime.size_bytes:
                raise ValueError("download Content-Length does not match the trusted manifest")
            while True:
                if cancel.is_set():
                    raise InterruptedError("更新已在提交前取消")
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if downloaded > manifest.runtime.size_bytes:
                    raise ValueError("download exceeds the size declared by the trusted manifest")
                now = time.monotonic()
                if now - last_report >= 0.2:
                    elapsed = max(now - started, 0.001)
                    ratio = min(downloaded / manifest.runtime.size_bytes, 1.0)
                    _write_job(
                        root,
                        job_id,
                        phase="downloading",
                        progress=2 + int(ratio * 53),
                        message="正在下载完整运行包。",
                        bytes_total=manifest.runtime.size_bytes,
                        bytes_downloaded=downloaded,
                        bytes_per_second=int(downloaded / elapsed),
                        cancellable=True,
                    )
                    last_report = now
        if downloaded != manifest.runtime.size_bytes:
            raise ValueError(f"download size mismatch: expected {manifest.runtime.size_bytes}, got {downloaded}")
        if cancel.is_set():
            raise InterruptedError("更新已在提交前取消")

        _write_job(root, job_id, phase="verifying", progress=58, message="正在校验运行包 SHA256。", cancellable=True)
        if digest.hexdigest().lower() != manifest.runtime.sha256:
            raise ValueError("downloaded runtime SHA256 does not match the trusted manifest")
        if cancel.is_set():
            raise InterruptedError("更新已在提交前取消")

        _write_job(root, job_id, phase="staging", progress=62, message="正在展开并验证完整候选版本。", cancellable=True)
        if extract_root.exists():
            shutil.rmtree(extract_root)
        _safe_extract(download, extract_root, cancel)
        payload = _payload_root(extract_root)
        _validate_payload(payload, manifest)
        tree_sha256 = _runtime_tree_sha256(payload)
        if cancel.is_set():
            raise InterruptedError("更新已在提交前取消")

        worker = root / "scripts" / "lifecycle" / "Worker.ps1"
        if not worker.is_file():
            raise ValueError("trusted lifecycle worker is missing from the installed runtime")
        _write_job(
            root,
            job_id,
            phase="awaiting_elevation",
            progress=68,
            message="候选版本已验证，正在请求系统授权完成切换。",
            cancellable=False,
            stage_root=str(payload),
        )
        worker_pid = _launch_worker(
            root,
            worker,
            paths.state_root,
            job_id,
            payload,
            manifest.version,
            tree_sha256,
        )
        worker_creation_time = _process_creation_token(worker_pid)
        handed_off = True
        _write_job(
            root,
            job_id,
            worker_pid=worker_pid,
            worker_creation_time=worker_creation_time,
        )
    except InterruptedError as exc:
        _write_job(root, job_id, phase="cancelled", progress=100, message=str(exc), cancellable=False)
    except Exception as exc:  # noqa: BLE001
        _write_job(
            root,
            job_id,
            phase="failed",
            progress=100,
            message=f"更新准备失败：{exc}",
            error=str(exc),
            cancellable=False,
        )
    finally:
        if not handed_off:
            _cleanup_precommit(transaction, download)
        with _ACTIVE_LOCK:
            _ACTIVE_THREADS.pop(job_id, None)
            _CANCEL_EVENTS.pop(job_id, None)


def _process_alive(pid: object) -> bool:
    try:
        process_id = int(pid)
    except (TypeError, ValueError):
        return False
    if process_id <= 0:
        return False
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(process_id, 0)
        return True
    except OSError:
        return False


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


def _process_creation_token(pid: object) -> int:
    try:
        process_id = int(pid)
    except (TypeError, ValueError):
        return 0
    if process_id <= 0 or os.name != "nt":
        return 0

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, process_id)
    if not handle:
        return 0
    try:
        created, exited, kernel, user = _FileTime(), _FileTime(), _FileTime(), _FileTime()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return 0
        return (int(created.high) << 32) | int(created.low)
    finally:
        kernel32.CloseHandle(handle)


def _worker_process_alive(job: dict[str, object]) -> bool:
    pid = job.get("worker_pid")
    if not _process_alive(pid):
        return False
    try:
        expected = int(job.get("worker_creation_time") or 0)
    except (TypeError, ValueError):
        expected = 0
    if expected <= 0:
        return True
    return _process_creation_token(pid) == expected


def _normalize_running_job(root: Path, job: dict[str, object]) -> dict[str, object]:
    if not job.get("running"):
        return job
    job_id = str(job.get("job_id") or "")
    phase = str(job.get("phase") or "")
    with _ACTIVE_LOCK:
        thread = _ACTIVE_THREADS.get(job_id)
        preparer_alive = bool(thread and thread.is_alive())

    if phase in _PREPARER_PHASES and not preparer_alive:
        return _write_job(
            root,
            job_id,
            phase="failed",
            progress=100,
            message="更新在提交前被中断，未修改已安装版本，可以重新检查并更新。",
            error="precommit_update_interrupted",
            interrupted=True,
            cancellable=False,
        )
    if phase in _WORKER_PHASES and not preparer_alive and not _worker_process_alive(job):
        return _write_job(
            root,
            job_id,
            phase="failed",
            progress=100,
            message="更新工作进程已中断；重新打开平台时会先尝试恢复或回滚。",
            error="update_worker_interrupted",
            interrupted=True,
            recovery_required=True,
            cancellable=False,
        )
    return job


def _prune_lifecycle_cache(paths: AppPaths) -> None:
    cutoff = time.time() - 7 * 24 * 60 * 60
    try:
        for archive in paths.lifecycle_cache_dir.glob("*.zip"):
            if archive.stat().st_mtime < cutoff:
                archive.unlink(missing_ok=True)
    except OSError:
        pass


def _cleanup_terminal_transaction(root: Path, job: dict[str, object]) -> None:
    phase = str(job.get("phase") or "")
    job_id = str(job.get("job_id") or "")
    if phase not in _TERMINAL_PHASES or not _valid_job_id(job_id):
        return
    if bool(job.get("recovery_required")) and not bool(job.get("rolled_back")):
        return
    if bool(job.get("cleanup_pending")):
        return
    if _worker_process_alive(job):
        return

    paths = AppPaths(root)
    transaction_root = paths.lifecycle_transactions_dir.resolve()
    transaction = (transaction_root / job_id).resolve()
    try:
        transaction.relative_to(transaction_root)
    except ValueError:
        return
    try:
        if transaction.is_dir():
            shutil.rmtree(transaction)
    except OSError:
        return
    try:
        for archive in paths.lifecycle_cache_dir.glob(f"*-{job_id}.zip"):
            archive.unlink(missing_ok=True)
    except OSError:
        pass


def run_update(root: Path) -> dict[str, object]:
    with _START_LOCK:
        return _run_update_locked(root)


def _run_update_locked(root: Path) -> dict[str, object]:
    current = update_status(root)
    if current.get("running"):
        return {"status": "error", "error": "已有更新任务正在运行", "job_id": current.get("job_id", "")}
    try:
        manifest, _ = _fetch_manifest(root)
        evaluation = _evaluate_update(root, manifest)
        if not evaluation["can_update"]:
            return {"status": "error", "error": str(evaluation["message"])}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": f"无法启动可信更新：{exc}"}

    paths = AppPaths(root)
    paths.ensure_runtime_dirs()
    _prune_lifecycle_cache(paths)
    job_id = uuid.uuid4().hex
    cancel = threading.Event()
    _write_job(
        root,
        job_id,
        phase="queued",
        progress=0,
        message="更新任务已创建。",
        version=manifest.version,
        cancellable=True,
    )
    thread = threading.Thread(
        target=_prepare_update,
        args=(root, job_id, manifest),
        daemon=True,
        name=f"hw-update-{job_id[:8]}",
    )
    with _ACTIVE_LOCK:
        _ACTIVE_THREADS[job_id] = thread
        _CANCEL_EVENTS[job_id] = cancel
    thread.start()
    return {"status": "ok", "job_id": job_id, "message": "更新下载已开始。", "version": manifest.version}


def cancel_update(root: Path, job_id: str = "") -> dict[str, object]:
    target = job_id or _latest_job_id(root)
    if not target:
        return {"status": "error", "error": "没有可取消的更新任务"}
    if not _valid_job_id(target):
        return {"status": "error", "error": "更新任务编号无效"}
    job = _read_job(root, target)
    if not job:
        return {"status": "error", "error": "更新任务不存在"}
    job = _normalize_running_job(root, job)
    if not job.get("running"):
        return {"status": "error", "error": "更新任务已经结束"}
    if not job.get("cancellable"):
        return {"status": "error", "error": "更新已进入提交阶段，不能取消"}
    with _ACTIVE_LOCK:
        event = _CANCEL_EVENTS.get(target)
    if event is None:
        return {"status": "error", "error": "更新准备线程已经退出，无法发送取消请求"}
    event.set()
    return {"status": "ok", "job_id": target, "message": "正在取消更新"}


def update_status(root: Path) -> dict[str, object]:
    job_id = _latest_job_id(root)
    if not job_id:
        return {
            "status": "ok",
            "job_id": "",
            "running": False,
            "done": False,
            "failed": False,
            "phase": "idle",
            "progress": 0,
            "message": "暂无更新任务。",
            "step": "idle",
            "log_tail": [],
        }
    job = _read_job(root, job_id) or {}
    if job:
        job = _normalize_running_job(root, job)
        _cleanup_terminal_transaction(root, job)
    job.setdefault("status", "ok")
    job.setdefault("step", str(job.get("phase") or "idle"))
    job.setdefault("log_tail", [])
    return job
