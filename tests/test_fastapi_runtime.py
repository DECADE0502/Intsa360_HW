from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.main import create_app


def test_health_reports_the_selected_runtime_identity(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    (runtime_root / "VERSION").write_text("0.4.0\n", encoding="utf-8")
    (runtime_root / "REVISION").write_text("test-revision\n", encoding="utf-8")

    application = create_app(runtime_root)
    assert isinstance(application, FastAPI)

    with TestClient(application, base_url="http://127.0.0.1:8765") as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "Insta360_HW",
        "schema_version": "v1",
        "runtime_root": str(runtime_root.resolve()),
        "version": "0.4.0",
        "revision": "test-revision",
    }
