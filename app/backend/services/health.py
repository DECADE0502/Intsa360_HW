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
    if not state_path.is_file():
        return {
            "status": "not_configured",
            "state_path": str(state_path),
            "enabled": None,
            "loader_paths": [],
            "owned_loader_count": 0,
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
            "enabled": None,
            "loader_paths": [],
            "owned_loader_count": 0,
            "error": str(exc),
        }

    owned_loaders: list[str] = []
    for value in loader_paths:
        directory = Path(value)
        loader = directory if directory.name.casefold() == CADENCE_LOADER.casefold() else directory / CADENCE_LOADER
        try:
            if loader.is_file() and CADENCE_MARKER in loader.read_text(encoding="utf-8-sig", errors="replace"):
                owned_loaders.append(str(loader))
        except OSError:
            continue
    if not enabled:
        status = "disabled"
    elif owned_loaders:
        status = "ok"
    else:
        status = "missing"
    return {
        "status": status,
        "state_path": str(state_path),
        "enabled": enabled,
        "loader_paths": loader_paths,
        "owned_loaders": owned_loaders,
        "owned_loader_count": len(owned_loaders),
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
