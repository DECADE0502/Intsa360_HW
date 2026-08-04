from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.main import create_app
from app.backend.refdes import PageRenderer, open_drawing
from app.backend.refdes.render import plan_pixels
from app.backend.services.refdes_service import RefdesService


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8765"


def _minimal_pdf(
    pages: list[list[tuple[str, int, int]]],
    *,
    size: int = 200,
) -> bytes:
    """Build a PDF whose vector text layer carries the given per-page labels.

    Hand-rolled so the fixture is deterministic and needs no writer library.
    """
    objects: list[bytes] = [b"", b""]  # catalog and pages, filled in below
    page_refs: list[int] = []
    for labels in pages:
        content = "".join(
            f"BT /F1 8 Tf {x} {y} Td ({text}) Tj ET\n" for text, x, y in labels
        ).encode("ascii")
        content_index = len(objects) + 1
        page_index = content_index + 1
        objects.append(
            b"<</Length " + str(len(content)).encode("ascii") + b">>\nstream\n" + content + b"endstream"
        )
        objects.append(
            (
                f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 {size} {size}]"
                f"/Resources<</Font<</F1 {{FONT}} 0 R>>>>/Contents {content_index} 0 R>>"
            ).encode("ascii")
        )
        page_refs.append(page_index)
    font_index = len(objects) + 1
    objects.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    objects[0] = b"<</Type/Catalog/Pages 2 0 R>>"
    kids = " ".join(f"{ref} 0 R" for ref in page_refs)
    objects[1] = (
        f"<</Type/Pages/Kids[{kids}]/Count {len(page_refs)}>>"
    ).encode("ascii")
    objects = [item.replace(b"{FONT}", str(font_index).encode("ascii")) for item in objects]

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
    (root / "VERSION").write_text("0.5.15\n", encoding="utf-8")
    shutil.copy2(ROOT / "config" / "capabilities.json", root / "config" / "capabilities.json")
    return root


def _headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/v1/session").json()["token"]
    return {"X-Insta360-Session": token, "Origin": BASE_URL}


def _service(tmp_path: Path, pdf: bytes) -> tuple[RefdesService, Path]:
    root = _runtime(tmp_path)
    drawing = root / "data" / "uploads" / "drawing.pdf"
    drawing.write_bytes(pdf)
    return RefdesService(root), drawing


# ------------------------------------------------------------------ reading


def test_drawing_alone_yields_every_printed_ref(tmp_path: Path) -> None:
    service, path = _service(
        tmp_path, _minimal_pdf([[("C1", 20, 180), ("R2", 100, 100), ("U3A", 150, 40)]])
    )

    drawing = service.open(str(path))

    assert drawing.page_count == 1
    assert {mark.ref for mark in drawing.pages[0].marks} == {"C1", "R2", "U3A"}
    assert drawing.ref_count == 3
    assert not drawing.notices


def test_marks_are_normalised_and_follow_the_printed_layout(tmp_path: Path) -> None:
    # PDF user space grows upward; normalised marks grow downward.
    service, path = _service(tmp_path, _minimal_pdf([[("C1", 20, 180), ("C2", 20, 20)]]))

    page = service.open(str(path)).pages[0]
    by_ref = {mark.ref: mark for mark in page.marks}

    assert by_ref["C1"].y < by_ref["C2"].y
    for mark in page.marks:
        assert 0.0 <= mark.x <= 1.0
        assert 0.0 <= mark.y <= 1.0
        assert mark.left <= mark.right
        assert mark.top <= mark.bottom


def test_repeated_ref_keeps_every_printed_instance(tmp_path: Path) -> None:
    service, path = _service(tmp_path, _minimal_pdf([[("C1", 20, 180), ("C1", 120, 60)]]))

    page = service.open(str(path)).pages[0]

    assert page.ref_count == 1
    assert len(page.marks) == 2
    assert len({mark.order for mark in page.marks}) == 2


def test_two_page_drawing_is_labelled_top_then_bottom(tmp_path: Path) -> None:
    service, path = _service(
        tmp_path, _minimal_pdf([[("C1", 20, 180)], [("C2", 20, 180)]])
    )

    drawing = service.open(str(path))

    assert [page.side_guess for page in drawing.pages] == ["top", "bottom"]


def test_drawing_without_text_layer_is_reported_not_silently_empty(tmp_path: Path) -> None:
    service, path = _service(tmp_path, _minimal_pdf([[]]))

    drawing = service.open(str(path))

    assert drawing.ref_count == 0
    assert any("没有可提取的位号文字" in notice for notice in drawing.notices)


def test_reopening_the_same_drawing_is_stable(tmp_path: Path) -> None:
    service, path = _service(tmp_path, _minimal_pdf([[("C1", 20, 180)]]))

    first = service.open(str(path))
    second = service.open(str(path))

    assert first.drawing_id == second.drawing_id
    assert service.get(first.drawing_id).ref_count == 1


