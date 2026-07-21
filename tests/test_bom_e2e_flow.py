from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app.backend.main import create_app


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8765"
SESSION_HEADER = "X-Insta360-Session"


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    shutil.copytree(ROOT / "config", root / "config")
    (root / "VERSION").write_text("0.4.0\n", encoding="utf-8")
    (root / "REVISION").write_text("0123456789abcdef\n", encoding="utf-8")
    return root


def _source_bom() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "Item",
            "Quantity",
            "Reference",
            "Part Number",
            "Value",
            "Model",
            "Description",
            "Name",
            "Unit",
        ]
    )
    sheet.append([1, 1, "SH1", "SH-PN", "SHIELD", "BRACKET-A", "Shield bracket", "Shield bracket", "pcs"])
    sheet.append([2, 1, "R1", "P1", "10K", "M1", "Description A", "Resistor", "pcs"])
    sheet.append([3, 1, "R2", "P1", "10K", "M2", "Description B", "Resistor", "pcs"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _process_material_source_bom() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Reference", "Part Number", "Value", "Model", "Description", "Name", "Unit"])
    sheet.append(["TP5", "TP-PN", "", "PROBE-A", "测试点 探针", "探针", "pcs"])
    sheet.append(["R1", "R-PN", "10K", "R0402", "普通贴片电阻", "电阻", "pcs"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _mutation_headers(client: TestClient) -> dict[str, str]:
    session = client.get("/api/v1/session")
    assert session.status_code == 200
    return {SESSION_HEADER: session.json()["token"], "Origin": BASE_URL}


def test_bom_process_confirmation_package_and_history_flow(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _mutation_headers(client)
        upload = client.post(
            "/api/v1/upload",
            files={"files": ("source.xlsx", _source_bom(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=headers,
        )
        assert upload.status_code == 200, upload.text
        source = upload.json()["files"][0]["path"]
        params: dict[str, object] = {
            "source_bom": source,
            "formats": ["plm"],
            "parent_code": "203010100819",
            "parent_desc": "E2E board",
            "name": "E2E_BOARD",
        }

        shield_review = client.post("/api/v1/tools/bom_process/run", json=params, headers=headers)
        assert shield_review.status_code == 200, shield_review.text
        assert shield_review.json()["status"] == "needs_confirmation"
        assert shield_review.json()["reason"] == "shield_bracket_candidates"
        assert shield_review.json()["shield_candidates"][0]["refs"] == ["SH1"]

        params["confirm_shields"] = True
        conflict_review = client.post("/api/v1/tools/bom_process/run", json=params, headers=headers)
        assert conflict_review.status_code == 200, conflict_review.text
        assert conflict_review.json()["status"] == "needs_confirmation"
        assert conflict_review.json()["reason"] == "part_property_conflicts"
        conflict = conflict_review.json()["conflicts"][0]
        assert conflict["code"] == "P1"

        params["merge_conflicts"] = True
        params["conflict_choices"] = {"P1": conflict["recommended_index"]}
        completed = client.post("/api/v1/tools/bom_process/run", json=params, headers=headers)
        assert completed.status_code == 200, completed.text
        result = completed.json()
        assert result["status"] == "ok"
        assert any(Path(item).name.endswith("_PLM_BOM.xlsx") for item in result["outputs"])
        assert any(Path(item).name.endswith("_NC未贴汇总.xlsx") for item in result["outputs"])

        package = client.post(
            "/api/package",
            json={"name": "E2E_BOARD", "files": result["outputs"]},
            headers=headers,
        )
        assert package.status_code == 200, package.text
        assert package.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            names = archive.namelist()
            assert any(name.endswith("_PLM_BOM.xlsx") for name in names)
            assert any(name.endswith("_NC未贴汇总.xlsx") for name in names)

        history = client.get("/api/history")
        assert history.status_code == 200, history.text
        assert any(
            run.get("tool") == "bom_process" and run.get("status") == "succeeded"
            for run in history.json()["runs"]
        )


def test_e2e_rejected_shield_stays_out_of_plm_and_keeps_raw_nc_name(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _mutation_headers(client)
        upload = client.post(
            "/api/v1/upload",
            files={"files": ("source.xlsx", _source_bom(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=headers,
        )
        assert upload.status_code == 200, upload.text
        params: dict[str, object] = {
            "source_bom": upload.json()["files"][0]["path"],
            "formats": ["plm"],
            "parent_code": "203010100819",
            "parent_desc": "E2E board",
            "name": "E2E_REJECT_SH",
        }

        shield_review = client.post("/api/v1/tools/bom_process/run", json=params, headers=headers)
        assert shield_review.json()["reason"] == "shield_bracket_candidates"

        params["confirm_shields"] = False
        conflict_review = client.post("/api/v1/tools/bom_process/run", json=params, headers=headers)
        conflict = conflict_review.json()["conflicts"][0]
        params["merge_conflicts"] = True
        params["conflict_choices"] = {"P1": conflict["recommended_index"]}
        completed = client.post("/api/v1/tools/bom_process/run", json=params, headers=headers)
        assert completed.status_code == 200, completed.text
        result = completed.json()
        assert result["status"] == "ok"

        plm_path = next(Path(path) for path in result["outputs"] if path.endswith("_PLM_BOM.xlsx"))
        nc_path = next(Path(path) for path in result["outputs"] if path.endswith("_NC未贴汇总.xlsx"))
        plm = load_workbook(plm_path, data_only=True)
        nc = load_workbook(nc_path, data_only=True)
        try:
            plm_refs = [str(row[8] or "") for row in plm.active.iter_rows(min_row=3, values_only=True)]
            nc_rows = list(nc.active.iter_rows(min_row=2, values_only=True))
        finally:
            plm.close()
            nc.close()

        assert all("SH1" not in refs for refs in plm_refs)
        shield_nc = next(row for row in nc_rows if row[2] == "SH-PN")
        assert shield_nc[1] == "SH1"
        assert shield_nc[3] == "Shield bracket"


def test_e2e_partnumber_tp_kept_by_user_choice(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _mutation_headers(client)
        upload = client.post(
            "/api/v1/upload",
            files={"files": ("source.xlsx", _process_material_source_bom(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=headers,
        )
        source = upload.json()["files"][0]["path"]
        params: dict[str, object] = {"source_bom": source, "formats": ["plm"], "name": "KEEP_TP"}

        review = client.post("/api/v1/tools/bom_process/run", json=params, headers=headers).json()
        assert review["reason"] == "process_material_candidates"
        params["confirm_process_materials"] = True
        params["process_material_keeps"] = [review["candidates"][0]["key"]]
        result = client.post("/api/v1/tools/bom_process/run", json=params, headers=headers).json()

        plm_path = next(Path(path) for path in result["outputs"] if path.endswith("_PLM_BOM.xlsx"))
        plm = load_workbook(plm_path, data_only=True)
        try:
            refs = [str(row[8] or "") for row in plm.active.iter_rows(min_row=3, values_only=True)]
        finally:
            plm.close()
        assert any("TP5" in item for item in refs)


def test_e2e_partnumber_tp_default_nc(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _mutation_headers(client)
        upload = client.post(
            "/api/v1/upload",
            files={"files": ("source.xlsx", _process_material_source_bom(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=headers,
        )
        params: dict[str, object] = {
            "source_bom": upload.json()["files"][0]["path"],
            "formats": ["plm"],
            "name": "DEFAULT_NC",
            "confirm_process_materials": True,
            "process_material_keeps": [],
        }

        result = client.post("/api/v1/tools/bom_process/run", json=params, headers=headers).json()
        nc_path = next(Path(path) for path in result["outputs"] if path.endswith("_NC未贴汇总.xlsx"))
        nc = load_workbook(nc_path, data_only=True)
        try:
            rows = list(nc.active.iter_rows(min_row=2, values_only=True))
        finally:
            nc.close()
        tp = next(row for row in rows if row[1] == "TP5")
        assert str(tp[7]).startswith("工艺件（描述含 测试点）")
