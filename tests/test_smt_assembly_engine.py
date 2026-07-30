from __future__ import annotations

from app.backend.contracts.smt_analysis import (
    SmtBomRequirement,
    SmtCoordinateOccurrence,
    SmtCoordinateQuality,
    SmtCoordinateSet,
    SmtMaterialOption,
)
from app.backend.smt_analysis.assembly import (
    ExplicitAssemblyDecision,
    analyze_assembly,
    requirements_from_rows,
)


def _coordinate_set(
    refs: list[tuple[str, str, str]],
    *,
    scope: str = "unknown",
) -> SmtCoordinateSet:
    return SmtCoordinateSet(
        coordinate_set_id="coords",
        source_asset_id="source",
        adapter_id="test",
        sheet_or_section="",
        declared_unit="mm",
        normalized_unit="mm",
        unit_state="verified",
        scope_semantics=scope,
        side_mapping={},
        rotation_semantics="unknown",
        quality_report=SmtCoordinateQuality(
            valid_rows=len(refs),
            rejected_rows=0,
            unnamed_rows=0,
            duplicate_refs=[],
            issues=[],
        ),
        occurrences=[
            SmtCoordinateOccurrence(
                occurrence_id=f"occ-{index}",
                raw_ref=ref,
                ref=ref,
                raw_x=str(index),
                raw_y=str(index + 1),
                normalized_x=float(index),
                normalized_y=float(index + 1),
                raw_side=side,
                side=side,
                raw_rotation="0",
                normalized_rotation=0,
                footprint=footprint,
                source_line=index + 1,
                warnings=[],
            )
            for index, (ref, side, footprint) in enumerate(refs)
        ],
    )


def _requirement(code: str = "PN-1") -> SmtBomRequirement:
    return SmtBomRequirement(
        parent_code="PCBA-1",
        quantity=1,
        materials=[
            SmtMaterialOption(
                part_number=code,
                description="",
                model="",
                grade="",
                is_primary=True,
            )
        ],
        source_rows=[2],
    )


def test_unknown_scope_never_auto_confirms_nc() -> None:
    result = analyze_assembly(
        coordinate_sets=[_coordinate_set([("R1", "top", "R0402")], scope="unknown")],
        bom_requirements={},
    )

    assert result.placements[0].assembly_state == "candidate_nc"


def test_full_design_scope_can_confirm_coordinate_minus_bom_as_nc() -> None:
    result = analyze_assembly(
        coordinate_sets=[
            _coordinate_set([("R1", "top", "R0402")], scope="full_design_set")
        ],
        bom_requirements={},
    )

    assert result.placements[0].assembly_state == "confirmed_nc"


def test_placement_only_scope_does_not_call_coordinate_minus_bom_nc() -> None:
    result = analyze_assembly(
        coordinate_sets=[
            _coordinate_set([("R1", "top", "R0402")], scope="placement_only")
        ],
        bom_requirements={},
    )

    assert result.placements[0].assembly_state == "coordinate_only"


def test_process_object_is_not_mixed_into_nc() -> None:
    result = analyze_assembly(
        coordinate_sets=[
            _coordinate_set([("TP1", "top", "TESTPOINT_PAD")], scope="full_design_set")
        ],
        bom_requirements={},
    )

    placement = result.placements[0]
    assert placement.role == "test_point"
    assert placement.assembly_state == "non_smt"


def test_netlist_is_only_supporting_evidence() -> None:
    result = analyze_assembly(
        coordinate_sets=[],
        bom_requirements={},
        netlist_refs={"R1"},
    )

    placement = result.placements[0]
    assert placement.assembly_state == "unresolved"
    assert placement.netlist_present is True
    assert any(item.kind == "netlist_membership" for item in placement.evidence_chain)


def test_bom_without_coordinate_and_coordinate_without_bom_are_distinct() -> None:
    result = analyze_assembly(
        coordinate_sets=[_coordinate_set([("R2", "top", "R0402")])],
        bom_requirements={"R1": _requirement()},
    )
    by_ref = {item.ref: item for item in result.placements}

    assert by_ref["R1"].assembly_state == "bom_only"
    assert by_ref["R2"].assembly_state == "candidate_nc"


def test_long_bom_source_row_list_is_summarized_without_losing_provenance() -> None:
    requirement = _requirement()
    requirement.source_rows = list(range(1, 501))

    result = analyze_assembly(
        coordinate_sets=[_coordinate_set([("R1", "top", "R0402")])],
        bom_requirements={"R1": requirement},
    )

    bom_evidence = next(
        item
        for item in result.placements[0].evidence_chain
        if item.kind == "bom_membership"
    )
    assert bom_evidence.source_location is not None
    assert len(bom_evidence.source_location) <= 240
    assert "共 500 行" in bom_evidence.source_location
    assert requirement.source_rows == list(range(1, 501))


def test_explicit_semantic_nc_overrides_unknown_scope() -> None:
    result = analyze_assembly(
        coordinate_sets=[_coordinate_set([("R1", "top", "R0402")])],
        bom_requirements={},
        explicit_decisions={
            "R1": ExplicitAssemblyDecision(
                destination="non_smt",
                exclusion_kind="nc",
                role="electronic",
            )
        },
    )

    assert result.placements[0].assembly_state == "confirmed_nc"


def test_alternate_rows_do_not_increase_physical_placement_count() -> None:
    requirements = requirements_from_rows(
        [
            {
                "parent_code": "PCBA-1",
                "material_code": "A",
                "substitute_group_code": "A",
                "substitute_priority": 0,
                "quantity": 4,
                "refs": ["C1", "C2", "C3", "C4"],
            },
            {
                "parent_code": "PCBA-1",
                "material_code": "B",
                "substitute_group_code": "A",
                "substitute_priority": 1,
                "quantity": 4,
                "refs": [],
            },
            {
                "parent_code": "PCBA-1",
                "material_code": "C",
                "substitute_group_code": "A",
                "substitute_priority": 2,
                "quantity": 4,
                "refs": [],
            },
        ]
    )

    assert set(requirements) == {"C1", "C2", "C3", "C4"}
    assert len(requirements["C1"].materials) == 3


def test_duplicate_coordinate_ref_is_conflicting() -> None:
    coordinates = _coordinate_set(
        [("R1", "top", "R0402"), ("R1", "bottom", "R0402")],
        scope="full_design_set",
    )
    result = analyze_assembly(
        coordinate_sets=[coordinates],
        bom_requirements={"R1": _requirement()},
    )

    assert result.placements[0].assembly_state == "conflicting"
    assert result.placements[0].blocking_reasons
