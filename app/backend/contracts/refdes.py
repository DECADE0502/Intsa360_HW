from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.backend.contracts.api import ContractModel


RefdesSide = Literal["top", "bottom", "unknown"]


class RefdesMark(ContractModel):
    """A printed refdes instance in normalised page coordinates (0..1, top-left)."""

    ref: str = Field(min_length=1, max_length=64)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)
    order: int = Field(ge=0)


class RefdesDrawingPage(ContractModel):
    page_number: int = Field(ge=1)
    pixel_width: int = Field(ge=1)
    pixel_height: int = Field(ge=1)
    image_url: str = Field(min_length=1, max_length=400)
    side_guess: RefdesSide = "unknown"
    has_text_layer: bool = True
    ref_count: int = Field(ge=0)
    marks: list[RefdesMark] = Field(default_factory=list)


class RefdesDrawing(ContractModel):
    drawing_id: str = Field(min_length=1, max_length=80)
    file_name: str = Field(min_length=1, max_length=400)
    media_type: str = Field(min_length=1, max_length=120)
    page_count: int = Field(ge=0)
    ref_count: int = Field(ge=0)
    pages: list[RefdesDrawingPage] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


class RefdesOpenRequest(ContractModel):
    path: str = Field(min_length=1, max_length=1000)
    label: Optional[str] = Field(default=None, max_length=400)
