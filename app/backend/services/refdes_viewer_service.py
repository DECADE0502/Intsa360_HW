from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Sequence

from app.backend.contracts.refdes_viewer import (
    RefdesDocument,
    RefdesOccurrence,
    RefdesPage,
    RefdesSide,
    RefdesTextLayer,
)
from app.backend.paths import AppPaths
from app.backend.smt_analysis.classifiers import sniff_media_type
from app.backend.smt_analysis.page_cache import PageCache, PageRenderPolicy
from app.backend.smt_analysis.refdes_extraction import extract_pdf_vector_refs


_HASH_CHUNK = 1024 * 1024
_SIGNATURE_BYTES = 4096
_DOCUMENT_VERSION = "refdes-viewer-v1"

# Assembly drawings are small in PDF units (often under 200pt) but carry hundreds
# of tiny refdes labels. The shared default caps rendering at 2x, which yields an
# unreadable ~370px preview, so this viewer renders by pixel budget instead.
_VIEWER_RENDER_POLICY = PageRenderPolicy(
    max_preview_pixels=6_000_000,
    max_render_scale=20.0,
)
_DOC_ID_RE = re.compile(r"doc-[0-9a-f]{24}")

# Reference designators printed on assembly drawings: one to four letters then
# digits, optionally a unit suffix letter (U12A). Bounded by non-alphanumerics so
# tokens embedded inside part numbers are not harvested.
_REF_RE = re.compile(r"(?<![A-Z0-9_])[A-Z]{1,4}\d{1,6}[A-Z]?(?![A-Z0-9_])", re.IGNORECASE)

_TOP_MARKERS = ("COMPONENT SIDE", "TOP SIDE", "TOP ASSEMBLY", "TOP VIEW", "正面", "顶面")
_BOTTOM_MARKERS = ("SOLDER SIDE", "BOTTOM SIDE", "BOTTOM ASSEMBLY", "BOTTOM VIEW", "反面", "底面")

_SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _guess_side(text: str) -> RefdesSide:
    upper = text.upper()
    top = any(marker in upper for marker in _TOP_MARKERS)
    bottom = any(marker in upper for marker in _BOTTOM_MARKERS)
    if top and not bottom:
        return "top"
    if bottom and not top:
        return "bottom"
    return "unknown"


def _page_id(doc_id: str, page_number: int) -> str:
    digest = hashlib.sha256(f"{doc_id}|{page_number}".encode("utf-8")).hexdigest()
    return f"page-{digest[:24]}"


def _assume_top_bottom(pages: list[RefdesPage]) -> list[RefdesPage]:
    """Assume the common two-page top/bottom export when text gives no hint.

    This is only a starting point; the viewer always lets the operator switch
    sides, so a wrong guess never blocks the work.
    """
    candidates = [page for page in pages if page.occurrence_count]
    if len(candidates) != 2 or any(page.side_guess != "unknown" for page in candidates):
        return pages
    first, second = sorted(candidates, key=lambda item: item.page_number)
    sides = {first.page_id: "top", second.page_id: "bottom"}
    return [
        page.model_copy(update={"side_guess": sides[page.page_id]})
        if page.page_id in sides
        else page
        for page in pages
    ]


