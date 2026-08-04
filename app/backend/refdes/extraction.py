from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable


# Reference designators as printed on drawings: one to four letters, digits, and
# an optional unit suffix letter (U12A). Bounded by non-alphanumerics so tokens
# embedded inside part numbers or net names are not harvested.
REF_RE = re.compile(r"(?<![A-Z0-9_])[A-Z]{1,4}\d{1,6}[A-Z]?(?![A-Z0-9_])", re.IGNORECASE)


@dataclass(frozen=True)
class RefBox:
    """One printed instance of a refdes, in normalised page coordinates.

    Coordinates are fractions of the page (0..1) with a top-left origin. They are
    deliberately resolution independent: the renderer and PDFium round preview
    dimensions slightly differently, and normalised values stay correct against
    whatever pixel size the page is eventually drawn at.
    """

    ref: str
    x: float
    y: float
    left: float
    top: float
    right: float
    bottom: float
    order: int


def find_refs(text: str) -> tuple[str, ...]:
    return tuple(sorted({match.upper() for match in REF_RE.findall(text or "")}))


def _normalise(
    box: tuple[float, float, float, float],
    *,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float]:
    """Convert a PDF character box (bottom-left origin) to page fractions."""
    left, bottom, right, top = box
    return (
        min(left, right) / page_width,
        (page_height - max(bottom, top)) / page_height,
        max(left, right) / page_width,
        (page_height - min(bottom, top)) / page_height,
    )


def locate_refs(
    text_page,
    *,
    refs: Iterable[str],
    page_width: float,
    page_height: float,
) -> tuple[RefBox, ...]:
    """Locate each refdes token in the PDF vector text layer.

    Only the vector text layer is consulted; scanned drawings are reported as
    having no refdes rather than being guessed at.
    """
    if not all(
        math.isfinite(value) and value > 0 for value in (float(page_width), float(page_height))
    ):
        raise ValueError("位号图页面尺寸无效")

    found: list[RefBox] = []
    seen: set[tuple[str, int, int]] = set()
    order = 0
    for ref in sorted({str(value).strip().upper() for value in refs if str(value).strip()}):
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
                    if raw is None or len(raw) != 4:
                        continue
                    values = tuple(float(value) for value in raw)
                    if all(math.isfinite(value) for value in values):
                        boxes.append(values)
                if not boxes:
                    continue
                left, top, right, bottom = _normalise(
                    (
                        min(item[0] for item in boxes),
                        min(item[1] for item in boxes),
                        max(item[2] for item in boxes),
                        max(item[3] for item in boxes),
                    ),
                    page_width=float(page_width),
                    page_height=float(page_height),
                )
                center_x = (left + right) / 2
                center_y = (top + bottom) / 2
                # Dedupe on a fine grid so the same label found twice by PDFium
                # collapses, while genuinely repeated placements stay distinct.
                key = (ref, round(center_x * 10_000), round(center_y * 10_000))
                if key in seen:
                    continue
                seen.add(key)
                found.append(
                    RefBox(
                        ref=ref,
                        x=center_x,
                        y=center_y,
                        left=left,
                        top=top,
                        right=right,
                        bottom=bottom,
                        order=order,
                    )
                )
                order += 1
        finally:
            searcher.close()
    return tuple(found)
