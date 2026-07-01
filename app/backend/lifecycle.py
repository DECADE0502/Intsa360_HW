from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def _check(check_id: str, name: str, ok: bool, message: str, severity: str = "fail") -> dict[str, object]:
    return {
        "id": check_id,
        "name": name,
        "status": "ok" if ok else severity,
        "message": message,
    }


def _read_manifest(root: Path) -> dict[str, object] | None:
    path = root / "install_manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _cadence_autoload_candidates() -> list[Path]:
    bases: list[Path] = []
    for value in [os.environ.get("HOME"), os.environ.get("USERPROFILE"), str(Path.home())]:
        if value:
            path = Path(value)
            if path not in bases:
                bases.append(path)
    return [base / "cdssetup" / "OrCAD_Capture" / "tclscripts" / "capAutoLoad" for base in bases]


def run_self_check(root: Path) -> dict[str, object]:
    manifest = _read_manifest(root)
    checks: list[dict[str, object]] = []

    checks.append(_check("install_root", "安装目录", root.exists() and root.is_dir(), str(root)))
    checks.append(_check("manifest", "安装清单", manifest is not None, "install_manifest.json 可读取" if manifest else "缺少或无法读取 install_manifest.json", "warn"))

    frontend_index = root / "app" / "frontend" / "index.html"
    checks.append(_check("frontend", "前端运行文件", frontend_index.exists(), str(frontend_index)))

    backend_entry = root / "app" / "backend" / "suite_app.py"
    checks.append(_check("backend", "后端入口", backend_entry.exists(), str(backend_entry)))

    python_ok = bool(shutil.which("python")) or (root / "runtime" / "python" / "python.exe").exists() or (root / ".venv" / "Scripts" / "python.exe").exists()
    checks.append(_check("python", "Python 运行时", python_ok, "找到 Python 运行时" if python_ok else "未找到 Python 运行时"))

    required_dirs = ["data", "data/uploads", "data/outputs", "data/history", "data/reports/runtime", "plugins/user/scripts"]
    missing_dirs = [item for item in required_dirs if not (root / item).exists()]
    checks.append(_check("data_dirs", "用户数据目录", not missing_dirs, "用户数据目录完整" if not missing_dirs else "缺少: " + ", ".join(missing_dirs), "warn"))

    config = root / "config" / "local.json"
    checks.append(_check("local_config", "本机配置", config.exists(), str(config), "warn"))

    cadence_dirs = _cadence_autoload_candidates()
    existing_cadence_dirs = [item for item in cadence_dirs if item.exists()]
    checks.append(
        _check(
            "cadence_present",
            "Cadence 环境",
            bool(existing_cadence_dirs),
            str(existing_cadence_dirs[0]) if existing_cadence_dirs else "未检测到 OrCAD Capture 自动加载目录，Cadence 集成不可用",
            "warn",
        )
    )

    cadence_loader = next(
        (item / "iac_bom_tool.tcl" for item in existing_cadence_dirs if (item / "iac_bom_tool.tcl").exists()),
        (cadence_dirs[0] / "iac_bom_tool.tcl") if cadence_dirs else Path("iac_bom_tool.tcl"),
    )
    checks.append(_check("cadence_loader", "Cadence 集成", cadence_loader.exists(), str(cadence_loader), "warn"))

    failed = len([item for item in checks if item["status"] == "fail"])
    warnings = len([item for item in checks if item["status"] == "warn"])
    return {
        "status": "ok",
        "summary": {
            "failed": failed,
            "warnings": warnings,
            "ok": len(checks) - failed - warnings,
            "total": len(checks),
        },
        "manifest": manifest or {},
        "checks": checks,
    }
