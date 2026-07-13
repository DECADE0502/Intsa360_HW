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


def load_capabilities(root: Path) -> dict[str, Any]:
    path = root / "config" / "capabilities.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_capabilities(data)
    overrides_path = AppPaths(root).capability_overrides_path
    if overrides_path.exists():
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            overrides = {}
        if isinstance(overrides, dict):
            for item in data["capabilities"]:
                override = overrides.get(str(item["id"]))
                if isinstance(override, bool) and item.get("type") == "cadence_tcl":
                    item["show_in_cadence"] = override
                    item["status"] = "available" if override else "disabled"
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

    target["show_in_cadence"] = bool(show_in_cadence)
    target["status"] = "available" if show_in_cadence else "disabled"
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
