from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from app.backend.contracts.smt_analysis import (
    BoardSide,
    SmtDrawingPage,
    SmtEvidence,
    SmtSourceAsset,
)
from app.backend.smt_analysis.evidence import evidence
from app.backend.smt_analysis.page_cache import PageCache
from app.backend.smt_analysis.refdes_extraction import extract_pdf_vector_refs


_REF_RE = re.compile(r"(?<![A-Z0-9_])(?:[A-Z]{1,4})\d{1,6}(?![A-Z0-9_])", re.IGNORECASE)


def _page_id(asset_id: str, page_number: int) -> str:
    digest = hashlib.sha256(f"{asset_id}|{page_number}".encode("utf-8")).hexdigest()
    return f"drawing-page-{digest[:24]}"


def _side_candidate(text: str) -> tuple[BoardSide, list[SmtEvidence]]:
    upper = text.upper()
    top_markers = ("COMPONENT SIDE", "TOP SIDE", "TOP ASSEMBLY", "正面")
    bottom_markers = ("SOLDER SIDE", "BOTTOM SIDE", "BOTTOM ASSEMBLY", "反面")
    top = any(marker in upper for marker in top_markers)
    bottom = any(marker in upper for marker in bottom_markers)
    if top and not bottom:
        return "top", [
            evidence(
                "page_side_text",
                "页面文字明确包含正面/Top 语义，仍需在叠加预览中确认。",
                weight="supporting",
            )
        ]
    if bottom and not top:
        return "bottom", [
            evidence(
                "page_side_text",
                "页面文字明确包含反面/Bottom 语义，仍需在叠加预览中确认。",
                weight="supporting",
            )
        ]
    if top and bottom:
        return "unknown", [
            evidence(
                "page_side_conflict",
                "同一页面同时出现正反面文字，不能自动决定面别。",
                weight="conflicting",
            )
        ]
    return "unknown", []


def _drawing_role(text: str, source_roles: set[str], ref_count: int) -> str:
    upper = text.upper()
    if "schematic_drawing" in source_roles and any(
        marker in upper for marker in ("SCHEMATIC", "NET NAME", "SHEET ", "PAGE ")
    ):
        return "unrelated_page"
    if ref_count >= 20 or any(
        marker in upper for marker in ("ART FILM", "ASSEMBLY", "COMPONENT SIDE", "SOLDER SIDE")
    ):
        return "board_unknown_side"
    if any(marker in upper for marker in ("NOTE", "说明", "REMARK")):
        return "assembly_note"
    if ref_count:
        return "table_page"
    return "unrelated_page"


def _preview_url(run_id: str, page_id: str) -> str:
    return f"/api/v1/smt-analysis/runs/{run_id}/pages/{page_id}/preview"


def build_drawing_pages(
    *,
    run_id: str,
    source_root: Path,
    assets: Iterable[SmtSourceAsset],
    cache: PageCache,
) -> list[SmtDrawingPage]:
    root = Path(source_root).resolve()
    pages: list[SmtDrawingPage] = []
    for asset in assets:
        roles = set(asset.roles)
        if not roles.intersection({"assembly_drawing", "schematic_drawing"}):
            continue
        path = (root / asset.relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("位号图相对路径越界") from exc
        if asset.media_type == "application/pdf":
            pages.extend(
                _build_pdf_pages(
                    run_id=run_id,
                    path=path,
                    asset=asset,
                    cache=cache,
                )
            )
        elif asset.media_type in {"image/png", "image/jpeg"}:
            cached = cache.render_image(path, source_sha256=asset.sha256)
            page_id = _page_id(asset.asset_id, 1)
            pages.append(
                SmtDrawingPage(
                    page_id=page_id,
                    source_asset_id=asset.asset_id,
                    page_number=1,
                    pixel_width=cached.pixel_width,
                    pixel_height=cached.pixel_height,
                    page_rotation=0,
                    crop_rect=None,
                    side_candidate="unknown",
                    drawing_role="board_unknown_side",
                    preview_url=_preview_url(run_id, page_id),
                    tile_manifest_url=None,
                    extracted_refs=[],
                    evidence=[
                        evidence(
                            "image_source",
                            "图片被保留为板面底图候选，面别与配准需确认。",
                            weight="supporting",
                        ),
                        evidence(
                            "cache_key",
                            "页面预览已写入受限本地缓存。",
                            weight="supporting",
                            value=cached.cache_key,
                        ),
                    ],
                )
            )
    return pages


def _build_pdf_pages(
    *,
    run_id: str,
    path: Path,
    asset: SmtSourceAsset,
    cache: PageCache,
) -> list[SmtDrawingPage]:
    try:
        import pypdfium2 as pdfium  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("当前运行时缺少本地 PDF 渲染组件") from exc
    document = None
    result: list[SmtDrawingPage] = []
    try:
        document = pdfium.PdfDocument(path)
        for page_index in range(len(document)):
            page = document[page_index]
            text_page = None
            try:
                text_page = page.get_textpage()
                text = text_page.get_text_range()
                refs = sorted(set(match.upper() for match in _REF_RE.findall(text)))
                side, side_evidence = _side_candidate(text)
                role = _drawing_role(text, set(asset.roles), len(refs))
                cached = cache.render_pdf_page(
                    path,
                    source_sha256=asset.sha256,
                    page_number=page_index + 1,
                )
                page_id = _page_id(asset.asset_id, page_index + 1)
                page_width, page_height = page.get_size()
                positioned_refs = extract_pdf_vector_refs(
                    text_page,
                    page_id=page_id,
                    refs=refs,
                    page_width=page_width,
                    page_height=page_height,
                    pixel_width=cached.pixel_width,
                    pixel_height=cached.pixel_height,
                )
            finally:
                if text_page is not None:
                    text_page.close()
                page.close()
            page_evidence: list[SmtEvidence] = [
                evidence(
                    "page_refdes_density",
                    f"页面矢量文本中提取到 {len(refs)} 个位号候选。",
                    weight="supporting" if refs else "weak",
                    value=str(len(refs)),
                ),
                evidence(
                    "cache_key",
                    "页面预览已写入受限本地缓存。",
                    weight="supporting",
                    value=cached.cache_key,
                ),
                *side_evidence,
            ]
            result.append(
                SmtDrawingPage(
                    page_id=page_id,
                    source_asset_id=asset.asset_id,
                    page_number=page_index + 1,
                    pixel_width=cached.pixel_width,
                    pixel_height=cached.pixel_height,
                    page_rotation=0,
                    crop_rect=None,
                    side_candidate=side,
                    drawing_role=role,
                    preview_url=_preview_url(run_id, page_id),
                    tile_manifest_url=None,
                    extracted_refs=refs,
                    positioned_refs=positioned_refs,
                    evidence=page_evidence,
                )
            )
        return result
    finally:
        if document is not None:
            document.close()
