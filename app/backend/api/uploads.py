from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Protocol

from python_multipart.multipart import MultipartParser, parse_options_header


DEFAULT_FILE_BYTES = 100 * 1024 * 1024
DEFAULT_REQUEST_BYTES = 200 * 1024 * 1024


class StreamRequest(Protocol):
    def stream(self) -> AsyncIterator[bytes]: ...


class UploadLimitError(ValueError):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class UploadLimits:
    file_bytes: int = DEFAULT_FILE_BYTES
    request_bytes: int = DEFAULT_REQUEST_BYTES

    def __post_init__(self) -> None:
        if self.file_bytes <= 0 or self.request_bytes <= 0:
            raise ValueError("upload limits must be positive")
        if self.file_bytes > self.request_bytes:
            raise ValueError("single-file upload limit must not exceed request limit")


def _positive_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def load_upload_limits() -> UploadLimits:
    return UploadLimits(
        file_bytes=_positive_env("INSTA360_HW_MAX_UPLOAD_FILE_BYTES", DEFAULT_FILE_BYTES),
        request_bytes=_positive_env("INSTA360_HW_MAX_UPLOAD_REQUEST_BYTES", DEFAULT_REQUEST_BYTES),
    )


async def stream_request_to_disk(request: StreamRequest, target: Path, *, request_limit: int) -> int:
    copied = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb") as handle:
            async for chunk in request.stream():
                if not chunk:
                    continue
                copied += len(chunk)
                if copied > request_limit:
                    raise UploadLimitError(
                        "request_too_large",
                        f"上传请求超过限制 {request_limit} 字节",
                    )
                handle.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return copied


def multipart_boundary(content_type_header: str) -> bytes:
    marker = "boundary="
    if marker not in content_type_header:
        raise ValueError("missing multipart boundary")
    boundary = content_type_header.split(marker, 1)[1].split(";", 1)[0].strip().strip('"')
    if not boundary:
        raise ValueError("missing multipart boundary")
    return boundary.encode("utf-8")


def _decode_header_value(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("latin-1", errors="replace")


def parse_multipart_files_from_disk(
    body_path: Path,
    content_type_header: str,
    target_dir: Path,
    *,
    file_limit: int,
) -> list[dict[str, str]]:
    boundary = multipart_boundary(content_type_header)
    files: list[dict[str, str]] = []
    created: list[Path] = []
    header_field = bytearray()
    header_value = bytearray()
    headers: dict[bytes, bytes] = {}
    output = None
    filename = ""
    target: Path | None = None
    written = 0
    finished = False

    def on_part_begin() -> None:
        nonlocal headers, output, filename, target, written
        headers = {}
        output = None
        filename = ""
        target = None
        written = 0

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_field.extend(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_value.extend(data[start:end])

    def on_header_end() -> None:
        headers[bytes(header_field).lower()] = bytes(header_value)
        header_field.clear()
        header_value.clear()

    def on_headers_finished() -> None:
        nonlocal output, filename, target
        disposition = headers.get(b"content-disposition", b"")
        _, options = parse_options_header(disposition)
        raw_filename = options.get(b"filename", b"")
        if not raw_filename:
            return
        filename = Path(_decode_header_value(raw_filename)).name
        if not filename:
            return
        target = target_dir / filename
        output = target.open("wb")
        created.append(target)

    def on_part_data(data: bytes, start: int, end: int) -> None:
        nonlocal written
        if output is None:
            return
        chunk = data[start:end]
        written += len(chunk)
        if written > file_limit:
            raise UploadLimitError(
                "file_too_large",
                f"文件 {filename or '<unknown>'} 超过限制 {file_limit} 字节",
            )
        output.write(chunk)

    def on_part_end() -> None:
        nonlocal output
        if output is not None:
            output.close()
            output = None
        if target is not None:
            files.append({"name": filename, "path": str(target)})

    def on_end() -> None:
        nonlocal finished
        finished = True

    parser = MultipartParser(
        boundary,
        callbacks={
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_headers_finished": on_headers_finished,
            "on_part_data": on_part_data,
            "on_part_end": on_part_end,
            "on_end": on_end,
        },
        max_size=body_path.stat().st_size,
    )
    try:
        with body_path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                parser.write(chunk)
        parser.finalize()
        if not finished:
            raise ValueError("upload truncated before final multipart boundary")
    except BaseException:
        if output is not None:
            output.close()
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return files
