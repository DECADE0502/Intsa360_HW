from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.backend.api.context import AppContext


CADENCE_LOADER = "iac_bom_tool.tcl"
CADENCE_MARKER = "# Insta360_HW Cadence Loader | schema=2 | managed=true"
CADENCE_OWNERSHIP_SCHEMA = 1


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def _database_health(context: "AppContext") -> dict[str, object]:
    path = context.paths.platform_database_path
    result: dict[str, object] = {
        "status": "not_initialized",
        "path": str(path),
        "exists": path.is_file(),
        "size": path.stat().st_size if path.is_file() else 0,
        "quick_check": "not_run",
        "migrations": [],
    }
    if not path.is_file():
        return result
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(path), timeout=1.0)
        connection.execute("PRAGMA query_only = ON")
        quick_check = str(connection.execute("PRAGMA quick_check(1)").fetchone()[0])
        migrations = [
            int(row[0])
            for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        ]
        result.update(
            status="ok" if quick_check.casefold() == "ok" else "degraded",
            quick_check=quick_check,
            migrations=migrations,
        )
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        result.update(status="error", quick_check="failed", error=str(exc))
    finally:
        if connection is not None:
            connection.close()
    return result


def _cadence_health(context: "AppContext") -> dict[str, object]:
    state_path = context.paths.state_root / "cadence_integration.json"
    ownership_path = context.paths.state_root / "cadence" / "integration_manifest.json"
    manifest_status = "missing"
    manifest_loader_paths: list[str] = []
    manifest_error = ""
    if ownership_path.is_file():
        try:
            manifest = json.loads(ownership_path.read_text(encoding="utf-8-sig"))
            if not isinstance(manifest, dict):
                raise ValueError("Cadence ownership manifest must be an object")
            if manifest.get("schema_version") != CADENCE_OWNERSHIP_SCHEMA or manifest.get("product") != "Insta360_HW":
                raise ValueError("Cadence ownership manifest identity is invalid")
            for entry in manifest.get("owned_files") or []:
                if not isinstance(entry, dict) or entry.get("kind") != "capture_loader":
                    continue
                value = str(entry.get("path") or "").strip()
                if value and Path(value).name.casefold() == CADENCE_LOADER.casefold():
                    manifest_loader_paths.append(value)
            manifest_status = "ok"
        except (OSError, ValueError, TypeError) as exc:
            manifest_status = "error"
            manifest_error = str(exc)

    if not state_path.is_file():
        return {
            "status": "not_configured",
            "state_path": str(state_path),
            "ownership_manifest_path": str(ownership_path),
            "manifest_status": manifest_status,
            "enabled": None,
            "loader_paths": [],
            "owned_loader_count": 0,
            **({"manifest_error": manifest_error} if manifest_error else {}),
        }
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError("Cadence integration state must be an object")
        enabled = bool(raw.get("enabled"))
        loader_paths = [str(value) for value in raw.get("loader_paths") or [] if str(value).strip()]
    except (OSError, ValueError, TypeError) as exc:
        return {
            "status": "error",
            "state_path": str(state_path),
            "ownership_manifest_path": str(ownership_path),
            "manifest_status": manifest_status,
            "enabled": None,
            "loader_paths": [],
            "owned_loader_count": 0,
            "error": str(exc),
            **({"manifest_error": manifest_error} if manifest_error else {}),
        }

    owned_loaders: list[str] = []
    seen: set[str] = set()
    for value in [*loader_paths, *manifest_loader_paths]:
        directory = Path(value)
        loader = directory if directory.name.casefold() == CADENCE_LOADER.casefold() else directory / CADENCE_LOADER
        normalized = str(loader.resolve())
        if normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        try:
            if loader.is_file() and CADENCE_MARKER in loader.read_text(encoding="utf-8-sig", errors="replace"):
                owned_loaders.append(normalized)
        except OSError:
            continue
    if not enabled:
        status = "disabled"
    elif manifest_status == "error":
        status = "degraded"
    elif owned_loaders:
        status = "ok"
    else:
        status = "missing"
    return {
        "status": status,
        "state_path": str(state_path),
        "ownership_manifest_path": str(ownership_path),
        "manifest_status": manifest_status,
        "enabled": enabled,
        "loader_paths": loader_paths,
        "owned_loaders": owned_loaders,
        "owned_loader_count": len(owned_loaders),
        **({"manifest_error": manifest_error} if manifest_error else {}),
    }


def collect_health(context: "AppContext") -> dict[str, object]:
    uptime = max(0.0, time.monotonic() - context.started_monotonic)
    database = _database_health(context)
    cadence = _cadence_health(context)
    status = "ok" if database["status"] not in {"error", "degraded"} else "degraded"
    return {
        "status": status,
        "service": "Insta360_HW",
        "schema_version": "v1",
        "pid": os.getpid(),
        "executable": str(Path(sys.executable).resolve()),
        "runtime_root": str(context.root.resolve()),
        "state_root": str(context.paths.state_root),
        "version": _read_text(context.root / "VERSION") or "0.0.0",
        "revision": _read_text(context.root / "REVISION"),
        "started_at": context.started_at.isoformat(),
        "uptime_seconds": round(uptime, 3),
        "database": database,
        "cadence": cadence,
    }