class RefdesViewerService:
    """Open a reference-designator drawing and expose every printed refdes.

    The drawing alone is enough: no BOM, no coordinate file and no registration.
    Reference positions come straight from the PDF vector text layer, which is
    where CAM assembly drawings already carry them.
    """

    def __init__(
        self,
        root: Path,
        *,
        allowed_roots: Sequence[Path] | None = None,
    ) -> None:
        self.paths = AppPaths(root)
        self.base_dir = self.paths.data_dir / "refdes_viewer"
        self.docs_dir = self.base_dir / "docs"
        self.cache_dir = self.base_dir / "cache"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        roots = allowed_roots if allowed_roots is not None else (self.paths.data_dir,)
        self._allowed_roots = tuple(Path(item).resolve() for item in roots)

    # ---------------------------------------------------------------- sources

    def _resolve_source(self, raw: str) -> Path:
        text = str(raw or "").strip()
        if not text:
            raise ValueError("请选择位号图文件")
        source = Path(text).resolve()
        if not source.is_file():
            raise ValueError(f"位号图文件不存在：{source}")
        for root in self._allowed_roots:
            try:
                source.relative_to(root)
            except ValueError:
                continue
            return source
        raise ValueError("位号图文件不在允许的目录内")

    def _document_path(self, doc_id: str) -> Path:
        key = str(doc_id or "").strip()
        if not _DOC_ID_RE.fullmatch(key):
            raise ValueError("位号图文档编号无效")
        return self.docs_dir / f"{key}.json"

    def _load_payload(self, doc_id: str) -> dict:
        path = self._document_path(doc_id)
        if not path.is_file():
            raise KeyError("位号图文档不存在或已过期，请重新打开文件")
        return json.loads(path.read_text(encoding="utf-8"))

    # -------------------------------------------------------------- lifecycle

    def open(self, path: str, *, label: str | None = None) -> RefdesDocument:
        source = self._resolve_source(path)
        with source.open("rb") as handle:
            prefix = handle.read(_SIGNATURE_BYTES)
        media_type = sniff_media_type(source, prefix)
        source_sha256 = _sha256_file(source)
        doc_id = "doc-" + hashlib.sha256(
            f"{_DOCUMENT_VERSION}|{source_sha256}".encode("utf-8")
        ).hexdigest()[:24]

        cache = PageCache(source.parent, self.cache_dir, policy=_VIEWER_RENDER_POLICY)
        notices: list[str] = []
        if media_type == "application/pdf":
            pages, cache_keys = self._pdf_pages(
                source,
                doc_id=doc_id,
                source_sha256=source_sha256,
                cache=cache,
            )
            if pages and not any(page.occurrence_count for page in pages):
                notices.append(
                    "这份 PDF 没有可提取的位号文字（可能是扫描件，或文字已转成曲线），"
                    "只能查看图像。"
                )
        elif media_type in _SUPPORTED_IMAGE_TYPES:
            pages, cache_keys = self._image_pages(
                source,
                doc_id=doc_id,
                source_sha256=source_sha256,
                cache=cache,
            )
            notices.append("图片位号图没有文字层，只能查看图像，无法自动提取位号。")
        else:
            raise ValueError("只支持 PDF 或 PNG/JPG 位号图")

        document = RefdesDocument(
            doc_id=doc_id,
            file_name=label or source.name,
            media_type=media_type,
            page_count=len(pages),
            ref_count=len({item.ref for page in pages for item in page.occurrences}),
            pages=pages,
            notices=notices,
        )
        payload = document.model_dump()
        payload["source_path"] = str(source)
        payload["page_cache_keys"] = cache_keys
        self._document_path(doc_id).write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        return document

    def get(self, doc_id: str) -> RefdesDocument:
        payload = self._load_payload(doc_id)
        payload.pop("source_path", None)
        payload.pop("page_cache_keys", None)
        return RefdesDocument.model_validate(payload)

    def preview(self, doc_id: str, page_id: str) -> tuple[Path, str]:
        payload = self._load_payload(doc_id)
        cache_keys = payload.get("page_cache_keys") or {}
        cache_key = cache_keys.get(str(page_id))
        if not cache_key:
            raise KeyError("位号图页面不存在")
        cached = PageCache(
            self.base_dir, self.cache_dir, policy=_VIEWER_RENDER_POLICY
        ).resolve(str(cache_key))
        return cached.image_path, cached.media_type

    # ------------------------------------------------------------------ pages

    def _pdf_pages(
        self,
        source: Path,
        *,
        doc_id: str,
        source_sha256: str,
        cache: PageCache,
    ) -> tuple[list[RefdesPage], dict[str, str]]:
        try:
            import pypdfium2 as pdfium  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - runtime packaging guard
            raise RuntimeError("当前运行时缺少本地 PDF 渲染组件") from exc

        pages: list[RefdesPage] = []
        cache_keys: dict[str, str] = {}
        document = pdfium.PdfDocument(source)
        try:
            for index in range(len(document)):
                page_number = index + 1
                page_id = _page_id(doc_id, page_number)
                page = document[page_number - 1]
                text_page = None
                try:
                    text_page = page.get_textpage()
                    text = text_page.get_text_range()
                    refs = sorted({match.upper() for match in _REF_RE.findall(text)})
                    cached = cache.render_pdf_page(
                        source,
                        source_sha256=source_sha256,
                        page_number=page_number,
                    )
                    page_width, page_height = page.get_size()
                    extracted = (
                        extract_pdf_vector_refs(
                            text_page,
                            page_id=page_id,
                            refs=refs,
                            page_width=page_width,
                            page_height=page_height,
                            pixel_width=cached.pixel_width,
                            pixel_height=cached.pixel_height,
                        )
                        if refs
                        else []
                    )
                    side = _guess_side(text)
                    text_layer: RefdesTextLayer = "vector" if text.strip() else "absent"
                finally:
                    if text_page is not None:
                        text_page.close()
                    page.close()

                cache_keys[page_id] = cached.cache_key
                occurrences = [
                    RefdesOccurrence(
                        occurrence_id=item.extracted_ref_id,
                        ref=item.ref,
                        x=item.image_x,
                        y=item.image_y,
                        left=item.bbox[0],
                        top=item.bbox[1],
                        right=item.bbox[2],
                        bottom=item.bbox[3],
                    )
                    for item in extracted
                ]
                pages.append(
                    RefdesPage(
                        page_id=page_id,
                        page_number=page_number,
                        pixel_width=cached.pixel_width,
                        pixel_height=cached.pixel_height,
                        preview_url=(
                            f"/api/v1/refdes-viewer/docs/{doc_id}/pages/{page_id}/preview"
                        ),
                        side_guess=side,
                        text_layer=text_layer,
                        ref_count=len({item.ref for item in occurrences}),
                        occurrence_count=len(occurrences),
                        occurrences=occurrences,
                    )
                )
        finally:
            document.close()

        return _assume_top_bottom(pages), cache_keys

    def _image_pages(
        self,
        source: Path,
        *,
        doc_id: str,
        source_sha256: str,
        cache: PageCache,
    ) -> tuple[list[RefdesPage], dict[str, str]]:
        cached = cache.render_image(source, source_sha256=source_sha256)
        page_id = _page_id(doc_id, 1)
        page = RefdesPage(
            page_id=page_id,
            page_number=1,
            pixel_width=cached.pixel_width,
            pixel_height=cached.pixel_height,
            preview_url=f"/api/v1/refdes-viewer/docs/{doc_id}/pages/{page_id}/preview",
            side_guess="unknown",
            text_layer="image",
            ref_count=0,
            occurrence_count=0,
            occurrences=[],
        )
        return [page], {page_id: cached.cache_key}
