from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from app.backend.refdes.extraction import RefBox, find_refs, locate_refs
from app.backend.refdes.render import DEFAULT_PIXEL_BUDGET, plan_pixels


_HASH_CHUNK = 1024 * 1024
_SIGNATURE_BYTES = 4096

_TOP_MARKERS = ("COMPONENT SIDE", "TOP SIDE", "TOP ASSEMBLY", "TOP VIEW", "正面", "顶面")
_BOTTOM_MARKERS = ("SOLDER SIDE", "BOTTOM SIDE", "BOTTOM ASSEMBLY", "BOTTOM VIEW", "反面", "底面")

SUPPORTED_IMAGE_TYPES = frozenset({"image/png", "image/jpeg"})


@dataclass(frozen=True)
class DrawingPage:
    page_number: int
    pixel_width: int
    pixel_height: int
    side_guess: str
    has_text_layer: bool
    refs: tuple[RefBox, ...]


@dataclass(frozen=True)
class Drawing:
    source: Path
    source_sha256: str
    media_type: str
    pages: tuple[DrawingPage, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sniff_media_type(path: Path) -> str:
    with path.open("rb") as handle:
        prefix = handle.read(_SIGNATURE_BYTES)
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _guess_side(text: str) -> str:
    upper = (text or "").upper()
    top = any(marker in upper for marker in _TOP_MARKERS)
    bottom = any(marker in upper for marker in _BOTTOM_MARKERS)
    if top and not bottom:
        return "top"
    if bottom and not top:
        return "bottom"
    return "unknown"


def _assume_top_bottom(pages: list[DrawingPage]) -> list[DrawingPage]:
    """A two-page drawing with refdes on both sides is top then bottom.

    Only a starting hint: the viewer always lets the operator switch pages, so a
    wrong guess never blocks the work.
    """
    candidates = [page for page in pages if page.refs]
    if len(candidates) != 2 or any(page.side_guess != "unknown" for page in candidates):
        return pages
    first, second = sorted(candidates, key=lambda item: item.page_number)
    sides = {first.page_number: "top", second.page_number: "bottom"}
    return [
        DrawingPage(
            page_number=page.page_number,
            pixel_width=page.pixel_width,
            pixel_height=page.pixel_height,
            side_guess=sides.get(page.page_number, page.side_guess),
            has_text_layer=page.has_text_layer,
            refs=page.refs,
        )
        for page in pages
    ]


def open_drawing(
    source: Path,
    *,
    pixel_budget: int = DEFAULT_PIXEL_BUDGET,
) -> Drawing:
    """Read a drawing's pages and refdes positions without rasterising anything.

    Page images are rendered later, one at a time, by `PageRenderer`. Both use
    `plan_pixels`, so refdes coordinates always match the rendered page.
    """
    source = Path(source)
    media_type = sniff_media_type(source)
    digest = sha256_file(source)

    if media_type == "application/pdf":
        pages = _pdf_pages(source, pixel_budget=pixel_budget)
    elif media_type in SUPPORTED_IMAGE_TYPES:
        pages = _image_pages(source, pixel_budget=pixel_budget)
    else:
        raise ValueError("只支持 PDF 或 PNG/JPG 位号图")

    return Drawing(
        source=source,
        source_sha256=digest,
        media_type=media_type,
        pages=tuple(pages),
    )


def _pdf_pages(source: Path, *, pixel_budget: int) -> list[DrawingPage]:
    try:
        import pypdfium2 as pdfium  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - runtime packaging guard
        raise RuntimeError("当前运行时缺少本地 PDF 渲染组件") from exc

    pages: list[DrawingPage] = []
    document = pdfium.PdfDocument(source)
    try:
        for index in range(len(document)):
            page = document[index]
            text_page = None
            try:
                text_page = page.get_textpage()
                text = text_page.get_text_range()
                page_width, page_height = page.get_size()
                pixel_width, pixel_height, _ = plan_pixels(
                    page_width, page_height, pixel_budget=pixel_budget
                )
                refs = find_refs(text)
                located = (
                    locate_refs(
                        text_page,
                        refs=refs,
                        page_width=page_width,
                        page_height=page_height,
                    )
                    if refs
                    else ()
                )
                pages.append(
                    DrawingPage(
                        page_number=index + 1,
                        pixel_width=pixel_width,
                        pixel_height=pixel_height,
                        side_guess=_guess_side(text),
                        has_text_layer=bool(text.strip()),
                        refs=located,
                    )
                )
            finally:
                if text_page is not None:
                    text_page.close()
                page.close()
    finally:
        document.close()
    return _assume_top_bottom(pages)


def _image_pages(source: Path, *, pixel_budget: int) -> list[DrawingPage]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - runtime packaging guard
        raise RuntimeError("当前运行时缺少本地图片处理组件") from exc

    with Image.open(source) as image:
        width, height = image.size
    pixels = max(1, width * height)
    if pixels > pixel_budget:
        ratio = (pixel_budget / pixels) ** 0.5
        width = max(1, int(width * ratio))
        height = max(1, int(height * ratio))
    return [
        DrawingPage(
            page_number=1,
            pixel_width=width,
            pixel_height=height,
            side_guess="unknown",
            has_text_layer=False,
            refs=(),
        )
    ]
