from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_DATA_ROW = re.compile(r"^\s*[^#!]+\s*!\s*[-+]?\d+(?:\.\d+)?\s*!\s*[-+]?\d+(?:\.\d+)?\s*!")
_SCHEMATIC_PARTS = {"schematic", "schematics", "sch", "原理图"}


@dataclass(frozen=True)
class DiscoveredSmtDirectory:
    root: Path
    xy_file: Path
    reference_pdf: Path | None
    file_count: int
    ignored_count: int


def _looks_like_xy(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")[:131072]
    except OSError:
        return False
    upper = text.upper()
    return (
        re.search(r"(?m)^\s*VERSION\s*=", upper) is not None
        and re.search(r"(?m)^\s*UUNITS\s*=\s*(MILS|MM)\s*$", upper) is not None
        and any(_DATA_ROW.match(line) for line in text.splitlines())
    )


def _is_schematic_path(path: Path, root: Path) -> bool:
    for part in path.relative_to(root).parts[:-1]:
        normalized = part.strip().lower()
        if normalized in _SCHEMATIC_PARTS or "原理图" in part:
            return True
    return False


def discover_smt_directory(root: Path) -> DiscoveredSmtDirectory:
    source = Path(root).resolve()
    if not source.is_dir():
        raise ValueError("请选择完整的 SMT 贴片资料目录。")

    files = [path for path in source.rglob("*") if path.is_file()]
    if len(files) > 10000:
        raise ValueError("SMT 资料目录文件过多，请确认没有误选上级目录。")

    xy_candidates = [path for path in files if path.suffix.lower() == ".txt" and _looks_like_xy(path)]
    if not xy_candidates:
        raise ValueError("所选目录中没有识别到有效 XY 坐标文件（需要 VERSION、UUNITS 和坐标数据行）。")
    xy_candidates.sort(
        key=lambda path: (
            len(path.relative_to(source).parts),
            0 if path.name.lower() == "xy.txt" else 1,
            path.as_posix().lower(),
        )
    )

    pdf_candidates = [
        path
        for path in files
        if path.suffix.lower() == ".pdf"
        and any(token in path.stem.upper() for token in ("SMD", "REF"))
        and not _is_schematic_path(path, source)
    ]
    pdf_candidates.sort(
        key=lambda path: (
            len(path.relative_to(source).parts),
            0 if "SMD" in path.stem.upper() else 1,
            path.as_posix().lower(),
        )
    )
    recognized = 1 + int(bool(pdf_candidates))
    return DiscoveredSmtDirectory(
        root=source,
        xy_file=xy_candidates[0],
        reference_pdf=pdf_candidates[0] if pdf_candidates else None,
        file_count=len(files),
        ignored_count=max(0, len(files) - recognized),
    )
