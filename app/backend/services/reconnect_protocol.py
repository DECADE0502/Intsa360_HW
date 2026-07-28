from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


PROTOCOL_KEY_PATH = r"Software\Classes\insta360-hw"
PROTOCOL_LABEL = "URL:Insta360_HW reconnect protocol"
PROTOCOL_OWNER = "Insta360_HW"


@dataclass(frozen=True)
class _Registration:
    exists: bool = False
    owned: bool = False
    ready: bool = False


def _resolve_installed_launcher(runtime_root: Path) -> Path | None:
    runtime = runtime_root.resolve()
    if runtime.parent.name.casefold() != "runtime":
        return None
    install_root = runtime.parent.parent
    metadata_path = install_root / "installation.json"
    launcher = install_root / "Insta360_HW.exe"
    if not metadata_path.is_file() or not launcher.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, dict):
        return None
    if (
        metadata.get("schema_version") != 3
        or metadata.get("product") != "Insta360_HW"
        or metadata.get("layout") != "versioned-runtime-v3"
    ):
        return None
    active_runtime = str(metadata.get("active_runtime") or "").replace("\\", "/")
    parts = [part for part in active_runtime.split("/") if part]
    if not parts or active_runtime.startswith("/") or any(part in {".", ".."} for part in parts):
        return None
    active_path = (install_root.joinpath(*parts)).resolve()
    try:
        active_path.relative_to(install_root.resolve())
    except ValueError:
        return None
    if active_path != runtime:
        return None
    return launcher.resolve()


def _query_value(registry: Any, key: Any, name: str) -> tuple[bool, str]:
    try:
        value, _ = registry.QueryValueEx(key, name)
    except OSError:
        return False, ""
    return True, str(value or "")


def _read_registration(registry: Any, hive: Any, key_path: str, expected_command: str) -> _Registration:
    access = registry.KEY_READ
    if hive == registry.HKEY_LOCAL_MACHINE:
        access |= getattr(registry, "KEY_WOW64_64KEY", 0)
    try:
        key = registry.OpenKey(hive, key_path, 0, access)
    except OSError:
        return _Registration()
    with key:
        _, label = _query_value(registry, key, "")
        _, owner = _query_value(registry, key, "Owner")
        protocol_value_exists, _ = _query_value(registry, key, "URL Protocol")
    command_path = key_path + r"\shell\open\command"
    try:
        command_key = registry.OpenKey(hive, command_path, 0, access)
    except OSError:
        command = ""
    else:
        with command_key:
            _, command = _query_value(registry, command_key, "")
    legacy_owned = label == PROTOCOL_LABEL and command.casefold() == expected_command.casefold()
    owned = owner == PROTOCOL_OWNER or legacy_owned
    ready = owned and protocol_value_exists and command.casefold() == expected_command.casefold()
    return _Registration(exists=True, owned=owned, ready=ready)


def _write_user_registration(registry: Any, key_path: str, launcher: Path) -> None:
    command = f'"{launcher}" "%1"'
    with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, key_path, 0, registry.KEY_WRITE) as key:
        registry.SetValueEx(key, "", 0, registry.REG_SZ, PROTOCOL_LABEL)
        registry.SetValueEx(key, "URL Protocol", 0, registry.REG_SZ, "")
        registry.SetValueEx(key, "Owner", 0, registry.REG_SZ, PROTOCOL_OWNER)
    with registry.CreateKeyEx(
        registry.HKEY_CURRENT_USER,
        key_path + r"\DefaultIcon",
        0,
        registry.KEY_WRITE,
    ) as key:
        registry.SetValueEx(key, "", 0, registry.REG_SZ, f'"{launcher}",0')
    with registry.CreateKeyEx(
        registry.HKEY_CURRENT_USER,
        key_path + r"\shell\open\command",
        0,
        registry.KEY_WRITE,
    ) as key:
        registry.SetValueEx(key, "", 0, registry.REG_SZ, command)


def ensure_reconnect_protocol(
    runtime_root: Path,
    *,
    registry_module: Any | None = None,
    key_path: str = PROTOCOL_KEY_PATH,
) -> dict[str, str]:
    launcher = _resolve_installed_launcher(runtime_root)
    if launcher is None:
        return {"status": "not_installed"}
    if registry_module is None:
        if os.name != "nt":
            return {"status": "not_windows"}
        import winreg as registry_module

    expected_command = f'"{launcher}" "%1"'
    try:
        machine = _read_registration(
            registry_module,
            registry_module.HKEY_LOCAL_MACHINE,
            key_path,
            expected_command,
        )
        if machine.ready:
            return {"status": "ready", "scope": "machine", "launcher": str(launcher)}
        if machine.exists and not machine.owned:
            return {"status": "conflict", "scope": "machine"}

        user = _read_registration(
            registry_module,
            registry_module.HKEY_CURRENT_USER,
            key_path,
            expected_command,
        )
        if user.ready:
            return {"status": "ready", "scope": "user", "launcher": str(launcher)}
        if user.exists and not user.owned:
            return {"status": "conflict", "scope": "user"}

        _write_user_registration(registry_module, key_path, launcher)
        repaired = _read_registration(
            registry_module,
            registry_module.HKEY_CURRENT_USER,
            key_path,
            expected_command,
        )
        if not repaired.ready:
            return {"status": "error", "scope": "user", "error": "verification_failed"}
        return {"status": "repaired", "scope": "user", "launcher": str(launcher)}
    except OSError as exc:
        return {"status": "error", "error": str(exc)}
