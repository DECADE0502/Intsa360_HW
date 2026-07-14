from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.api.uploads import UploadLimitError, UploadLimits, stream_request_to_disk
from app.backend.main import create_app


BASE_URL = "http://127.0.0.1:8765"
SESSION_HEADER = "X-Insta360-Session"


def _client(tmp_path: Path) -> TestClient:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "VERSION").write_text("0.4.0\n", encoding="utf-8")
    return TestClient(create_app(root), base_url=BASE_URL)


def _session_headers(client: TestClient, *, origin: str = BASE_URL) -> dict[str, str]:
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    return {SESSION_HEADER: response.json()["token"], "Origin": origin}


def test_mutation_requires_session_header(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.delete("/api/v1/history")

    assert response.status_code == 403
    assert response.json()["error_kind"] == "session_required"


def test_api_rejects_non_local_host(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/session", headers={"Host": "attacker.example"})

    assert response.status_code == 400
    assert response.json()["error_kind"] == "invalid_host"


def test_mutation_rejects_cross_site_origin_even_with_valid_token(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        headers = _session_headers(client, origin="https://attacker.example")
        response = client.delete("/api/v1/history", headers=headers)

    assert response.status_code == 403
    assert response.json()["error_kind"] == "invalid_origin"


def test_valid_same_origin_session_allows_mutation(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.delete("/api/v1/history", headers=_session_headers(client))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_rejects_request_over_configured_limit(tmp_path: Path) -> None:
    app = create_app(tmp_path / "runtime")
    app.state.upload_limits = UploadLimits(file_bytes=8, request_bytes=16)
    with TestClient(app, base_url=BASE_URL) as client:
        headers = _session_headers(client)
        response = client.post(
            "/api/v1/upload",
            files={"files": ("large.bin", b"0123456789", "application/octet-stream")},
            headers=headers,
        )

    assert response.status_code == 413
    assert response.json()["error_kind"] == "request_too_large"


def test_upload_rejects_single_file_over_configured_limit(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    app = create_app(root)
    app.state.upload_limits = UploadLimits(file_bytes=8, request_bytes=1024)
    with TestClient(app, base_url=BASE_URL) as client:
        headers = _session_headers(client)
        response = client.post(
            "/api/v1/upload",
            files={"files": ("large.bin", b"0123456789", "application/octet-stream")},
            headers=headers,
        )

    assert response.status_code == 413
    assert response.json()["error_kind"] == "file_too_large"
    uploads = root / "data" / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def test_interrupted_stream_removes_partial_body(tmp_path: Path) -> None:
    class InterruptedRequest:
        async def stream(self):
            yield b"partial"
            raise ConnectionError("client disconnected")

    target = tmp_path / "request.body"
    try:
        asyncio.run(stream_request_to_disk(InterruptedRequest(), target, request_limit=1024))
    except ConnectionError:
        pass
    else:
        raise AssertionError("interrupted stream must fail")

    assert not target.exists()


def test_package_traversal_is_rejected_after_session_validation(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    app = create_app(root)
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(
            "/api/v1/package",
            json={"files": ["../outside.txt"]},
            headers=_session_headers(client),
        )

    assert response.status_code == 400
    assert response.json()["error_kind"] == "bad_package_path"

