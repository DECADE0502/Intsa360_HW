from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI


ROOT = Path(__file__).resolve().parents[2]
SERVICE_NAME = "Insta360_HW"
SCHEMA_VERSION = "v1"


def _read_runtime_value(runtime_root: Path, name: str) -> str:
    try:
        return (runtime_root / name).read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def create_app(root: Path | None = None) -> FastAPI:
    """Create the minimal versioned FastAPI service for one runtime root."""
    runtime_root = (root or ROOT).resolve()
    app = FastAPI(title=SERVICE_NAME, version=_read_runtime_value(runtime_root, "VERSION"))

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {
            "service": SERVICE_NAME,
            "schema_version": SCHEMA_VERSION,
            "runtime_root": str(runtime_root),
            "version": _read_runtime_value(runtime_root, "VERSION"),
            "revision": _read_runtime_value(runtime_root, "REVISION"),
        }

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Insta360_HW FastAPI service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
