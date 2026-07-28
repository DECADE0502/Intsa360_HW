from __future__ import annotations

import json
from pathlib import Path

from app.backend.services.reconnect_protocol import (
    PROTOCOL_KEY_PATH,
    PROTOCOL_LABEL,
    PROTOCOL_OWNER,
    ensure_reconnect_protocol,
)


class _FakeKey:
    def __init__(self, registry: "_FakeRegistry", hive: str, path: str) -> None:
        self.registry = registry
        self.hive = hive
        self.path = path

    def __enter__(self) -> "_FakeKey":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _FakeRegistry:
    HKEY_LOCAL_MACHINE = "HKLM"
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_WRITE = 2
    KEY_WOW64_64KEY = 4
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], dict[str, str]] = {}

    def OpenKey(self, hive: str, path: str, *_args: object) -> _FakeKey:
        if (hive, path) not in self.values:
            raise FileNotFoundError(path)
        return _FakeKey(self, hive, path)

    def CreateKeyEx(self, hive: str, path: str, *_args: object) -> _FakeKey:
        self.values.setdefault((hive, path), {})
        return _FakeKey(self, hive, path)

    def QueryValueEx(self, key: _FakeKey, name: str) -> tuple[str, int]:
        values = self.values[(key.hive, key.path)]
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], self.REG_SZ

    def SetValueEx(self, key: _FakeKey, name: str, _reserved: int, _kind: int, value: str) -> None:
        self.values[(key.hive, key.path)][name] = value


class _WriteDeniedRegistry(_FakeRegistry):
    def CreateKeyEx(self, hive: str, path: str, *_args: object) -> _FakeKey:
        raise PermissionError(f"write denied: {hive}\\{path}")


def _installed_runtime(
    tmp_path: Path,
    *,
    install_relative: Path = Path("HWAgent"),
) -> tuple[Path, Path]:
    install_root = tmp_path / install_relative
    runtime_name = "0.5.8+" + ("a" * 40)
    runtime_root = install_root / "runtime" / runtime_name
    runtime_root.mkdir(parents=True)
    launcher = install_root / "Insta360_HW.exe"
    launcher.write_bytes(b"launcher")
    (install_root / "installation.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "product": "Insta360_HW",
                "layout": "versioned-runtime-v3",
                "active_runtime": f"runtime/{runtime_name}",
            }
        ),
        encoding="utf-8",
    )
    return runtime_root, launcher.resolve()


def _registration_values(launcher: Path) -> dict[str, str]:
    return {
        "": PROTOCOL_LABEL,
        "URL Protocol": "",
        "Owner": PROTOCOL_OWNER,
        "command": f'"{launcher}" "%1"',
    }


def test_repairs_missing_protocol_for_active_installed_runtime(tmp_path: Path) -> None:
    runtime_root, launcher = _installed_runtime(tmp_path)
    registry = _FakeRegistry()

    result = ensure_reconnect_protocol(runtime_root, registry_module=registry)

    assert result == {"status": "repaired", "scope": "user", "launcher": str(launcher)}
    root = registry.values[(registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH)]
    command = registry.values[
        (registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH + r"\shell\open\command")
    ][""]
    assert root == {"": PROTOCOL_LABEL, "URL Protocol": "", "Owner": PROTOCOL_OWNER}
    assert command == f'"{launcher}" "%1"'


def test_uses_actual_custom_install_path_with_spaces_and_unicode(tmp_path: Path) -> None:
    runtime_root, launcher = _installed_runtime(
        tmp_path,
        install_relative=Path("自定义软件目录") / "Insta360 HW Platform",
    )
    registry = _FakeRegistry()

    result = ensure_reconnect_protocol(runtime_root, registry_module=registry)

    command = registry.values[
        (registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH + r"\shell\open\command")
    ][""]
    icon = registry.values[
        (registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH + r"\DefaultIcon")
    ][""]
    assert result["launcher"] == str(launcher)
    assert command == f'"{launcher}" "%1"'
    assert icon == f'"{launcher}",0'


