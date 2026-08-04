from __future__ import annotations

from pathlib import Path

import pytest

from app.backend.tools.bom_classify import (
    analyze_placement,
    apply_resolutions,
    build_normalized_row,
    classification_config,
    classify,
)
from app.backend.tools.bom_process import ParsedSource


BASE = {
    "part_number": "",
    "value": "",
    "name": "",
    "model": "",
    "desc": "",
    "grade": "",
    "unit": "",
    "manufacturer": "",
    "pcb_footprint": "",
    "pcb_package": "",
    "source_package": "",
    "source_part": "",
    "source_library": "",
    "implementation_path": "",
    "datasheet": "",
}


def row(ref: str = "X1", **values: str):
    return build_normalized_row(2, (ref,), {**BASE, **values})


def result(ref: str = "X1", **values: str):
    return classify(row(ref, **values), classification_config())


def test_formal_identity_outranks_description_only_process_text() -> None:
    classified = result(part_number="MAT-1001", desc="镀金测试点")

    assert classified.identity_status == "identity_confirmed"
    assert classified.state == "confirmed_material"
    assert classified.rule_id == "R1"
    assert classified.recommended_action == "keep"
    assert classified.suggested_destination == "smt"


def test_reference_and_package_together_can_recommend_process_zone() -> None:
    classified = result(
        "TP17",
        part_number="MAT-1001",
        desc="测试点",
        pcb_footprint="TESTPOINT_TP0P4",
        source_part="TESTPOINT.Normal",
    )

    assert classified.state == "confirmed_material"
    assert classified.role == "test_point"
    assert classified.role_confidence == "strong"
    assert classified.rule_id == "R4"
    assert classified.suggested_destination == "non_smt"
    assert classified.exclusion_kind == "process_only"


def test_reference_prefix_alone_never_overrides_formal_identity() -> None:
    classified = result("TP17", part_number="MAT-1001", desc="普通贴片器件", pcb_footprint="R0402")

    assert classified.state == "confirmed_material"
    assert classified.rule_id == "R1"
    assert classified.suggested_destination == "smt"


def test_shield_is_forced_review_and_always_has_a_default_recommendation() -> None:
    classified = result(
        "SH1",
        part_number="MAT-1001",
        value="TP0P4",
        desc="测试点",
        pcb_footprint="TP0P4",
    )

    assert classified.role == "shield"
    assert classified.sh_review is True
    assert classified.rule_id == "R3"
    assert classified.recommended_action == "exclude"
    assert classified.suggested_destination == "non_smt"
    assert classified.shield_subtype == "cover"
    assert "shield_type_and_destination_required" in classified.blocking_reasons


def test_shield_with_pure_nc_is_resolved_before_type() -> None:
    classified = result("SH1", part_number="MAT-1001", value="NC")

    assert classified.state == "confirmed_nc"
    assert classified.role == "shield"
    assert classified.suggested_destination == "non_smt"
    assert classified.exclusion_kind == "nc"
    assert not classified.requires_review


def test_ambiguous_mechanical_text_never_auto_excludes_coded_material() -> None:
    classified = result("H1", part_number="MAT-1001", desc="焊接铜柱结构件")

    assert classified.state == "confirmed_material"
    assert classified.rule_id == "R1"
    assert classified.recommended_action == "keep"


def test_vendor_mpn_is_not_promoted_to_internal_part_number() -> None:
    classified = result("MTG1", value="SMTSO-M3-10ET", pcb_footprint="SMTSO_M3")

    assert classified.identity_status == "identity_candidate_mpn"
    assert classified.suggested_code == ""
    assert classified.suggested_mpn == "SMTSO-M3-10ET"
    assert classified.recommended_action is None


def test_internal_code_candidate_can_be_prefilled_for_material_review() -> None:
    classified = result("H1", value="A.BC1234", desc="焊接铜柱")

    assert classified.identity_status == "identity_candidate_internal"
    assert classified.state == "suspected_material"
    assert classified.suggested_code == "A.BC1234"
    assert classified.suggested_destination == "smt"


