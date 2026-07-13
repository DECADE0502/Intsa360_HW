from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from app.backend.paths import AppPaths


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a JSON object: {path}")
    return data


def load_config(root: Path) -> dict[str, Any]:
    config_dir = root / "config"
    default_config = _read_json(config_dir / "default.json")
    local_path = AppPaths(root).local_config_path
    if not local_path.exists() and (config_dir / "local.json").exists():
        local_path = config_dir / "local.json"
    if not local_path.exists():
        return default_config

    return _deep_merge(default_config, _read_json(local_path))
