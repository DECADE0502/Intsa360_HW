from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.backend.paths import AppPaths


REQUIRED_KEYS = {
    "id",
    "type",
    "name",
    "description",
    "category",
    "status",
    "show_in_platform",
    "show_in_cadence",
}

PLUGIN_STATE_SCHEMA = 1


class PluginStateRepository:
    """Persistent enablement state shared by the backend and Cadence renderer."""

    def __init__(self, root: Path) -> None:
        self.paths = AppPaths(root)

    @property
    def path(self) -> Path:
        return self.paths.plugin_state_path

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": PLUGIN_STATE_SCHEMA, "plugins": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": PLUGIN_STATE_SCHEMA, "plugins": {}}
        if not isinstance(data, dict) or data.get("schema_version") != PLUGIN_STATE_SCHEMA:
            return {"schema_version": PLUGIN_STATE_SCHEMA, "plugins": {}}

        plugins = data.get("plugins")
        if not isinstance(plugins, dict):
            return {"schema_version": PLUGIN_STATE_SCHEMA, "plugins": {}}

        normalized: dict[str, dict[str, bool]] = {}
        for plugin_id, value in plugins.items():
            if isinstance(value, dict) and type(value.get("enabled")) is bool:
                normalized[str(plugin_id)] = {"enabled": value["enabled"]}
        return {"schema_version": PLUGIN_STATE_SCHEMA, "plugins": normalized}

    def enabled(self, plugin_id: str, default: bool) -> bool:
        entry = self._load()["plugins"].get(plugin_id)
        return entry["enabled"] if entry is not None else default

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        data = self._load()
        data["plugins"][plugin_id] = {"enabled": bool(enabled)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _apply_plugin_state(data: dict[str, Any], repository: PluginStateRepository) -> None:
    for item in data["capabilities"]:
        if item.get("type") != "cadence_tcl":
            continue
        enabled = repository.enabled(str(item["id"]), bool(item.get("show_in_cadence")))
        item["show_in_cadence"] = enabled
        item["status"] = "available" if enabled else "disabled"


def load_capabilities(root: Path) -> dict[str, Any]:
    path = root / "config" / "capabilities.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_capabilities(data)
    _apply_plugin_state(data, PluginStateRepository(root))
    return data


def validate_capabilities(data: dict[str, Any]) -> None:
    if data.get("platform", {}).get("name") != "Insta360硬件提效平台":
        raise ValueError("平台名称必须为 Insta360硬件提效平台")
    if data.get("platform", {}).get("cadence_menu") != "insta360_HW":
        raise ValueError("Cadence 菜单必须为 insta360_HW")

    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("capabilities must be a list")

    seen: set[str] = set()
    for item in capabilities:
        if not isinstance(item, dict):
            raise ValueError("capability item must be object")
        missing = REQUIRED_KEYS - set(item)
        if missing:
            raise ValueError(f"{item.get('id', '<unknown>')} 缺少字段: {', '.join(sorted(missing))}")
        item_id = str(item["id"])
        if item_id in seen:
            raise ValueError(f"重复能力 id: {item_id}")
        seen.add(item_id)
        if item["type"] == "cadence_tcl" and "command" not in item:
            raise ValueError(f"Cadence 脚本缺少 command: {item_id}")


def set_cadence_menu_visibility(root: Path, capability_id: str, show_in_cadence: bool) -> dict[str, Any]:
    data = load_capabilities(root)

    target: Optional[dict[str, Any]] = None
    for item in data["capabilities"]:
        if str(item["id"]) == capability_id:
            target = item
            break
    if target is None:
        raise KeyError(f"未找到能力: {capability_id}")
    if target["type"] != "cadence_tcl":
        raise ValueError("只有 Cadence Tcl 脚本可以挂载到 Cadence 菜单")
    if show_in_cadence and (target.get("can_enable") is not True or not target.get("module")):
        raise ValueError("该脚本尚未拆分为安全模块，暂不能挂载到 Cadence 菜单")
    if show_in_cadence:
        module_path = (root / str(target["module"])).resolve()
        try:
            module_path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"Cadence Tcl module escapes runtime root: {target['module']}") from exc
        if not module_path.is_file():
            raise ValueError(f"Cadence Tcl module does not exist: {module_path}")

    target["show_in_cadence"] = bool(show_in_cadence)
    target["status"] = "available" if show_in_cadence else "disabled"
    PluginStateRepository(root).set_enabled(capability_id, bool(show_in_cadence))

    # Keep the old file as a write-only compatibility mirror; plugin_state.json is read authority.
    overrides_path = AppPaths(root).capability_overrides_path
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        overrides = json.loads(overrides_path.read_text(encoding="utf-8-sig")) if overrides_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        overrides = {}
    if not isinstance(overrides, dict):
        overrides = {}
    overrides[capability_id] = bool(show_in_cadence)
    overrides_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
