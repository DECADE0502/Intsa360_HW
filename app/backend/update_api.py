from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def read_version(root: Path) -> str:
    path = root / "VERSION"
    if not path.exists():
        return "0.0.0"
    # utf-8-sig tolerates a stray BOM if the file was written by an editor or
    # PowerShell Set-Content -Encoding utf8; strip() drops surrounding whitespace.
    return path.read_text(encoding="utf-8-sig").strip() or "0.0.0"


def read_revision(root: Path) -> str:
    path = root / "REVISION"
    if path.exists():
        value = path.read_text(encoding="utf-8-sig").strip()
        if value:
            return value
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _short_revision(value: str) -> str:
    return value[:7] if value else ""


def version_payload(root: Path) -> dict[str, object]:
    return {"status": "ok", "version": read_version(root), "revision": read_revision(root), "message": "版本读取成功"}


def _has_git() -> bool:
    """True if git.exe is on PATH. The git update path needs this; the default
    zip path does not, so callers no longer gate on it."""
    import shutil
    return shutil.which("git") is not None


def _update_log_path(root: Path) -> Path:
    return root / "data" / "reports" / "runtime" / "update_latest.log"


def _update_pid_path(root: Path) -> Path:
    return root / "data" / "reports" / "runtime" / "update_latest.pid"


def _uninstall_log_path(root: Path) -> Path:
    return root / "data" / "reports" / "runtime" / "uninstall_latest.log"


def _temp_uninstall_log_path() -> Path:
    return _get_temp_path() / "hwagent_uninstall_latest.log"


