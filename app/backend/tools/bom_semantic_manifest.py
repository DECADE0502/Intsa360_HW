from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.backend.bom_semantics.contracts import (
    BOM_COMPARE_SCHEMA_VERSION,
    BOM_SEMANTIC_MODEL_VERSION,
)
from app.backend.bom_semantics.models import BoardBOM
from app.backend.bom_semantics.normalization import normalize_workbook
from app.backend.bom_semantics.substitutes import build_board_boms
from app.backend.tools.bom_decisions import DecisionManifest


SEMANTIC_MANIFEST_KIND = "bom_process_semantic_manifest"


def _normalized_ref(value: object) -> str:
    return str(value or "").strip().upper()


def _mapping_list(value: object, field: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError(f"BOM 语义清单缺少 {field} 列表。")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"BOM 语义清单 {field} 必须只包含对象。")
    return tuple(dict(item) for item in value)


def _flatten_boards(
    boards: tuple[BoardBOM, ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    placements: list[dict[str, object]] = []
    groups: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    for board in boards:
        placements.extend(placement.payload() for placement in board.placements)
        groups.extend(group.payload() for group in board.substitute_groups)
        findings.extend(finding.payload() for finding in board.findings)
    return placements, groups, findings


def _decision_refs(
    decisions: tuple[dict[str, object], ...] | list[dict[str, object]],
    destination: str,
) -> set[str]:
    return {
        ref
        for decision in decisions
        if str(decision.get("destination") or "") == destination
        for value in decision.get("refs") or []
        if (ref := _normalized_ref(value))
    }


def _placement_refs(placements: list[dict[str, object]]) -> set[str]:
    return {
        ref
        for placement in placements
        if (ref := _normalized_ref(placement.get("reference")))
    }


def _validate_placement_partition(
    placements: list[dict[str, object]],
    decisions: tuple[dict[str, object], ...] | list[dict[str, object]],
) -> None:
    semantic_refs = _placement_refs(placements)
    decision_refs = _decision_refs(decisions, "smt")
    if semantic_refs == decision_refs:
        return
    missing = sorted(decision_refs - semantic_refs)
    unexpected = sorted(semantic_refs - decision_refs)
    details: list[str] = []
    if missing:
        details.append("处理决策存在但成品 BOM 缺失：" + ",".join(missing[:20]))
    if unexpected:
        details.append("成品 BOM 存在但处理决策缺失：" + ",".join(unexpected[:20]))
    raise ValueError("BOM 语义清单生成失败：" + "；".join(details))


@dataclass(frozen=True)
class SemanticBomManifest:
    schema_version: int
    model_version: str
    rule_version: str
    source_fingerprint: str
    processed_source_fingerprint: str
    boards: tuple[dict[str, object], ...]
    placements: tuple[dict[str, object], ...]
    substitute_group_records: tuple[dict[str, object], ...]
    decisions: tuple[dict[str, object], ...]
    findings: tuple[dict[str, object], ...]
    summary: dict[str, object]
    source_file: str = ""

    def installed_by_ref(self) -> dict[str, dict[str, object]]:
        item_lookup: dict[tuple[str, str], dict[str, object]] = {}
        for board in self.boards:
            parent_code = str(board.get("parent_code") or "")
            for raw_item in board.get("items") or []:
                if not isinstance(raw_item, Mapping):
                    continue
                item = dict(raw_item)
                key = parent_code, str(item.get("material_code") or "")
                if key not in item_lookup or item.get("substitute_priority") == 0:
                    item_lookup[key] = item

        result: dict[str, dict[str, object]] = {}
        for placement in self.placements:
            ref = _normalized_ref(placement.get("reference"))
            if not ref:
                continue
            parent_code = str(placement.get("parent_code") or "")
            material_code = str(placement.get("material_code") or "")
            item = item_lookup.get((parent_code, material_code), {})
            variants = item.get("variants") if isinstance(item, Mapping) else None
            variant = (
                dict(variants[0])
                if isinstance(variants, list) and variants and isinstance(variants[0], Mapping)
                else {}
            )
            result[ref] = {
                **dict(placement),
                "refs": [ref],
                "part_number": material_code,
                "material_code": material_code,
                "name": str(variant.get("name") or ""),
                "model": str(variant.get("model") or ""),
                "description": str(variant.get("description") or ""),
                "grade": str(variant.get("grade") or ""),
                "package": str(
                    variant.get("pcb_footprint")
                    or variant.get("pcb_package")
                    or ""
                ),
            }
        return result

    def non_smt_by_ref(self) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for decision in self.decisions:
            if str(decision.get("destination") or "") != "non_smt":
                continue
            snapshot = decision.get("material_snapshot")
            material = dict(snapshot) if isinstance(snapshot, Mapping) else {}
            for value in decision.get("refs") or []:
                ref = _normalized_ref(value)
                if not ref:
                    continue
                result[ref] = {
                    "refs": [ref],
                    "part_number": str(material.get("part_number") or ""),
                    "material_code": str(material.get("part_number") or ""),
                    "name": str(material.get("name") or ""),
                    "model": str(material.get("model") or ""),
                    "description": str(material.get("desc") or ""),
                    "grade": str(material.get("grade") or ""),
                    "package": str(
                        material.get("pcb_footprint")
                        or material.get("pcb_package")
                        or ""
                    ),
                    "destination": "non_smt",
                    "exclusion_kind": str(decision.get("exclusion_kind") or ""),
                    "role": str(decision.get("role") or ""),
                    "subtype": str(decision.get("subtype") or ""),
                }
        return result

    def substitute_groups(self) -> list[dict[str, object]]:
        return [dict(group) for group in self.substitute_group_records]

    def alternative_items(self) -> list[dict[str, object]]:
        alternatives: list[dict[str, object]] = []
        for group in self.substitute_group_records:
            for item in group.get("alternative_items") or []:
                if isinstance(item, Mapping):
                    alternatives.append(dict(item))
        return alternatives


def parse_semantic_manifest(payload: object, *, source_file: str = "") -> SemanticBomManifest:
    if not isinstance(payload, Mapping):
        raise ValueError("BOM 语义清单顶层必须是对象。")
    if payload.get("manifest_kind") != SEMANTIC_MANIFEST_KIND:
        raise ValueError("文件不是 BOM 处理语义清单。")
    if int(payload.get("schema_version") or 0) != BOM_COMPARE_SCHEMA_VERSION:
        raise ValueError("BOM 语义清单 schema 版本不受支持。")
    if str(payload.get("model_version") or "") != BOM_SEMANTIC_MODEL_VERSION:
        raise ValueError("BOM 语义清单模型版本不受支持。")

    manifest = SemanticBomManifest(
        schema_version=BOM_COMPARE_SCHEMA_VERSION,
        model_version=BOM_SEMANTIC_MODEL_VERSION,
        rule_version=str(payload.get("rule_version") or ""),
        source_fingerprint=str(payload.get("source_fingerprint") or ""),
        processed_source_fingerprint=str(payload.get("processed_source_fingerprint") or ""),
        boards=_mapping_list(payload.get("boards"), "boards"),
        placements=_mapping_list(payload.get("placements"), "placements"),
        substitute_group_records=_mapping_list(
            payload.get("substitute_groups"),
            "substitute_groups",
        ),
        decisions=_mapping_list(payload.get("decisions"), "decisions"),
        findings=_mapping_list(payload.get("findings"), "findings"),
        summary=dict(payload.get("summary") or {}),
        source_file=source_file,
    )
    refs = list(manifest.installed_by_ref())
    if len(refs) != len(manifest.placements):
        raise ValueError("BOM 语义清单存在空位号或重复实际贴装位号。")
    _validate_placement_partition(list(manifest.placements), list(manifest.decisions))
    return manifest


def load_semantic_manifest(path: Path) -> SemanticBomManifest:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"无法读取 BOM 语义清单：{source.name}") from exc
    except ValueError as exc:
        raise ValueError(f"BOM 语义清单不是有效 JSON：{source.name}") from exc
    return parse_semantic_manifest(payload, source_file=str(source))


def write_semantic_manifest(
    path: Path,
    processed_bom: Path,
    decision_manifest: DecisionManifest,
) -> Path:
    normalized = normalize_workbook(Path(processed_bom))
    boards = build_board_boms(normalized)
    placements, groups, board_findings = _flatten_boards(boards)
    findings = [finding.payload() for finding in normalized.findings] + board_findings
    _validate_placement_partition(placements, list(decision_manifest.placements))
    payload = {
        "manifest_kind": SEMANTIC_MANIFEST_KIND,
        "schema_version": BOM_COMPARE_SCHEMA_VERSION,
        "model_version": BOM_SEMANTIC_MODEL_VERSION,
        "rule_version": decision_manifest.rule_version,
        "source_fingerprint": decision_manifest.source_fingerprint,
        "processed_source_fingerprint": normalized.envelope.source_fingerprint,
        "processed_bom": str(Path(processed_bom)),
        "boards": [board.payload() for board in boards],
        "placements": placements,
        "substitute_groups": groups,
        "decisions": list(decision_manifest.placements),
        "findings": findings,
        "summary": {
            "board_count": len(boards),
            "material_count": sum(len(board.items) for board in boards),
            "actual_reference_count": len(placements),
            "substitute_group_count": len(groups),
            "alternative_material_count": sum(
                len(group.alternative_items)
                for board in boards
                for group in board.substitute_groups
            ),
            "non_smt_reference_count": len(
                _decision_refs(list(decision_manifest.placements), "non_smt")
            ),
            "finding_count": len(findings),
        },
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    load_semantic_manifest(destination)
    return destination
