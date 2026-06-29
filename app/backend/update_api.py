from __future__ import annotations

import subprocess
from pathlib import Path


def read_version(root: Path) -> str:
    path = root / "VERSION"
    if not path.exists():
        return "0.0.0"
    # utf-8-sig tolerates a stray BOM if the file was written by an editor or
    # PowerShell Set-Content -Encoding utf8; strip() drops surrounding whitespace.
    return path.read_text(encoding="utf-8-sig").strip() or "0.0.0"


def version_payload(root: Path) -> dict[str, object]:
    return {"status": "ok", "version": read_version(root), "message": "版本读取成功"}


def _has_git() -> bool:
    """True if git.exe is on PATH. The git update path needs this; the default
    zip path does not, so callers no longer gate on it."""
    import shutil
    return shutil.which("git") is not None


def _update_log_path(root: Path) -> Path:
    return root / "data" / "reports" / "runtime" / "update_latest.log"


def _uninstall_log_path(root: Path) -> Path:
    return root / "data" / "reports" / "runtime" / "uninstall_latest.log"


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
        return "uninstall.ps1" in text or "hwagent_full_uninstall.ps1" in text
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


def _fetch_remote_version(root: Path) -> tuple[str, str]:
    """Fetch the remote VERSION over HTTPS. Returns (version, status) where
    status is 'ok' on success or an error description. Uses urllib so no
    third-party dependency is required."""
    import json
    import urllib.request
    repo = _remote_repo_path(root)
    url = f"https://raw.githubusercontent.com/{repo}/main/VERSION"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HWAgent-Updater"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            # utf-8-sig tolerates a BOM on the remote file; strip() drops newlines.
            body = resp.read().decode("utf-8-sig", errors="replace").strip()
        return body, "ok"
    except Exception as exc:  # noqa: BLE001 — network errors are expected
        return "", f"无法获取远程版本：{exc}"


def check_update(root: Path) -> dict[str, object]:
    config = root / "config" / "local.json"
    local_version = read_version(root)
    remote_version, remote_status = _fetch_remote_version(root)
    has_update = False
    if remote_status == "ok" and remote_version:
        has_update = _parse_version(remote_version) > _parse_version(local_version)
    return {
        "status": "ok",
        "version": local_version,
        "remote_version": remote_version,
        "has_update": has_update,
        "can_update": (root / "update.ps1").exists(),
        "git_available": _has_git(),
        "remote_status": remote_status,
        "config": str(config),
        "message": "发现新版本，可一键更新" if has_update else ("已是最新版本" if remote_status == "ok" else "远程版本检查失败"),
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
    """Report which uninstall modes are available from the platform UI."""
    script = root / "uninstall.ps1"
    return {
        "status": "ok",
        "can_uninstall": script.exists(),
        "modes": ["detach", "full"] if script.exists() else [],
        "install_dir": str(root),
        "message": "卸载检查完成",
    }


def run_uninstall(root: Path, mode: str = "detach") -> dict[str, object]:
    """Trigger uninstallation. Detach only removes Cadence integration; Full
    deletes the whole platform directory. Because the running backend lives in
    that directory, Full uses a detached helper process from TEMP.
    """
    if mode not in {"detach", "full"}:
        return {"status": "error", "error": "无效的卸载模式"}

    script = root / "uninstall.ps1"
    if not script.exists():
        return {"status": "error", "error": "未找到卸载脚本"}

    log_dir = root / "data" / "reports" / "runtime"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = _uninstall_log_path(root)
    try:
        log_file.write_text("__HWAGENT_UNINSTALL_PROGRESS__ 0 Preparing uninstall\n", encoding="utf-8")
    except OSError:
        pass

    pwsh_mode = "Detach" if mode == "detach" else "Full"
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
        "-Mode", pwsh_mode,
        "-InstallDir", str(root),
        "-Force",
    ]

    if mode == "detach":
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
        return {"status": "ok", "message": "已开始移除 Cadence 集成", "mode": "detach"}

    # Full: the running service holds the install directory open, so we cannot
    # delete it from this process. Spawn a detached helper from a neutral CWD.
    temp_dir = _get_temp_path()
    ps_helper = temp_dir / "hwagent_full_uninstall.ps1"
    ps_helper.write_text(
        _full_uninstall_helper(root, cmd, log_file),
        encoding="utf-8",
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_helper)],
        cwd=temp_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return {"status": "ok", "message": "完整卸载已启动，平台窗口将在稍后关闭", "mode": "full"}


def _get_temp_path() -> Path:
    import tempfile
    return Path(tempfile.gettempdir())


def _full_uninstall_helper(root: Path, uninstall_cmd: list[str], log_path: Path | None = None) -> str:
    """Build a detached helper script that invokes uninstall.ps1 in Full mode.
    The helper itself runs from TEMP so it never sits inside the dir being removed.
    """
    import json
    cmd_json = json.dumps(uninstall_cmd)
    log_json = json.dumps(str(log_path or _uninstall_log_path(root)))
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
