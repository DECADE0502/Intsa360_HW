from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class PageRenderPolicy:
    max_preview_pixels: int = 4_000_000
    max_render_scale: float = 2.0
    jpeg_quality: int = 90

    def __post_init__(self) -> None:
        if self.max_preview_pixels <= 0:
            raise ValueError("max_preview_pixels must be positive")
        if self.max_render_scale <= 0:
            raise ValueError("max_render_scale must be positive")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")


@dataclass(frozen=True)
class CachedPage:
    cache_key: str
    image_path: Path
    pixel_width: int
    pixel_height: int
    media_type: Literal["image/png", "image/jpeg"]


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


class PageCache:
    def __init__(
        self,
        source_root: Path,
        cache_root: Path,
        *,
        policy: PageRenderPolicy | None = None,
    ) -> None:
        self.source_root = Path(source_root).resolve()
        self.cache_root = Path(cache_root).resolve()
        self.policy = policy or PageRenderPolicy()
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _source(self, path: Path) -> Path:
        source = Path(path).resolve()
        if not _within(source, self.source_root) or not source.is_file():
            raise ValueError("位号图资产不在本次 SMT 资料目录内")
        return source

    def _key(
        self,
        *,
        source_sha256: str,
        page_number: int,
        rotation: int,
        crop_rect: tuple[float, float, float, float] | None,
    ) -> str:
        payload = json.dumps(
            {
                "source": source_sha256,
                "page": page_number,
                "rotation": rotation,
                "crop": crop_rect,
                "max_pixels": self.policy.max_preview_pixels,
                "max_scale": self.policy.max_render_scale,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _destination(self, key: str, suffix: str = ".png") -> Path:
        folder = self.cache_root / key[:2] / key[2:4]
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{key}{suffix}"

    def resolve(self, cache_key: str) -> CachedPage:
        """Resolve one cache entry without trusting a caller-provided path."""
        key = str(cache_key).strip().lower()
        if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
            raise ValueError("页面缓存键无效")
        image_path = self._destination(key)
        metadata = image_path.with_suffix(".json")
        if not image_path.is_file() or not metadata.is_file():
            raise FileNotFoundError("页面预览缓存不存在")
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        return CachedPage(
            cache_key=key,
            image_path=image_path,
            pixel_width=int(payload["pixel_width"]),
            pixel_height=int(payload["pixel_height"]),
            media_type="image/png",
        )

    def render_pdf_page(
        self,
        path: Path,
        *,
        source_sha256: str,
        page_number: int,
        rotation: int = 0,
        crop_rect: tuple[float, float, float, float] | None = None,
    ) -> CachedPage:
        source = self._source(path)
        if page_number < 1:
            raise ValueError("PDF 页码必须从 1 开始")
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("PDF 页面旋转角度无效")
        key = self._key(
            source_sha256=source_sha256,
            page_number=page_number,
            rotation=rotation,
            crop_rect=crop_rect,
        )
        destination = self._destination(key)
        metadata = destination.with_suffix(".json")
        if destination.is_file() and metadata.is_file():
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            return CachedPage(
                cache_key=key,
                image_path=destination,
                pixel_width=int(payload["pixel_width"]),
                pixel_height=int(payload["pixel_height"]),
                media_type="image/png",
            )

        try:
            import pypdfium2 as pdfium  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("当前运行时缺少本地 PDF 渲染组件") from exc
        document = None
        page = None
        bitmap = None
        image = None
        temporary = destination.with_suffix(".tmp.png")
        metadata_temporary = metadata.with_suffix(".tmp.json")
        try:
            document = pdfium.PdfDocument(source)
            if page_number > len(document):
                raise ValueError(f"PDF 只有 {len(document)} 页")
            page = document[page_number - 1]
            width, height = page.get_size()
            page_pixels = max(float(width) * float(height), 1.0)
            scale = min(
                self.policy.max_render_scale,
                math.sqrt(self.policy.max_preview_pixels / page_pixels),
            )
            bitmap = page.render(scale=scale, rotation=rotation)
            image = bitmap.to_pil()
            if crop_rect is not None:
                left, top, right, bottom = crop_rect
                if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                    raise ValueError("页面裁切区域超出预览范围")
                image = image.crop((left, top, right, bottom))
            image.save(temporary, format="PNG", optimize=True)
            metadata_temporary.write_text(
                json.dumps(
                    {"pixel_width": image.width, "pixel_height": image.height},
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            temporary.replace(destination)
            metadata_temporary.replace(metadata)
            return CachedPage(
                cache_key=key,
                image_path=destination,
                pixel_width=image.width,
                pixel_height=image.height,
                media_type="image/png",
            )
        finally:
            temporary.unlink(missing_ok=True)
            metadata_temporary.unlink(missing_ok=True)
            if image is not None:
                image.close()
            if bitmap is not None:
                bitmap.close()
            if page is not None:
                page.close()
            if document is not None:
                document.close()

    def render_image(
        self,
        path: Path,
        *,
        source_sha256: str,
        rotation: int = 0,
        crop_rect: tuple[float, float, float, float] | None = None,
    ) -> CachedPage:
        source = self._source(path)
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("图片旋转角度无效")
        key = self._key(
            source_sha256=source_sha256,
            page_number=1,
            rotation=rotation,
            crop_rect=crop_rect,
        )
        destination = self._destination(key)
        metadata = destination.with_suffix(".json")
        if destination.is_file() and metadata.is_file():
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            return CachedPage(
                cache_key=key,
                image_path=destination,
                pixel_width=int(payload["pixel_width"]),
                pixel_height=int(payload["pixel_height"]),
                media_type="image/png",
            )
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("当前运行时缺少本地图片处理组件") from exc

        temporary = destination.with_suffix(".tmp.png")
        metadata_temporary = metadata.with_suffix(".tmp.json")
        with Image.open(source) as original:
            image = original.convert("RGB")
            try:
                if rotation:
                    image = image.rotate(-rotation, expand=True)
                if crop_rect is not None:
                    left, top, right, bottom = crop_rect
                    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                        raise ValueError("图片裁切区域超出预览范围")
                    image = image.crop((left, top, right, bottom))
                if image.width * image.height > self.policy.max_preview_pixels:
                    ratio = math.sqrt(self.policy.max_preview_pixels / (image.width * image.height))
                    image.thumbnail(
                        (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
                    )
                image.save(temporary, format="PNG", optimize=True)
                metadata_temporary.write_text(
                    json.dumps(
                        {"pixel_width": image.width, "pixel_height": image.height},
                        separators=(",", ":"),
                    ),
                    encoding="utf-8",
                )
                temporary.replace(destination)
                metadata_temporary.replace(metadata)
                return CachedPage(
                    cache_key=key,
                    image_path=destination,
                    pixel_width=image.width,
                    pixel_height=image.height,
                    media_type="image/png",
                )
            finally:
                image.close()
