from __future__ import annotations

import pytest

from app.backend.tools.bom_domain import (
    BOM_RULE_VERSION,
    BOM_SCHEMA_VERSION,
    CLASSIFICATION_STATES,
    DECISION_SOURCES,
    EXCLUSION_KINDS,
    IDENTITY_STATUSES,
    MATERIAL_ROLES,
    PLACEMENT_DESTINATIONS,
    SHIELD_SUBTYPES,
    PlacementResolution,
    SourceQualityIssue,
    SourceQualityReport,
    stable_fingerprint,
)


def test_bom_v2_contract_has_fixed_public_enums() -> None:
    assert BOM_SCHEMA_VERSION == 2
    assert BOM_RULE_VERSION
    assert IDENTITY_STATUSES == {
        "identity_confirmed",
        "identity_weak",
        "identity_candidate_internal",
        "identity_candidate_mpn",
        "identity_missing",
        "identity_conflict",
    }
    assert CLASSIFICATION_STATES == {
        "confirmed_material",
        "suspected_material",
        "suspected_process",
        "conflicting",
        "insufficient_data",
        "confirmed_nc",
    }
    assert MATERIAL_ROLES == {
        "electronic",
        "smt_mechanical",
        "shield",
        "test_point",
        "short_symbol",
        "mounting_hole",
        "fiducial",
        "unknown",
    }
    assert PLACEMENT_DESTINATIONS == {"smt", "non_smt"}
    assert EXCLUSION_KINDS == {"nc", "process_only", "scope_excluded", "user_excluded"}
    assert DECISION_SOURCES == {"rule", "history_exact", "user"}
    assert SHIELD_SUBTYPES == {"bracket", "cover", "other"}


def test_resolution_enforces_destination_and_exclusion_contract() -> None:
    PlacementResolution(destination="smt", role="electronic").validate()
    PlacementResolution(
        destination="non_smt",
        exclusion_kind="process_only",
        role="test_point",
    ).validate()

    with pytest.raises(ValueError, match="requires an exclusion kind"):
        PlacementResolution(destination="non_smt", role="test_point").validate()
    with pytest.raises(ValueError, match="cannot have an exclusion kind"):
        PlacementResolution(destination="smt", exclusion_kind="nc", role="electronic").validate()


def test_shield_resolution_requires_explicit_subtype_and_consistent_zone() -> None:
    PlacementResolution(destination="smt", role="shield", subtype="bracket").validate()
    PlacementResolution(
        destination="non_smt",
        exclusion_kind="scope_excluded",
        role="shield",
        subtype="cover",
    ).validate()

    with pytest.raises(ValueError, match="requires bracket, cover or other"):
        PlacementResolution(destination="smt", role="shield").validate()
    with pytest.raises(ValueError, match="shield bracket must"):
        PlacementResolution(
            destination="non_smt",
            exclusion_kind="scope_excluded",
            role="shield",
            subtype="bracket",
        ).validate()


def test_quality_report_is_machine_readable() -> None:
    report = SourceQualityReport(
        source_rows=3,
        parsed_rows=2,
        occurrence_count=4,
        physical_part_count=3,
        issues=(
            SourceQualityIssue(
                "quantity_mismatch",
                "warning",
                "数量与位号数不一致",
                (8,),
                ("R1", "R2"),
                {"quantity": 3, "reference_count": 2},
            ),
        ),
    ).payload()

    assert report["issue_count"] == 1
    assert report["severity_counts"] == {"warning": 1}
    assert report["issues"][0]["details"]["quantity"] == 3


def test_stable_fingerprint_ignores_mapping_key_order() -> None:
    assert stable_fingerprint("decision", {"part": "A", "value": "1"}) == stable_fingerprint(
        "decision", {"value": "1", "part": "A"}
    )
