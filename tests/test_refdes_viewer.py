from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.main import create_app
from app.backend.services.refdes_viewer_service import RefdesViewerService


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8765"


def _minimal_pdf(labels: list[tuple[str, int, int]], *, size: int = 200) -> bytes:
    """Build a one-page PDF whose vector text layer carries the given labels.

    Hand-rolled so the fixture stays deterministic and needs no writer library.
    """
    content = "".join(
        f"BT /F1 8 Tf {x} {y} Td ({text}) Tj ET\n" for text, x, y in labels
    ).encode("ascii")
    objects: list[bytes] = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        (
            f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 {size} {size}]"
            "/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>"
        ).encode("ascii"),
        b"<</Length " + str(len(content)).encode("ascii") + b">>\nstream\n" + content + b"endstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    (root / "config").mkdir(parents=True)
    (root / "data" / "uploads").mkdir(parents=True)
    (root / "VERSION").write_text("0.5.8\n", encoding="utf-8")
    shutil.copy2(ROOT / "config" / "capabilities.json", root / "config" / "capabilities.json")
    return root


def _headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/v1/session").json()["token"]
    return {"X-Insta360-Session": token, "Origin": BASE_URL}


def _service_with(tmp_path: Path, pdf_bytes: bytes) -> tuple[RefdesViewerService, Path]:
    root = _runtime(tmp_path)
    drawing = root / "data" / "uploads" / "drawing.pdf"
    drawing.write_bytes(pdf_bytes)
    return RefdesViewerService(root), drawing


def test_pdf_alone_yields_every_printed_ref_with_positions(tmp_path: Path) -> None:
    service, drawing = _service_with(
        tmp_path,
        _minimal_pdf([("C1", 20, 180), ("R2", 100, 100), ("U3A", 150, 40)]),
    )

    document = service.open(str(drawing))

    assert document.page_count == 1
    page = document.pages[0]
    assert {item.ref for item in page.occurrences} == {"C1", "R2", "U3A"}
    assert page.text_layer == "vector"
    assert document.ref_count == 3
    assert not document.notices


def test_positions_follow_the_printed_layout(tmp_path: Path) -> None:
    # PDF user space grows upward; preview pixels grow downward.
    service, drawing = _service_with(
        tmp_path,
        _minimal_pdf([("C1", 20, 180), ("C2", 20, 20)]),
    )

    page = service.open(str(drawing)).pages[0]
    by_ref = {item.ref: item for item in page.occurrences}

    assert by_ref["C1"].y < by_ref["C2"].y
    assert all(0 <= item.x <= page.pixel_width for item in page.occurrences)
    assert all(0 <= item.y <= page.pixel_height for item in page.occurrences)


def test_repeated_ref_keeps_every_occurrence(tmp_path: Path) -> None:
    service, drawing = _service_with(
        tmp_path,
        _minimal_pdf([("C1", 20, 180), ("C1", 120, 60)]),
    )

    page = service.open(str(drawing)).pages[0]

    assert page.ref_count == 1
    assert page.occurrence_count == 2
    assert len({item.occurrence_id for item in page.occurrences}) == 2


def test_drawing_without_text_layer_is_reported_not_silently_empty(tmp_path: Path) -> None:
    service, drawing = _service_with(tmp_path, _minimal_pdf([]))

    document = service.open(str(drawing))

    assert document.ref_count == 0
    assert any("没有可提取的位号文字" in notice for notice in document.notices)


def test_reopening_the_same_drawing_is_stable(tmp_path: Path) -> None:
    service, drawing = _service_with(tmp_path, _minimal_pdf([("C1", 20, 180)]))

    first = service.open(str(drawing))
    second = service.open(str(drawing))

    assert first.doc_id == second.doc_id
    assert service.get(first.doc_id).ref_count == 1


def test_sources_outside_the_data_directory_are_rejected(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(_minimal_pdf([("C1", 20, 180)]))

    service = RefdesViewerService(root)

    try:
        service.open(str(outside))
    except ValueError as exc:
        assert "不在允许的目录内" in str(exc)
    else:
        raise AssertionError("path outside the data directory should be rejected")


def test_api_opens_a_drawing_and_serves_its_page_image(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    drawing = root / "data" / "uploads" / "drawing.pdf"
    drawing.write_bytes(_minimal_pdf([("C1", 20, 180), ("R2", 100, 100)]))

    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _headers(client)
        response = client.post(
            "/api/v1/refdes-viewer/docs",
            json={"path": str(drawing)},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        document = response.json()
        assert document["ref_count"] == 2

        page = document["pages"][0]
        preview = client.get(page["preview_url"], headers=headers)
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/png"
        assert preview.content.startswith(b"\x89PNG")

        reread = client.get(
            f"/api/v1/refdes-viewer/docs/{document['doc_id']}", headers=headers
        )
        assert reread.status_code == 200
        assert reread.json()["ref_count"] == 2


def test_api_reports_unknown_documents_as_not_found(tmp_path: Path) -> None:
    root = _runtime(tmp_path)

    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _headers(client)
        missing = client.get(
            "/api/v1/refdes-viewer/docs/doc-" + "0" * 24, headers=headers
        )
        assert missing.status_code == 404

        invalid = client.get("/api/v1/refdes-viewer/docs/not-a-doc", headers=headers)
        assert invalid.status_code == 400


def test_real_assembly_drawing_when_opted_in(tmp_path: Path) -> None:
    raw = os.environ.get("SMT_REAL_SAMPLE_DIR", "")
    if not raw:
        return
    folder = Path(raw)
    source = next(path for path in folder.glob("*.pdf") if "SMD" in path.name.upper())
    root = _runtime(tmp_path)
    drawing = root / "data" / "uploads" / source.name
    shutil.copy2(source, drawing)

    document = RefdesViewerService(root).open(str(drawing))

    assert document.page_count == 2
    assert document.ref_count > 300
    for page in document.pages:
        # Every printed refdes must be locatable, otherwise the list cannot
        # navigate to it.
        assert page.occurrence_count >= page.ref_count > 0
        assert page.pixel_width >= 1500
    assert {page.side_guess for page in document.pages} == {"top", "bottom"}
