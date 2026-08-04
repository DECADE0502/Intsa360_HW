from __future__ import annotations

from fastapi import FastAPI

from .files import api_router as files_router
from .diagnostics import router as diagnostics_router
from .health import router as health_router
from .history import router as history_router
from .jobs import router as jobs_router
from .lifecycle import router as lifecycle_router
from .plugins import router as plugins_router
from .smt_view import router as smt_view_router
from .tools import router as tools_router
from app.backend.api.security import session_router


RESOURCE_ROUTERS = (
    tools_router,
    files_router,
    diagnostics_router,
    history_router,
    jobs_router,
    plugins_router,
    lifecycle_router,
    smt_view_router,
)


def include_versioned_routes(app: FastAPI) -> None:
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(session_router, prefix="/api/v1")
    for router in RESOURCE_ROUTERS:
        app.include_router(router, prefix="/api/v1")
