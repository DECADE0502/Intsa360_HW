from __future__ import annotations

import subprocess
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
    try:
        import subprocess
        # tasklist filters for powershell running update.ps1 by command line.
        out = subprocess.run(
            ["wmic", "process", "where",
             "name='powershell.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return "update.ps1" in (out.stdout or "")
    except Exception:  # noqa: BLE001
        return False


def _is_uninstall_running(root: Path) -> bool:
    try:
        out = subprocess.run(
            ["wmic", "process", "where", "name='powershell.exe'", "get", "commandline"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = out.stdout or ""
        return "uninstall.ps1" in text
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
    """owner/repo extracted from the update.ps1 default Repo param, so the
    remote VERSION URL stays in sync with whatever the updater targets."""
    import re
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
    """Best-effort semantic-version tuple for comparison. Non-numeric suffixes
    like '-dev' are stripped so 0.2.0-dev compares as 0.2.0."""
    nums = []
    for part in text.strip().split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


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
                if zip_version and _parse_version(zip_version) > _parse_version(body):
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
    import json
    import urllib.request

    repo = _remote_repo_path(root)
    url = f"https://api.github.com/repos/{repo}/commits/main"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HWAgent-Updater", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        sha = str(payload.get("sha") or "").strip()
        return sha, "ok" if sha else "empty_remote_revision"
    except Exception as exc:  # noqa: BLE001
        return "", f"无法获取远程修订：{exc}"


def _normalize_update_notice(raw: dict[str, Any], remote_version: str = "", remote_revision: str = "") -> dict[str, object]:
    highlights = raw.get("highlights")
    if not isinstance(highlights, list):
        highlights = []
    highlights = [str(item).strip() for item in highlights if str(item or "").strip()]
    revision = str(raw.get("revision") or remote_revision or "").strip()
    return {
        "version": str(raw.get("version") or remote_version or "").strip(),
        "revision": revision,
        "target_revision": _short_revision(revision),
        "date": str(raw.get("date") or "").strip(),
        "title": str(raw.get("title") or "更新公告").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "highlights": highlights,
        "compatibility": str(raw.get("compatibility") or "").strip(),
        "trace": raw.get("trace") if isinstance(raw.get("trace"), dict) else {},
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
                    if _parse_version(zip_version) > _parse_version(raw_version):
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
    local_tuple = _parse_version(local_version)
    if remote_status in _REMOTE_VERSION_OK_STATUSES and remote_version:
        remote_tuple = _parse_version(remote_version)
        if remote_tuple > local_tuple:
            has_update = True
            update_reason = "version"
        elif remote_tuple == local_tuple and remote_revision_status == "ok" and remote_revision and local_revision and remote_revision != local_revision:
            has_update = True
            update_reason = "revision"
    notice_version = str(remote_notice.get("version") or "").strip() if remote_notice else ""
    if not has_update and notice_status in _REMOTE_VERSION_OK_STATUSES and notice_version:
        notice_tuple = _parse_version(notice_version)
        if notice_tuple > local_tuple:
            remote_version = notice_version
            remote_status = "ok_notice_version"
            has_update = True
            update_reason = "notice_version"
    if remote_notice:
        remote_notice = _normalize_update_notice(dict(remote_notice), remote_version, remote_revision)
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

    # Capture the update output to a log file instead of DEVNULL, so failures
    # are diagnosable (network issues, extraction errors).
    log_dir = root / "data" / "reports" / "runtime"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = _update_log_path(root)
    try:
        log_out = open(log_file, "w", encoding="utf-8")
    except OSError:
        log_out = None  # fall back to DEVNULL if the log can't be opened

    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=str(root),
        stdout=log_out if log_out else subprocess.DEVNULL,
        stderr=subprocess.STDOUT if log_out else subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return {"status": "ok", "message": "更新已在后台启动，完成后服务会自动重启。可在「系统状态」查看更新日志。", "version": read_version(root)}


def check_uninstall(root: Path) -> dict[str, object]:
    """Report platform-side removal actions.

    The web platform only supports detaching Cadence integration. Full product
    removal must be owned by Windows Apps / Insta360_HW_Setup.exe so Inno keeps
    registry and install-directory cleanup consistent.
    """
    script = root / "uninstall.ps1"
    return {
        "status": "ok",
        "can_uninstall": script.exists(),
        "modes": ["detach"] if script.exists() else [],
        "install_dir": str(root),
        "message": "卸载检查完成",
    }


def run_uninstall(root: Path, mode: str = "detach") -> dict[str, object]:
    """Run the safe platform-side detach action.

    Full uninstall from the web UI is intentionally disabled. The supported
    full removal path is Windows Apps or running Insta360_HW_Setup.exe, which
    uses the installer/uninstaller lifecycle instead of deleting the running
    service from inside its own web page.
    """
    if mode != "detach":
        return {"status": "error", "error": "请通过 Windows 设置或 Insta360_HW_Setup.exe 卸载平台"}

    script = root / "uninstall.ps1"
    if not script.exists():
        return {"status": "error", "error": "未找到卸载脚本"}

    log_file = _uninstall_log_path(root)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        log_file.write_text("__HWAGENT_UNINSTALL_PROGRESS__ 0 Preparing uninstall\n", encoding="utf-8")
    except OSError:
        pass

    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
        "-Mode", "Detach",
        "-InstallDir", str(root),
        "-Force",
    ]

    # Detach is safe to run while the service is up; it only touches the
    # Cadence autoload dirs, not the install root.
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
    return {"status": "ok", "message": "已开始移除 Cadence 集成", "mode": "detach"}


def _get_temp_path() -> Path:
    import tempfile
    return Path(tempfile.gettempdir())


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
