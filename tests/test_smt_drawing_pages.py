from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from app.backend.contracts.smt_analysis import SmtSourceAsset
from app.backend.smt_analysis.drawings import build_drawing_pages
from app.backend.smt_analysis.page_cache import PageCache, PageRenderPolicy


def _source(path: Path, *, media_type: str, roles: list[str]) -> SmtSourceAsset:
    payload = path.read_bytes()
    return SmtSourceAsset(
        asset_id=f"asset-{path.stem}",
        relative_path=path.name,
        sha256=hashlib.sha256(payload).hexdigest(),
        media_type=media_type,
        file_size=len(payload),
        roles=roles,
        classification_state="candidate",
        evidence=[],
        page_count=1 if media_type == "application/pdf" else None,
        sheet_names=[],
    )


def test_image_becomes_local_board_background_candidate(tmp_path: Path) -> None:
    image_path = tmp_path / "board.png"
    Image.new("RGB", (800, 600), "white").save(image_path)
    cache = PageCache(tmp_path, tmp_path / "cache")

    pages = build_drawing_pages(
        run_id="run-1",
        source_root=tmp_path,
        assets=[_source(image_path, media_type="image/png", roles=["assembly_drawing"])],
        cache=cache,
    )

    assert len(pages) == 1
    assert pages[0].drawing_role == "board_unknown_side"
    assert pages[0].preview_url.endswith("/preview")
    cache_key = next(item.value for item in pages[0].evidence if item.kind == "cache_key")
    assert cache_key
    assert list((tmp_path / "cache").rglob(f"{cache_key}.png"))


def test_large_image_preview_is_bounded(tmp_path: Path) -> None:
    image_path = tmp_path / "large.png"
    Image.new("RGB", (2000, 1000), "white").save(image_path)
    cache = PageCache(
        tmp_path,
        tmp_path / "cache",
        policy=PageRenderPolicy(max_preview_pixels=100_000),
    )

    cached = cache.render_image(
        image_path,
        source_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
    )

    assert cached.pixel_width * cached.pixel_height <= 100_000


def test_page_cache_rejects_path_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (10, 10), "white").save(outside)
    cache = PageCache(source, tmp_path / "cache")

    try:
        cache.render_image(outside, source_sha256="a" * 64)
    except ValueError as exc:
        assert "不在本次 SMT 资料目录" in str(exc)
    else:
        raise AssertionError("path traversal should be rejected")


def test_real_pdf_pages_are_independently_rendered_when_opted_in(tmp_path: Path) -> None:
    import os

    raw = os.environ.get("SMT_REAL_SAMPLE_DIR", "")
    if not raw:
        return
    folder = Path(raw)
    pdf = next(path for path in folder.glob("*.pdf") if "SMD" in path.name.upper())
    cache = PageCache(folder, tmp_path / "cache")
    pages = build_drawing_pages(
        run_id="real-run",
        source_root=folder,
        assets=[_source(pdf, media_type="application/pdf", roles=["assembly_drawing"])],
        cache=cache,
    )

    assert len(pages) == 2
    assert all(page.pixel_width and page.pixel_height for page in pages)
    assert all(page.drawing_role == "board_unknown_side" for page in pages)
    assert all(page.extracted_refs for page in pages)
    assert all(page.positioned_refs for page in pages)
    assert all(
        {item.ref for item in page.positioned_refs} <= set(page.extracted_refs)
        for page in pages
    )
