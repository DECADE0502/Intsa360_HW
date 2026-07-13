from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STATE_ROOT_ENV = "INSTA360_HW_STATE_ROOT"
PRODUCT = "Insta360_HW"
INSTALL_SCHEMA = 2


def _resolve_root(value: Path | str, *, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path == path.parent:
        raise ValueError(f"{label} must not be a filesystem root: {path}")
    return path


def _is_development_root(root: Path) -> bool:
    return (root / ".git").exists() or (root / "pyproject.toml").is_file()


def _read_install_manifest(root: Path) -> dict[str, Any] | None:
    path = root / "install_manifest.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"runtime install manifest is invalid: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("runtime install manifest must be an object")
    if raw.get("product") != PRODUCT:
        raise ValueError("runtime install manifest does not identify Insta360_HW")
    if type(raw.get("schema")) is not int or raw["schema"] != INSTALL_SCHEMA:
        raise ValueError("runtime install manifest has an unsupported schema")
    if raw.get("layout") != "runtime-v2":
        raise ValueError("runtime install manifest has an unsupported layout")
    return raw


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_state_root(runtime_root: Path, state_root: Path, *, installed: bool) -> Path:
    if state_root == state_root.parent:
        raise ValueError(f"state root must not be a filesystem root: {state_root}")
    if not installed:
        return state_root
    if state_root == runtime_root or _is_within(state_root, runtime_root):
        raise ValueError("installed mutable state must be outside the immutable runtime root")
    if _is_within(runtime_root, state_root):
        raise ValueError("state root must not be a parent of the installed runtime root")
    return state_root


def resolve_state_root(runtime_root: Path) -> Path:
    """Resolve the stable mutable-state root for one runtime identity."""
    runtime = _resolve_root(runtime_root, label="runtime root")
    development = _is_development_root(runtime)
    install_manifest = None if development else _read_install_manifest(runtime)
    installed = install_manifest is not None and not development

    explicit = os.environ.get(STATE_ROOT_ENV, "").strip()
    if explicit:
        state = _resolve_root(explicit, label="state root")
    elif development or not installed:
        state = runtime
    else:
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if not local_app_data:
            raise RuntimeError("LOCALAPPDATA is required for an installed Insta360_HW runtime")
        state = _resolve_root(Path(local_app_data) / PRODUCT, label="state root")
    return _validate_state_root(runtime, state, installed=installed)


@dataclass(frozen=True)
class AppPaths:
    root: Path
    state_root_override: Path | None = None

    @property
    def runtime_root(self) -> Path:
        return _resolve_root(self.root, label="runtime root")

    @property
    def is_development(self) -> bool:
        return _is_development_root(self.runtime_root)

    @property
    def is_installed(self) -> bool:
        if self.is_development:
            return False
        return _read_install_manifest(self.runtime_root) is not None

    @property
    def state_root(self) -> Path:
        if self.state_root_override is not None:
            state = _resolve_root(self.state_root_override, label="state root")
            return _validate_state_root(self.runtime_root, state, installed=self.is_installed)
        return resolve_state_root(self.runtime_root)

    @property
    def data_dir(self) -> Path:
        return self.state_root / "data"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def runtime_log_dir(self) -> Path:
        return self.data_dir / "reports" / "runtime"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def history_dir(self) -> Path:
        return self.data_dir / "history"

    @property
    def config_dir(self) -> Path:
        return self.state_root / "config"

    @property
    def local_config_path(self) -> Path:
        return self.config_dir / "local.json"

    @property
    def capability_overrides_path(self) -> Path:
        return self.config_dir / "capability_overrides.json"

    @property
    def user_plugins_dir(self) -> Path:
        return self.state_root / "plugins" / "user"

    @property
    def lifecycle_dir(self) -> Path:
        return self.state_root / "lifecycle"

    @property
    def lifecycle_jobs_dir(self) -> Path:
        return self.lifecycle_dir / "jobs"

    @property
    def lifecycle_transactions_dir(self) -> Path:
        return self.lifecycle_dir / "transactions"

    @property
    def lifecycle_cache_dir(self) -> Path:
        return self.lifecycle_dir / "cache"

    def ensure_runtime_dirs(self) -> None:
        for path in (
            self.state_root,
            self.data_dir,
            self.inbox_dir,
            self.outputs_dir,
            self.runtime_log_dir,
            self.uploads_dir,
            self.history_dir,
            self.config_dir,
            self.user_plugins_dir / "scripts",
            self.lifecycle_jobs_dir,
            self.lifecycle_transactions_dir,
            self.lifecycle_cache_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
