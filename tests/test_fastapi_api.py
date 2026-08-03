from __future__ import annotations

import inspect
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend import suite_app
from app.backend.main import create_app


ROOT = Path(__file__).resolve().parents[1]


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    shutil.copytree(ROOT / "config", root / "config")
    shutil.copytree(ROOT / "cadence", root / "cadence")
    shutil.copytree(ROOT / "app" / "frontend", root / "app" / "frontend")
    (root / "VERSION").write_text("0.4.0\n", encoding="utf-8")
    (root / "REVISION").write_text("0123456789abcdef\n", encoding="utf-8")
    return root


def test_versioned_and_legacy_tool_routes_share_one_fastapi_handler(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)

    with TestClient(create_app(root), base_url="http://127.0.0.1:8765") as client:
        canonical = client.get("/api/v1/tools")
        legacy = client.get("/api/tools")

    assert canonical.status_code == 200
    assert legacy.status_code == 200
    assert canonical.json() == legacy.json()
    assert len(canonical.json()["tools"]) == 8


def test_legacy_suite_app_contains_only_server_compatibility_adapter() -> None:
    source = inspect.getsource(suite_app)

    assert "BaseHTTPRequestHandler" not in source
    assert "ThreadingHTTPServer" not in source
    assert "def do_GET" not in source
    assert "def do_POST" not in source
    assert "def do_DELETE" not in source
    assert '"/api/' not in source
