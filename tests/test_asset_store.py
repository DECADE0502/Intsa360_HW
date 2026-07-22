from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.backend import assets, history
from app.backend.main import create_app
from app.backend.paths import AppPaths
from app.backend.repositories.assets_repository import AssetsRepository
from app.backend.repositories.database import PlatformDatabase
from app.backend.repositories.runs_repository import RunsRepository


BASE_URL = "http://127.0.0.1:8765"


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "VERSION").write_text("0.4.0\n", encoding="utf-8")
    return root


def test_database_creates_versioned_asset_and_run_schema(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    database = PlatformDatabase(root)

    with database.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        versions = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()

    assert {"assets", "runs", "run_inputs", "run_outputs", "schema_migrations", "repository_state"} <= tables
    assert versions == [(1,), (2,)]
    assert AppPaths(root).platform_database_path.is_file()


def test_successful_run_promotes_inputs_and_outputs_in_one_store(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    source = root / "data" / "uploads" / "session-a" / "source.xlsx"
    output = root / "data" / "outputs" / "bom" / "BOARD_A_PLM_BOM.xlsx"
    source.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    output.write_bytes(b"processed")

    run_id = history.record(
        root,
        "bom_process",
        "BOM 处理",
        {"source_bom": str(source)},
        {"status": "ok", "summary": {"records": 12}, "outputs": [str(output)]},
    )

    assert run_id is not None
    UUID(run_id)
    with sqlite3.connect(AppPaths(root).platform_database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM run_inputs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM run_outputs").fetchone()[0] == 1
        relative_paths = {row[0] for row in connection.execute("SELECT relative_path FROM assets")}
    assert relative_paths == {"uploads/session-a/source.xlsx", "outputs/bom/BOARD_A_PLM_BOM.xlsx"}

    listed = history.list_runs(root)
    reusable = assets.list_assets(root)["groups"]["processed_bom"]
    assert listed[0]["id"] == run_id
    assert listed[0]["outputs"] == ["bom/BOARD_A_PLM_BOM.xlsx"]
    assert reusable[0]["run_id"] == run_id
    assert reusable[0]["path"] == str(output)
    UUID(reusable[0]["id"])


def test_processed_bom_asset_exposes_contract_matched_decision_manifest(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    output_dir = root / "data" / "outputs" / "bom"
    output_dir.mkdir(parents=True)
    bom = output_dir / "BOARD_A_PLM_BOM.xlsx"
    manifest = output_dir / "renamed-machine-readable-output.json"
    bom.write_bytes(b"processed")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "rule_version": "2.0.0",
                "source_fingerprint": "source",
                "placements": [],
            }
        ),
        encoding="utf-8",
    )
    history.record(
        root,
        "bom_process",
        "BOM 处理",
        {},
        {"status": "ok", "outputs": [str(bom), str(manifest)]},
    )

    reusable = assets.list_assets(root)["groups"]["processed_bom"]

    assert reusable[0]["path"] == str(bom)
    assert reusable[0]["decision_manifest"] == str(manifest)


def test_legacy_json_history_migration_is_idempotent_and_keeps_subdirectories(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    first = root / "data" / "outputs" / "alpha" / "BOARD_PLM_BOM.xlsx"
    second = root / "data" / "outputs" / "beta" / "BOARD_PLM_BOM.xlsx"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    index = root / "data" / "history" / "index.json"
    index.parent.mkdir(parents=True)
    index.write_text(
        json.dumps(
            [
                {
                    "id": "legacy_alpha",
                    "time": "2026-01-01 10:00:00",
                    "tool": "bom_process",
                    "tool_name": "BOM 处理",
                    "outputs": ["alpha/BOARD_PLM_BOM.xlsx"],
                },
                {
                    "id": "legacy_beta",
                    "time": "2026-01-01 11:00:00",
                    "tool": "bom_process",
                    "tool_name": "BOM 处理",
                    "outputs": ["beta/BOARD_PLM_BOM.xlsx"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    first_listing = history.list_runs(root)
    second_listing = history.list_runs(root)
    reusable = assets.list_assets(root)["groups"]["processed_bom"]

    assert len(first_listing) == len(second_listing) == 2
    assert {item["id"] for item in first_listing} == {item["id"] for item in second_listing}
    assert all(UUID(item["id"]) for item in first_listing)
    assert {item["path"] for item in reusable} == {str(first), str(second)}
    with sqlite3.connect(AppPaths(root).platform_database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 2


def test_completed_legacy_migration_skips_scans_after_new_records(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    output = root / "data" / "outputs" / "bom" / "BOARD_PLM_BOM.xlsx"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"bom")
    for index in range(2):
        history.record(
            root,
            "bom_process",
            "BOM 处理",
            {},
            {"status": "ok", "outputs": [str(output)], "summary": {"index": index}},
        )

    with patch.object(RunsRepository, "_legacy_entries", side_effect=AssertionError("legacy scan repeated")) as scan:
        RunsRepository(root)

    scan.assert_not_called()


def test_asset_metadata_rebuild_rehashes_files_and_marks_missing_assets(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    output = root / "data" / "outputs" / "bom" / "BOARD_PLM_BOM.xlsx"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"old")
    history.record(root, "bom_process", "BOM 处理", {}, {"status": "ok", "outputs": [str(output)]})
    repository = AssetsRepository(root)
    asset = repository.list()[0]

    output.write_bytes(b"new-content")
    rebuilt = repository.rebuild_metadata(asset.id)

    assert rebuilt["updated"] == 1
    refreshed = repository.get(asset.id)
    assert refreshed.size == len(b"new-content")
    assert refreshed.sha256 == hashlib.sha256(b"new-content").hexdigest()
    assert refreshed.metadata.get("missing") is not True

    output.unlink()
    missing = repository.rebuild_metadata(asset.id)
    assert missing == {"updated": 1, "missing": 1}
    assert repository.get(asset.id).metadata["missing"] is True


def test_assets_rebuild_endpoint_uses_session_protection(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    output = root / "data" / "outputs" / "bom" / "BOARD_PLM_BOM.xlsx"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"bom")
    history.record(root, "bom_process", "BOM 处理", {}, {"status": "ok", "outputs": [str(output)]})
    app = create_app(root)

    with TestClient(app, base_url=BASE_URL) as client:
        denied = client.post("/api/v1/assets/rebuild")
        token = client.get("/api/v1/session").json()["token"]
        accepted = client.post(
            "/api/v1/assets/rebuild",
            headers={"X-Insta360-Session": token, "Origin": BASE_URL},
        )

    assert denied.status_code == 403
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ok"
    assert accepted.json()["updated"] == 1


def test_deleted_run_is_not_reimported_from_its_compatibility_mirror(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    output = root / "data" / "outputs" / "bom" / "BOARD_PLM_BOM.xlsx"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"bom")
    run_id = history.record(root, "bom_process", "BOM 处理", {}, {"status": "ok", "outputs": [str(output)]})
    assert run_id is not None

    assert history.remove_run(root, run_id) is True

    assert history.list_runs(root) == []
    assert history.get_run(root, run_id) is None


def test_unwritable_legacy_index_does_not_break_sqlite_history(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    output = root / "data" / "outputs" / "bom" / "BOARD_PLM_BOM.xlsx"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"bom")
    legacy_index = root / "data" / "history" / "index.json"
    legacy_index.mkdir(parents=True)

    run_id = history.record(root, "bom_process", "BOM 处理", {}, {"status": "ok", "outputs": [str(output)]})

    assert run_id is not None
    assert history.list_runs(root)[0]["id"] == run_id
    assert history.get_run(root, run_id) is not None
