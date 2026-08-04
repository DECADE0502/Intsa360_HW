from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.backend.parsers._workbook import open_bom_workbook
from app.backend.parsers.bom_table import normalize_header, read_bom_rows, split_refs
from app.backend.tools.bom_decisions import load_decision_manifest
from app.backend.tools.bom_semantic_manifest import load_semantic_manifest


NC_KINDS = {"nc", "system_nc", "user_excluded", "insufficient_default"}
NON_SMT_KINDS = {"process_only", "process_default", "scope_excluded"}


@dataclass(frozen=True)
class BomState:
    installed: dict[str, dict[str, object]]
    excluded: dict[str, dict[str, object]]
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


def _bom_by_ref(path: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for row in read_bom_rows(path, require_refs=True):
        material = _material_payload(row)
        for value in row.get("refs") or []:
            ref = _normalized_ref(value)
            if ref:
                result.setdefault(ref, material)
    return result


def _find_column(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    normalized_aliases = {normalize_header(alias) for alias in aliases}
    return next((index for index, value in enumerate(headers, start=1) if value in normalized_aliases), None)


def _read_nc_summary(path: Path) -> dict[str, dict[str, object]]:
    with open_bom_workbook(path, data_only=True) as workbook:
        worksheet = workbook.active
        header_row = 0
        columns: dict[str, int] = {}
        for row in range(1, min(worksheet.max_row, 30) + 1):
            headers = [normalize_header(worksheet.cell(row, col).value) for col in range(1, worksheet.max_column + 1)]
            reference = _find_column(headers, ("位号", "Reference", "RefDes"))
            kind = _find_column(headers, ("判定类型", "排除类型", "Decision Type"))
            if reference:
                header_row = row
                columns = {
                    "reference": reference,
                    "kind": kind or 0,
                    "part_number": _find_column(headers, ("子项编码", "物料编码", "Part Number")) or 0,
                    "name": _find_column(headers, ("物料名称", "名称")) or 0,
                    "model": _find_column(headers, ("型号", "型号/封装")) or 0,
                    "description": _find_column(headers, ("描述", "物料描述")) or 0,
                    "reason": _find_column(headers, ("过滤原因", "判定原因", "原因")) or 0,
                }
                break
        if not header_row:
            raise ValueError("NC 汇总表中没有识别到位号列。")

        def value(row: int, field: str) -> object:
            column = columns.get(field, 0)
            return worksheet.cell(row, column).value if column else ""

        result: dict[str, dict[str, object]] = {}
        for row in range(header_row + 1, worksheet.max_row + 1):
            kind = str(value(row, "kind") or "system_nc").strip()
            for raw_ref in split_refs(value(row, "reference")):
                ref = _normalized_ref(raw_ref)
                if not ref:
                    continue
                status = "non_smt" if kind in NON_SMT_KINDS else "nc"
                result[ref] = {
                    "status": status,
                    "decision_kind": kind,
                    "reason": str(value(row, "reason") or ""),
                    "material_code": str(value(row, "part_number") or ""),
                    "name": str(value(row, "name") or ""),
                    "model": str(value(row, "model") or ""),
                    "description": str(value(row, "description") or ""),
                    "grade": "",
                    "package": "",
                }
        return result


def load_bom_state(
    bom_path: Path,
    *,
    semantic_manifest_path: Path | None = None,
    decision_manifest_path: Path | None = None,
    nc_path: Path | None = None,
) -> BomState:
    notices: list[str] = []
    if semantic_manifest_path is not None:
        manifest = load_semantic_manifest(semantic_manifest_path)
        manifest.verify_processed_bom(bom_path)
        installed = {ref: _material_payload(row) for ref, row in manifest.installed_by_ref().items()}
        excluded: dict[str, dict[str, object]] = {}
        for ref, row in manifest.non_smt_by_ref().items():
            kind = str(row.get("exclusion_kind") or "")
            excluded[ref] = {
                **_material_payload(row),
                "status": "nc" if kind in NC_KINDS else "non_smt",
                "decision_kind": kind,
                "reason": str(row.get("reason") or ""),
            }
        return BomState(installed=installed, excluded=excluded, notices=tuple(notices))

    installed = _bom_by_ref(bom_path)
    excluded = _read_nc_summary(nc_path) if nc_path is not None else {}
    if decision_manifest_path is not None:
        manifest = load_decision_manifest(decision_manifest_path)
        for ref, decision in manifest.by_ref().items():
            destination = str(decision.get("destination") or "")
            if destination == "smt":
                installed.setdefault(ref, _material_payload(dict(decision.get("material_snapshot") or {})))
                continue
            kind = str(decision.get("exclusion_kind") or "")
            excluded[ref] = {
                **_material_payload(dict(decision.get("material_snapshot") or {})),
                "status": "nc" if kind in NC_KINDS else "non_smt",
                "decision_kind": kind,
                "reason": str(decision.get("reason") or ""),
            }
    if not excluded:
        notices.append("未提供 NC 汇总或判定清单，坐标中未出现在成品 BOM 的位号将标记为“仅坐标有”。")
    overlap = sorted(set(installed) & set(excluded))
    if overlap:
        notices.append(f"有 {len(overlap)} 个位号同时出现在成品 BOM 与排除清单中，按排除清单显示并请人工核对。")
    return BomState(installed=installed, excluded=excluded, notices=tuple(notices))


def baseline_by_ref(path: Path | None) -> dict[str, dict[str, object]]:
    return _bom_by_ref(path) if path is not None else {}
