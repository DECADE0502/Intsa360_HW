from __future__ import annotations

import mimetypes
import re
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote

from openpyxl.utils.exceptions import InvalidFileException


USER_INPUT_ERROR_PATTERNS = ("缺少", "输入", "表头识别失败")


def safe_child(base: Path, requested: str) -> Path | None:
    target = (base / requested).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target


def resolve_output_member(outputs_dir: Path, requested: object) -> Path:
    text = unquote(str(requested)).strip()
    if not text:
        raise ValueError("empty package path")
    if text.startswith("\\\\") or text.startswith("//"):
        raise ValueError("package path must be inside data/outputs")
    normalized = text.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", normalized):
        candidate = Path(text)
        try:
            relative = candidate.resolve().relative_to(outputs_dir.resolve())
        except (OSError, ValueError) as exc:
            raise ValueError("package path must be inside data/outputs") from exc
    else:
        parts = [part for part in normalized.split("/") if part]
        if ".." in parts:
            raise ValueError("package path must not contain '..'")
        relative_parts = parts
        for index in range(0, max(len(parts) - 1, 0)):
            if [part.lower() for part in parts[index : index + 2]] == ["data", "outputs"]:
                relative_parts = parts[index + 2 :]
                break
        relative = Path(*relative_parts) if relative_parts else Path("")
    target = safe_child(outputs_dir, relative.as_posix())
    if target is None:
        raise ValueError("package path must be inside data/outputs")
    return target


def content_disposition(filename: str) -> str:
    fallback = "".join(
        character if 32 <= ord(character) < 127 and character not in {'"', "\\", ";"} else "_"
        for character in filename
    )
    encoded = quote(filename.encode("utf-8"))
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'


def content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def is_user_input_error(exc: Exception) -> bool:
    message = str(exc)
    return isinstance(
        exc,
        (KeyError, ValueError, FileNotFoundError, PermissionError, zipfile.BadZipFile, InvalidFileException),
    ) or any(pattern in message for pattern in USER_INPUT_ERROR_PATTERNS)


def error_payload(message: str, *, kind: str | None = None) -> dict[str, object]:
    return {
        "status": "error",
        "error": message,
        "message": message,
        "user_message": message,
        "error_kind": kind or "tool_error",
    }