def test_migrates_owned_user_registration_from_previous_install_path(tmp_path: Path) -> None:
    runtime_root, launcher = _installed_runtime(tmp_path)
    registry = _FakeRegistry()
    registry.values[(registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH)] = {
        "": PROTOCOL_LABEL,
        "URL Protocol": "",
        "Owner": PROTOCOL_OWNER,
    }
    registry.values[
        (registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH + r"\shell\open\command")
    ] = {"": r'"D:\Previous Install\Insta360_HW.exe" "%1"'}

    result = ensure_reconnect_protocol(runtime_root, registry_module=registry)

    command = registry.values[
        (registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH + r"\shell\open\command")
    ][""]
    assert result == {"status": "repaired", "scope": "user", "launcher": str(launcher)}
    assert command == f'"{launcher}" "%1"'


def test_keeps_ready_machine_registration_as_primary_authority(tmp_path: Path) -> None:
    runtime_root, launcher = _installed_runtime(tmp_path)
    registry = _FakeRegistry()
    values = _registration_values(launcher)
    registry.values[(registry.HKEY_LOCAL_MACHINE, PROTOCOL_KEY_PATH)] = {
        "": values[""],
        "URL Protocol": values["URL Protocol"],
        "Owner": values["Owner"],
    }
    registry.values[
        (registry.HKEY_LOCAL_MACHINE, PROTOCOL_KEY_PATH + r"\shell\open\command")
    ] = {"": values["command"]}

    result = ensure_reconnect_protocol(runtime_root, registry_module=registry)

    assert result == {"status": "ready", "scope": "machine", "launcher": str(launcher)}
    assert not any(hive == registry.HKEY_CURRENT_USER for hive, _ in registry.values)


def test_owned_stale_machine_registration_gets_current_user_fallback(tmp_path: Path) -> None:
    runtime_root, launcher = _installed_runtime(tmp_path)
    registry = _FakeRegistry()
    registry.values[(registry.HKEY_LOCAL_MACHINE, PROTOCOL_KEY_PATH)] = {
        "": PROTOCOL_LABEL,
        "URL Protocol": "",
        "Owner": PROTOCOL_OWNER,
    }
    registry.values[
        (registry.HKEY_LOCAL_MACHINE, PROTOCOL_KEY_PATH + r"\shell\open\command")
    ] = {"": r'"C:\Removed Install\Insta360_HW.exe" "%1"'}

    result = ensure_reconnect_protocol(runtime_root, registry_module=registry)

    user_command = registry.values[
        (registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH + r"\shell\open\command")
    ][""]
    assert result == {"status": "repaired", "scope": "user", "launcher": str(launcher)}
    assert user_command == f'"{launcher}" "%1"'


def test_does_not_override_foreign_machine_registration(tmp_path: Path) -> None:
    runtime_root, _ = _installed_runtime(tmp_path)
    registry = _FakeRegistry()
    registry.values[(registry.HKEY_LOCAL_MACHINE, PROTOCOL_KEY_PATH)] = {
        "": "URL:Another application",
        "URL Protocol": "",
        "Owner": "AnotherApplication",
    }

    result = ensure_reconnect_protocol(runtime_root, registry_module=registry)

    assert result == {"status": "conflict", "scope": "machine"}
    assert not any(hive == registry.HKEY_CURRENT_USER for hive, _ in registry.values)


def test_does_not_override_foreign_user_registration(tmp_path: Path) -> None:
    runtime_root, _ = _installed_runtime(tmp_path)
    registry = _FakeRegistry()
    registry.values[(registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH)] = {
        "": "URL:Another application",
        "URL Protocol": "",
        "Owner": "AnotherApplication",
    }

    result = ensure_reconnect_protocol(runtime_root, registry_module=registry)

    assert result == {"status": "conflict", "scope": "user"}
    assert registry.values[(registry.HKEY_CURRENT_USER, PROTOCOL_KEY_PATH)]["Owner"] == "AnotherApplication"


def test_reports_user_registry_write_denial_without_breaking_backend_startup(tmp_path: Path) -> None:
    runtime_root, _ = _installed_runtime(tmp_path)

    result = ensure_reconnect_protocol(runtime_root, registry_module=_WriteDeniedRegistry())

    assert result["status"] == "error"
    assert "write denied" in result["error"]


def test_ignores_inactive_or_uninstalled_runtime(tmp_path: Path) -> None:
    runtime_root, _ = _installed_runtime(tmp_path)
    metadata_path = runtime_root.parent.parent / "installation.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["active_runtime"] = "runtime/0.5.7+" + ("b" * 40)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    registry = _FakeRegistry()

    result = ensure_reconnect_protocol(runtime_root, registry_module=registry)

    assert result == {"status": "not_installed"}
    assert registry.values == {}
