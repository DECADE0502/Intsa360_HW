from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from app.backend.api.common import content_type, safe_child
from app.backend.api.context import build_context
from app.backend.api.legacy import include_legacy_routes
from app.backend.api.routers import include_versioned_routes
from app.backend.api.routers.files import output_router
from app.backend.api.security import install_security


ROOT = Path(__file__).resolve().parents[2]
SERVICE_NAME = "Insta360_HW"


def _read_runtime_value(runtime_root: Path, name: str) -> str:
    try:
        return (runtime_root / name).read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def create_app(root: Path | None = None) -> FastAPI:
    context = build_context(root or ROOT)
    runtime_root = context.root
    app = FastAPI(title=SERVICE_NAME, version=_read_runtime_value(runtime_root, "VERSION") or "0.0.0")
    app.state.context = context
    install_security(app)

    include_versioned_routes(app)
    include_legacy_routes(app)
    app.include_router(output_router)

    frontend_dir = runtime_root / "app" / "frontend"

    @app.get("/{requested:path}", include_in_schema=False)
    def frontend(requested: str):
        relative = "index.html" if requested in {"", "/"} else requested
        target = safe_child(frontend_dir, relative)
        if target is None or not target.is_file():
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(
            target,
            media_type=content_type(target),
            headers={"Cache-Control": "no-store"},
        )

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Insta360 hardware efficiency platform.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
