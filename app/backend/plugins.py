from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from app.backend.capabilities import load_capabilities, set_cadence_menu_visibility
from app.backend.paths import AppPaths


PLUGIN_MENU = "insta360_HW"
DEFAULT_CADENCE_SYSTEM_SCRIPT_DIRS = [
    Path(r"D:\CADENCE\Cadence\SPB_17.4\tools\capture\tclscripts\capAutoLoad"),
]


def _safe_plugin_child(base: Path, requested: str) -> Path:
    target = (base / requested).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"plugin path escapes plugin root: {requested}") from exc
    return target


def _script_dirs(system_script_dirs: Iterable[Path] | None) -> list[Path]:
    dirs = list(system_script_dirs) if system_script_dirs is not None else DEFAULT_CADENCE_SYSTEM_SCRIPT_DIRS
    return [Path(item) for item in dirs]


def _plugin_id_from_official_script(path: Path) -> str:
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("_") or path.stem
    return f"cadence_official.{safe_stem}"


def _official_cadence_plugins(system_script_dirs: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    plugins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for directory in _script_dirs(system_script_dirs):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.tcl")):
            plugin_id = _plugin_id_from_official_script(path)
            if plugin_id in seen:
                continue
            seen.add(plugin_id)
            plugins.append(
                {
                    "id": plugin_id,
                    "name": path.stem,
                    "description": f"Cadence official autoload script: {path}",
                    "category": "Cadence 系统脚本",
                    "type": "cadence_tcl",
                    "source": "system",
                    "readonly": True,
                    "manageable": False,
                    "menu": "Cadence capAutoLoad",
                    "status": "available",
                    "path": str(path),
                    "module": str(path),
                    "show_in_platform": True,
                    "show_in_cadence": False,
                    "can_enable": False,
                    "requires_confirmation": False,
                    "danger_level": "low",
                }
            )
    return plugins


def _platform_plugin_from_capability(platform: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    plugin = dict(item)
    plugin["source"] = "platform"
    plugin["readonly"] = False
    plugin["manageable"] = True
    plugin["menu"] = platform.get("cadence_menu") or PLUGIN_MENU
    plugin.setdefault("description", "")
    plugin.setdefault("category", "平台脚本")
    plugin.setdefault("status", "available" if plugin.get("show_in_cadence") else "disabled")
    plugin.setdefault("show_in_platform", True)
    plugin.setdefault("show_in_cadence", False)
    plugin.setdefault("can_enable", True)
    plugin.setdefault("requires_confirmation", False)
    plugin.setdefault("danger_level", "medium")
    if plugin.get("module"):
        plugin["module"] = str(plugin["module"]).replace("\\", "/")
    return plugin


def _platform_plugins_from_capabilities(root: Path) -> list[dict[str, Any]]:
    data = load_capabilities(root)
    platform = data.get("platform", {})
    return [
        _platform_plugin_from_capability(platform, item)
        for item in data.get("capabilities", [])
        if item.get("type") == "cadence_tcl"
    ]


def _load_manifest(path: Path, source: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"plugin manifest must be object: {path}")
    for key in ["id", "name", "type", "command"]:
        if not data.get(key):
            raise ValueError(f"plugin manifest missing {key}: {path}")
    plugin = dict(data)
    plugin["manifest"] = str(path)
    plugin["source"] = source
    plugin["readonly"] = source == "system"
    plugin["manageable"] = source in {"platform", "user"}
    plugin["menu"] = PLUGIN_MENU
    plugin.setdefault("description", "")
    plugin.setdefault("category", "Cadence 脚本" if source == "system" else "自定义脚本")
    plugin.setdefault("status", "available" if plugin.get("show_in_cadence") else "disabled")
    plugin.setdefault("show_in_platform", True)
    plugin.setdefault("show_in_cadence", False)
    plugin.setdefault("can_enable", True)
    plugin.setdefault("requires_confirmation", False)
    plugin.setdefault("danger_level", "medium")

    if plugin.get("type") == "cadence_tcl":
        script = str(plugin.get("script") or plugin.get("module") or "").strip()
        if not script:
            raise ValueError(f"cadence_tcl plugin missing script: {path}")
        base = path.parent
        script_path = _safe_plugin_child(base, script)
        try:
            relative = script_path.relative_to(path.parents[2])
            plugin["module"] = relative.as_posix()
        except ValueError:
            plugin["module"] = script_path.as_posix()
        plugin["script"] = script.replace("\\", "/")
    return plugin


def _manifest_plugins(root: Path, source: str, warnings: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    directory = AppPaths(root).user_plugins_dir if source == "user" else root / "plugins" / source
    if not directory.exists():
        return []
    plugins: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            plugins.append(_load_manifest(path, source))
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            if warnings is not None:
                warnings.append({"source": source, "path": str(path), "message": str(exc)})
    return plugins


def load_plugins(root: Path, system_script_dirs: Iterable[Path] | None = None) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    system = _official_cadence_plugins(system_script_dirs)
    platform = _platform_plugins_from_capabilities(root) + _manifest_plugins(root, "platform", warnings)
    user = _manifest_plugins(root, "user", warnings)
    plugins = system + platform + user
    return {
        "platform": {"name": "Insta360硬件提效平台", "cadence_menu": PLUGIN_MENU},
        "plugins": plugins,
        "groups": {"system": system, "platform": platform, "user": user},
        "warnings": warnings,
        "summary": {
            "total": len(plugins),
            "system": len(system),
            "platform": len(platform),
            "user": len(user),
            "enabled": len([item for item in plugins if item.get("show_in_cadence") is True]),
        },
    }


def _find_user_manifest(root: Path, plugin_id: str) -> tuple[Path, dict[str, Any]]:
    directory = AppPaths(root).user_plugins_dir
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(data, dict):
                continue
            if str(data.get("id")) == plugin_id:
                return path, data
    raise KeyError(f"未找到插件: {plugin_id}")


def set_plugin_cadence_menu_visibility(
    root: Path,
    plugin_id: str,
    show_in_cadence: bool,
    system_script_dirs: Iterable[Path] | None = None,
) -> dict[str, Any]:
    platform_plugins = {item["id"]: item for item in _platform_plugins_from_capabilities(root)}
    if plugin_id in platform_plugins:
        updated = set_cadence_menu_visibility(root, plugin_id, show_in_cadence)
        platform = load_capabilities(root).get("platform", {})
        return _platform_plugin_from_capability(platform, updated)

    official_ids = {item["id"] for item in _official_cadence_plugins(system_script_dirs)}
    if plugin_id in official_ids:
        raise PermissionError("Cadence 系统脚本只能查看，不能由平台启停或挂载")

    path, data = _find_user_manifest(root, plugin_id)
    if data.get("type") != "cadence_tcl":
        raise ValueError("只有 Cadence Tcl 插件可以挂载到 Cadence 菜单")
    if show_in_cadence and not data.get("command"):
        raise ValueError("插件缺少 command，无法挂载")

    data["show_in_cadence"] = bool(show_in_cadence)
    data["status"] = "available" if show_in_cadence else "disabled"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _load_manifest(path, "user")
