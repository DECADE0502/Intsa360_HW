from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.backend.parsers.refs import natural_key
from app.backend.parsers.xy import Component, UnitInfo, parse_xy_file


@dataclass(frozen=True)
class BoardGeometry:
    units: UnitInfo
    components: tuple[Component, ...]
    bbox: dict[str, float]
    source_span: dict[str, float]


def build_board_geometry(path: Path) -> BoardGeometry:
    units, parsed = parse_xy_file(Path(path))
    if not parsed:
        raise ValueError("XY 坐标文件中没有器件数据。")

    by_ref: dict[str, Component] = {}
    for component in parsed:
        ref = component.ref.strip().upper()
        if not ref:
            continue
        if ref in by_ref:
            raise ValueError(f"XY 坐标文件中位号 {ref} 重复，无法确定唯一位置。")
        by_ref[ref] = Component(
            ref=ref,
            x_mm=component.x_mm,
            y_mm=component.y_mm,
            rotation=component.rotation,
            side=component.side,
            footprint=component.footprint,
            source_line=component.source_line,
        )
    if not by_ref:
        raise ValueError("XY 坐标文件中没有有效位号。")

    components = tuple(sorted(by_ref.values(), key=lambda item: natural_key(item.ref)))
    min_x = min(item.x_mm for item in components)
    max_x = max(item.x_mm for item in components)
    min_y = min(item.y_mm for item in components)
    max_y = max(item.y_mm for item in components)
    width = max_x - min_x
    height = max_y - min_y
    margin = max(1.0, min(3.0, max(width, height) * 0.04))
    return BoardGeometry(
        units=units,
        components=components,
        bbox={
            "min_x": min_x - margin,
            "min_y": min_y - margin,
            "max_x": max_x + margin,
            "max_y": max_y + margin,
            "width": width + margin * 2,
            "height": height + margin * 2,
        },
        source_span={"width": width, "height": height},
    )
