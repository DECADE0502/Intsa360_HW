from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path


# Assembly drawings are physically small in PDF units (often under 200pt) yet
# carry hundreds of tiny refdes labels, so the preview is sized by a pixel budget
# rather than a scale multiplier.
DEFAULT_PIXEL_BUDGET = 6_000_000
MAX_SCALE = 20.0

# PNG `optimize=True` re-runs zlib for a fraction of a percent: on a 6M pixel
# line-art page it costs roughly 0.4s and saves ~10KB. Encoding dominated the old
# implementation's page cost, so this uses a plain moderate compression level.
PNG_COMPRESS_LEVEL = 3


@dataclass(frozen=True)
class RenderedPage:
    cache_key: str
    image_path: Path
    pixel_width: int
    pixel_height: int
    media_type: str = "image/png"


def plan_pixels(
    page_width: float,
    page_height: float,
    *,
    pixel_budget: int = DEFAULT_PIXEL_BUDGET,
) -> tuple[int, int, float]:
    """Decide the preview size for a page, deterministically.

    Both refdes extraction (at open time) and rasterisation (on demand) call this,
    so marker coordinates always match the image that is eventually rendered.
    """
    width = float(page_width)
    height = float(page_height)
    if not (math.isfinite(width) and math.isfinite(height)) or width <= 0 or height <= 0:
        raise ValueError("位号图页面尺寸无效")
    scale = min(MAX_SCALE, math.sqrt(pixel_budget / (width * height)))
    return max(1, int(width * scale)), max(1, int(height * scale)), scale


class PageRenderer:
    """Rasterise drawing pages one at a time, caching the result on disk."""

    def __init__(self, cache_root: Path, *, pixel_budget: int = DEFAULT_PIXEL_BUDGET) -> None:
        self.cache_root = Path(cache_root).resolve()
        self.pixel_budget = int(pixel_budget)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _key(self, *, source_sha256: str, page_number: int) -> str:
        payload = json.dumps(
            {
                "source": source_sha256,
                "page": page_number,
                "budget": self.pixel_budget,
                "compress": PNG_COMPRESS_LEVEL,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _destination(self, key: str) -> Path:
        folder = self.cache_root / key[:2] / key[2:4]
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{key}.png"

    def _cached(self, key: str) -> RenderedPage | None:
        image = self._destination(key)
        metadata = image.with_suffix(".json")
        if not image.is_file() or not metadata.is_file():
            return None
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        return RenderedPage(
            cache_key=key,
            image_path=image,
            pixel_width=int(payload["pixel_width"]),
            pixel_height=int(payload["pixel_height"]),
        )

    def resolve(self, cache_key: str) -> RenderedPage:
        """Resolve a cache entry by key, never trusting a caller-supplied path."""
        key = str(cache_key).strip().lower()
        if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
            raise ValueError("位号图页面缓存键无效")
        cached = self._cached(key)
        if cached is None:
            raise FileNotFoundError("位号图页面预览缓存不存在")
        return cached

    def render_pdf_page(
        self,
        source: Path,
        *,
        source_sha256: str,
        page_number: int,
    ) -> RenderedPage:
        if page_number < 1:
            raise ValueError("位号图页码必须从 1 开始")
        key = self._key(source_sha256=source_sha256, page_number=page_number)
        cached = self._cached(key)
        if cached is not None:
            return cached

        try:
            import pypdfium2 as pdfium  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - runtime packaging guard
            raise RuntimeError("当前运行时缺少本地 PDF 渲染组件") from exc

        destination = self._destination(key)
        metadata = destination.with_suffix(".json")
        image_temp = destination.with_suffix(".tmp.png")
        metadata_temp = metadata.with_suffix(".tmp.json")
        document = pdfium.PdfDocument(source)
        page = None
        bitmap = None
        image = None
        try:
            if page_number > len(document):
                raise ValueError(f"位号图只有 {len(document)} 页")
            page = document[page_number - 1]
            page_width, page_height = page.get_size()
            _, _, scale = plan_pixels(
                page_width, page_height, pixel_budget=self.pixel_budget
            )
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            image.save(image_temp, format="PNG", compress_level=PNG_COMPRESS_LEVEL)
            metadata_temp.write_text(
                json.dumps(
                    {"pixel_width": image.width, "pixel_height": image.height},
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            image_temp.replace(destination)
            metadata_temp.replace(metadata)
            return RenderedPage(
                cache_key=key,
                image_path=destination,
                pixel_width=image.width,
                pixel_height=image.height,
            )
        finally:
            image_temp.unlink(missing_ok=True)
            metadata_temp.unlink(missing_ok=True)
            if image is not None:
                image.close()
            if bitmap is not None:
                bitmap.close()
            if page is not None:
                page.close()
            document.close()

    def render_image_file(
        self,
        source: Path,
        *,
        source_sha256: str,
    ) -> RenderedPage:
        key = self._key(source_sha256=source_sha256, page_number=1)
        cached = self._cached(key)
        if cached is not None:
            return cached
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - runtime packaging guard
            raise RuntimeError("当前运行时缺少本地图片处理组件") from exc

        destination = self._destination(key)
        metadata = destination.with_suffix(".json")
        image_temp = destination.with_suffix(".tmp.png")
        metadata_temp = metadata.with_suffix(".tmp.json")
        try:
            with Image.open(source) as original:
                image = original.convert("RGB")
                try:
                    pixels = image.width * image.height
                    if pixels > self.pixel_budget:
                        ratio = math.sqrt(self.pixel_budget / pixels)
                        image.thumbnail(
                            (
                                max(1, int(image.width * ratio)),
                                max(1, int(image.height * ratio)),
                            )
                        )
                    image.save(image_temp, format="PNG", compress_level=PNG_COMPRESS_LEVEL)
                    metadata_temp.write_text(
                        json.dumps(
                            {"pixel_width": image.width, "pixel_height": image.height},
                            separators=(",", ":"),
                        ),
                        encoding="utf-8",
                    )
                    image_temp.replace(destination)
                    metadata_temp.replace(metadata)
                    return RenderedPage(
                        cache_key=key,
                        image_path=destination,
                        pixel_width=image.width,
                        pixel_height=image.height,
                    )
                finally:
                    image.close()
        finally:
            image_temp.unlink(missing_ok=True)
            metadata_temp.unlink(missing_ok=True)
