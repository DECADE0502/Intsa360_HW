from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.backend.smt_view.registration import AffineRegistration


REF_RE = re.compile(r"(?<![A-Z0-9_])[A-Z]{1,4}\d{1,6}[A-Z]?(?![A-Z0-9_])", re.IGNORECASE)
DEFAULT_PIXEL_BUDGET = 6_000_000
PNG_COMPRESS_LEVEL = 3


@dataclass(frozen=True)
class PdfReference:
    ref: str
    x: float
    y: float


@dataclass(frozen=True)
class PdfDrawingPage:
    page_number: int
    width: float
    height: float
    refs: tuple[PdfReference, ...]


@dataclass(frozen=True)
class PdfDrawing:
    source: Path
    sha256: str
    pages: tuple[PdfDrawingPage, ...]


@dataclass(frozen=True)
class RenderedDrawing:
    cache_key: str
    image_path: Path
    pixel_width: int
    pixel_height: int
    crop: tuple[float, float, float, float]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locate_refs(
    text_page,
    text: str,
    *,
    page_origin_x: float,
    page_origin_y: float,
) -> tuple[PdfReference, ...]:
    found: list[PdfReference] = []
    seen: set[tuple[str, int, int]] = set()
    for ref in sorted({match.upper() for match in REF_RE.findall(text or "")}):
        searcher = text_page.search(ref, match_case=False, match_whole_word=True)
        try:
            while occurrence := searcher.get_next():
                index, count = occurrence
                boxes: list[tuple[float, float, float, float]] = []
                for position in range(index, index + count):
                    try:
                        raw = text_page.get_charbox(position, loose=True)
                    except (IndexError, RuntimeError, ValueError):
                        continue
                    if raw is not None and len(raw) == 4:
                        values = tuple(float(value) for value in raw)
                        if all(math.isfinite(value) for value in values):
                            boxes.append(values)
                if not boxes:
                    continue
                left = min(min(item[0], item[2]) for item in boxes)
                right = max(max(item[0], item[2]) for item in boxes)
                bottom = min(min(item[1], item[3]) for item in boxes)
                top = max(max(item[1], item[3]) for item in boxes)
                # Text boxes use the PDF page's absolute coordinate space, while
                # render crops use a zero-based page canvas. Normalize once here.
                x = (left + right) / 2.0 - page_origin_x
                y = (bottom + top) / 2.0 - page_origin_y
                key = (ref, round(x * 100), round(y * 100))
                if key not in seen:
                    seen.add(key)
                    found.append(PdfReference(ref=ref, x=x, y=y))
        finally:
            searcher.close()
    return tuple(found)


def open_pdf_drawing(path: Path) -> PdfDrawing:
    try:
        import pypdfium2 as pdfium  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - runtime packaging guard
        raise RuntimeError("当前运行时缺少 PDF 位号图组件。") from exc

    source = Path(path).resolve()
    if not source.is_file():
        raise ValueError("没有找到 SMD/REF 位号图 PDF。")
    pages: list[PdfDrawingPage] = []
    document = pdfium.PdfDocument(source)
    try:
        for index in range(len(document)):
            page = document[index]
            text_page = None
            try:
                width, height = (float(value) for value in page.get_size())
                bbox = tuple(float(value) for value in page.get_bbox())
                text_page = page.get_textpage()
                text = text_page.get_text_range()
                pages.append(
                    PdfDrawingPage(
                        index + 1,
                        width,
                        height,
                        _locate_refs(
                            text_page,
                            text,
                            page_origin_x=bbox[0],
                            page_origin_y=bbox[1],
                        ),
                    )
                )
            finally:
                if text_page is not None:
                    text_page.close()
                page.close()
    finally:
        document.close()
    return PdfDrawing(source=source, sha256=sha256_file(source), pages=tuple(pages))


