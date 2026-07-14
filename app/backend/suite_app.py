from __future__ import annotations

import argparse
from pathlib import Path

from app.backend.api.cadence import cadence_hot_reload_command, parse_cadence_loader_paths
from app.backend.api.server import FastApiCompatServer
from app.backend.main import create_app


ROOT = Path(__file__).resolve().parents[2]

# Compatibility exports for launchers and 0.3.x integration tests.
_parse_cadence_loader_paths = parse_cadence_loader_paths
_cadence_hot_reload_command = cadence_hot_reload_command


def create_server(
    root: Path = ROOT,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> FastApiCompatServer:
    return FastApiCompatServer(create_app(root), host, port)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Insta360 hardware efficiency platform.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = create_server(host=args.host, port=args.port)
    host, port = server.server_address
    print(f"Insta360 hardware efficiency platform running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
