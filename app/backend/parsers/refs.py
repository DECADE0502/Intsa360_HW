from __future__ import annotations

import re

_NAT_RE = re.compile(r"(\d+)")


def natural_key(ref: str) -> list[object]:
    return [int(token) if token.isdigit() else token.lower() for token in _NAT_RE.split(str(ref or ""))]
