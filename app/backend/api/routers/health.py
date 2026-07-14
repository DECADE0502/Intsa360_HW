from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from app.backend.api.context import AppContext, get_context
from app.backend.services.health import collect_health


SERVICE_NAME = "Insta360_HW"
SCHEMA_VERSION = "v1"
router = APIRouter(tags=["health"])
legacy_router = APIRouter(tags=["health"])


@router.get("/health")
def health(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return collect_health(context)


@legacy_router.get("/health", include_in_schema=False)
def legacy_health(context: AppContext = Depends(get_context)) -> dict[str, object]:
    payload = collect_health(context)
    return {
        **payload,
        "product": SERVICE_NAME,
        "root": str(context.root),
        "instance_token": os.environ.get("INSTA360_HW_INSTANCE_TOKEN", ""),
    }
