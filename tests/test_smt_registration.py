from __future__ import annotations

import math

import pytest

from app.backend.contracts.smt_analysis import SmtRegistrationAnchor
from app.backend.smt_analysis.registration import (
    RegistrationError,
    apply_transform,
    registration_candidates,
    solve_registration,
)
from app.backend.smt_analysis.registration_validation import RegistrationPolicy


def _anchors(transform, points):
    result = []
    for index, (x, y) in enumerate(points):
        image_x, image_y = apply_transform(transform, x, y)
        result.append(
            SmtRegistrationAnchor(
                anchor_id=f"a-{index}",
                ref=f"R{index + 1}",
                coordinate_x=x,
                coordinate_y=y,
                image_x=image_x,
                image_y=image_y,
                source="user",
                inlier=True,
            )
        )
    return result


@pytest.mark.parametrize(
    ("model", "transform"),
    [
        ("similarity", (2.0, -0.5, 0.5, 2.0, 100.0, 50.0)),
        ("similarity_with_mirror", (2.0, 0.5, 0.5, -2.0, 100.0, 50.0)),
        ("affine", (2.0, 0.2, -0.1, 1.8, 100.0, 50.0)),
    ],
)
def test_registration_round_trip(model, transform) -> None:
    anchors = _anchors(transform, [(0, 0), (10, 0), (0, 10), (8, 7)])

    result = solve_registration(
        coordinate_set_id="coords",
        page_id="page",
        side="top",
        model=model,
        anchors=anchors,
        coordinate_bounds=(0, 0, 10, 10),
        image_bounds=(0, 0, 200, 200),
        decision_source="user_confirmed",
    )

    assert result.confidence_state == "verified"
    assert result.validation.p95_error == pytest.approx(0.0, abs=1e-9)
    assert all(math.isfinite(value) for value in result.transform)
    assert apply_transform(result.transform, 3, 4) == pytest.approx(
        apply_transform(transform, 3, 4)
    )


def test_collinear_anchors_are_rejected() -> None:
    anchors = _anchors((1, 0, 0, 1, 0, 0), [(0, 0), (1, 1), (2, 2)])

    with pytest.raises(RegistrationError, match="共线"):
        solve_registration(
            coordinate_set_id="coords",
            page_id="page",
            side="top",
            model="similarity",
            anchors=anchors,
        )


def test_duplicate_anchor_positions_are_rejected() -> None:
    anchors = _anchors((1, 0, 0, 1, 0, 0), [(0, 0), (10, 0), (0, 10)])
    anchors[2] = anchors[2].model_copy(
        update={"image_x": anchors[1].image_x, "image_y": anchors[1].image_y}
    )

    with pytest.raises(RegistrationError, match="重复"):
        solve_registration(
            coordinate_set_id="coords",
            page_id="page",
            side="top",
            model="similarity",
            anchors=anchors,
        )


def test_automatic_verification_requires_explicit_calibrated_policy() -> None:
    anchors = _anchors((2, 0, 0, 2, 10, 20), [(0, 0), (10, 0), (0, 10)])

    result = solve_registration(
        coordinate_set_id="coords",
        page_id="page",
        side="top",
        model="similarity",
        anchors=anchors,
        coordinate_bounds=(0, 0, 10, 10),
        image_bounds=(0, 0, 100, 100),
        decision_source="automatic",
    )

    assert result.confidence_state == "needs_confirmation"
    assert "registration_policy_unconfigured" in result.validation.blocking_reasons


def test_explicit_policy_can_verify_exact_synthetic_solution() -> None:
    anchors = _anchors((2, 0, 0, 2, 10, 20), [(0, 0), (10, 0), (0, 10), (10, 10)])
    policy = RegistrationPolicy(
        minimum_anchor_count=3,
        minimum_spatial_coverage=0.5,
        maximum_median_error=0.001,
        maximum_p95_error=0.001,
        minimum_inside_ratio=1.0,
    )

    result = solve_registration(
        coordinate_set_id="coords",
        page_id="page",
        side="top",
        model="similarity",
        anchors=anchors,
        coordinate_bounds=(0, 0, 10, 10),
        image_bounds=(0, 0, 100, 100),
        decision_source="automatic",
        policy=policy,
    )

    assert result.confidence_state == "verified"


def test_candidate_solver_keeps_mirror_as_distinct_model() -> None:
    anchors = _anchors((2, 0.5, 0.5, -2, 10, 20), [(0, 0), (10, 0), (0, 10), (8, 7)])

    candidates = registration_candidates(anchors)

    assert candidates[0].model == "similarity_with_mirror"
    assert candidates[0].median_error == pytest.approx(0.0, abs=1e-9)
