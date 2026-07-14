from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from app.backend import update_api
from app.backend.api.context import AppContext, get_context


SERVICE_NAME = "Insta360_HW"
SCHEMA_VERSION = "v1"
router = APIRouter(tags=["health"])
legacy_router = APIRouter(tags=["health"])


@router.get("/health")
def health(context: AppContext = Depends(get_context)) -> dict[str, str]:
    return {
        "service": SERVICE_NAME,
        "schema_version": SCHEMA_VERSION,
        "runtime_root": str(context.root.resolve()),
        "version": update_api.read_version(context.root),
        "revision": update_api.read_revision(context.root),
    }


@legacy_router.get("/health", include_in_schema=False)
def legacy_health(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return {
        "status": "ok",
        "product": SERVICE_NAME,
        "root": str(context.root),
        "state_root": str(context.paths.state_root),
        "version": update_api.read_version(context.root),
        "revision": update_api.read_revision(context.root),
        "instance_token": os.environ.get("INSTA360_HW_INSTANCE_TOKEN", ""),
        "pid": os.getpid(),
    }

