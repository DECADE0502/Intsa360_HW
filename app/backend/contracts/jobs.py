from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import Field, JsonValue, StrictBool

from app.backend.contracts.api import ApiError, ContractModel


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPhase(str, Enum):
    QUEUED = "queued"
    RECOGNIZING = "recognizing"
    PROCESSING = "processing"
    REVIEWING = "reviewing"
    PACKAGING = "packaging"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    STAGING = "staging"
    COMMITTING = "committing"
    RESTARTING = "restarting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(ContractModel):
    id: UUID
    kind: str = Field(min_length=1, max_length=80)
    status: JobStatus
    phase: JobPhase
    progress: float = Field(ge=0, le=100, strict=True)
    message: str
    cancellable: StrictBool
    result: Optional[dict[str, JsonValue]] = None
    error: Optional[ApiError] = None
    created_at: datetime
    updated_at: datetime
