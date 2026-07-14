from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.backend.contracts.api import ContractModel


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
    pinned: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts:
            raise ValueError("asset path must be relative and cannot traverse parents")
        return normalized


class ToolRun(ContractModel):
    id: UUID
    tool_id: str = Field(min_length=1, max_length=80)
    status: ToolRunStatus
    input_asset_ids: list[UUID] = Field(default_factory=list)
    output_asset_ids: list[UUID] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    decisions: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: Optional[datetime] = None
