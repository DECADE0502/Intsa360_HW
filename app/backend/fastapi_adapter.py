from __future__ import annotations

from typing import Any


BACKEND_MODE = "stdlib"


def create_app() -> Any | None:
    """Optional FastAPI hook.

    The packaged tool intentionally keeps the stdlib HTTP server as the release
    baseline so one-click installs do not need extra Python dependencies.
    """

    return None
