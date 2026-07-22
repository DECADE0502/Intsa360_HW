from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Mapping, Sequence


BOM_SCHEMA_VERSION = 2
BOM_RULE_VERSION = "2.0.0"

IDENTITY_STATUSES = frozenset({
    "identity_confirmed",
    "identity_weak",
    "identity_candidate_internal",
    "identity_candidate_mpn",
    "identity_missing",
    "identity_conflict",
})

CLASSIFICATION_STATES = frozenset({
    "confirmed_material",
    "suspected_material",
    "suspected_process",
    "conflicting",
    "insufficient_data",
    "confirmed_nc",
})

MATERIAL_ROLES = frozenset({
    "electronic",
    "smt_mechanical",
    "shield",
    "test_point",
    "short_symbol",
    "mounting_hole",
    "fiducial",
    "unknown",
})

PLACEMENT_DESTINATIONS = frozenset({"smt", "non_smt"})
EXCLUSION_KINDS = frozenset({"nc", "process_only", "scope_excluded", "user_excluded"})
DECISION_SOURCES = frozenset({"rule", "history_exact", "user"})
SHIELD_SUBTYPES = frozenset({"bracket", "cover", "other"})


def stable_fingerprint(namespace: str, values: Sequence[object] | Mapping[str, object]) -> str:
    if isinstance(values, Mapping):
        normalized = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    else:
        normalized = "\x1f".join(str(value or "").strip().casefold() for value in values)
    return hashlib.sha256(f"{namespace}\x1e{normalized}".encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class SourceQualityIssue:
    code: str
    severity: str
    message: str
    row_numbers: tuple[int, ...] = ()
    refs: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "row_numbers": list(self.row_numbers),
            "refs": list(self.refs),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class SourceQualityReport:
    source_rows: int = 0
    parsed_rows: int = 0
    occurrence_count: int = 0
    physical_part_count: int = 0
    issues: tuple[SourceQualityIssue, ...] = ()

    def payload(self) -> dict[str, object]:
        severity_counts: dict[str, int] = {}
        code_counts: dict[str, int] = {}
        for issue in self.issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
            code_counts[issue.code] = code_counts.get(issue.code, 0) + 1
        return {
            "source_rows": self.source_rows,
            "parsed_rows": self.parsed_rows,
            "occurrence_count": self.occurrence_count,
            "physical_part_count": self.physical_part_count,
            "issue_count": len(self.issues),
            "severity_counts": severity_counts,
            "code_counts": code_counts,
            "issues": [issue.payload() for issue in self.issues],
        }


@dataclass(frozen=True)
class RefOccurrence:
    source_row: int
    raw_ref: str
    normalized_ref: str
    physical_ref: str
    part_number: str = ""
    package_signature: str = ""
    unit_marker: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "source_row": self.source_row,
            "raw_ref": self.raw_ref,
            "normalized_ref": self.normalized_ref,
            "physical_ref": self.physical_ref,
            "part_number": self.part_number,
            "package_signature": self.package_signature,
            "unit_marker": self.unit_marker,
        }


@dataclass(frozen=True)
class PhysicalPart:
    reference: str
    source_rows: tuple[int, ...]
    occurrence_count: int
    merge_kind: str = "single"
    source_refs: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "source_rows": list(self.source_rows),
            "occurrence_count": self.occurrence_count,
            "merge_kind": self.merge_kind,
            "source_refs": list(self.source_refs),
            "conflicts": list(self.conflicts),
        }


@dataclass(frozen=True)
class MaterialIdentity:
    status: str
    part_number: str = ""
    internal_candidate: str = ""
    mpn_candidate: str = ""
    strength: str = "weak"
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in IDENTITY_STATUSES:
            raise ValueError(f"invalid identity status: {self.status}")

    def payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "part_number": self.part_number,
            "internal_candidate": self.internal_candidate,
            "mpn_candidate": self.mpn_candidate,
            "strength": self.strength,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RoleDecision:
    role: str
    confidence: str
    forced_review: bool = False
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.role not in MATERIAL_ROLES:
            raise ValueError(f"invalid material role: {self.role}")

    def payload(self) -> dict[str, object]:
        return {
            "role": self.role,
            "confidence": self.confidence,
            "forced_review": self.forced_review,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class PlacementResolution:
    destination: str
    exclusion_kind: str = ""
    role: str = "unknown"
    subtype: str = ""
    part_number_override: str = ""
    field_patch: Mapping[str, str] = field(default_factory=dict)
    decision_source: str = "user"

    def validate(self) -> None:
        if self.destination not in PLACEMENT_DESTINATIONS:
            raise ValueError(f"invalid placement destination: {self.destination}")
        if self.destination == "smt" and self.exclusion_kind:
            raise ValueError("SMT destination cannot have an exclusion kind")
        if self.destination == "non_smt" and self.exclusion_kind not in EXCLUSION_KINDS:
            raise ValueError("non-SMT destination requires an exclusion kind")
        if self.role not in MATERIAL_ROLES:
            raise ValueError(f"invalid material role: {self.role}")
        if self.role == "shield" and self.subtype not in SHIELD_SUBTYPES:
            raise ValueError("shield decision requires bracket, cover or other subtype")
        if self.role == "shield" and self.subtype == "bracket" and self.destination != "smt":
            raise ValueError("shield bracket must be placed in the SMT destination")
        if self.role == "shield" and self.subtype == "cover" and (
            self.destination != "non_smt" or self.exclusion_kind != "scope_excluded"
        ):
            raise ValueError("shield cover must be a non-SMT scope exclusion")
        if self.decision_source not in DECISION_SOURCES:
            raise ValueError(f"invalid decision source: {self.decision_source}")

    def payload(self) -> dict[str, object]:
        self.validate()
        return {
            "destination": self.destination,
            "exclusion_kind": self.exclusion_kind,
            "role": self.role,
            "subtype": self.subtype,
            "part_number_override": self.part_number_override,
            "field_patch": dict(self.field_patch),
            "decision_source": self.decision_source,
        }


@dataclass(frozen=True)
class DecisionRecord:
    group_id: str
    decision_fingerprint: str
    refs: tuple[str, ...]
    identity_status: str
    classification_state: str
    rule_id: str
    rule_version: str
    resolution: PlacementResolution
    evidence: tuple[Mapping[str, object], ...] = ()
    material_snapshot: Mapping[str, str] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "decision_fingerprint": self.decision_fingerprint,
            "refs": list(self.refs),
            "identity_status": self.identity_status,
            "classification_state": self.classification_state,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            **self.resolution.payload(),
            "evidence": [dict(item) for item in self.evidence],
            "material_snapshot": dict(self.material_snapshot),
        }
