from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.backend.contracts.api import ContractModel


PlacementStatus = Literal["placed", "nc", "non_smt", "bom_only", "xy_only"]
PlacementSide = Literal["top", "bottom"]
VersionChange = Literal["none", "added", "removed", "replaced"]


class SmtViewBoardRequest(ContractModel):
    source_dir: str = Field(min_length=1, max_length=1200)
    bom_path: str = Field(min_length=1, max_length=1200)
    nc_path: Optional[str] = Field(default=None, max_length=1200)
    semantic_manifest_path: Optional[str] = Field(default=None, max_length=1200)
    decision_manifest_path: Optional[str] = Field(default=None, max_length=1200)
    baseline_bom_path: Optional[str] = Field(default=None, max_length=1200)
    label: Optional[str] = Field(default=None, max_length=300)


class SmtViewBounds(ContractModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class SmtViewPlacement(ContractModel):
    ref: str = Field(min_length=1, max_length=80)
    x_mm: float
    y_mm: float
    rotation: int = Field(ge=0, lt=360)
    side: PlacementSide
    footprint: str = ""
    status: PlacementStatus
    material_code: str = ""
    name: str = ""
    model: str = ""
    description: str = ""
    grade: str = ""
    package: str = ""
    reason: str = ""
    decision_kind: str = ""
    version_change: VersionChange = "none"
    baseline_material_code: str = ""


class SmtViewUnmappedItem(ContractModel):
    ref: str = Field(min_length=1, max_length=80)
    status: Literal["bom_only"] = "bom_only"
    material_code: str = ""
    name: str = ""
    model: str = ""
    description: str = ""
    reason: str = ""
    version_change: VersionChange = "none"


class SmtViewBoard(ContractModel):
    schema_version: Literal[1] = 1
    board_id: str = Field(min_length=12, max_length=80)
    label: str = Field(min_length=1, max_length=300)
    xy_file_name: str = Field(min_length=1, max_length=400)
    xy_version: str = ""
    xy_units: Literal["mils", "mm"]
    bbox: SmtViewBounds
    source_span: dict[str, float]
    placements: list[SmtViewPlacement]
    bom_only: list[SmtViewUnmappedItem]
    xy_only: list[str]
    summary: dict[str, int]
    reference_drawing_name: Optional[str] = None
    reference_drawing_url: Optional[str] = None
    notices: list[str] = Field(default_factory=list)
