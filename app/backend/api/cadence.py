from __future__ import annotations

import subprocess
from pathlib import Path

from app.backend.windows_process import system_powershell


CADENCE_LOADER_MARKER = "__HWAGENT_CADENCE_LOADER__ "
CADENCE_NONE_MARKER = "__HWAGENT_CADENCE_NONE__"


def parse_cadence_loader_paths(output: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for line in output.splitlines():
        if not line.startswith(CADENCE_LOADER_MARKER):
            continue
        value = line[len(CADENCE_LOADER_MARKER) :].strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            paths.append(value)
    return paths


def cadence_hot_reload_command(installed: list[str]) -> str:
    if not installed:
        return ""
    path = installed[0].replace("\\", "/").replace("{", r"\{").replace("}", r"\}")
    return f"source {{{path}}}"


def cadence_redeploy_message(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith(CADENCE_NONE_MARKER):
            continue
        message = stripped[len(CADENCE_NONE_MARKER) :].strip()
        return message or "未检测到 Cadence 环境，已跳过菜单部署"
    return "Cadence 集成已重新安装"


def redeploy_cadence_loader(root: Path) -> tuple[bool, list[str], str]:
    script = root / "scripts" / "redeploy_cadence_loader.ps1"
    if not script.exists():
        raise FileNotFoundError("未找到 Cadence 菜单重新部署脚本")
    try:
        completed = subprocess.run(
            [system_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=str(root),
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Cadence 菜单重新部署超时，请关闭 OrCAD Capture 后重试。") from None
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "Cadence 菜单重新部署失败").strip())
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    installed = parse_cadence_loader_paths(output)
    return True, installed, output

