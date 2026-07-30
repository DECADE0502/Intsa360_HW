from __future__ import annotations

import re
from dataclasses import dataclass

from app.backend.contracts.smt_analysis import PlacementRole, SmtEvidence
from app.backend.smt_analysis.evidence import evidence


_REF_PREFIX = re.compile(r"^([A-Z_]+)")


@dataclass(frozen=True)
class RoleInference:
    role: PlacementRole
    evidence: tuple[SmtEvidence, ...]
    strong_process_role: bool


_EXPLICIT_ROLE_MAP: dict[str, PlacementRole] = {
    "electronic": "smt_component",
    "smt_mechanical": "mechanical",
    "shield": "mechanical",
    "test_point": "test_point",
    "short_symbol": "manual_assembly",
    "mounting_hole": "mounting_hole",
    "fiducial": "fiducial",
    "unknown": "unknown",
}


def infer_role(
    ref: str,
    footprint: str,
    *,
    explicit_role: str = "",
    explicit_subtype: str = "",
) -> RoleInference:
    normalized_ref = str(ref or "").strip().upper()
    normalized_footprint = str(footprint or "").strip().upper()
    items: list[SmtEvidence] = []
    if explicit_role:
        mapped = _EXPLICIT_ROLE_MAP.get(explicit_role, "unknown")
        items.append(
            evidence(
                "bom_semantic_role",
                "BOM 处理记录已明确器件角色。",
                weight="strong",
                value=":".join(part for part in (explicit_role, explicit_subtype) if part),
            )
        )
        return RoleInference(
            role=mapped,
            evidence=tuple(items),
            strong_process_role=mapped
            in {"test_point", "fiducial", "mounting_hole", "tooling_hole", "panel_object"},
        )

    match = _REF_PREFIX.match(normalized_ref)
    prefix = match.group(1) if match else ""
    if prefix:
        items.append(
            evidence(
                "reference_prefix",
                "位号前缀只作为角色提示，不能单独决定装机或 NC。",
                weight="weak",
                value=prefix,
            )
        )

    footprint_process = {
        "test_point": any(token in normalized_footprint for token in ("TESTPOINT", "TEST_POINT", "TPAD")),
        "fiducial": any(token in normalized_footprint for token in ("FIDUCIAL", "MARK")),
        "mounting_hole": any(
            token in normalized_footprint for token in ("MOUNTINGHOLE", "MOUNTING_HOLE", "NPTH", "TOOLING")
        ),
        "mechanical": any(
            token in normalized_footprint for token in ("SMTSO", "STANDOFF", "NUT", "SCREW", "COPPER_POST")
        ),
    }
    if prefix in {"TP", "Z_TP"} and footprint_process["test_point"]:
        items.append(
            evidence(
                "reference_and_footprint",
                "测试点位号与测试点封装相互佐证。",
                weight="strong",
                value=normalized_footprint,
            )
        )
        return RoleInference("test_point", tuple(items), True)
    if prefix in {"FID", "MARK"} and footprint_process["fiducial"]:
        items.append(
            evidence(
                "reference_and_footprint",
                "Mark/Fiducial 位号与封装相互佐证。",
                weight="strong",
                value=normalized_footprint,
            )
        )
        return RoleInference("fiducial", tuple(items), True)
    if prefix in {"H", "MH"} and footprint_process["mounting_hole"]:
        items.append(
            evidence(
                "reference_and_footprint",
                "孔位号与无电气/安装孔封装相互佐证。",
                weight="strong",
                value=normalized_footprint,
            )
        )
        return RoleInference("mounting_hole", tuple(items), True)
    if prefix in {"MTG", "H", "MH"} and footprint_process["mechanical"]:
        items.append(
            evidence(
                "reference_and_footprint",
                "机械位号与贴片机械封装相互佐证。",
                weight="strong",
                value=normalized_footprint,
            )
        )
        return RoleInference("mechanical", tuple(items), False)
    return RoleInference("unknown", tuple(items), False)