@pytest.mark.parametrize("field", ["source_library", "implementation_path", "datasheet"])
def test_capture_diagnostic_paths_are_legal(field: str) -> None:
    classified = result(part_number="MAT-1001", desc="普通器件", **{field: r"D:\Cadence\part.olb"})

    assert classified.state == "confirmed_material"


@pytest.mark.parametrize("field", ["part_number", "value", "model", "name", "desc", "pcb_footprint"])
def test_path_in_material_business_field_is_blocking(field: str) -> None:
    values = {"part_number": "MAT-1001", "desc": "普通器件", field: r"D:\Cadence\part.olb"}
    classified = result(**values)

    assert classified.state == "conflicting"
    assert classified.rule_id == "R7"


def test_non_empty_process_symbol_part_number_is_still_a_material_identity() -> None:
    classified = result(
        "TP1",
        part_number="TESTPOINT",
        value="TEST POINT",
        pcb_footprint="TESTPOINT_TP0P4",
    )

    assert classified.identity_status == "identity_confirmed"
    assert classified.state == "confirmed_material"
    assert classified.rule_id == "R4"
    assert classified.recommended_action == "exclude"


def test_jumper_resistor_whitelist_cancels_short_symbol_role() -> None:
    classified = result(
        "JP1",
        part_number="MAT-1001",
        value="0R",
        desc="跳线电阻 0402",
        source_part="SHORT_L2.Normal",
    )

    assert classified.state == "confirmed_material"
    assert classified.role == "electronic"


@pytest.mark.parametrize("source_package", ["Short", "Shor"])
def test_jp_short_package_and_capture_truncation_are_corroborated_process_symbols(source_package: str) -> None:
    classified = result(
        "JP10",
        value="Short_L1",
        pcb_footprint="sp2-L1",
        source_package=source_package,
    )

    assert classified.role == "short_symbol"
    assert classified.state == "suspected_process"
    assert classified.rule_id == "R6P"
    assert classified.suggested_destination == "non_smt"


def test_confirmed_material_with_part_number_and_value_stays_readonly() -> None:
    classified = result("C108", part_number="C.C1225M21", value="2.2uF/6.3V", pcb_footprint="C0201")

    assert classified.state == "confirmed_material"
    assert classified.rule_id == "R1"
    assert classified.requires_review is False


def test_hole_role_requires_reference_and_library_corroboration() -> None:
    classified = result("H1", value="GND", pcb_footprint="MOUNTINGHOLE_GND")

    assert classified.state == "suspected_process"
    assert classified.role == "mounting_hole"
    assert classified.suggested_destination == "non_smt"


def test_coded_h_reference_with_smt_mechanical_package_is_confirmed_material() -> None:
    classified = result(
        "H1",
        part_number="MAT-1001",
        desc="焊接铜柱",
        pcb_footprint="SMTSO_M3_STANDOFF",
    )

    assert classified.state == "confirmed_material"
    assert classified.role == "smt_mechanical"
    assert classified.recommended_action == "keep"


def test_fiducial_requires_process_review_when_evidence_is_corroborated() -> None:
    classified = result("FID1", value="FIDUCIAL", source_part="FIDUCIAL.Normal")

    assert classified.state == "suspected_process"
    assert classified.role == "fiducial"


@pytest.mark.parametrize(
    ("values", "state", "rule_id"),
    [
        ({"value": "NC"}, "confirmed_nc", "R2"),
        ({"part_number": "MAT-1001", "value": "NC"}, "confirmed_nc", "R2C"),
        ({"desc": "未分类但有实质描述"}, "suspected_material", "R6M"),
        ({}, "insufficient_data", "R8"),
    ],
)
def test_remaining_state_machine_branches(values: dict[str, str], state: str, rule_id: str) -> None:
    classified = result(**values)

    assert classified.state == state
    assert classified.rule_id == rule_id


