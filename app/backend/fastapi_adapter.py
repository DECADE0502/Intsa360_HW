from __future__ import annotations

from .main import create_app


BACKEND_MODE = "fastapi"
app = create_app()

__all__ = ["BACKEND_MODE", "app", "create_app"]
