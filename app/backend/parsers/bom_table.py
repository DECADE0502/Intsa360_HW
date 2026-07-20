from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from app.backend.parsers._workbook import build_merged_cell_lookup, open_bom_workbook


REF_SPLIT_RE = re.compile(r"[,;\s]+")

FIELD_ALIASES = {
    "reference": ["位号", "位置号", "Reference", "Ref", "RefDes", "Designator", "BOM1位号", "BOM2位号"],
    "part_number": ["编号", "料号", "物料编码", "子项编码", "编码子", "编码（子）", "编码(子)", "Part Number", "PN"],
    "description": ["描述", "物料描述", "子项描述", "描述子", "描述（子）", "描述(子)", "器件描述", "器件描述（新整理）", "Description"],
    "quantity": ["数量", "用量", "Qty", "Quantity"],
    "name": ["名称", "物料名称", "Part Type"],
    "package": ["封装名", "PCB封装", "PCB Footprint", "Package", "Footprint"],
    "value": ["Value", "值"],
    "model": ["型号", "规格型号", "规格", "Model", "MPN"],
    "grade": ["物料优选等级", "优选等级", "物料等级", "等级"],
    "unit": ["单位", "Unit", "UOM"],
}

INHERIT_FIELDS = frozenset({"part_number", "name", "description", "model", "grade", "unit", "package", "value"})


def normalize_header(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"##.*$", "", text)
    text = text.replace("*", "").replace("{", "").replace("}", "")
    return re.sub(r"\s+", "", text)


def find_header(ws, required: Iterable[str], scan_rows: int = 30) -> tuple[int, dict[str, int]]:
    required = list(required)
    best_row = 1
    best_map: dict[str, int] = {}
    for row in range(1, min(ws.max_row, scan_rows) + 1):
        normalized_values = [normalize_header(ws.cell(row, col).value) for col in range(1, ws.max_column + 1)]
        mapping: dict[str, int] = {}
        for canonical, aliases in FIELD_ALIASES.items():
            normalized_aliases = {normalize_header(alias) for alias in aliases}
            for idx, value in enumerate(normalized_values, start=1):
                if value in normalized_aliases:
                    mapping[canonical] = idx
                    break
        score = sum(1 for key in required if key in mapping)
        if score > sum(1 for key in required if key in best_map):
            best_row = row
            best_map = mapping
    missing = [key for key in required if key not in best_map]
    if missing:
        raise ValueError(f"表头识别失败，缺少字段: {', '.join(missing)}")
    return best_row, best_map


def _choose_best_column(
    normalized_values: list[str],
    aliases: Iterable[str],
    anchor_col: int | None = None,
    prefer_after_anchor: bool = False,
) -> int | None:
    normalized_aliases = {normalize_header(alias) for alias in aliases}
    matches = [idx for idx, value in enumerate(normalized_values, start=1) if value in normalized_aliases]
    if not matches:
        return None
    if anchor_col is not None and prefer_after_anchor:
        after_anchor = [idx for idx in matches if idx > anchor_col]
        if after_anchor:
            return after_anchor[0]
    return matches[0]


def _choose_reference_column(ws, header_row: int, normalized_values: list[str], anchor_col: int | None) -> int | None:
    aliases = {normalize_header(alias) for alias in FIELD_ALIASES["reference"]}
    matches = [idx for idx, value in enumerate(normalized_values, start=1) if value in aliases]
    if not matches:
        return None

    def score(col: int) -> tuple[int, int, int, int]:
        ref_like = 0
        non_empty = 0
        for row in range(header_row + 1, min(ws.max_row, header_row + 50) + 1):
            value = ws.cell(row, col).value
            if value is None or str(value).strip() == "":
                continue
            non_empty += 1
            ref_like += sum(
                1
                for token in split_refs(value)
                if re.fullmatch(r"[A-Za-z_]+\d+[A-Za-z]?", token)
            )
        after_anchor = int(anchor_col is not None and col > anchor_col)
        return ref_like, non_empty, after_anchor, -col

    return max(matches, key=score)


def refine_mapping(ws, header_row: int, mapping: dict[str, int]) -> dict[str, int]:
    normalized_values = [normalize_header(ws.cell(header_row, col).value) for col in range(1, ws.max_column + 1)]
    refined = dict(mapping)

    part_col = _choose_best_column(normalized_values, FIELD_ALIASES["part_number"])
    if part_col:
        refined["part_number"] = part_col

    for key in ["description", "quantity", "name", "package", "value", "model", "grade", "unit"]:
        col = _choose_best_column(
            normalized_values,
            FIELD_ALIASES[key],
            anchor_col=refined.get("part_number"),
            prefer_after_anchor=key in {"description", "quantity", "name", "package", "value"},
        )
        if col:
            refined[key] = col
    reference_col = _choose_reference_column(
        ws,
        header_row,
        normalized_values,
        refined.get("part_number"),
    )
    if reference_col:
        refined["reference"] = reference_col
    return refined


def split_refs(value: object) -> list[str]:
    return [part for part in REF_SPLIT_RE.split(str(value or "").strip()) if part]


def read_bom_rows(path: Path, require_refs: bool = True) -> list[dict[str, object]]:
    with open_bom_workbook(path, data_only=True) as wb:
        ws = wb.active
        merged_lookup = build_merged_cell_lookup(ws)
        header_row, mapping = find_header(ws, ["reference", "part_number", "description", "quantity"])
        mapping = refine_mapping(ws, header_row, mapping)

        def field_value(row: int, field: str, fallback: str | None = None) -> object:
            mapped_field = field if field in mapping else fallback
            if mapped_field is None or mapped_field not in mapping:
                return None
            col = mapping[mapped_field]
            value = ws.cell(row, col).value
            if value is None and mapped_field in INHERIT_FIELDS:
                value = merged_lookup.get((row, col))
            return value

        rows: list[dict[str, object]] = []
        for row in range(header_row + 1, ws.max_row + 1):
            refs = split_refs(field_value(row, "reference"))
            part_number = str(field_value(row, "part_number") or "").strip()
            if require_refs and not refs:
                continue
            if not refs and not part_number:
                continue
            rows.append(
                {
                    "source_row": row,
                    "reference": ",".join(refs),
                    "refs": refs,
                    "part_number": part_number,
                    "model": str(field_value(row, "model") or "").strip(),
                    "grade": str(field_value(row, "grade") or "").strip(),
                    "description": str(field_value(row, "description") or "").strip(),
                    "quantity": field_value(row, "quantity"),
                    "name": str(field_value(row, "name", "description") or "").strip(),
                    "package": str(field_value(row, "package", "description") or "").strip(),
                    "value": str(field_value(row, "value", "description") or "").strip(),
                    "unit": str(field_value(row, "unit") or "").strip(),
                }
            )
        return rows
