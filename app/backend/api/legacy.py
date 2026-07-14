from __future__ import annotations

from fastapi import FastAPI

from app.backend.api.routers import RESOURCE_ROUTERS
from app.backend.api.routers.health import legacy_router as legacy_health_router
from app.backend.api.security import session_router


def include_legacy_routes(app: FastAPI) -> None:
    """Expose 0.3.x paths as aliases to the versioned FastAPI handlers."""
    app.include_router(legacy_health_router, prefix="/api")
    app.include_router(session_router, prefix="/api", include_in_schema=False)
    for router in RESOURCE_ROUTERS:
        app.include_router(router, prefix="/api", include_in_schema=False)
