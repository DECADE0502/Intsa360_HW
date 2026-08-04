from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Sequence

from app.backend.contracts.refdes import (
    RefdesDrawing,
    RefdesDrawingPage,
    RefdesMark,
)
from app.backend.paths import AppPaths
from app.backend.refdes import PageRenderer, open_drawing


_VERSION = "refdes-v1"
_ID_RE = re.compile(r"dwg-[0-9a-f]{24}")
# 1e-5 of a page is well under a tenth of a pixel at preview resolution.
_COORD_DIGITS = 5


class RefdesService:
    """Open refdes drawings and serve their pages.

    Opening only reads page geometry and refdes positions, which is fast even for
    a twenty-page schematic. Page images are rasterised one at a time when the
    viewer actually asks for them.
    """

    def __init__(
        self,
        root: Path,
        *,
        allowed_roots: Sequence[Path] | None = None,
    ) -> None:
        self.paths = AppPaths(root)
        self.base_dir = self.paths.data_dir / "refdes"
        self.index_dir = self.base_dir / "drawings"
        self.cache_dir = self.base_dir / "pages"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.renderer = PageRenderer(self.cache_dir)
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

    def _index_path(self, drawing_id: str) -> Path:
        key = str(drawing_id or "").strip()
        if not _ID_RE.fullmatch(key):
            raise ValueError("位号图编号无效")
        return self.index_dir / f"{key}.json"

    def _load(self, drawing_id: str) -> dict:
        path = self._index_path(drawing_id)
        if not path.is_file():
            raise KeyError("位号图不存在或已过期，请重新打开文件")
        return json.loads(path.read_text(encoding="utf-8"))

    # -------------------------------------------------------------- lifecycle

    def open(self, path: str, *, label: str | None = None) -> RefdesDrawing:
        source = self._resolve_source(path)
        drawing = open_drawing(source)
        drawing_id = "dwg-" + hashlib.sha256(
            f"{_VERSION}|{drawing.source_sha256}".encode("utf-8")
        ).hexdigest()[:24]

        pages = [
            RefdesDrawingPage(
                page_number=page.page_number,
                pixel_width=page.pixel_width,
                pixel_height=page.pixel_height,
                image_url=(
                    f"/api/v1/refdes/drawings/{drawing_id}/pages/{page.page_number}/image"
                ),
                side_guess=page.side_guess,
                has_text_layer=page.has_text_layer,
                ref_count=len({mark.ref for mark in page.refs}),
                marks=[
                    RefdesMark(
                        ref=mark.ref,
                        x=round(mark.x, _COORD_DIGITS),
                        y=round(mark.y, _COORD_DIGITS),
                        left=round(mark.left, _COORD_DIGITS),
                        top=round(mark.top, _COORD_DIGITS),
                        right=round(mark.right, _COORD_DIGITS),
                        bottom=round(mark.bottom, _COORD_DIGITS),
                        order=mark.order,
                    )
                    for mark in page.refs
                ],
            )
            for page in drawing.pages
        ]

        notices: list[str] = []
        if drawing.media_type != "application/pdf":
            notices.append("图片位号图没有文字层，只能查看图像，无法自动提取位号。")
        elif pages and not any(page.marks for page in pages):
            notices.append(
                "这份 PDF 没有可提取的位号文字（可能是扫描件，或文字已转成曲线），只能查看图像。"
            )

        payload = RefdesDrawing(
            drawing_id=drawing_id,
            file_name=label or source.name,
            media_type=drawing.media_type,
            page_count=len(pages),
            ref_count=len({mark.ref for page in pages for mark in page.marks}),
            pages=pages,
            notices=notices,
        )
        record = payload.model_dump()
        record["source_path"] = str(source)
        record["source_sha256"] = drawing.source_sha256
        self._index_path(drawing_id).write_text(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        return payload

    def get(self, drawing_id: str) -> RefdesDrawing:
        record = self._load(drawing_id)
        record.pop("source_path", None)
        record.pop("source_sha256", None)
        return RefdesDrawing.model_validate(record)

    def page_image(self, drawing_id: str, page_number: int) -> tuple[Path, str]:
        """Rasterise one page on demand; repeat views hit the disk cache."""
        record = self._load(drawing_id)
        source = Path(str(record.get("source_path") or ""))
        digest = str(record.get("source_sha256") or "")
        if not source.is_file() or not digest:
            raise KeyError("位号图源文件已不可用，请重新打开文件")
        if not any(page["page_number"] == page_number for page in record.get("pages") or []):
            raise KeyError("位号图页面不存在")
        if str(record.get("media_type") or "") == "application/pdf":
            rendered = self.renderer.render_pdf_page(
                source, source_sha256=digest, page_number=page_number
            )
        else:
            rendered = self.renderer.render_image_file(source, source_sha256=digest)
        return rendered.image_path, rendered.media_type
