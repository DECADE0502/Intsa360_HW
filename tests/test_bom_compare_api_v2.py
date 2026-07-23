from __future__ import annotations

import runpy
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.main import create_app
from app.backend.tools.bom_compare import run_bom_compare


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tests" / "fixtures" / "bom_semantics" / "build_fixtures.py"
BASE_URL = "http://127.0.0.1:8765"


def _fixtures(tmp_path: Path) -> dict[str, Path]:
    return runpy.run_path(str(BUILDER))["build_all"](tmp_path)


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    (root / "config").mkdir(parents=True)
    (root / "data" / "uploads").mkdir(parents=True)
    (root / "VERSION").write_text("0.5.5\n", encoding="utf-8")
    shutil.copy2(ROOT / "config" / "capabilities.json", root / "config" / "capabilities.json")
    return root


def _headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/v1/session").json()["token"]
    return {
        "X-Insta360-Session": token,
        "Origin": BASE_URL,
    }


def test_inspect_returns_schema_v2_quality_and_substitute_summary(tmp_path: Path) -> None:
    path = _fixtures(tmp_path)["substitutes"]

    result = run_bom_compare(tmp_path, {"action": "inspect", "source": str(path)})

    assert result["status"] == "ok"
    assert result["schema_version"] == 2
    assert result["action"] == "inspect"
    assert result["summary"]["parent_codes"] == ["BOARD-A"]
    assert result["summary"]["actual_reference_count"] == 4
    assert result["summary"]["substitute_group_count"] == 1
    assert result["inspection"]["can_compare"] is True


def test_legacy_two_file_request_keeps_workbench_and_adds_semantic_layers(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)

    result = run_bom_compare(
        tmp_path,
        {
            "bom1": str(paths["ordinary"]),
            "bom2": str(paths["substitutes"]),
            "output_dir": str(tmp_path / "outputs"),
        },
    )

    assert result["status"] == "ok"
    assert result["schema_version"] == 2
    assert result["compare"]["key_label"] == "位号"
    assert result["semantic"]["summary"]["actual_reference_count_new"] == 4
    assert len(result["semantic"]["placement_diff"]) > 0
    assert result["source_inspections"]["new"]["boards"][0]["placement_count"] == 4
    assert "rows" not in result["source_inspections"]["new"]["boards"][0]
    assert len(result["outputs"]) == 3
    assert all(Path(path).is_file() for path in result["outputs"])


def test_api_compare_records_semantic_summary_without_refresh(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    paths = _fixtures(runtime / "data" / "uploads")
    app = create_app(runtime)

    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            "/api/v1/tools/bom_compare/run",
            json={
                "action": "compare",
                "bom1": str(paths["ordinary"]),
                "bom2": str(paths["substitutes"]),
                "output_dir": "bom_compare",
            },
            headers=_headers(client),
        )
        history = client.get("/api/v1/history").json()["runs"]

    assert response.status_code == 200
    assert response.json()["schema_version"] == 2
    assert history[0]["tool"] == "bom_compare"
    assert history[0]["summary"]["semantic"]["analysis_fingerprint"]
    assert history[0]["summary"]["semantic"]["substitute_group_count_new"] == 1
