from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.backend.tools.bom_domain import (
    BOM_SCHEMA_VERSION,
    EXCLUSION_KINDS,
    MATERIAL_ROLES,
    PLACEMENT_DESTINATIONS,
    SHIELD_SUBTYPES,
)


@dataclass(frozen=True)
class DecisionManifest:
    schema_version: int
    rule_version: str
    source_fingerprint: str
    placements: tuple[dict[str, object], ...]

    def by_ref(self) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for placement in self.placements:
            for raw_ref in placement["refs"]:
                ref = str(raw_ref).strip().upper()
                previous = result.get(ref)
                if previous is not None and _decision_signature(previous) != _decision_signature(placement):
                    raise ValueError(f"BOM 决策清单中位号 {ref} 存在互相冲突的决议。")
                result[ref] = placement
        return result


def _decision_signature(placement: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        str(placement.get(field) or "").strip()
        for field in ("destination", "exclusion_kind", "role", "subtype", "decision_fingerprint")
    )


def _validated_placement(raw: object, index: int) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"BOM 决策清单第 {index + 1} 项不是对象。")
    refs_raw = raw.get("refs")
    if not isinstance(refs_raw, list):
        raise ValueError(f"BOM 决策清单第 {index + 1} 项缺少位号列表。")
    refs = list(dict.fromkeys(str(value).strip().upper() for value in refs_raw if str(value).strip()))
    if not refs:
        raise ValueError(f"BOM 决策清单第 {index + 1} 项没有有效位号。")

    destination = str(raw.get("destination") or "").strip()
    exclusion_kind = str(raw.get("exclusion_kind") or "").strip()
    role = str(raw.get("role") or "unknown").strip()
    subtype = str(raw.get("subtype") or "").strip()
    if destination not in PLACEMENT_DESTINATIONS:
        raise ValueError(f"BOM 决策清单第 {index + 1} 项目标区域无效。")
    if destination == "smt" and exclusion_kind:
        raise ValueError(f"BOM 决策清单第 {index + 1} 项的贴片决议不能带排除类型。")
    if destination == "non_smt" and exclusion_kind not in EXCLUSION_KINDS:
        raise ValueError(f"BOM 决策清单第 {index + 1} 项缺少有效排除类型。")
    if role not in MATERIAL_ROLES:
        raise ValueError(f"BOM 决策清单第 {index + 1} 项器件角色无效。")
    if role == "shield":
        if subtype not in SHIELD_SUBTYPES:
            raise ValueError(f"BOM 决策清单第 {index + 1} 项屏蔽类型无效。")
        if subtype == "bracket" and destination != "smt":
            raise ValueError("屏蔽支架必须归入贴片区。")
        if subtype == "cover" and (destination != "non_smt" or exclusion_kind != "scope_excluded"):
            raise ValueError("屏蔽罩必须归入非贴片区并标记为范围排除。")

    material = raw.get("material_snapshot")
    return {
        **dict(raw),
        "refs": refs,
        "destination": destination,
        "exclusion_kind": exclusion_kind,
        "role": role,
        "subtype": subtype,
        "material_snapshot": dict(material) if isinstance(material, Mapping) else {},
    }


def parse_decision_manifest(payload: object) -> DecisionManifest:
    if not isinstance(payload, Mapping):
        raise ValueError("BOM 决策清单不是有效对象。")
    try:
        schema_version = int(payload.get("schema_version") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("BOM 决策清单 schema_version 无效。") from exc
    if schema_version != BOM_SCHEMA_VERSION:
        raise ValueError(
            f"BOM 决策清单版本不兼容：需要 schema {BOM_SCHEMA_VERSION}，实际为 {schema_version or '未知'}。"
        )
    rule_version = str(payload.get("rule_version") or "").strip()
    if not rule_version:
        raise ValueError("BOM 决策清单缺少 rule_version。")
    placements_raw = payload.get("placements")
    if not isinstance(placements_raw, list):
        raise ValueError("BOM 决策清单缺少 placements 列表。")
    manifest = DecisionManifest(
        schema_version=schema_version,
        rule_version=rule_version,
        source_fingerprint=str(payload.get("source_fingerprint") or "").strip(),
        placements=tuple(_validated_placement(item, index) for index, item in enumerate(placements_raw)),
    )
    manifest.by_ref()
    return manifest


def load_decision_manifest(path: Path) -> DecisionManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"无法读取 BOM 决策清单：{path.name}") from exc
    except ValueError as exc:
        raise ValueError(f"BOM 决策清单不是有效 JSON：{path.name}") from exc
    return parse_decision_manifest(payload)