def test_sources_outside_the_data_directory_are_rejected(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(_minimal_pdf([[("C1", 20, 180)]]))

    try:
        RefdesService(root).open(str(outside))
    except ValueError as exc:
        assert "不在允许的目录内" in str(exc)
    else:
        raise AssertionError("path outside the data directory should be rejected")


# ---------------------------------------------------------------- rendering


def test_opening_never_rasterises_pages(tmp_path: Path) -> None:
    """Opening must stay cheap: page images are rendered only when requested."""
    service, path = _service(
        tmp_path, _minimal_pdf([[("C1", 20, 180)] for _ in range(12)])
    )

    drawing = service.open(str(path))
    cached = list(service.cache_dir.rglob("*.png"))

    assert drawing.page_count == 12
    assert cached == []


def test_page_image_is_rendered_on_demand_then_cached(tmp_path: Path) -> None:
    service, path = _service(tmp_path, _minimal_pdf([[("C1", 20, 180)], [("C2", 20, 180)]]))
    drawing = service.open(str(path))

    image, media_type = service.page_image(drawing.drawing_id, 1)

    assert media_type == "image/png"
    assert image.is_file()
    # Only the requested page was rasterised.
    assert len(list(service.cache_dir.rglob("*.png"))) == 1

    again, _ = service.page_image(drawing.drawing_id, 1)
    assert again == image
    assert len(list(service.cache_dir.rglob("*.png"))) == 1


def test_reported_page_size_matches_the_rendered_image(tmp_path: Path) -> None:
    """The stage is sized from the reported dimensions, so they must be usable."""
    service, path = _service(tmp_path, _minimal_pdf([[("C1", 20, 180)]]))
    drawing = service.open(str(path))
    page = drawing.pages[0]

    rendered = PageRenderer(service.cache_dir).render_pdf_page(
        path,
        source_sha256=open_drawing(path).source_sha256,
        page_number=1,
    )

    # PDFium rounds up where plan_pixels truncates, so allow a single pixel.
    assert abs(rendered.pixel_width - page.pixel_width) <= 1
    assert abs(rendered.pixel_height - page.pixel_height) <= 1


def test_plan_pixels_respects_the_budget_and_rejects_bad_sizes() -> None:
    width, height, scale = plan_pixels(200, 100, pixel_budget=1_000_000)

    assert width * height <= 1_000_000
    assert scale > 1

    for bad in ((0, 100), (100, 0), (-1, 10)):
        try:
            plan_pixels(*bad)
        except ValueError:
            continue
        raise AssertionError(f"invalid page size accepted: {bad}")


# ---------------------------------------------------------------------- api


def test_api_opens_a_drawing_and_serves_a_page_image(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    path = root / "data" / "uploads" / "drawing.pdf"
    path.write_bytes(_minimal_pdf([[("C1", 20, 180), ("R2", 100, 100)]]))

    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _headers(client)
        response = client.post(
            "/api/v1/refdes/drawings", json={"path": str(path)}, headers=headers
        )
        assert response.status_code == 200, response.text
        drawing = response.json()
        assert drawing["ref_count"] == 2

        page = drawing["pages"][0]
        image = client.get(page["image_url"], headers=headers)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content.startswith(b"\x89PNG")

        reread = client.get(
            f"/api/v1/refdes/drawings/{drawing['drawing_id']}", headers=headers
        )
        assert reread.status_code == 200
        assert reread.json()["ref_count"] == 2


def test_api_rejects_unknown_drawings_and_pages(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    path = root / "data" / "uploads" / "drawing.pdf"
    path.write_bytes(_minimal_pdf([[("C1", 20, 180)]]))

    with TestClient(create_app(root), base_url=BASE_URL) as client:
        headers = _headers(client)
        assert (
            client.get("/api/v1/refdes/drawings/dwg-" + "0" * 24, headers=headers).status_code
            == 404
        )
        assert client.get("/api/v1/refdes/drawings/nope", headers=headers).status_code == 400

        drawing = client.post(
            "/api/v1/refdes/drawings", json={"path": str(path)}, headers=headers
        ).json()
        missing_page = client.get(
            f"/api/v1/refdes/drawings/{drawing['drawing_id']}/pages/99/image",
            headers=headers,
        )
        assert missing_page.status_code == 404


# ------------------------------------------------------------- real drawings


def test_real_assembly_drawing_when_opted_in(tmp_path: Path) -> None:
    raw = os.environ.get("SMT_REAL_SAMPLE_DIR", "")
    if not raw:
        return
    folder = Path(raw)
    source = next(path for path in folder.glob("*.pdf") if "SMD" in path.name.upper())
    root = _runtime(tmp_path)
    path = root / "data" / "uploads" / source.name
    shutil.copy2(source, path)

    drawing = RefdesService(root).open(str(path))

    assert drawing.page_count == 2
    assert drawing.ref_count > 300
    assert {page.side_guess for page in drawing.pages} == {"top", "bottom"}
    for page in drawing.pages:
        # Every printed refdes must be locatable or the list cannot navigate.
        assert page.marks and page.ref_count > 0
        assert page.pixel_width >= 1500


def test_multi_page_schematic_opens_quickly_when_opted_in(tmp_path: Path) -> None:
    """A 19-page schematic used to block for ~21s because every page was rendered."""
    raw = os.environ.get("SMT_REAL_SCHEMATIC", "")
    if not raw:
        return
    source = Path(raw)
    if not source.is_file():
        return
    root = _runtime(tmp_path)
    path = root / "data" / "uploads" / source.name
    shutil.copy2(source, path)
    service = RefdesService(root)

    started = time.monotonic()
    drawing = service.open(str(path))
    elapsed = time.monotonic() - started

    assert drawing.page_count > 5
    assert elapsed < 5.0, f"opening took {elapsed:.1f}s"
    assert list(service.cache_dir.rglob("*.png")) == []
