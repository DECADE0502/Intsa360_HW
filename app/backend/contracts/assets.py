from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import Field, JsonValue, StrictBool, field_validator

from app.backend.contracts.api import ContractModel
from app.backend.contracts.validation import normalize_windows_safe_relative_path


class AssetKind(str, Enum):
    BOM = "bom"
    NETLIST = "netlist"
    REPORT = "report"
    OUTPUT = "output"


class ToolRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Asset(ContractModel):
    id: UUID
    kind: AssetKind
    format: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    size: int = Field(ge=0, strict=True)
    created_at: datetime
    source_run_id: Optional[UUID] = None
    pinned: StrictBool = False
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return normalize_windows_safe_relative_path(value)


class ToolRun(ContractModel):
    id: UUID
    tool_id: str = Field(min_length=1, max_length=80)
    status: ToolRunStatus
    input_asset_ids: list[UUID] = Field(default_factory=list)
    output_asset_ids: list[UUID] = Field(default_factory=list)
    params: dict[str, JsonValue] = Field(default_factory=dict)
    decisions: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime
    completed_at: Optional[datetime] = None
