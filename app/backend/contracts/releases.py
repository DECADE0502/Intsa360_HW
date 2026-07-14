from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import AnyHttpUrl, Field, field_validator

from app.backend.contracts.api import ContractModel
from app.backend.contracts.validation import require_windows_safe_filename


SEMVER_PATTERN = (
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class BuildKind(str, Enum):
    DEV = "dev"
    PUBLISHED = "published"


class ReleaseAsset(ContractModel):
    name: str = Field(min_length=1)
    url: AnyHttpUrl
    size: int = Field(gt=0, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")

    @field_validator("name")
    @classmethod
    def require_plain_filename(cls, value: str) -> str:
        return require_windows_safe_filename(value)

    @field_validator("url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("release asset URL must use HTTPS")
        return value


class ReleaseManifestV3(ContractModel):
    schema_version: int = Field(default=3, ge=3, le=3, strict=True)
    version: str = Field(pattern=SEMVER_PATTERN)
    revision: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    build_kind: BuildKind
    published_at: datetime
    min_updater_version: str = Field(pattern=SEMVER_PATTERN)
    assets: list[ReleaseAsset] = Field(min_length=1)
    changelog: list[str] = Field(default_factory=list)
    signature: str = Field(min_length=1)
