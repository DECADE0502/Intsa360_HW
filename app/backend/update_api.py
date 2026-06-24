from __future__ import annotations

import subprocess
from pathlib import Path


def read_version(root: Path) -> str:
    path = root / "VERSION"
    if not path.exists():
        return "0.0.0"
    return path.read_text(encoding="utf-8").strip() or "0.0.0"


def version_payload(root: Path) -> dict[str, object]:
    return {"status": "ok", "version": read_version(root), "message": "版本读取成功"}


def check_update(root: Path) -> dict[str, object]:
    config = root / "config" / "local.json"
    return {
        "status": "ok",
        "version": read_version(root),
        "can_update": (root / "update.ps1").exists(),
        "config": str(config),
        "message": "更新检查完成",
    }


def run_update(root: Path) -> dict[str, object]:
    script = root / "update.ps1"
    if not script.exists():
        return {"status": "error", "error": "未找到更新脚本"}
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return {"status": "ok", "message": "更新已启动", "version": read_version(root)}
