from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, StrictBool

from app.backend.contracts.api import ContractModel


class PluginSource(str, Enum):
    SYSTEM = "system"
    PLATFORM = "platform"
    USER = "user"


class ActivationMode(str, Enum):
    HOT_RELOAD = "hot_reload"
    RESTART = "restart"


class PluginState(ContractModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", min_length=1, max_length=120)
    name: str = Field(min_length=1)
    source: PluginSource
    enabled: StrictBool
    entry_script: str = Field(min_length=1)
    activation: ActivationMode
    compatible_capture_versions: list[str] = Field(default_factory=list)
    validation_error: Optional[str] = None
