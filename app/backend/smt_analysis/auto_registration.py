from __future__ import annotations

import math
from collections import Counter, defaultdict

from app.backend.contracts.smt_analysis import (
    SmtCoordinateSet,
    SmtDrawingPage,
    SmtRegistration,
    SmtRegistrationAnchor,
)
from app.backend.smt_analysis.registration import (
    RegistrationError,
    registration_candidates,
    solve_registration,
)


def propose_vector_registration(
    *,
    coordinate_set: SmtCoordinateSet,
    page: SmtDrawingPage,
    side: str,
) -> SmtRegistration | None:
    """Build a reviewable registration candidate from unambiguous shared refs.

    This function never promotes a candidate to verified without an explicitly
    calibrated policy. Ambiguous duplicate text labels are omitted rather than
    guessed.
    """

    if side not in {"top", "bottom"}:
        return None
    if page.drawing_role not in {
        "board_top_candidate",
        "board_bottom_candidate",
        "board_unknown_side",
    }:
        return None
    if page.pixel_width is None or page.pixel_height is None:
        return None

    coordinates = defaultdict(list)
    for occurrence in coordinate_set.occurrences:
        if occurrence.side not in {side, "unknown"}:
            continue
        if occurrence.normalized_x is None or occurrence.normalized_y is None:
            continue
        coordinates[occurrence.ref.upper()].append(occurrence)

    drawing_positions = defaultdict(list)
    for positioned in page.positioned_refs:
        drawing_positions[positioned.ref.upper()].append(positioned)

    anchors: list[SmtRegistrationAnchor] = []
    for ref in sorted(set(coordinates) & set(drawing_positions)):
        coordinate_matches = coordinates[ref]
        drawing_matches = drawing_positions[ref]
        if len(coordinate_matches) != 1 or len(drawing_matches) != 1:
            continue
        occurrence = coordinate_matches[0]
        positioned = drawing_matches[0]
        assert occurrence.normalized_x is not None
        assert occurrence.normalized_y is not None
        anchors.append(
            SmtRegistrationAnchor(
                anchor_id=f"auto-{positioned.extracted_ref_id}",
                ref=ref,
                coordinate_x=occurrence.normalized_x,
                coordinate_y=occurrence.normalized_y,
                image_x=positioned.image_x,
                image_y=positioned.image_y,
                source=positioned.source,
                inlier=True,
            )
        )
    if len(anchors) < 3:
        return None

    coordinate_positions = Counter(
        (anchor.coordinate_x, anchor.coordinate_y) for anchor in anchors
    )
    image_positions = Counter((anchor.image_x, anchor.image_y) for anchor in anchors)
    anchors = [
        anchor
        for anchor in anchors
        if coordinate_positions[(anchor.coordinate_x, anchor.coordinate_y)] == 1
        and image_positions[(anchor.image_x, anchor.image_y)] == 1
    ]
    if len(anchors) < 3:
        return None

    candidates = [
        item
        for item in registration_candidates(anchors)
        if item.model in {"similarity", "similarity_with_mirror"}
    ]
    if not candidates:
        return None
    best = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    gap = (
        max(0.0, runner_up.median_error - best.median_error)
        if runner_up is not None
        else None
    )
    mirror_ambiguous = bool(
        runner_up is not None
        and math.isclose(
            best.median_error,
            runner_up.median_error,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
        and math.isclose(
            best.p95_error,
            runner_up.p95_error,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
    )
    all_points = [
        (item.normalized_x, item.normalized_y)
        for item in coordinate_set.occurrences
        if item.side in {side, "unknown"}
        and item.normalized_x is not None
        and item.normalized_y is not None
    ]
    coordinate_bounds = (
        min(point[0] for point in all_points),
        min(point[1] for point in all_points),
        max(point[0] for point in all_points),
        max(point[1] for point in all_points),
    )
    try:
        return solve_registration(
            coordinate_set_id=coordinate_set.coordinate_set_id,
            page_id=page.page_id,
            side=side,
            model=best.model,
            anchors=anchors,
            coordinate_bounds=coordinate_bounds,
            image_bounds=(
                0.0,
                0.0,
                float(page.pixel_width),
                float(page.pixel_height),
            ),
            validation_points=all_points,
            decision_source="automatic",
            runner_up_gap=gap,
            mirror_ambiguous=mirror_ambiguous,
        )
    except RegistrationError:
        return None
