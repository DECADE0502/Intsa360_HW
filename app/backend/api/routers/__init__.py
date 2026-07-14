from __future__ import annotations

from fastapi import FastAPI

from .files import api_router as files_router
from .health import router as health_router
from .history import router as history_router
from .lifecycle import router as lifecycle_router
from .plugins import router as plugins_router
from .tools import router as tools_router


RESOURCE_ROUTERS = (
    tools_router,
    files_router,
    history_router,
    plugins_router,
    lifecycle_router,
)


def include_versioned_routes(app: FastAPI) -> None:
    app.include_router(health_router, prefix="/api/v1")
    for router in RESOURCE_ROUTERS:
        app.include_router(router, prefix="/api/v1")
