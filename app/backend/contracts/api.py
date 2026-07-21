from __future__ import annotations

import math
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


def _require_finite_numbers(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("wire contracts cannot contain NaN or infinite numbers")
    if isinstance(value, dict):
        for item in value.values():
            _require_finite_numbers(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _require_finite_numbers(item)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_finite_numbers(self) -> "ContractModel":
        for value in self.__dict__.values():
            _require_finite_numbers(value)
        return self


class ApiError(ContractModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1)
    details: Optional[dict[str, JsonValue]] = None


class SmtComponent(ContractModel):
    ref: str
    x_mm: float
    y_mm: float
    rotation: int
    side: Literal["top", "bottom"]
    footprint: str
    part_number: str
    description: str
    model: str
    grade: str
    status: Literal["installed", "nc", "missing_bom", "missing_layout"]
    high_risk: bool


class SmtBoard(ContractModel):
    outline_rings: list[list[tuple[float, float]]]
    bbox_mm: tuple[float, float, float, float]
    source: Literal["dxf", "gerber_bbox", "explicit"]


class SmtSanityItem(ContractModel):
    ref: str
    note: str
    severity: Literal["high", "medium", "low"]


class SmtFootprintConflict(ContractModel):
    ref: str
    xy_footprint: str
    netlist_footprint: str
    bom_footprint: str
    note: str


class SmtSanity(ContractModel):
    missing_layout: list[SmtSanityItem] = Field(default_factory=list)
    missing_bom: list[SmtSanityItem] = Field(default_factory=list)
    missing_netlist: list[SmtSanityItem] = Field(default_factory=list)
    footprint_conflicts: list[SmtFootprintConflict] = Field(default_factory=list)


class SmtSkippedSanity(ContractModel):
    status: Literal["skipped_no_netlist"]


class SmtNcSummary(ContractModel):
    total: int = Field(ge=0)
    refs: list[str] = Field(default_factory=list)


class SmtFaiTable(ContractModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[JsonValue]] = Field(default_factory=list)


class SmtLayoutSummary(ContractModel):
    total_components: int = Field(ge=0)
    top_count: int = Field(ge=0)
    bottom_count: int = Field(ge=0)
    nc_count: int = Field(ge=0)
    high_risk_count: int = Field(ge=0)


class SmtLayoutResponse(ContractModel):
    status: Literal["ok", "error", "needs_confirmation"]
    tool: Literal["smt_layout"]
    outputs: list[str] = Field(default_factory=list)
    board: Optional[SmtBoard] = None
    components: list[SmtComponent] = Field(default_factory=list)
    nc_summary: Optional[SmtNcSummary] = None
    sanity: Optional[Union[SmtSanity, SmtSkippedSanity]] = None
    fai_table: Optional[SmtFaiTable] = None
    summary: Optional[SmtLayoutSummary] = None
    error: Optional[str] = None
    message: Optional[str] = None
    user_message: Optional[str] = None
    error_kind: Optional[str] = None
