from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.backend.parsers.bom_table import read_bom_rows


@dataclass(frozen=True)
class BomState:
    installed: dict[str, dict[str, object]]
    notices: tuple[str, ...]


def _normalized_ref(value: object) -> str:
    return str(value or "").strip().upper()


def _material_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "material_code": str(row.get("material_code") or row.get("part_number") or ""),
        "name": str(row.get("name") or ""),
        "model": str(row.get("model") or row.get("value") or ""),
        "description": str(row.get("description") or row.get("desc") or ""),
        "grade": str(row.get("grade") or ""),
        "package": str(row.get("package") or row.get("pcb_footprint") or row.get("pcb_package") or ""),
    }


def bom_by_ref(path: Path | None) -> dict[str, dict[str, object]]:
    if path is None:
        return {}
    result: dict[str, dict[str, object]] = {}
    for row in read_bom_rows(Path(path), require_refs=True):
        material = _material_payload(row)
        for value in row.get("refs") or []:
            ref = _normalized_ref(value)
            if ref:
                result.setdefault(ref, material)
    return result


def load_bom_state(path: Path) -> BomState:
    installed = bom_by_ref(path)
    if not installed:
        raise ValueError("成品 BOM 中没有识别到有效位号，请确认选择的是 PLM/OA 成品 BOM。")
    return BomState(
        installed=installed,
        notices=("NC 按 XY 坐标位号减去成品 BOM 位号计算。",),
    )


def baseline_by_ref(path: Path | None) -> dict[str, dict[str, object]]:
    return bom_by_ref(path)
