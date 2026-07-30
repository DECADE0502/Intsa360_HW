from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient
from openpyxl import Workbook
from PIL import Image

from app.backend.main import create_app


BASE_URL = "http://127.0.0.1:8765"
SESSION_HEADER = "X-Insta360-Session"


def _headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/v1/session").json()["token"]
    return {SESSION_HEADER: token, "Origin": BASE_URL}


def _runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "VERSION").write_text("0.5.11\n", encoding="utf-8")
    upload = root / "data" / "uploads" / "smt-session"
    source = upload / "vendor-package"
    source.mkdir(parents=True)
    (source / "placement-export.data").write_text(
        "\n".join(
            [
                "VERSION=2.0",
                "UUNITS=MM",
                "C1 ! 0 ! 0 ! 0 !  ! C0402",
                "C2 ! 10 ! 0 ! 0 !  ! C0402",
                "C3 ! 0 ! 10 ! 0 !  ! C0402",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    Image.new("RGB", (400, 300), "white").save(source / "board.png")

    bom = upload / "processed.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["子项编码", "描述", "数量", "位号"])
    sheet.append(["PN-C", "电容", 2, "C1,C2"])
    workbook.save(bom)
    workbook.close()
    return root, source, bom


def test_run_confirmation_registration_and_decision_survive_reload(tmp_path: Path) -> None:
    root, source, bom = _runtime(tmp_path)
    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _headers(client)
        started = client.post(
            "/api/v1/smt-analysis/runs",
            headers=headers,
            json={"smt_folder": str(source), "processed_bom": str(bom)},
        )
        assert started.status_code == 200, started.text
        initial = started.json()
        assert initial["state"] == "needs_confirmation"
        assert len(initial["coordinate_sets"]) == 1
        assert len(initial["drawing_pages"]) == 1

        coordinate_set = initial["coordinate_sets"][0]
        page = initial["drawing_pages"][0]
        confirmed = client.post(
            f"/api/v1/smt-analysis/runs/{initial['run_id']}/sources/confirm",
            headers=headers,
            json={
                "coordinate_set_id": coordinate_set["coordinate_set_id"],
                "scope_semantics": "full_design_set",
                "pages": {page["page_id"]: "top"},
                "side_mapping": {},
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        confirmed_payload = confirmed.json()
        state_by_ref = {
            item["ref"]: item["assembly_state"]
            for item in confirmed_payload["placements"]
        }
        assert state_by_ref == {
            "C1": "installed",
            "C2": "installed",
            "C3": "confirmed_nc",
        }

        registered = client.post(
            f"/api/v1/smt-analysis/runs/{initial['run_id']}/registrations",
            headers=headers,
            json={
                "coordinate_set_id": coordinate_set["coordinate_set_id"],
                "page_id": page["page_id"],
                "side": "top",
                "model": "similarity",
                "confirmed": True,
                "anchors": [
                    {
                        "anchor_id": "a1",
                        "ref": "C1",
                        "coordinate_x": 0,
                        "coordinate_y": 0,
                        "image_x": 50,
                        "image_y": 50,
                        "source": "user",
                        "inlier": True,
                    },
                    {
                        "anchor_id": "a2",
                        "ref": "C2",
                        "coordinate_x": 10,
                        "coordinate_y": 0,
                        "image_x": 150,
                        "image_y": 50,
                        "source": "user",
                        "inlier": True,
                    },
                    {
                        "anchor_id": "a3",
                        "ref": "C3",
                        "coordinate_x": 0,
                        "coordinate_y": 10,
                        "image_x": 50,
                        "image_y": 150,
                        "source": "user",
                        "inlier": True,
                    },
                ],
            },
        )
        assert registered.status_code == 200, registered.text
        registered_payload = registered.json()
        assert registered_payload["state"] == "review"
        assert registered_payload["blocking_reasons"] == []
        assert all(
            item["image_x"] is not None
            for item in registered_payload["placements"]
            if item["coordinate_occurrence_ids"]
        )

        c3 = next(
            item
            for item in registered_payload["placements"]
            if item["ref"] == "C3"
        )
        decided = client.post(
            (
                f"/api/v1/smt-analysis/runs/{initial['run_id']}"
                f"/placements/{c3['placement_id']}/decision"
            ),
            headers=headers,
            json={
                "action": "confirm_nc",
                "role": "smt_component",
                "reason": "人工复核",
            },
        )
        assert decided.status_code == 200, decided.text
        reloaded = client.get(
            f"/api/v1/smt-analysis/runs/{initial['run_id']}"
        ).json()
        reloaded_c3 = next(
            item for item in reloaded["placements"] if item["ref"] == "C3"
        )
        assert reloaded_c3["decision"]["reason"] == "人工复核"

        finalized = client.post(
            f"/api/v1/smt-analysis/runs/{initial['run_id']}/finalize",
            headers=headers,
        )
        assert finalized.status_code == 200, finalized.text
        assert finalized.json()["state"] == "deliver"

        exported = client.post(
            f"/api/v1/smt-analysis/runs/{initial['run_id']}/export",
            headers=headers,
        )
        assert exported.status_code == 200, exported.text
        delivery = exported.json()
        assert delivery["status"] == "ok"
        assert {
            artifact["label"] for artifact in delivery["artifacts"]
        } >= {"SMT装配审查报告", "SMT装配审查快照", "正面位号标注图"}

        package = client.get(
            f"/outputs/{quote(delivery['package_path'], safe='/')}"
        )
        assert package.status_code == 200
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            assert set(archive.namelist()) == {
                "SMT装配审查报告.xlsx",
                "SMT装配审查快照.json",
                "正面位号标注图.png",
            }
            assert archive.testzip() is None

        preview = client.get(page["preview_url"])
        assert preview.status_code == 200
        assert preview.headers["content-type"].startswith("image/png")


def test_identical_inputs_reuse_run_and_paths_cannot_escape_data_root(
    tmp_path: Path,
) -> None:
    root, source, bom = _runtime(tmp_path)
    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _headers(client)
        request = {"smt_folder": str(source), "processed_bom": str(bom)}
        first = client.post(
            "/api/v1/smt-analysis/runs",
            headers=headers,
            json=request,
        )
        second = client.post(
            "/api/v1/smt-analysis/runs",
            headers=headers,
            json=request,
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["run_id"] == second.json()["run_id"]

        outside = tmp_path / "outside"
        outside.mkdir()
        escaped = client.post(
            "/api/v1/smt-analysis/runs",
            headers=headers,
            json={"smt_folder": str(outside), "processed_bom": str(bom)},
        )
        assert escaped.status_code == 400
        assert "平台数据目录" in escaped.json()["user_message"]
