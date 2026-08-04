"""Placement classification decides in a fixed order: identity, then installation,
then type. A row that carries a part number always gets a recommendation.

Failure class guarded here: a row with a non-empty part number whose placement
recommendation was withheld because of its reference prefix or its descriptive
text, leaving a review item with nothing to accept.
"""

from __future__ import annotations

import pytest

from app.backend.tools.bom_classify import (
    analyze_placement,
    build_normalized_row,
    classification_config,
    classify,
)


BASE_FIELDS = {
    field: ""
    for field in (
        "part_number", "value", "name", "model", "desc", "grade", "unit",
        "pcb_footprint", "pcb_package", "source_package", "source_part",
    )
}


def make_row(refs=("X1",), row_number: int = 2, **fields):
    return build_normalized_row(row_number, refs, {**BASE_FIELDS, **fields})


# The reported case, a sibling differing in prefix/code/description/package, and
# the boundary neighbour that must keep behaving as before.
CASES = [
    pytest.param(
        {"refs": ("SH1",), "part_number": "302010300327", "value": "TP0P4",
         "desc": "测试点,TP0P4", "pcb_footprint": "TP0P4", "source_part": "TP_NP.Normal"},
        "non_smt", "exclude", id="reported-shield-with-wrong-library-metadata",
    ),
    pytest.param(
        {"refs": ("TP10",), "part_number": "Test", "value": "TP1P0",
         "desc": "测试点,TP0P8", "pcb_footprint": "TESTPOINT_TP1P0"},
        "non_smt", "exclude", id="sibling-test-point-with-inconsistent-package",
    ),
    pytest.param(
        {"refs": ("R1",), "part_number": "R.C1102F01", "value": "10K",
         "desc": "贴片电阻,10K,F,1/20W,R0201", "pcb_footprint": "R0201"},
        "smt", "keep", id="boundary-ordinary-coded-part",
    ),
]


@pytest.mark.parametrize("fields,destination,action", CASES)
def test_a_coded_row_always_receives_a_recommendation(
    fields: dict, destination: str, action: str
) -> None:
    result = classify(make_row(**fields), classification_config())

    assert result.identity_status == "identity_confirmed"
    assert result.recommended_action == action
    assert result.suggested_destination == destination


def test_an_uncoded_row_still_asks_for_a_code() -> None:
    """The boundary of the class: with no code there is nothing to recommend."""
    result = classify(
        make_row(refs=("U16",), value="AP5256", pcb_footprint="QFN61-0P5-8X8_1P5"),
        classification_config(),
    )

    assert result.identity_status != "identity_confirmed"
    assert result.requires_review


@pytest.mark.parametrize("code", ["302010300327", "P-ALPHA-01", "Test"])
def test_identity_comes_from_the_code_column_alone(code: str) -> None:
    """Code schemes change between projects, so no shape or value list may judge one."""
    result = classify(make_row(part_number=code, desc="普通器件"), classification_config())

    assert result.identity_status == "identity_confirmed"


@pytest.mark.parametrize("prefix", ["SH", "U"])
def test_a_prefix_can_neither_deny_identity_nor_override_nc(prefix: str) -> None:
    config = classification_config()
    installed = classify(make_row(refs=(f"{prefix}1",), part_number="302010300327", value="10K"), config)
    not_installed = classify(make_row(refs=(f"{prefix}1",), part_number="302010300327", value="NC"), config)

    assert installed.identity_status == "identity_confirmed"
    assert installed.state != "confirmed_nc"
    assert not_installed.state == "confirmed_nc"
    assert not not_installed.requires_review


def test_shield_defaults_to_a_cover_so_the_form_is_answerable() -> None:
    result = classify(
        make_row(refs=("SH1",), part_number="302010300327", desc="IAC4,主板屏蔽罩,A5052"),
        classification_config(),
    )

    assert result.role == "shield"
    assert result.shield_subtype == "cover"
    assert result.exclusion_kind == "scope_excluded"


def test_a_code_contradicting_its_description_is_reported_not_adjudicated() -> None:
    rows = [
        make_row(refs=("TP1",), row_number=2, part_number="Test", desc="测试点,TP0P4"),
        make_row(refs=("R1",), row_number=3, part_number="R.C1102F01", desc="贴片电阻,10K"),
    ]

    analysis = analyze_placement(rows, classification_config())
    listed = {ref for item in analysis.code_verification for ref in item["refs"]}

    assert listed == {"TP1"}
    assert analysis.code_verification[0]["part_number"] == "Test"
    assert analysis.code_verification[0]["reason"]
    # Reporting must not turn into another gate.
    assert not analysis.review_groups


def test_no_review_group_is_emitted_without_something_to_accept() -> None:
    """The class invariant: a coded group always carries a recommendation."""
    rows = [
        make_row(refs=("SH1",), row_number=2, part_number="302010300327", desc="测试点,TP0P4"),
        make_row(refs=("TP10",), row_number=3, part_number="Test", desc="测试点,TP0P8"),
        make_row(refs=("MTG1",), row_number=4, part_number="302020400107", desc="表贴螺母柱"),
    ]

    analysis = analyze_placement(rows, classification_config())

    stuck = [
        group.refs
        for group in analysis.review_groups
        if group.classification.recommended_action is None
        and group.classification.identity_status == "identity_confirmed"
    ]
    assert not stuck
