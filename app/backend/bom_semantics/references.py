from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


REFERENCE_SPLIT_RE = re.compile(r"[,，;；\s]+")
NATURAL_RE = re.compile(r"(\d+)")


@dataclass(frozen=True)
class ReferenceParseResult:
    references: tuple[str, ...]
    flags: tuple[str, ...]
    ignored_tokens: tuple[str, ...] = ()


def natural_reference_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(token) if token.isdigit() else token.casefold()
        for token in NATURAL_RE.split(str(value or ""))
    )


def normalize_reference_token(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).upper()


def split_reference_tokens(value: object) -> tuple[str, ...]:
    raw = str(value or "").strip()
    return tuple(token for token in REFERENCE_SPLIT_RE.split(raw) if token)


def parse_references(
    value: object,
    resolution: Mapping[str, object] | str | None = None,
) -> ReferenceParseResult:
    action = ""
    replacement = ""
    if isinstance(resolution, Mapping):
        action = str(resolution.get("action") or "")
        replacement = str(resolution.get("value") or "")
    elif resolution is not None:
        action = str(resolution)

    source_value = replacement if action == "replace" else value
    references: set[str] = set()
    flags: set[str] = set()
    ignored: list[str] = []
    for raw_token in split_reference_tokens(source_value):
        token = normalize_reference_token(raw_token)
        if not token:
            continue
        if token == "60":
            ignored.append(token)
            continue
        if token.isdigit():
            if action == "empty":
                ignored.append(token)
                continue
            if action != "keep" and action != "replace":
                flags.add("numeric_reference_suspected")
        references.add(token)
    return ReferenceParseResult(
        references=tuple(sorted(references, key=natural_reference_key)),
        flags=tuple(sorted(flags)),
        ignored_tokens=tuple(ignored),
    )
