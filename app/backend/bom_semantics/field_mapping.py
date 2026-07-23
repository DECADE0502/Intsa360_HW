from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from app.backend.bom_semantics.models import WorkbookProfile


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "item": ("项次", "item", "序号"),
    "level": ("层级", "level"),
    "parent_code": ("父项编码", "编码父", "编码（父）", "编码(父)", "parent code"),
    "parent_description": ("父项描述", "描述父", "描述（父）", "描述(父)", "板名", "parent description"),
    "material_code": (
        "子项编码",
        "编码子",
        "编码（子）",
        "编码(子)",
        "物料编码",
        "料号",
        "part number",
        "pn",
        "编码",
    ),
    "name": ("名称", "物料名称", "part type"),
    "model": ("型号", "规格型号", "规格", "model", "mpn"),
    "description": (
        "物料描述",
        "子项描述",
        "描述子",
        "描述（子）",
        "描述(子)",
        "器件描述",
        "器件描述（新整理）",
        "description",
    ),
    "unit": ("单位", "默认单位", "unit", "uom"),
    "quantity": ("数量", "用量", "quantity", "qty"),
    "reference": ("位号", "reference", "ref", "refdes", "designator"),
    "remark": ("备注", "remark", "note"),
    "grade": ("物料优选等级", "优选等级", "物料等级", "等级"),
    "grade_remark": ("物料优选等级备注", "等级备注"),
    "substitute_group_code": ("替代组编码", "替代组", "substitute group"),
    "substitute_strategy": ("替代策略",),
    "substitute_mode": ("替代方式",),
    "substitute_priority": ("替代优先级", "优先级"),
    "issue_method": ("发料方式", "领料方式"),
    "mrp": ("是否参与mrp运算", "参与mrp", "mrp"),
    "jump_level": ("是否跳层", "跳层"),
    "hardware_version": ("硬件版本", "适用版本", "版本"),
    "change_type": ("变更类型",),
    "change_status": ("状态", "变更状态"),
    "affected_bom": ("受影响bom",),
    "highest_bom": ("最高层级bom",),
    "project": ("受影响项目", "研发项目", "项目"),
    "manufacturer": ("制造商", "manufacturer"),
    "pcb_footprint": ("pcb footprint", "footprint"),
    "pcb_package": ("pcb封装", "封装"),
}

REQUIRED_FIELDS = ("material_code", "quantity")
_SPACE_RE = re.compile(r"\s+")
_OA_SUFFIX_RE = re.compile(r"##.*$")


def normalize_header(value: object) -> str:
    text = str(value or "").strip()
    text = _OA_SUFFIX_RE.sub("", text)
    text = text.replace("*", "").replace("{", "").replace("}", "")
    text = text.replace("_", " ")
    text = _SPACE_RE.sub("", text)
    return text.casefold()


NORMALIZED_ALIASES: dict[str, frozenset[str]] = {
    field: frozenset(normalize_header(alias) for alias in aliases)
    for field, aliases in FIELD_ALIASES.items()
}


@dataclass(frozen=True)
class HeaderDetection:
    row: int
    score: int
    field_columns: Mapping[str, int]
    mapping_candidates: Mapping[str, tuple[int, ...]]
    repeated_header_rows: tuple[int, ...] = ()


def _candidate_columns(values: Iterable[object]) -> dict[str, list[int]]:
    normalized = [normalize_header(value) for value in values]
    candidates: dict[str, list[int]] = {}
    for field, aliases in NORMALIZED_ALIASES.items():
        matches = [index for index, value in enumerate(normalized, start=1) if value in aliases]
        if matches:
            candidates[field] = matches
    return candidates


