from __future__ import annotations

import asyncio
import os
import socket
import threading

import uvicorn
from fastapi import FastAPI


def _configure_windows_event_loop() -> None:
    """Avoid Proactor accept failures after an updater health probe disconnects."""
    if os.name != "nt":
        return
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is not None and not isinstance(asyncio.get_event_loop_policy(), selector_policy):
        asyncio.set_event_loop_policy(selector_policy())


class FastApiCompatServer:
    """Expose the legacy server lifecycle over one pre-bound Uvicorn socket."""

    def __init__(self, app: FastAPI, host: str, port: int) -> None:
        self._app = app
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((host, port))
        self._socket.listen(2048)
        self.server_address = self._socket.getsockname()[:2]
        config = uvicorn.Config(
            app,
            host=host,
            port=int(self.server_address[1]),
            access_log=False,
            log_level="critical",
            lifespan="off",
        )
        self._server = uvicorn.Server(config)
        self._stopped = threading.Event()
        self.session_token = str(app.state.session_token)

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        del poll_interval
        _configure_windows_event_loop()
        try:
            self._server.run(sockets=[self._socket])
        finally:
            self._stopped.set()

    def shutdown(self) -> None:
        self._server.should_exit = True
        self._stopped.wait(timeout=5)

    def server_close(self) -> None:
        try:
            self._socket.close()
        except OSError:
            pass
        closer = getattr(self._app.state, "close_observability", None)
        if callable(closer):
            closer()