def _find_cadence_autoload_dirs() -> list[Path]:
    import os

    candidates = [
        Path(r"D:\CADENCE\Cadence\SPB_Data\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad"),
        Path(r"D:\CADENCE\Cadence\SPB_17.4\tools\capture\tclscripts\capAutoLoad"),
    ]
    for base in (os.environ.get("USERPROFILE"), os.environ.get("HOME")):
        if base:
            candidates.append(Path(base) / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad")
    seen: set[str] = set()
    result: list[Path] = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _remove_cadence_loader_artifacts(auto_load_dirs: list[Path]) -> list[str]:
    removed: list[str] = []
    for directory in auto_load_dirs:
        if not directory.exists():
            continue
        for target in [directory / "iac_bom_tool.tcl", directory / "iac_bom_tool_backup"]:
            if not target.exists():
                continue
            try:
                if target.is_dir():
                    import shutil
                    shutil.rmtree(target)
                else:
                    target.unlink()
                removed.append(str(target))
            except OSError:
                pass
        for backup_dir in directory.glob("_disabled_hwagent_loader_*"):
            try:
                import shutil
                shutil.rmtree(backup_dir)
                removed.append(str(backup_dir))
            except OSError:
                pass
    return removed


def _is_update_running(root: Path) -> bool:
    """True if an update.ps1 process is currently running. Used to distinguish
    'update finished' from 'update crashed' — if the process is gone but the
    log lacks a done marker, it failed."""
    pid_path = _update_pid_path(root)
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return False
        if pid <= 0 or pid == os.getpid():
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    return _is_powershell_script_running("update.ps1")


def _is_uninstall_running(root: Path) -> bool:
    return _is_powershell_script_running("uninstall.ps1")


def _is_powershell_script_running(script_name: str) -> bool:
    try:
        safe_script_name = script_name.replace("'", "''")
        command = (
            f"$scriptName = '{safe_script_name}'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like '*powershell*' -and "
            "$_.CommandLine -match '(?i)(^|\\s)-File(\\s|$)' -and "
            "$_.CommandLine -like ('*' + $scriptName + '*') } | "
            "Select-Object -First 1 -ExpandProperty ProcessId"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return out.returncode == 0 and bool((out.stdout or "").strip())
    except Exception:  # noqa: BLE001
        return False


def update_status(root: Path) -> dict[str, object]:
    """Report live update progress by parsing the update log. Returns:
      - running: whether update.ps1 is still executing
      - progress: 0-100 from the last __HWAGENT_PROGRESS__ marker
      - step: human-readable current step
      - done: True if __HWAGENT_DONE__ was written (update succeeded)
      - failed: True if process is gone but no done marker (crashed)
      - log_tail: last ~30 log lines for the live console
    """
    log_path = _update_log_path(root)
    log_text = ""
    log_tail: list[str] = []
    if log_path.exists():
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            log_tail = [ln for ln in log_text.splitlines() if ln.strip()][-30:]
        except OSError:
            pass

    running = _is_update_running(root)
    done = "__HWAGENT_DONE__" in log_text
    if done:
        running = False
    failed_marker = ""
    for line in log_text.splitlines():
        if line.startswith("__HWAGENT_FAILED__"):
            failed_marker = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else "update failed"
    if failed_marker:
        running = False

    # Parse the latest progress marker for the percentage + step label.
    progress = 0
    step = ""
    last_marker = None
    for line in log_text.splitlines():
        if line.startswith("__HWAGENT_PROGRESS__"):
            last_marker = line
    if last_marker:
        parts = last_marker.split(None, 2)
        if len(parts) >= 2:
            try:
                progress = int(parts[1])
            except ValueError:
                pass
        if len(parts) >= 3:
            step = parts[2]

    # If the process has exited without a done marker, the update failed.
    failed = bool(failed_marker) or ((not running) and (not done) and bool(log_text) and progress > 0)

    # Filter the machine markers out of the displayed log tail.
    clean_tail = [ln for ln in log_tail if not ln.startswith("__HWAGENT")]

    message = "更新进行中"
    if done:
        message = "更新完成，服务正在重启"
    elif failed:
        message = "更新失败，请查看日志"
    elif not running and not log_text:
        message = "无更新任务"

    return {
        "status": "ok",
        "running": running,
        "done": done,
        "failed": failed,
        "progress": progress,
        "step": step,
        "message": message,
        "error": failed_marker,
        "log_tail": clean_tail,
    }


def uninstall_status(root: Path) -> dict[str, object]:
    log_path = _uninstall_log_path(root)
    if not log_path.exists():
        temp_log = _temp_uninstall_log_path()
        if temp_log.exists():
            log_path = temp_log
    log_text = ""
    log_tail: list[str] = []
    if log_path.exists():
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            log_tail = [ln for ln in log_text.splitlines() if ln.strip()][-30:]
        except OSError:
            pass

    running = _is_uninstall_running(root)
    done = "__HWAGENT_UNINSTALL_DONE__" in log_text

    progress = 0
    step = ""
    last_marker = None
    for line in log_text.splitlines():
        if line.startswith("__HWAGENT_UNINSTALL_PROGRESS__"):
            last_marker = line
    if last_marker:
        parts = last_marker.split(None, 2)
        if len(parts) >= 2:
            try:
                progress = int(parts[1])
            except ValueError:
                pass
        if len(parts) >= 3:
            step = parts[2]

    failed = (not running) and (not done) and bool(log_text) and progress > 0
    clean_tail = [ln for ln in log_tail if not ln.startswith("__HWAGENT")]

    message = "卸载进行中"
    if done:
        message = "卸载完成"
    elif failed:
        message = "卸载可能已中断，请查看日志"
    elif not running and not log_text:
        message = "暂无卸载任务"

    return {
        "status": "ok",
        "running": running,
        "done": done,
        "failed": failed,
        "progress": progress,
        "step": step,
        "message": message,
        "log_tail": clean_tail,
    }


def _remote_repo_path(root: Path) -> str:
    """Resolve owner/repo for remote update checks.

    Priority: local override, published notice trace, update.ps1 default, then
    the historical repository fallback.
    """
    import json
    import re

    def valid_repo(value: object) -> str:
        text = str(value or "").strip()
        return text if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", text) else ""

    local_config = root / "config" / "local.json"
    if local_config.exists():
        try:
            data = json.loads(local_config.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("update"), dict):
                repo = valid_repo(data["update"].get("repo"))
                if repo:
                    return repo
        except (ValueError, OSError):
            pass

    notice = root / "UPDATE_NOTICE.json"
    if notice.exists():
        try:
            data = json.loads(notice.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and isinstance(data.get("trace"), dict):
                repo = valid_repo(data["trace"].get("repo"))
                if repo:
                    return repo
        except (ValueError, OSError):
            pass

    script = root / "update.ps1"
    if script.exists():
        match = re.search(r'\$Repo\s*=\s*"(https?://github\.com/[^"]+)"', script.read_text(encoding="utf-8"))
        if match:
            url = match.group(1)
            m = re.match(r"^https?://github\.com/(.+?)(\.git)?/?$", url)
            if m:
                return m.group(1)
    return "DECADE0502/Intsa360_HW"


def _parse_version(text: str) -> tuple:
    """Return numeric major/minor/patch for legacy callers."""
    core, _pre = _parse_semver(text)
    return core


def _parse_semver(text: str) -> tuple[tuple[int, int, int], list[object]]:
    import re

    value = (text or "").strip()
    value = value[1:] if value.startswith("v") else value
    value = value.split("+", 1)[0]
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?$", value)
    if not match:
        raise ValueError(f"invalid version: {text!r}")
    core = tuple(int(match.group(i) or 0) for i in range(1, 4))
    prerelease = []
    if match.group(4):
        for part in match.group(4).split("."):
            prerelease.append(int(part) if part.isdigit() else part.lower())
    return core, prerelease


def _compare_prerelease(left: list[object], right: list[object]) -> int:
    if not left and not right:
        return 0
    if not left:
        return 1
    if not right:
        return -1
    for a, b in zip(left, right):
        if a == b:
            continue
        if isinstance(a, int) and isinstance(b, str):
            return -1
        if isinstance(a, str) and isinstance(b, int):
            return 1
        return -1 if a < b else 1
    if len(left) == len(right):
        return 0
    return -1 if len(left) < len(right) else 1


def _compare_versions(left: str, right: str) -> int:
    left_core, left_pre = _parse_semver(left)
    right_core, right_pre = _parse_semver(right)
    if left_core != right_core:
        return -1 if left_core < right_core else 1
    return _compare_prerelease(left_pre, right_pre)


def _is_revision_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    ancestor = (ancestor or "").strip()
    descendant = (descendant or "").strip()
    if not ancestor or not descendant:
        return False
    try:
        out = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return out.returncode == 0
    except Exception:  # noqa: BLE001
        return False


_REMOTE_VERSION_OK_STATUSES = {"ok", "ok_raw", "ok_zip", "ok_notice_version"}


def _fetch_remote_version(root: Path) -> tuple[str, str]:
    """Fetch remote VERSION. Prefer GitHub Contents API, fall back to raw."""
    import base64
    import json
    import urllib.request

    repo = _remote_repo_path(root)
    api_url = f"https://api.github.com/repos/{repo}/contents/VERSION?ref=main"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "HWAgent-Updater", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        content = str(payload.get("content") or "")
        body = base64.b64decode(content).decode("utf-8-sig", errors="replace").strip()
        return body, "ok"
    except Exception as exc:  # noqa: BLE001
        try:
            raw_url = f"https://raw.githubusercontent.com/{repo}/main/VERSION"
            with urllib.request.urlopen(raw_url, timeout=10) as resp:
                body = resp.read().decode("utf-8-sig", errors="replace").strip()
            zip_body, zip_status = _fetch_file_from_codeload_zip(repo, "VERSION")
            if zip_status == "ok_zip":
                zip_version = zip_body.decode("utf-8-sig", errors="replace").strip()
                if zip_version and _compare_versions(zip_version, body) > 0:
                    return zip_version, zip_status
            return body, "ok_raw" if body else "empty_remote_version"
        except Exception as raw_exc:  # noqa: BLE001
            zip_body, zip_status = _fetch_file_from_codeload_zip(repo, "VERSION")
            if zip_status == "ok_zip":
                return zip_body.decode("utf-8-sig", errors="replace").strip(), zip_status
            return "", f"remote version fetch failed: {exc}; raw fallback failed: {raw_exc}; zip fallback: {zip_status}"


def _fetch_file_from_codeload_zip(repo: str, relative_path: str) -> tuple[bytes, str]:
    import io
    import urllib.request
    import zipfile

    url = f"https://codeload.github.com/{repo}/zip/refs/heads/main"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HWAgent-Updater"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            suffix = "/" + relative_path.replace("\\", "/")
            for name in archive.namelist():
                if name.endswith(suffix):
                    return archive.read(name), "ok_zip"
        return b"", "missing_in_zip"
    except Exception as exc:  # noqa: BLE001
        return b"", f"zip fallback failed: {exc}"


def _fetch_remote_revision(root: Path) -> tuple[str, str]:
    import base64
    import json
    import urllib.request

    repo = _remote_repo_path(root)
    api_url = f"https://api.github.com/repos/{repo}/contents/REVISION?ref=main"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "HWAgent-Updater", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        content = str(payload.get("content") or "")
        revision = base64.b64decode(content).decode("utf-8-sig", errors="replace").strip()
        return revision, "ok" if revision else "empty_remote_revision"
    except Exception as exc:  # noqa: BLE001
        try:
            raw_url = f"https://raw.githubusercontent.com/{repo}/main/REVISION"
            with urllib.request.urlopen(raw_url, timeout=10) as resp:
                revision = resp.read().decode("utf-8-sig", errors="replace").strip()
            return revision, "ok_raw" if revision else "empty_remote_revision"
        except Exception as raw_exc:  # noqa: BLE001
            zip_body, zip_status = _fetch_file_from_codeload_zip(repo, "REVISION")
            if zip_status == "ok_zip":
                return zip_body.decode("utf-8-sig", errors="replace").strip(), zip_status
            return "", f"remote revision fetch failed: {exc}; raw fallback failed: {raw_exc}; zip fallback: {zip_status}"


def _normalize_update_notice(raw: dict[str, Any], remote_version: str = "", remote_revision: str = "") -> dict[str, object]:
    highlights = raw.get("highlights")
    if not isinstance(highlights, list):
        highlights = []
    highlights = [str(item).strip() for item in highlights if str(item or "").strip()]
    revision = str(remote_revision or raw.get("revision") or "").strip()
    assets = []
    for item in raw.get("assets") if isinstance(raw.get("assets"), list) else []:
        if not isinstance(item, dict):
            continue
        sha256 = str(item.get("sha256") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256) or not url or not kind:
            continue
        try:
            size_bytes = int(item.get("size_bytes") or 0)
        except (TypeError, ValueError):
            size_bytes = 0
        assets.append({"kind": kind, "url": url, "sha256": sha256, "size_bytes": size_bytes})
    return {
        "version": str(raw.get("version") or remote_version or "").strip(),
        "revision": revision,
        "target_revision": _short_revision(revision),
        "date": str(raw.get("date") or "").strip(),
        "title": str(raw.get("title") or "更新公告").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "highlights": highlights,
        "compatibility": str(raw.get("compatibility") or "").strip(),
        "assets": assets,
        "trace": raw.get("trace") if isinstance(raw.get("trace"), dict) else {},
    }


def _resolve_update_download_metadata(remote_notice: dict[str, object] | None) -> dict[str, object]:
    """Describe the actual updater path without overstating integrity.

    update.ps1 does not consume UPDATE_NOTICE.assets directly. It first asks
    GitHub Releases for a runtime zip and only then uses the release API
    sha/digest; if that lookup fails it falls back to the codeload source zip.
    Therefore a sha256 stored in UPDATE_NOTICE is advisory, not proof that the
    next download will be verified.
    """
    assets = remote_notice.get("assets", []) if remote_notice else []
    release_asset = next(
        (
            asset
            for asset in assets
            if isinstance(asset, dict)
            and asset.get("kind") == "release_zip"
            and str(asset.get("sha256") or "")
        ),
        None,
    )
    if release_asset:
        return {
            "download_strategy": "runtime_release_or_source_zip",
            "integrity_status": "runtime_release_sha_pending",
            "expected_sha256": "",
            "integrity_verified": False,
        }
    return {
        "download_strategy": "source_zip_fallback",
        "integrity_status": "unverified_source_zip",
        "expected_sha256": "",
        "integrity_verified": False,
    }


def _fetch_remote_update_notice(root: Path) -> tuple[dict[str, object], str]:
    import base64
    import json
    import urllib.request

    repo = _remote_repo_path(root)
    api_url = f"https://api.github.com/repos/{repo}/contents/UPDATE_NOTICE.json?ref=main"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "HWAgent-Updater", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        content = str(payload.get("content") or "")
        body = base64.b64decode(content).decode("utf-8-sig", errors="replace")
        raw = json.loads(body)
        if not isinstance(raw, dict):
            return {}, "invalid_notice"
        return _normalize_update_notice(raw), "ok"
    except Exception as exc:  # noqa: BLE001
        try:
            raw_url = f"https://raw.githubusercontent.com/{repo}/main/UPDATE_NOTICE.json"
            with urllib.request.urlopen(raw_url, timeout=10) as resp:
                raw_body = resp.read()
            raw = json.loads(raw_body.decode("utf-8-sig", errors="replace"))
            zip_body, zip_status = _fetch_file_from_codeload_zip(repo, "UPDATE_NOTICE.json")
            if zip_status == "ok_zip":
                zip_raw = json.loads(zip_body.decode("utf-8-sig", errors="replace"))
                if isinstance(zip_raw, dict):
                    raw_version = str(raw.get("version") or "") if isinstance(raw, dict) else ""
                    zip_version = str(zip_raw.get("version") or "")
                    if _compare_versions(zip_version, raw_version) > 0:
                        return _normalize_update_notice(zip_raw), zip_status
            if not isinstance(raw, dict):
                return {}, "invalid_notice"
            return _normalize_update_notice(raw), "ok_raw"
        except Exception as raw_exc:  # noqa: BLE001
            zip_body, zip_status = _fetch_file_from_codeload_zip(repo, "UPDATE_NOTICE.json")
            if zip_status == "ok_zip":
                raw = json.loads(zip_body.decode("utf-8-sig", errors="replace"))
                if not isinstance(raw, dict):
                    return {}, "invalid_notice"
                return _normalize_update_notice(raw), zip_status
            return {}, f"update notice fetch failed: {exc}; raw fallback failed: {raw_exc}; zip fallback: {zip_status}"


def check_update(root: Path) -> dict[str, object]:
    config = root / "config" / "local.json"
    local_version = read_version(root)
    local_revision = read_revision(root)
    remote_version, remote_status = _fetch_remote_version(root)
    remote_revision, remote_revision_status = _fetch_remote_revision(root)
    remote_notice, notice_status = _fetch_remote_update_notice(root)
    has_update = False
    update_reason = ""
    if remote_status in _REMOTE_VERSION_OK_STATUSES and remote_version:
        remote_cmp = _compare_versions(remote_version, local_version)
        if remote_cmp > 0:
            has_update = True
            update_reason = "version"
        elif (
            remote_cmp == 0
            and remote_revision_status in {"ok", "ok_raw", "ok_zip"}
            and remote_revision
            and local_revision
            and remote_revision != local_revision
        ):
            # Same version, different revision = a hotfix landed. Do NOT gate
            # this on `git merge-base --is-ancestor`: installed runtimes ship
            # WITHOUT .git, so ancestor check would always fail and hotfixes
            # would never reach real users. REVISION is a signed release
            # marker (set by bump_version.ps1) - a plain inequality is the
            # correct signal that the packaged revision has advanced.
            has_update = True
            update_reason = "revision"
    notice_version = str(remote_notice.get("version") or "").strip() if remote_notice else ""
    if not has_update and notice_status in _REMOTE_VERSION_OK_STATUSES and notice_version:
        if _compare_versions(notice_version, local_version) > 0:
            remote_version = notice_version
            remote_status = "ok_notice_version"
            has_update = True
            update_reason = "notice_version"
    if remote_notice:
        remote_notice = _normalize_update_notice(dict(remote_notice), remote_version, remote_revision)
    download_meta = _resolve_update_download_metadata(remote_notice)
    if has_update:
        message = "发现新版本，可一键更新"
    elif remote_status in _REMOTE_VERSION_OK_STATUSES:
        message = "已是最新版本"
    else:
        message = "远程版本检查失败"
    return {
        "status": "ok",
        "version": local_version,
        "revision": local_revision,
        "remote_version": remote_version,
        "remote_revision": remote_revision,
        "update_notice": remote_notice if has_update else {},
        "expected_sha256": download_meta["expected_sha256"] if has_update else "",
        "integrity_verified": download_meta["integrity_verified"] if has_update else False,
        "integrity_status": download_meta["integrity_status"] if has_update else "",
        "download_strategy": download_meta["download_strategy"] if has_update else "",
        "notice_status": notice_status,
        "has_update": has_update,
        "update_reason": update_reason,
        "can_update": (root / "update.ps1").exists(),
        "git_available": _has_git(),
        "remote_status": remote_status,
        "remote_revision_status": remote_revision_status,
        "display_remote": f"{remote_version} ({_short_revision(remote_revision)})" if remote_revision else remote_version,
        "config": str(config),
        "message": message,
    }


def run_update(root: Path) -> dict[str, object]:
    script = root / "update.ps1"
    if not script.exists():
        return {"status": "error", "error": "未找到更新脚本"}

    if _is_update_running(root):
        return {
            "status": "ok",
            "already_running": True,
            "message": "更新已经在进行中，请查看当前进度",
            "version": read_version(root),
        }

    # Capture the update output to a log file instead of DEVNULL, so failures
    # are diagnosable (network issues, extraction errors).
    log_dir = root / "data" / "reports" / "runtime"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = _update_log_path(root)
    try:
        log_out = open(log_file, "w", encoding="utf-8")
    except OSError:
        log_out = None  # fall back to DEVNULL if the log can't be opened

    process = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=str(root),
        stdout=log_out if log_out else subprocess.DEVNULL,
        stderr=subprocess.STDOUT if log_out else subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        _update_pid_path(root).write_text(str(process.pid), encoding="utf-8")
    except OSError:
        pass
    if log_out:
        log_out.close()
    return {"status": "ok", "message": "更新已在后台启动，完成后服务会自动重启。可在「系统状态」查看更新日志。", "version": read_version(root)}


def check_uninstall(root: Path) -> dict[str, object]:
    """Report platform-side removal actions.

    The web platform only supports detaching Cadence integration. Full product
    removal must be owned by Windows Apps / Insta360_HW_Setup.exe so Inno keeps
    registry and install-directory cleanup consistent.

    Preferred detach path is now ``cadence_only`` — a standalone script that
    only removes the Cadence loader without stopping platform services. The
    legacy ``detach`` mode (via uninstall.ps1) is retained for compatibility
    but should not be used from the running platform, because uninstall.ps1
    calls Stop-HwAgentServicesByPort which would kill the very service that
    spawned it.
    """
    cadence_script = root / "scripts" / "remove_cadence_loader.ps1"
    legacy_script = root / "uninstall.ps1"
    modes: list[str] = []
    if cadence_script.exists():
        modes.append("cadence_only")
    if legacy_script.exists():
        modes.append("detach")
    return {
        "status": "ok",
        "can_uninstall": bool(modes),
        "modes": modes,
        "install_dir": str(root),
        "message": "卸载检查完成",
    }


def run_uninstall(root: Path, mode: str = "cadence_only") -> dict[str, object]:
    """Run the safe platform-side detach action.

    Full uninstall from the web UI is intentionally disabled. The supported
    full removal path is Windows Apps or running Insta360_HW_Setup.exe, which
    uses the installer/uninstaller lifecycle instead of deleting the running
    service from inside its own web page.

    ``cadence_only`` is the mode the running platform must use. It invokes
    ``scripts/remove_cadence_loader.ps1``, which only removes the Cadence
    loader files and does NOT call Stop-HwAgentServicesByPort. Calling the
    legacy ``detach`` mode from inside the running service would race the
    service against its own shutdown and drop the response mid-flight.
    """
    if mode not in {"cadence_only", "detach"}:
        return {"status": "error", "error": "请通过 Windows 设置或 Insta360_HW_Setup.exe 卸载平台"}

    log_file = _uninstall_log_path(root)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        log_file.write_text("__HWAGENT_UNINSTALL_PROGRESS__ 0 Preparing uninstall\n", encoding="utf-8")
    except OSError:
        pass

    if mode == "cadence_only":
        script = root / "scripts" / "remove_cadence_loader.ps1"
        if not script.exists():
            return {"status": "error", "error": "未找到 remove_cadence_loader.ps1"}
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script),
            "-InstallDir", str(root),
        ]
    else:  # legacy "detach" — uninstall.ps1 stops platform services
        script = root / "uninstall.ps1"
        if not script.exists():
            return {"status": "error", "error": "未找到卸载脚本"}
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script),
            "-Mode", "Detach",
            "-InstallDir", str(root),
            "-Force",
        ]

    # cadence_only is safe to run while the service is up; it only touches the
    # Cadence autoload dirs and never invokes Stop-HwAgentServicesByPort.
    try:
        log_out = open(log_file, "a", encoding="utf-8")
    except OSError:
        log_out = None
    subprocess.Popen(
        cmd,
        cwd=str(root),
        stdout=log_out if log_out else subprocess.DEVNULL,
        stderr=subprocess.STDOUT if log_out else subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if log_out:
        log_out.close()
    return {"status": "ok", "message": "已开始移除 Cadence 集成", "mode": mode}


def _get_temp_path() -> Path:
    import tempfile
    return Path(tempfile.gettempdir())


def collect_diagnostic_report(root: Path) -> str:
    """Collect diagnostic info as multiline text, safe to display or download.

    The output is intentionally readable and support-focused: it lists version
    info, embedded runtime status, GitHub reachability, Cadence loader presence,
    port ownership, filesystem permissions, and a tail of launcher.log so a user
    can copy-paste it back to us when reporting an issue.
    """
    import datetime as _datetime
    import json as _json
    import platform as _platform
    import socket as _socket
    import urllib.error as _urlerror
    import urllib.request as _urlrequest

    lines: list[str] = []
    lines.append("=== Insta360 HW Diagnostic Report ===")
    lines.append(f"Generated: {_datetime.datetime.now(_datetime.timezone.utc).isoformat()}")
    lines.append(f"OS: {_platform.platform()}")
    lines.append(f"Root: {root}")
    try:
        lines.append(f"Local version: {read_version(root)}")
        lines.append(f"Local revision: {_short_revision(read_revision(root))}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  ERROR reading version/revision: {exc}")
    lines.append("")

    # 1. Python runtime
    lines.append("## Python Runtime")
    py_exe = root / "runtime" / "python" / "python.exe"
    if py_exe.exists():
        try:
            v = subprocess.check_output(
                [str(py_exe), "--version"],
                text=True,
                timeout=5,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()
            lines.append(f"  Embedded Python: {v} at {py_exe}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  Embedded Python: ERROR {exc}")
        try:
            v = subprocess.check_output(
                [str(py_exe), "-c", "import openpyxl; print(openpyxl.__version__)"],
                text=True,
                timeout=5,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()
            lines.append(f"  openpyxl (embedded): {v}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  openpyxl (embedded): ERROR {exc}")
    else:
        lines.append(f"  Embedded Python NOT FOUND at {py_exe}")
    # Best-effort report for whatever python is running the service (helps dev).
    lines.append(f"  Service Python: {sys.version.splitlines()[0]} at {sys.executable}")
    try:
        import openpyxl  # noqa: PLC0415

        lines.append(f"  openpyxl (service): {openpyxl.__version__}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  openpyxl (service): ERROR {exc}")

    # 2. Launcher VersionInfo (Windows only)
    lines.append("")
    lines.append("## Launcher VersionInfo")
    exe = root / "Insta360_HW.exe"
    if exe.exists() and sys.platform == "win32":
        try:
            escaped = str(exe).replace("'", "''")
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Item '{escaped}').VersionInfo | "
                "Format-List FileVersion, ProductVersion, CompanyName, ProductName | Out-String",
            ]
            v = subprocess.check_output(
                cmd,
                text=True,
                timeout=8,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()
            for ln in v.splitlines():
                lines.append(f"  {ln}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  ERROR {exc}")
    elif not exe.exists():
        lines.append(f"  Insta360_HW.exe not found at {exe}")
    else:
        lines.append("  Not on Windows; skipping VersionInfo")

    # 3. UPDATE_NOTICE integrity
    lines.append("")
    lines.append("## UPDATE_NOTICE.json Integrity")
    notice_path = root / "UPDATE_NOTICE.json"
    if notice_path.exists():
        try:
            notice = _json.loads(notice_path.read_text(encoding="utf-8-sig"))
            lines.append(f"  version: {notice.get('version')}")
            lines.append(f"  revision: {notice.get('revision', '(empty)')}")
            assets = notice.get("assets") if isinstance(notice.get("assets"), list) else []
            lines.append(f"  assets: {len(assets)} entries")
            for asset in assets:
                if not isinstance(asset, dict):
                    lines.append("    - <invalid asset entry>")
                    continue
                sha = str(asset.get("sha256") or "")
                sha_ok = len(sha) == 64 and all(ch in "0123456789abcdef" for ch in sha.lower())
                lines.append(
                    f"    - {asset.get('kind', '?')}: sha256_len={len(sha)} "
                    f"({'valid' if sha_ok else 'INVALID; expected 64 hex chars'})"
                )
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  ERROR parsing: {exc}")
    else:
        lines.append(f"  UPDATE_NOTICE.json NOT FOUND at {notice_path}")

    # 4. GitHub reachability
    lines.append("")
    lines.append("## GitHub Reachability")
    try:
        req = _urlrequest.Request(
            "https://raw.githubusercontent.com",
            method="HEAD",
            headers={"User-Agent": "HWAgent-Diagnostic"},
        )
        with _urlrequest.urlopen(req, timeout=3):
            lines.append("  raw.githubusercontent.com: REACHABLE")
    except _urlerror.HTTPError as http_exc:
        lines.append(f"  raw.githubusercontent.com: HTTP {http_exc.code} (still reachable)")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  raw.githubusercontent.com: UNREACHABLE ({type(exc).__name__}: {exc})")

    # 5. Cadence Home
    lines.append("")
    lines.append("## Cadence Home")
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    lines.append(f"  HOME/USERPROFILE: {home or '(unset)'}")
    if home:
        auto_load = Path(home) / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad"
        lines.append(f"  autoLoad dir: {'EXISTS' if auto_load.exists() else 'MISSING'} ({auto_load})")
        loader = auto_load / "iac_bom_tool.tcl"
        lines.append(f"  iac_bom_tool.tcl: {'PRESENT' if loader.exists() else 'MISSING'}")

    # 6. Port 8765
    lines.append("")
    lines.append("## Port 8765")
    try:
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", 8765))
        sock.close()
        if result == 0:
            lines.append("  Port 8765: OCCUPIED (someone listening)")
            if sys.platform == "win32":
                try:
                    cmd = [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Get-NetTCPConnection -LocalPort 8765 -State Listen "
                        "-ErrorAction SilentlyContinue | Select-Object -First 1 OwningProcess | "
                        "ForEach-Object { Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue | "
                        "Select-Object Id, ProcessName } | Format-List | Out-String",
                    ]
                    out = subprocess.check_output(
                        cmd,
                        text=True,
                        timeout=5,
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    ).strip()
                    for ln in out.splitlines():
                        if ln.strip():
                            lines.append(f"    {ln}")
                except Exception:  # noqa: BLE001
                    pass
        else:
            lines.append("  Port 8765: FREE")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  Port 8765: ERROR checking ({exc})")

    # 7. Filesystem permissions
    lines.append("")
    lines.append("## Filesystem Permissions")
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        appdata_root = Path(localappdata) / "Insta360_HW"
        try:
            appdata_root.mkdir(parents=True, exist_ok=True)
            test_file = appdata_root / ".diag_write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            lines.append(f"  %LOCALAPPDATA%\\Insta360_HW: WRITABLE")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  %LOCALAPPDATA%\\Insta360_HW: NOT WRITABLE ({exc})")
    else:
        lines.append("  LOCALAPPDATA env var unset")
    try:
        test_file = root / ".diag_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        lines.append(f"  install root: WRITABLE")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  install root: NOT WRITABLE ({exc})")

    # 8. Recent launcher.log tail
    lines.append("")
    lines.append("## Recent launcher.log (last 50 lines)")
    log_candidates: list[Path] = []
    if localappdata:
        log_candidates.append(Path(localappdata) / "Insta360_HW" / "launcher.log")
    log_candidates.append(root / "data" / "reports" / "runtime" / "launcher_latest.log")
    picked: Path | None = None
    for candidate in log_candidates:
        if candidate.exists():
            picked = candidate
            break
    if picked is not None:
        lines.append(f"  Source: {picked}")
        try:
            content = picked.read_text(encoding="utf-8", errors="replace")
            tail = content.splitlines()[-50:]
            lines.extend("  " + ln for ln in tail)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  ERROR reading log: {exc}")
    else:
        lines.append(f"  launcher.log NOT FOUND (checked: {', '.join(str(p) for p in log_candidates)})")

    lines.append("")
    lines.append("=== End of Report ===")
    return "\n".join(lines)


