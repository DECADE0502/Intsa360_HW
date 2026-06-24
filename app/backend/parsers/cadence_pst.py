from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


_NAT_RE = re.compile(r"(\d+)")


def natural_key(value: str) -> list[object]:
    return [int(token) if token.isdigit() else token.lower() for token in _NAT_RE.split(str(value))]


def natural_join(values: Iterable[str]) -> str:
    return ",".join(sorted(set(values), key=natural_key))


def read_text_guess(path: Path) -> str:
    for encoding in ("utf-8", "gb18030", "cp936"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def clean_pst_string(value: str) -> str:
    text = value.strip().rstrip(";").rstrip(":").strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        text = text[1:-1]
    return text.strip()


def _parse_node_tokens(line: str) -> tuple[str, str] | None:
    tokens = line.strip().split()
    if len(tokens) >= 3 and tokens[0].upper() == "NODE_NAME":
        return tokens[1], tokens[2]
    return None


def parse_net_file(folder: Path) -> dict[str, dict[str, list[str]]]:
    path = folder / "pstxnet.dat"
    if not path.exists():
        raise ValueError(f"缺少 pstxnet.dat: {folder}")

    nets: dict[str, dict[str, set[str]]] = {}
    current: str | None = None
    pending_name = False

    for raw in read_text_guess(path).splitlines():
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper == "NET_NAME":
            pending_name = True
            current = None
            continue
        if pending_name:
            name = clean_pst_string(line)
            if name and not name.startswith("@") and "=" not in name:
                current = name
                nets.setdefault(current, {"refs": set(), "pins": set(), "nodes": set()})
                pending_name = False
            continue
        node = _parse_node_tokens(line)
        if node and current:
            ref, pin = node
            nets[current]["refs"].add(ref)
            nets[current]["pins"].add(pin)
            nets[current]["nodes"].add(f"{ref}.{pin}")
            continue

        # Simple fallback: NET N1 R1.1 C1.2
        parts = line.split()
        if not parts:
            continue
        if parts[0].upper() == "NET" and len(parts) >= 2:
            name = parts[1]
            tokens = parts[2:]
        else:
            name = parts[0]
            tokens = parts[1:]
        if not tokens or name in {"FILE_TYPE", "C_SIGNAL"} or "=" in name:
            continue
        entry = nets.setdefault(clean_pst_string(name), {"refs": set(), "pins": set(), "nodes": set()})
        for token in tokens:
            clean = clean_pst_string(token)
            ref, _, pin = clean.partition(".")
            if not ref:
                continue
            entry["refs"].add(ref)
            if pin:
                entry["pins"].add(pin)
                entry["nodes"].add(f"{ref}.{pin}")
            else:
                entry["nodes"].add(ref)

    return {
        name: {
            "refs": sorted(data["refs"], key=natural_key),
            "pins": sorted(data["pins"], key=natural_key),
            "nodes": sorted(data["nodes"], key=natural_key),
        }
        for name, data in nets.items()
    }


def parse_part_file(folder: Path) -> dict[str, str]:
    path = folder / "pstxprt.dat"
    if not path.exists():
        raise ValueError(f"缺少 pstxprt.dat: {folder}")

    parts: dict[str, str] = {}
    pending_part = False
    part_re = re.compile(r"^([A-Za-z]+\d+[A-Za-z0-9_-]*)\s+'([^']+)'")
    for raw in read_text_guess(path).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper() == "PART_NAME":
            pending_part = True
            continue
        match = part_re.match(line)
        if match:
            parts[match.group(1)] = match.group(2).strip()
            pending_part = False
            continue
        if pending_part:
            tokens = line.split(None, 1)
            if len(tokens) >= 2:
                parts[tokens[0]] = clean_pst_string(tokens[1])
                pending_part = False
    return parts

