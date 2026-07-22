from __future__ import annotations

import json
import os
import socket
import threading
import time
from urllib.request import urlopen

import pytest
from fastapi import FastAPI

from app.backend.api.server import FastApiCompatServer


@pytest.mark.skipif(os.name != "nt", reason="Windows socket accept regression")
def test_server_accepts_health_after_queued_clients_disconnect() -> None:
    app = FastAPI()
    app.state.session_token = "test-session-token"

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    server = FastApiCompatServer(app, "127.0.0.1", 0)
    host, port = server.server_address
    for _ in range(8):
        client = socket.create_connection((host, port), timeout=1)
        client.close()

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    payload: dict[str, str] | None = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with urlopen(f"http://{host}:{port}/api/health", timeout=1) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except OSError:
                time.sleep(0.1)
        assert payload == {"status": "ok"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert not thread.is_alive()