def test_physical_identity_conflict_is_r7() -> None:
    conflicted = build_normalized_row(
        2,
        ("U1",),
        {**BASE, "part_number": "MAT-1001", "desc": "IC"},
        physical_conflicts=("same_physical_ref_multiple_part_numbers",),
    )

    classified = classify(conflicted, classification_config())

    assert classified.identity_status == "identity_conflict"
    assert classified.rule_id == "R7"
    assert classified.blocking_reasons == ("same_physical_ref_multiple_part_numbers",)


def test_api_v2_payload_contains_contract_and_ordered_evidence() -> None:
    analysis = analyze_placement(
        [row("SH1", part_number="MAT-1001", desc="屏蔽件")],
        classification_config(),
        source_fingerprint="source-123",
    )
    payload = analysis.payload()
    group = payload["groups"][0]

    assert payload["schema_version"] == 2
    assert payload["rule_version"]
    assert payload["source_fingerprint"] == "source-123"
    assert "quality_report" in payload
    assert "readonly_groups" in payload
    for key in (
        "group_id",
        "source_rows",
        "physical_refs",
        "identity_status",
        "state",
        "role",
        "role_confidence",
        "suggested_destination",
        "blocking_reasons",
        "original_fields",
        "inferred_fields",
        "evidence",
        "decision_fingerprint",
    ):
        assert key in group
    priorities = [int(item["priority"]) for item in group["evidence"]]
    assert priorities == sorted(priorities)


def test_new_resolution_contract_writes_zone_role_and_decision_manifest() -> None:
    source_row = row("X1", value="A.BC1234", desc="结构件")
    raw = {field: source_row.value(field) for field in BASE}
    raw["reference"] = "X1"
    parsed = ParsedSource(Path("source.xlsx"), [raw], [2], (source_row,))
    analysis = analyze_placement([source_row], classification_config())
    group = analysis.review_groups[0]

    resolved, summary = apply_resolutions(parsed, analysis, {
        group.key: {
            "destination": "smt",
            "role": "smt_mechanical",
            "part_number_override": "A.BC1234",
            "field_patch": {"name": "贴片机械件"},
            "decision_source": "user",
        },
    })

    assert resolved.raw_rows[0]["_placement_destination"] == "smt"
    assert resolved.raw_rows[0]["_placement_role"] == "smt_mechanical"
    assert summary["decision_records"][0]["destination"] == "smt"
    assert summary["decision_records"][0]["decision_source"] == "user"


def test_shield_subtype_defaults_from_the_selected_destination() -> None:
    source_row = row("SH1", part_number="MAT-1001", desc="屏蔽件")
    raw = {field: source_row.value(field) for field in BASE}
    raw["reference"] = "SH1"
    parsed = ParsedSource(Path("source.xlsx"), [raw], [2], (source_row,))
    analysis = analyze_placement([source_row], classification_config())
    group = analysis.review_groups[0]

    resolved, summary = apply_resolutions(parsed, analysis, {
        group.key: {
            "destination": "smt",
            "role": "shield",
            "decision_source": "user",
        },
    })

    assert resolved.raw_rows[0]["part_number"] == "MAT-1001"
    assert summary["destination_counts"] == {"smt": 1}


def test_decision_fingerprint_changes_when_any_key_attribute_changes() -> None:
    original = result(part_number="MAT-1001", value="10K", desc="电阻", pcb_footprint="R0402")
    same = result(part_number="MAT-1001", value="10K", desc="电阻", pcb_footprint="R0402")
    changed = result(part_number="MAT-1001", value="11K", desc="电阻", pcb_footprint="R0402")

    assert original.decision_fingerprint == same.decision_fingerprint
    assert original.decision_fingerprint != changed.decision_fingerprint
