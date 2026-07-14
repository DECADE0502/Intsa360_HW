from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI, Request

from app.backend.paths import AppPaths


DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5
REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = ("authorization", "password", "secret", "session", "token")
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(authorization|x-insta360-session|session_token|token|secret|password)"
    r"(\s*[:=]\s*)(?:bearer\s+)?([^\s,;]+)"
)


def redact_text(value: object, secrets: Iterable[str] = ()) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), REDACTED)
    return _ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", text)


def _redact_value(value: object, secrets: tuple[str, ...], key: str = "") -> object:
    if any(marker in key.casefold() for marker in _SENSITIVE_KEYS):
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): _redact_value(item, secrets, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(value, secrets)


class RedactingJsonFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self.secrets = tuple(str(secret) for secret in secrets if str(secret))

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "event": redact_text(getattr(record, "event", record.name), self.secrets),
            "message": redact_text(record.getMessage(), self.secrets),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict) and context:
            payload["context"] = _redact_value(context, self.secrets)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info), self.secrets)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def configure_platform_logging(
    root: Path,
    *,
    secrets: Iterable[str] = (),
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    if max_bytes <= 0 or backup_count < 1:
        raise ValueError("log rotation limits must be positive")
    log_dir = AppPaths(root).runtime_log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"insta360_hw.{uuid.uuid4().hex}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        log_dir / "platform.jsonl",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(RedactingJsonFormatter(secrets))
    logger.addHandler(handler)
    return logger


def close_platform_logging(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.flush()
        finally:
            handler.close()


def install_request_logging(app: FastAPI, logger: logging.Logger) -> None:
    @app.middleware("http")
    async def log_request(request: Request, call_next):
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except BaseException as exc:  # noqa: BLE001
            logger.error(
                "HTTP request failed",
                extra={
                    "event": "http_request_failed",
                    "context": {
                        "method": request.method,
                        "path": request.url.path,
                        "error_type": type(exc).__name__,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    },
                },
            )
            raise
        logger.info(
            "HTTP request completed",
            extra={
                "event": "http_request",
                "context": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                },
            },
        )
        return response
