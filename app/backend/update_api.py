from __future__ import annotations

import json
import os
import platform
import re
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from app.backend import lifecycle_update, lifecycle_v3
from app.backend.paths import AppPaths
from app.backend.windows_process import system_powershell


LIFECYCLE_JOB_PHASES = (
    "idle",
    "checking",
    "queued",
    "downloading",
    "verifying",
    "staging",
    "awaiting_elevation",
    "committing",
    "switching",
    "integrating",
    "verifying_runtime",
    "completed",
    "failed",
    "cancelled",
)
_TERMINAL_PHASES = {"completed", "failed", "cancelled"}
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_UPDATE_MESSAGE_TRANSLATIONS = {
    "Update task created.": "更新任务已创建。",
    "Verifying staged runtime files.": "正在复核候选版本文件。",
    "Copying the candidate runtime into the installation.": "正在复制候选版本到安装目录。",
    "Verifying copied runtime files.": "正在校验复制后的完整版本。",
    "Existing runtime found; verifying identical content.": "检测到同版本目录，正在确认内容一致。",
    "Candidate runtime files copied and verified.": "新版本文件已复制并通过完整性校验。",
    "Preparing rollback protection and checking Cadence integration.": "正在建立回滚保护并检查 Cadence 集成状态。",
    "Rollback protection is ready; stopping the previous backend.": "回滚保护已就绪，正在停止旧版后台服务。",
    "Activating the verified runtime pointer.": "正在原子切换到已验证的新版本。",
    "Deploying Cadence integration from the active runtime.": "正在从新版本部署 Cadence 集成。",
    "Starting and verifying the activated backend.": "正在启动并验证新版本后台服务。",
    "Update completed and the new runtime passed verification.": "更新完成，新版本已通过启动验证。",
    "Update completed; deferred cleanup will be retried later.": "更新已完成；旧版本清理将在后续自动重试。",
}
_UPDATE_MESSAGE_PREFIX_TRANSLATIONS = {
    "Update failed and the previous runtime was restored: ": "更新失败，已恢复到更新前版本：",
    "Update failed and rollback also failed: ": "更新失败且自动回滚失败：",
}


def _update_backend(root: Path):
    runtime = root.resolve()
    return lifecycle_v3 if lifecycle_v3.is_versioned_install(runtime) else lifecycle_update


def read_version(root: Path) -> str:
    try:
        return (root / "VERSION").read_text(encoding="utf-8-sig").strip()
    except OSError:
        return "0.0.0"


def read_revision(root: Path) -> str:
    try:
        return (root / "REVISION").read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def version_payload(root: Path) -> dict[str, object]:
    revision = read_revision(root)
    return {
        "status": "ok",
        "version": read_version(root),
        "revision": revision,
        "short_revision": revision[:12],
    }


def _find_cadence_autoload_dirs() -> list[Path]:
    candidates: list[Path] = []
    home_profile = ""
    if os.environ.get("HOMEDRIVE") and os.environ.get("HOMEPATH"):
        home_profile = os.environ["HOMEDRIVE"] + os.environ["HOMEPATH"]
    for base in (
        os.environ.get("SPB_DATA"),
        os.environ.get("CDS_DATA"),
        os.environ.get("HOME"),
        home_profile,
        os.environ.get("USERPROFILE"),
    ):
        if not base:
            continue
        path = Path(base) / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
        capture_root = path.parents[1]
        if capture_root.is_dir() and path not in candidates:
            candidates.append(path)
    return candidates