def _full_uninstall_helper(root: Path, uninstall_cmd: list[str], log_path: Path | None = None) -> str:
    """Build a detached helper script that invokes uninstall.ps1 in Full mode.
    The helper itself runs from TEMP so it never sits inside the dir being removed.
    """
    import json
    cmd_json = json.dumps(uninstall_cmd)
    log_json = json.dumps(str(log_path or _temp_uninstall_log_path()))
    return (
        "$ErrorActionPreference='Continue'\n"
        "Set-Location $env:TEMP\n"
        f"$log = {log_json}\n"
        "function Mark([int]$p, [string]$s) {\n"
        "  try { Add-Content -LiteralPath $log -Encoding UTF8 -Value (\"__HWAGENT_UNINSTALL_PROGRESS__ \" + $p + \" \" + $s) } catch {}\n"
        "}\n"
        "Mark 10 'Uninstall request accepted'\n"
        "Start-Sleep -Milliseconds 700\n"
        "Mark 30 'Removing Cadence integration'\n"
        "Start-Sleep -Milliseconds 700\n"
        "Mark 60 'Stopping platform service and deleting files'\n"
        f"$cmd = {cmd_json}\n"
        "try {\n"
        "  & $cmd[0] @($cmd | Select-Object -Skip 1) 2>&1 | Tee-Object -FilePath $log -Append | Out-Null\n"
        "  Mark 100 'Uninstall complete'\n"
        "  try { Add-Content -LiteralPath $log -Encoding UTF8 -Value '__HWAGENT_UNINSTALL_DONE__' } catch {}\n"
        "} catch {\n"
        "  try { Add-Content -LiteralPath $log -Encoding UTF8 -Value ('__HWAGENT_UNINSTALL_FAILED__ ' + $_.Exception.Message) } catch {}\n"
        "}\n"
        "# Self-cleanup of this helper script.\n"
        "try { Remove-Item $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue } catch {}\n"
    )