def crop_for_xy(
    registration: AffineRegistration,
    xy_points: Iterable[tuple[float, float]],
    *,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float]:
    points = list(xy_points)
    if not points:
        raise ValueError("当前面没有可用于裁剪的 XY 位号。")
    min_x = min(item[0] for item in points)
    max_x = max(item[0] for item in points)
    min_y = min(item[1] for item in points)
    max_y = max(item[1] for item in points)
    # Component centers can sit several millimetres inside an irregular board edge.
    # Keep a generous engineering margin so the real outline is not clipped.
    margin = max(5.0, max(max_x - min_x, max_y - min_y) * 0.12)
    corners = [
        registration.transform(x, y)
        for x in (min_x - margin, max_x + margin)
        for y in (min_y - margin, max_y + margin)
    ]
    left = max(0.0, min(item[0] for item in corners))
    right = min(page_width, max(item[0] for item in corners))
    bottom = max(0.0, min(item[1] for item in corners))
    top = min(page_height, max(item[1] for item in corners))
    if right - left < 1 or top - bottom < 1:
        raise ValueError("位号图自动裁剪范围无效。")
    return left, bottom, right, top


class DrawingRenderer:
    def __init__(self, cache_root: Path, *, pixel_budget: int = DEFAULT_PIXEL_BUDGET) -> None:
        self.cache_root = Path(cache_root).resolve()
        self.pixel_budget = int(pixel_budget)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _key(self, source_sha256: str, page_number: int, crop: tuple[float, float, float, float]) -> str:
        raw = json.dumps(
            {"source": source_sha256, "page": page_number, "crop": [round(value, 4) for value in crop], "budget": self.pixel_budget},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _paths(self, key: str) -> tuple[Path, Path]:
        folder = self.cache_root / key[:2] / key[2:4]
        folder.mkdir(parents=True, exist_ok=True)
        image = folder / f"{key}.png"
        return image, image.with_suffix(".json")

    def resolve(self, key: str) -> Path:
        normalized = str(key).strip().lower()
        if len(normalized) != 64 or any(value not in "0123456789abcdef" for value in normalized):
            raise KeyError("位号图缓存键无效。")
        image, metadata = self._paths(normalized)
        if not image.is_file() or not metadata.is_file():
            raise KeyError("位号图缓存不存在或已清理。")
        return image

    def render(
        self,
        drawing: PdfDrawing,
        *,
        page_number: int,
        crop: tuple[float, float, float, float],
    ) -> RenderedDrawing:
        key = self._key(drawing.sha256, page_number, crop)
        destination, metadata = self._paths(key)
        if destination.is_file() and metadata.is_file():
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            return RenderedDrawing(key, destination, int(payload["width"]), int(payload["height"]), crop)

        try:
            import pypdfium2 as pdfium  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("当前运行时缺少 PDF 位号图组件。") from exc
        left, bottom, right, top = crop
        page_info = drawing.pages[page_number - 1]
        crop_width = right - left
        crop_height = top - bottom
        scale = min(20.0, math.sqrt(self.pixel_budget / (crop_width * crop_height)))
        temp_image = destination.with_suffix(".tmp.png")
        temp_metadata = metadata.with_suffix(".tmp.json")
        document = pdfium.PdfDocument(drawing.source)
        page = bitmap = image = None
        try:
            page = document[page_number - 1]
            bitmap = page.render(
                scale=scale,
                crop=(left, bottom, page_info.width - right, page_info.height - top),
            )
            image = bitmap.to_pil()
            image.save(temp_image, format="PNG", compress_level=PNG_COMPRESS_LEVEL)
            temp_metadata.write_text(json.dumps({"width": image.width, "height": image.height}), encoding="utf-8")
            temp_image.replace(destination)
            temp_metadata.replace(metadata)
            return RenderedDrawing(key, destination, image.width, image.height, crop)
        finally:
            temp_image.unlink(missing_ok=True)
            temp_metadata.unlink(missing_ok=True)
            if image is not None:
                image.close()
            if bitmap is not None:
                bitmap.close()
            if page is not None:
                page.close()
            document.close()
