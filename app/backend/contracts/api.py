from __future__ import annotations

import math
from typing import Optional

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
