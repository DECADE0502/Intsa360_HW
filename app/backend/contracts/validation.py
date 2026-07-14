from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_WINDOWS_INVALID_COMPONENT_CHARS = frozenset('<>:"|?*')
_WINDOWS_DEVICE_DIGIT_TRANSLATION = str.maketrans({"¹": "1", "²": "2", "³": "3"})


def _require_windows_safe_component(value: str) -> None:
    if not value or value in {".", ".."}:
        raise ValueError("path contains an empty or relative component")
    if value.endswith((" ", ".")):
        raise ValueError("Windows path components cannot end with a space or dot")
    if any(ord(character) < 32 or character in _WINDOWS_INVALID_COMPONENT_CHARS for character in value):
        raise ValueError("path contains a character that is invalid on Windows")
    basename = value.split(".", 1)[0].upper().translate(_WINDOWS_DEVICE_DIGIT_TRANSLATION)
    if basename in _WINDOWS_RESERVED_NAMES:
        raise ValueError("path uses a reserved Windows device name")


def normalize_windows_safe_relative_path(value: str) -> str:
    if value != value.strip():
        raise ValueError("asset path cannot have surrounding whitespace")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not path.parts or path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts:
        raise ValueError("asset path must be relative and cannot traverse parents")
    for component in path.parts:
        _require_windows_safe_component(component)
    return path.as_posix()


def require_windows_safe_filename(value: str) -> str:
    if value != value.strip() or "/" in value or "\\" in value:
        raise ValueError("filename must be a plain Windows filename")
    _require_windows_safe_component(value)
    return value
