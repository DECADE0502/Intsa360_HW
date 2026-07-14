from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend import assets, history
from app.backend.main import create_app
from app.backend.paths import AppPaths
from app.backend.repositories.database import PlatformDatabase
from app.backend.services.diagnostics import build_diagnostic_package
from app.backend.services.platform_logging import (
    DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_BYTES,
    close_platform_logging,
    configure_platform_logging,
)


BASE_URL = "http://127.0.0.1:8765"


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "VERSION").write_text("0.4.0\n", encoding="utf-8")
    (root / "REVISION").write_text("observability-test\n", encoding="utf-8")
    return root


def test_health_reports_factual_process_database_and_cadence_state(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    PlatformDatabase(root)
    loader = root / "cadence-test" / "iac_bom_tool.tcl"
    loader.parent.mkdir()
    loader.write_text("# Insta360_HW Cadence Loader | schema=2 | managed=true\n", encoding="utf-8")
    (root / "cadence_integration.json").write_text(
        json.dumps({"schema_version": 2, "enabled": True, "loader_paths": [str(loader.parent)]}),
        encoding="utf-8",
    )
    ownership = root / "cadence" / "integration_manifest.json"
    ownership.parent.mkdir()
    ownership.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product": "Insta360_HW",
                "owned_files": [{"kind": "capture_loader", "path": str(loader), "sha256": ""}],
            }
        ),
        encoding="utf-8",
    )
    app = create_app(root)

    with TestClient(app, base_url=BASE_URL) as client:
        payload = client.get("/api/v1/health").json()

    assert payload["status"] == "ok"
    assert payload["pid"] == os.getpid()
    assert Path(payload["executable"]).resolve() == Path(sys.executable).resolve()
    assert payload["runtime_root"] == str(root.resolve())
    assert payload["state_root"] == str(root.resolve())
    assert payload["version"] == "0.4.0"
    assert payload["revision"] == "observability-test"
    assert payload["uptime_seconds"] >= 0
    assert payload["database"]["status"] == "ok"
    assert payload["database"]["quick_check"] == "ok"
    assert payload["database"]["migrations"] == [1, 2]
    assert payload["cadence"]["status"] == "ok"
    assert payload["cadence"]["manifest_status"] == "ok"
    assert payload["cadence"]["ownership_manifest_path"] == str(ownership)
    assert payload["cadence"]["owned_loader_count"] == 1


def test_structured_logs_rotate_and_redact_session_secrets(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    secret = "local-session-secret-123"
    logger = configure_platform_logging(root, secrets=[secret], max_bytes=700, backup_count=2)
    try:
        for index in range(60):
            logger.info(
                "request token=%s item=%s",
                secret,
                index,
                extra={
                    "event": "test_request",
                    "context": {
                        "session_token": secret,
                        "Authorization": f"Bearer {secret}",
                        "item": index,
                    },
                },
            )
    finally:
        close_platform_logging(logger)

    files = sorted(AppPaths(root).runtime_log_dir.glob("platform.jsonl*"))
    assert DEFAULT_MAX_BYTES == 20 * 1024 * 1024
    assert DEFAULT_BACKUP_COUNT == 5
    assert 2 <= len(files) <= 3
    combined = "".join(path.read_text(encoding="utf-8") for path in files)
    assert secret not in combined
    assert "[REDACTED]" in combined
    for line in combined.splitlines():
        payload = json.loads(line)
        assert {"timestamp", "level", "event", "message"} <= payload.keys()


def test_diagnostic_package_excludes_user_files_until_assets_are_explicitly_selected(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    output = root / "data" / "outputs" / "bom" / "PRIVATE_BOARD_PLM_BOM.xlsx"
    output.parent.mkdir(parents=True)
    private_content = b"PRIVATE-BOM-CONTENT-MUST-NOT-LEAK"
    output.write_bytes(private_content)
    history.record(root, "bom_process", "BOM 处理", {}, {"status": "ok", "outputs": [str(output)]})
    asset = assets.list_assets(root)["groups"]["processed_bom"][0]
    secret = "diagnostic-session-secret"
    logger = configure_platform_logging(root, secrets=[secret])
    try:
        logger.info("session=%s", secret, extra={"event": "secret_test"})
    finally:
        close_platform_logging(logger)
    disguised_user_file = AppPaths(root).runtime_log_dir / "private-bom.xlsx"
    disguised_user_file.write_bytes(private_content)

    default_package = build_diagnostic_package(root, secrets=[secret])
    with zipfile.ZipFile(io.BytesIO(default_package)) as archive:
        default_names = archive.namelist()
        default_payload = b"".join(archive.read(name) for name in default_names)
    assert "diagnostic_report.txt" in default_names
    assert "health.json" in default_names
    assert not any(name.startswith("selected_assets/") for name in default_names)
    assert "logs/private-bom.xlsx" not in default_names
    assert private_content not in default_payload
    assert secret.encode("utf-8") not in default_payload

    selected_package = build_diagnostic_package(root, selected_asset_ids=[asset["id"]], secrets=[secret])
    with zipfile.ZipFile(io.BytesIO(selected_package)) as archive:
        selected_names = archive.namelist()
        selected_payload = b"".join(archive.read(name) for name in selected_names)
    assert any(name.startswith(f"selected_assets/{asset['id']}/") for name in selected_names)
    assert private_content in selected_payload


def test_diagnostic_package_api_requires_session_only_when_selecting_user_assets(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    app = create_app(root)

    with TestClient(app, base_url=BASE_URL) as client:
        default_response = client.get("/api/v1/diagnostics/package")
        denied = client.post("/api/v1/diagnostics/package", json={"asset_ids": []})
        token = client.get("/api/v1/session").json()["token"]
        selected = client.post(
            "/api/v1/diagnostics/package",
            json={"asset_ids": []},
            headers={"X-Insta360-Session": token, "Origin": BASE_URL},
        )

    assert default_response.status_code == 200
    assert default_response.headers["content-type"] == "application/zip"
    assert denied.status_code == 403
    assert selected.status_code == 200
    assert selected.headers["content-type"] == "application/zip"


def test_offline_diagnostic_script_uses_the_packaging_service() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "collect_diagnostics.ps1"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "app.backend.services.diagnostics" in text
    assert "[string]$OutputPath" in text
