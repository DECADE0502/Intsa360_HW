from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Component:
    ref: str
    x_mm: float
    y_mm: float
    rotation: int
    side: Literal["top", "bottom"]
    footprint: str
    source_line: int


@dataclass(frozen=True)
class UnitInfo:
    version: str
    units: Literal["mils", "mm"]
    scale: float


def _parse_assignment(line: str) -> tuple[str, str] | None:
    key, separator, value = line.partition("=")
    if not separator:
        return None
    normalized = key.strip().upper()
    if normalized not in {"VERSION", "UUNITS"}:
        return None
    return normalized, value.strip()


def _rotation(value: str, line_number: int) -> int:
    try:
        numeric = float(value)
    except ValueError as exc:
        raise ValueError(f"XY 第 {line_number} 行旋转角度无效") from exc
    if not numeric.is_integer():
        raise ValueError(f"XY 第 {line_number} 行旋转角度无效")
    return int(numeric) % 360


def parse_xy_file(path: Path) -> tuple[UnitInfo, list[Component]]:
    source = Path(path)
    version = ""
    units: Literal["mils", "mm"] | None = None
    scale = 0.0
    pending_rows: list[tuple[int, list[str]]] = []

    with source.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            assignment = _parse_assignment(line)
            if assignment:
                key, value = assignment
                if key == "VERSION":
                    version = value
                else:
                    normalized_units = value.upper()
                    if normalized_units == "MILS":
                        units, scale = "mils", 0.0254
                    elif normalized_units == "MM":
                        units, scale = "mm", 1.0
                    else:
                        raise ValueError(f"XY 不支持的 UUNITS：{value}")
                continue
            fields = [field.strip() for field in line.split("!")]
            if len(fields) not in {6, 7}:
                raise ValueError(f"XY 第 {line_number} 行字段数不符")
            pending_rows.append((line_number, fields))

    if units is None:
        raise ValueError("XY 文件缺少 UUNITS 声明")

    components: list[Component] = []
    for line_number, fields in pending_rows:
        ref, x_value, y_value, rotation_value, mirror, footprint = fields[:6]
        if not ref or not footprint:
            raise ValueError(f"XY 第 {line_number} 行字段数不符")
        try:
            x_mm = float(x_value) * scale
            y_mm = float(y_value) * scale
        except ValueError as exc:
            raise ValueError(f"XY 第 {line_number} 行坐标无效") from exc
        components.append(
            Component(
                ref=ref,
                x_mm=x_mm,
                y_mm=y_mm,
                rotation=_rotation(rotation_value, line_number),
                side="bottom" if mirror.lower() == "m" else "top",
                footprint=footprint,
                source_line=line_number,
            )
        )

    return UnitInfo(version=version, units=units, scale=scale), components