def _resolve_description_columns(
    values: list[object],
    candidates: dict[str, list[int]],
) -> None:
    normalized = [normalize_header(value) for value in values]
    generic_description = normalize_header("描述")
    generic_columns = [index for index, value in enumerate(normalized, start=1) if value == generic_description]
    parent_code_columns = candidates.get("parent_code", [])
    material_code_columns = candidates.get("material_code", [])

    if "parent_description" not in candidates and parent_code_columns:
        expected = parent_code_columns[0] + 1
        if expected in generic_columns:
            candidates["parent_description"] = [expected]

    explicit_description = candidates.get("description", [])
    if material_code_columns:
        material_col = material_code_columns[0]
        after_material = [col for col in generic_columns if col > material_col]
        if after_material:
            preferred = after_material[-1] if len(after_material) > 1 else after_material[0]
            candidates["description"] = [preferred, *[col for col in explicit_description if col != preferred]]
    elif generic_columns and "description" not in candidates:
        candidates["description"] = [generic_columns[-1]]


def map_header_values(values: list[object]) -> tuple[dict[str, int], dict[str, tuple[int, ...]], int]:
    candidates = _candidate_columns(values)
    _resolve_description_columns(values, candidates)
    mapping = {field: columns[0] for field, columns in candidates.items() if columns}
    score_fields = {
        "material_code",
        "parent_code",
        "quantity",
        "reference",
        "substitute_group_code",
        "substitute_priority",
        "change_type",
        "change_status",
    }
    score = sum(3 if field in {"material_code", "quantity"} else 1 for field in score_fields if field in mapping)
    return mapping, {field: tuple(columns) for field, columns in candidates.items()}, score


def is_header_row(values: list[object], primary_mapping: Mapping[str, int] | None = None) -> bool:
    mapping, _, score = map_header_values(values)
    if "material_code" not in mapping:
        return False
    if primary_mapping is None:
        return score >= 4
    shared = {"material_code", "quantity"}.intersection(mapping).intersection(primary_mapping)
    return len(shared) == 2


def detect_header(worksheet: object, scan_rows: int = 50) -> HeaderDetection | None:
    best: tuple[int, int, dict[str, int], dict[str, tuple[int, ...]]] | None = None
    max_row = min(int(worksheet.max_row or 0), scan_rows)
    max_column = int(worksheet.max_column or 0)
    for row in range(1, max_row + 1):
        values = [worksheet.cell(row, col).value for col in range(1, max_column + 1)]
        mapping, candidates, score = map_header_values(values)
        if "material_code" not in mapping:
            continue
        candidate = (score, -row, mapping, candidates)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    if best is None:
        return None
    score, negative_row, mapping, candidates = best
    header_row = -negative_row
    repeated: list[int] = []
    for row in range(header_row + 1, int(worksheet.max_row or 0) + 1):
        values = [worksheet.cell(row, col).value for col in range(1, max_column + 1)]
        if is_header_row(values, mapping):
            repeated.append(row)
    return HeaderDetection(
        row=header_row,
        score=score,
        field_columns=mapping,
        mapping_candidates=candidates,
        repeated_header_rows=tuple(repeated),
    )


def apply_mapping_overrides(
    mapping: Mapping[str, int],
    overrides: Mapping[str, int] | None,
    max_column: int,
) -> dict[str, int]:
    resolved = dict(mapping)
    for field, column in (overrides or {}).items():
        if field not in FIELD_ALIASES:
            raise ValueError(f"未知 BOM 字段映射: {field}")
        column_number = int(column)
        if column_number < 1 or column_number > max_column:
            raise ValueError(f"BOM 字段 {field} 的列号超出工作表范围")
        resolved[field] = column_number
    return resolved


def infer_profile(mapping: Mapping[str, int], unique_parent_codes: int = 0) -> WorkbookProfile:
    if {"change_type", "change_status", "material_code"}.issubset(mapping):
        return WorkbookProfile.OA_ECR
    if {"level", "material_code"}.issubset(mapping) and "parent_code" not in mapping:
        return WorkbookProfile.OA_BOM
    if "parent_code" in mapping and "material_code" in mapping:
        if unique_parent_codes > 1:
            return WorkbookProfile.PLM_MULTI_BOARD
        return WorkbookProfile.PLM_SINGLE_BOARD
    if {"material_code", "reference"}.issubset(mapping):
        return WorkbookProfile.CAPTURE_RAW
    return WorkbookProfile.UNKNOWN


def missing_required_fields(mapping: Mapping[str, int]) -> tuple[str, ...]:
    return tuple(field for field in REQUIRED_FIELDS if field not in mapping)
