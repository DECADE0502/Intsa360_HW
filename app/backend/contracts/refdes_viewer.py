from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.backend.contracts.api import ContractModel


RefdesSide = Literal["top", "bottom", "unknown"]
RefdesTextLayer = Literal["vector", "absent", "image"]


class RefdesOccurrence(ContractModel):
    """One printed instance of a reference designator on a rendered page.

    Coordinates use the preview image pixel space with a top-left origin, so the
    frontend can place markers without knowing anything about PDF user space.
    """

    occurrence_id: str = Field(min_length=1, max_length=80)
    ref: str = Field(min_length=1, max_length=64)
    x: float
    y: float
    left: float
    top: float
    right: float
    bottom: float


class RefdesPage(ContractModel):
    page_id: str = Field(min_length=1, max_length=80)
    page_number: int = Field(ge=1)
    pixel_width: int = Field(ge=1)
    pixel_height: int = Field(ge=1)
    preview_url: str = Field(min_length=1, max_length=400)
    side_guess: RefdesSide = "unknown"
    text_layer: RefdesTextLayer = "vector"
    ref_count: int = Field(ge=0)
    occurrence_count: int = Field(ge=0)
    occurrences: list[RefdesOccurrence] = Field(default_factory=list)


class RefdesDocument(ContractModel):
    doc_id: str = Field(min_length=1, max_length=80)
    file_name: str = Field(min_length=1, max_length=400)
    media_type: str = Field(min_length=1, max_length=120)
    page_count: int = Field(ge=0)
    ref_count: int = Field(ge=0)
    pages: list[RefdesPage] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


class RefdesOpenRequest(ContractModel):
    path: str = Field(min_length=1, max_length=1000)
    label: Optional[str] = Field(default=None, max_length=400)
