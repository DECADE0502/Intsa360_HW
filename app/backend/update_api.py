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
    that directory, Full uses a detached helper process that waits for this
    service to exit before deleting — so the directory is not locked.
    """
    if mode not in {"detach", "full"}:
        return {"status": "error", "error": "无效的卸载模式"}

    script = root / "uninstall.ps1"
    if not script.exists():
        return {"status": "error", "error": "未找到卸载脚本"}

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
        subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {"status": "ok", "message": "已移除 Cadence 集成，平台文件已保留", "mode": "detach"}

    # Full: the running service holds the install directory open, so we cannot
    # delete it from this process. Spawn a detached helper that waits for the
    # backend to exit, then runs the recursive removal from a neutral CWD.
    temp_dir = _get_temp_path()
    ps_helper = temp_dir / "hwagent_full_uninstall.ps1"
    ps_helper.write_text(
        _full_uninstall_helper(root, cmd),
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


def _full_uninstall_helper(root: Path, uninstall_cmd: list[str]) -> str:
    """Build a detached helper script that waits for the backend to exit, then
    invokes uninstall.ps1 in Full mode. Waiting avoids the directory lock; the
    helper itself runs from TEMP so it never sits inside the dir being removed.
    """
    import json
    cmd_json = json.dumps(uninstall_cmd)
    return (
        "$ErrorActionPreference='Continue'\n"
        "Set-Location $env:TEMP\n"
        "# Wait until no suite_app.py python process holds the install dir.\n"
        "for ($i=0; $i -lt 120; $i++) {\n"
        "  $busy = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Name -like 'python*' -and $_.CommandLine -and "
        "$_.CommandLine.Contains('suite_app.py') }\n"
        "  if (-not $busy) { break }\n"
        "  Start-Sleep -Milliseconds 500\n"
        "}\n"
        "# Give the browser a moment to release file handles too.\n"
        "Start-Sleep -Seconds 1\n"
        f"$cmd = {cmd_json}\n"
        "try { & $cmd[0] @($cmd | Select-Object -Skip 1) } catch {}\n"
        "# Self-cleanup of this helper script.\n"
        "try { Remove-Item $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue } catch {}\n"
    )
