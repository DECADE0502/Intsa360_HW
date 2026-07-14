from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from app.backend.api.common import error_payload
from app.backend.api.context import AppContext, get_context
from app.backend.api.uploads import UploadLimits, load_upload_limits


SESSION_HEADER = "X-Insta360-Session"
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
session_router = APIRouter(tags=["session"])


def _hostname(authority: str) -> str:
    if not authority or any(character in authority for character in "/\\@"):
        return ""
    try:
        return (urlsplit("//" + authority).hostname or "").lower()
    except ValueError:
        return ""


def _security_error(kind: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(error_payload(message, kind=kind), status_code=status)


def install_security(app: FastAPI) -> None:
    app.state.session_token = secrets.token_urlsafe(32)
    app.state.upload_limits = load_upload_limits()

    @app.middleware("http")
    async def local_session_guard(request: Request, call_next):
        host_header = request.headers.get("host", "")
        if _hostname(host_header) not in LOCAL_HOSTS:
            return _security_error("invalid_host", "请求 Host 不是本机地址", 400)

        if request.method.upper() in MUTATION_METHODS:
            origin = request.headers.get("origin", "").strip()
            if origin:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme not in {"http", "https"}
                    or parsed.username is not None
                    or parsed.password is not None
                    or _hostname(parsed.netloc) not in LOCAL_HOSTS
                    or parsed.netloc.casefold() != host_header.casefold()
                ):
                    return _security_error("invalid_origin", "请求 Origin 与本地平台不一致", 403)

            supplied = request.headers.get(SESSION_HEADER, "")
            expected = str(request.app.state.session_token)
            if not supplied or not secrets.compare_digest(supplied, expected):
                return _security_error("session_required", "写操作缺少有效的平台会话令牌", 403)

            if request.url.path in {"/api/upload", "/api/v1/upload"}:
                raw_length = request.headers.get("content-length", "").strip()
                if raw_length:
                    try:
                        content_length = int(raw_length)
                    except ValueError:
                        return _security_error("invalid_content_length", "Content-Length 无效", 400)
                    limits: UploadLimits = request.app.state.upload_limits
                    if content_length > limits.request_bytes:
                        return _security_error(
                            "request_too_large",
                            f"上传请求超过限制 {limits.request_bytes} 字节",
                            413,
                        )
        return await call_next(request)


@session_router.get("/session")
def session(request: Request, context: AppContext = Depends(get_context)) -> dict[str, object]:
    del context
    return {
        "status": "ok",
        "token": str(request.app.state.session_token),
        "header": SESSION_HEADER,
    }

