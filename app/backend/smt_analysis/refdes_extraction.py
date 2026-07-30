from __future__ import annotations

import hashlib
import math
from typing import Iterable

from app.backend.contracts.smt_analysis import SmtExtractedRef


def _pixel_box(
    box: tuple[float, float, float, float],
    *,
    page_width: float,
    page_height: float,
    pixel_width: int,
    pixel_height: int,
) -> tuple[float, float, float, float]:
    left, bottom, right, top = box
    scale_x = pixel_width / page_width
    scale_y = pixel_height / page_height
    pixel_left = min(left, right) * scale_x
    pixel_right = max(left, right) * scale_x
    pixel_top = (page_height - max(bottom, top)) * scale_y
    pixel_bottom = (page_height - min(bottom, top)) * scale_y
    return pixel_left, pixel_top, pixel_right, pixel_bottom


def extract_pdf_vector_refs(
    text_page,
    *,
    page_id: str,
    refs: Iterable[str],
    page_width: float,
    page_height: float,
    pixel_width: int,
    pixel_height: int,
) -> list[SmtExtractedRef]:
    """Locate already-recognized refdes tokens in PDF vector text.

    PDFium character boxes use page coordinates with a bottom-left origin.
    The public contract stores preview-image coordinates with a top-left origin.
    OCR is deliberately not attempted here.
    """

    dimensions = (
        float(page_width),
        float(page_height),
        float(pixel_width),
        float(pixel_height),
    )
    if not all(math.isfinite(value) and value > 0 for value in dimensions):
        raise ValueError("PDF 页面或预览尺寸无效")

    result: list[SmtExtractedRef] = []
    seen: set[tuple[str, int, int, int]] = set()
    for ref in sorted({str(value).strip().upper() for value in refs if str(value).strip()}):
        searcher = text_page.search(
            ref,
            match_case=False,
            match_whole_word=True,
        )
        try:
            while occurrence := searcher.get_next():
                index, count = occurrence
                boxes: list[tuple[float, float, float, float]] = []
                for char_index in range(index, index + count):
                    try:
                        raw_box = text_page.get_charbox(char_index, loose=True)
                    except (IndexError, RuntimeError, ValueError):
                        continue
                    if raw_box is None or len(raw_box) != 4:
                        continue
                    values = tuple(float(value) for value in raw_box)
                    if all(math.isfinite(value) for value in values):
                        boxes.append(values)
                if not boxes:
                    continue
                page_box = (
                    min(item[0] for item in boxes),
                    min(item[1] for item in boxes),
                    max(item[2] for item in boxes),
                    max(item[3] for item in boxes),
                )
                pixel_box = _pixel_box(
                    page_box,
                    page_width=page_width,
                    page_height=page_height,
                    pixel_width=pixel_width,
                    pixel_height=pixel_height,
                )
                left, top, right, bottom = pixel_box
                image_x = (left + right) / 2
                image_y = (top + bottom) / 2
                dedupe_key = (
                    ref,
                    round(image_x),
                    round(image_y),
                    count,
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                digest = hashlib.sha256(
                    (
                        f"{page_id}|{ref}|{index}|"
                        f"{image_x:.6f}|{image_y:.6f}"
                    ).encode("utf-8")
                ).hexdigest()
                result.append(
                    SmtExtractedRef(
                        extracted_ref_id=f"vector-ref-{digest[:24]}",
                        ref=ref,
                        image_x=image_x,
                        image_y=image_y,
                        bbox=pixel_box,
                        source="vector_text",
                        source_index=index,
                    )
                )
        finally:
            searcher.close()
    return sorted(
        result,
        key=lambda item: (item.ref, item.source_index, item.image_y, item.image_x),
    )