def _string(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _number(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _localize_update_message(value: object, default: str = "") -> str:
    message = _string(value, default)
    translated = _UPDATE_MESSAGE_TRANSLATIONS.get(message)
    if translated:
        return translated
    for prefix, localized in _UPDATE_MESSAGE_PREFIX_TRANSLATIONS.items():
        if message.startswith(prefix):
            return localized + message[len(prefix):]
    return message


def _update_check_payload(root: Path, raw: dict[str, object]) -> dict[str, object]:
    remote_status = _string(raw.get("remote_status"), "error")
    error = _string(raw.get("error"))
    download_strategy = _string(raw.get("download_strategy"), "none")
    if download_strategy not in {"release_runtime_zip", "none"}:
        download_strategy = "none"
    payload: dict[str, object] = {
        "status": "ok",
        "version": _string(raw.get("version"), read_version(root)),
        "revision": _string(raw.get("revision"), read_revision(root)),
        "remote_version": _string(raw.get("remote_version")),
        "remote_revision": _string(raw.get("remote_revision")),
        "display_remote": _string(raw.get("display_remote")),
        "has_update": bool(raw.get("has_update")) if remote_status == "ok" else False,
        "can_update": bool(raw.get("can_update")) if remote_status == "ok" else False,
        "installed_runtime": bool(raw.get("installed_runtime")),
        "minimum_launcher_version": _string(raw.get("minimum_launcher_version")),
        "update_reason": _string(raw.get("update_reason"), "manifest_unavailable"),
        "remote_status": remote_status,
        "remote_revision_status": _string(raw.get("remote_revision_status"), remote_status),
        "notice_status": _string(raw.get("notice_status"), remote_status),
        "update_notice": raw.get("update_notice") if isinstance(raw.get("update_notice"), dict) else {},
        "expected_sha256": _string(raw.get("expected_sha256")),
        "integrity_verified": bool(raw.get("integrity_verified")) if remote_status == "ok" else False,
        "integrity_status": _string(raw.get("integrity_status"), "manifest_invalid"),
        "download_strategy": download_strategy,
        "message": _string(raw.get("message"), "无法读取可信更新清单。"),
        "error": error,
    }
    return payload


def check_update(root: Path) -> dict[str, object]:
    """Check exactly one release manifest without treating network loss as an API failure."""
    try:
        raw = _update_backend(root).check_update(root)
    except Exception as exc:  # noqa: BLE001
        raw = {
            "remote_status": "error",
            "update_reason": "manifest_unavailable",
            "message": "无法读取更新清单。",
            "error": str(exc),
        }
    return _update_check_payload(root, raw if isinstance(raw, dict) else {})


def _update_status_payload(raw: dict[str, object]) -> dict[str, object]:
    phase = _string(raw.get("phase"), "idle")
    malformed = phase not in LIFECYCLE_JOB_PHASES
    if malformed:
        phase = "failed"
    running = phase != "idle" and phase not in _TERMINAL_PHASES
    done = phase == "completed"
    failed = phase == "failed"
    cancelled = phase == "cancelled"
    raw_log_tail = raw.get("log_tail")
    log_tail = (
        [_localize_update_message(item) for item in raw_log_tail]
        if isinstance(raw_log_tail, list) and all(isinstance(item, str) for item in raw_log_tail)
        else []
    )
    return {
        "status": "ok",
        "job_id": _string(raw.get("job_id")),
        "running": running,
        "done": done,
        "failed": failed,
        "cancelled": cancelled,
        "phase": phase,
        "progress": max(0, min(100, _number(raw.get("progress"), 0))),
        "step": _string(raw.get("step"), phase),
        "message": _localize_update_message(raw.get("message"), "当前没有正在执行的更新任务。"),
        "log_tail": log_tail,
        "started_at": _string(raw.get("started_at")),
        "updated_at": _string(raw.get("updated_at")),
        "detail_current": _number(raw.get("detail_current"), 0),
        "detail_total": _number(raw.get("detail_total"), 0),
        "detail_unit": _string(raw.get("detail_unit")),
        "cancellable": bool(raw.get("cancellable")) if running else False,
        "bytes_total": _number(raw.get("bytes_total"), 0),
        "bytes_downloaded": _number(raw.get("bytes_downloaded"), 0),
        "bytes_per_second": _number(raw.get("bytes_per_second"), 0),
        "rolled_back": bool(raw.get("rolled_back")),
        "rollback_error": _string(raw.get("rollback_error")),
        "cleanup_pending": bool(raw.get("cleanup_pending")),
        "cleanup_warning": _string(raw.get("cleanup_warning")),
        "interrupted": bool(raw.get("interrupted")),
        "recovery_required": bool(raw.get("recovery_required")),
        "error": _string(raw.get("error")) or ("Malformed lifecycle job state." if malformed else ""),
    }


def update_status(root: Path) -> dict[str, object]:
    try:
        raw = _update_backend(root).update_status(root)
    except Exception as exc:  # noqa: BLE001
        raw = {"phase": "failed", "message": "无法读取更新任务状态。", "error": str(exc)}
    return _update_status_payload(raw if isinstance(raw, dict) else {})


def run_update(root: Path) -> dict[str, object]:
    try:
        raw = _update_backend(root).run_update(root)
    except Exception as exc:  # noqa: BLE001
        raw = {"status": "error", "error": str(exc)}
    raw = raw if isinstance(raw, dict) else {}
    return {
        "status": "ok" if raw.get("status") == "ok" else "error",
        "job_id": _string(raw.get("job_id")),
        "version": _string(raw.get("version")),
        "message": _string(raw.get("message"), "无法启动更新任务。"),
        "error": _string(raw.get("error")),
    }


def cancel_update(root: Path, job_id: str = "") -> dict[str, object]:
    try:
        raw = _update_backend(root).cancel_update(root, job_id)
    except Exception as exc:  # noqa: BLE001
        raw = {"status": "error", "error": str(exc)}
    raw = raw if isinstance(raw, dict) else {}
    status = update_status(root)
    return {
        "status": "ok" if raw.get("status") == "ok" else "error",
        "job_id": _string(raw.get("job_id"), _string(status["job_id"])),
        "phase": _string(status["phase"]),
        "cancellable": bool(status["cancellable"]),
        "message": _string(raw.get("message"), "无法取消更新任务。"),
        "error": _string(raw.get("error")),
    }


def reconnect_update(root: Path) -> dict[str, object]:
    return {**update_status(root), "reconnected": True}


def check_uninstall(root: Path) -> dict[str, object]:
    return {
        "status": "ok",
        "can_uninstall": False,
        "modes": ["cadence_only"],
        "install_dir": str(root),
        "message": "请通过 Windows 设置或 Insta360_HW_Setup.exe 完整卸载平台。",
    }


def uninstall_status(root: Path) -> dict[str, object]:
    return {"status": "ok", "running": False, "done": False, "failed": False, "progress": 0, "message": "网页端不执行平台完整卸载。"}


def run_uninstall(root: Path, mode: str = "cadence_only") -> dict[str, object]:
    if mode not in {"cadence_only", "detach"}:
        return {"status": "error", "error": "平台内仅支持移除 Cadence 集成。"}
    script = root / "scripts" / "remove_cadence_loader.ps1"
    if not script.exists():
        return {"status": "error", "error": f"缺少 Cadence 集成移除脚本：{script}"}
    try:
        completed = subprocess.run(
            [system_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-InstallDir", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "移除 Cadence 集成超时，请关闭 OrCAD Capture 后重试。"}
    if completed.returncode != 0:
        return {"status": "error", "error": completed.stderr.strip() or completed.stdout.strip() or "Cadence 集成移除失败。"}
    return {"status": "ok", "message": "Cadence 集成已移除。", "output": completed.stdout}


def _notice_integrity_lines(root: Path) -> list[str]:
    path = root / "UPDATE_NOTICE.json"
    if not path.exists():
        return [f"path: {path}", "status: missing"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"path: {path}", f"status: INVALID ({exc})"]
    if not isinstance(raw, dict):
        return [f"path: {path}", "status: INVALID (root is not an object)"]
    lines = [f"path: {path}", "status: parsed"]
    assets = raw.get("assets")
    if not isinstance(assets, list):
        return [*lines, "assets: INVALID (expected a list)"]
    if not assets:
        return [*lines, "assets: none"]
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            lines.append(f"asset[{index}]: INVALID (not an object)")
            continue
        digest = _string(asset.get("sha256"))
        state = "valid" if _SHA256_RE.fullmatch(digest) else "INVALID"
        lines.append(
            f"asset[{index}]: kind={_string(asset.get('kind'), 'unknown')} "
            f"url={_string(asset.get('url'), 'missing')} sha256_len={len(digest)} {state}"
        )
    return lines


def _port_state(port: int) -> str:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return "open"
    except OSError:
        return "closed"


def _filesystem_permission_line(state_root: Path) -> str:
    probe = state_root / f".diagnostic-{uuid.uuid4().hex}.tmp"
    try:
        state_root.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return f"state_root: writable ({state_root})"
    except OSError as exc:
        return f"state_root: unavailable ({state_root}): {exc}"


def collect_diagnostic_report(root: Path) -> str:
    """Produce a useful local report without making a live update-network request."""
    runtime_root = root.resolve()
    paths = AppPaths(runtime_root)
    state_root = paths.state_root
    launcher = runtime_root / "Insta360_HW.exe"
    lines = [
        "Insta360_HW diagnostic report",
        "================================",
        "",
        "## Python Runtime",
        f"executable: {sys.executable}",
        f"version: {platform.python_version()}",
        f"platform: {platform.platform()}",
        "",
        "## Launcher VersionInfo",
        f"runtime_root: {runtime_root}",
        f"state_root: {state_root}",
        f"launcher: {launcher}",
        f"launcher_exists: {launcher.exists()}",
        f"runtime_version: {read_version(runtime_root)}",
        f"runtime_revision: {read_revision(runtime_root)}",
        "",
        "## UPDATE_NOTICE.json Integrity",
        *_notice_integrity_lines(runtime_root),
        "",
        "## GitHub Reachability",
        "remote update manifest not probed; diagnostics are offline deterministic.",
        "",
        "## Cadence Home",
    ]
    for directory in _find_cadence_autoload_dirs():
        loader = directory / "iac_bom_tool.tcl"
        lines.append(f"autoload_dir: {directory}")
        lines.append(f"loader: {'present' if loader.exists() else 'missing'} ({loader})")
    lines.extend(
        [
            "",
            "## Port 8765",
            f"127.0.0.1:8765: {_port_state(8765)}",
            "",
            "## Filesystem Permissions",
            _filesystem_permission_line(state_root),
            "",
            "## Lifecycle Job",
            json.dumps(update_status(runtime_root), ensure_ascii=False, indent=2, sort_keys=True),
            "",
            "## Recent launcher.log",
        ]
    )
    log_paths = [state_root / "logs" / "launcher.log", paths.runtime_log_dir / "launcher_latest.log"]
    for log in log_paths:
        if log.exists():
            lines.append(f"log: {log} ({log.stat().st_size} bytes)")
        else:
            lines.append(f"log: missing ({log})")
    lines.extend(["", "=== End of Report ===", ""])
    return "\n".join(lines)


__all__ = [
    "LIFECYCLE_JOB_PHASES",
    "cancel_update",
    "check_update",
    "reconnect_update",
    "run_update",
    "update_status",
    "read_version",
    "read_revision",
    "version_payload",
    "check_uninstall",
    "uninstall_status",
    "run_uninstall",
    "collect_diagnostic_report",
]
