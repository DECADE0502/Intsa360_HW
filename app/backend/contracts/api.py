from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


T = TypeVar("T")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiError(ContractModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1)
    details: Optional[dict[str, Any]] = None


class ApiEnvelope(ContractModel, Generic[T]):
    ok: bool
    request_id: UUID
    data: Optional[T] = None
    error: Optional[ApiError] = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "ApiEnvelope[T]":
        if self.ok and self.error is not None:
            raise ValueError("successful responses cannot include an error")
        if not self.ok and self.error is None:
            raise ValueError("failed responses must include an error")
        return self
