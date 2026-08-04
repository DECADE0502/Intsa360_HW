from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.backend.contracts.api import ContractModel


PlacementStatus = Literal["placed", "nc", "bom_only"]
PlacementSide = Literal["top", "bottom"]


class SmtViewBoardRequest(ContractModel):
    source_dir: str = Field(min_length=1, max_length=1200)
    bom_path: str = Field(min_length=1, max_length=1200)
    semantic_manifest_path: Optional[str] = Field(default=None, max_length=1200)
    netlist_dir: Optional[str] = Field(default=None, max_length=1200)
    label: Optional[str] = Field(default=None, max_length=300)


class SmtViewRegistration(ContractModel):
    anchor_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    median_mm: float = Field(ge=0)
    p90_mm: float = Field(ge=0)
    max_mm: float = Field(ge=0)
    trusted: bool


class SmtViewDrawing(ContractModel):
    page_number: int = Field(ge=1)
    image_url: str = Field(min_length=1)
    pixel_width: int = Field(gt=0)
    pixel_height: int = Field(gt=0)
    registration: SmtViewRegistration


class SmtViewPlacement(ContractModel):
    ref: str = Field(min_length=1, max_length=80)
    x_mm: float
    y_mm: float
    drawing_x: float
    drawing_y: float
    rotation: int = Field(ge=0, lt=360)
    side: PlacementSide
    footprint: str = ""
    status: Literal["placed", "nc"]
    material_code: str = ""
    name: str = ""
    model: str = ""
    description: str = ""
    grade: str = ""
    package: str = ""
    reason: str = ""
    package_status: str = ""
    package_kind: str = ""
    net_package: str = ""
    package_note: str = ""


class SmtViewUnmappedItem(ContractModel):
    ref: str = Field(min_length=1, max_length=80)
    status: Literal["bom_only"] = "bom_only"
    material_code: str = ""
    name: str = ""
    model: str = ""
    description: str = ""
    reason: str = ""


class SmtViewBoard(ContractModel):
    schema_version: Literal[2] = 2
    board_id: str = Field(min_length=12, max_length=80)
    label: str = Field(min_length=1, max_length=300)
    xy_file_name: str = Field(min_length=1, max_length=400)
    xy_version: str = ""
    xy_units: Literal["mils", "mm"]
    placements: list[SmtViewPlacement]
    bom_only: list[SmtViewUnmappedItem]
    summary: dict[str, int]
    drawings: dict[PlacementSide, SmtViewDrawing]
    reference_drawing_name: str
    reference_drawing_url: str
    package_report_outputs: list[str] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
