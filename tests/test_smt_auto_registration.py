from __future__ import annotations

import pytest

from app.backend.contracts.smt_analysis import (
    SmtCoordinateOccurrence,
    SmtCoordinateQuality,
    SmtCoordinateSet,
    SmtDrawingPage,
    SmtExtractedRef,
)
from app.backend.smt_analysis.auto_registration import (
    propose_vector_registration,
)
from app.backend.smt_analysis.refdes_extraction import (
    extract_pdf_vector_refs,
)


class _Searcher:
    def __init__(self, values):
        self.values = iter(values)
        self.closed = False

    def get_next(self):
        return next(self.values, None)

    def close(self):
        self.closed = True


class _TextPage:
    def __init__(self):
        self.searchers = []
        self.boxes = {
            0: (10.0, 20.0, 15.0, 30.0),
            1: (15.0, 20.0, 20.0, 30.0),
        }

    def search(self, text, **_kwargs):
        searcher = _Searcher([(0, 2)] if text == "R1" else [])
        self.searchers.append(searcher)
        return searcher

    def get_charbox(self, index, loose=False):
        assert loose is True
        return self.boxes[index]


def test_vector_text_boxes_are_converted_to_preview_coordinates() -> None:
    text_page = _TextPage()

    refs = extract_pdf_vector_refs(
        text_page,
        page_id="page-1",
        refs=["R1"],
        page_width=100,
        page_height=200,
        pixel_width=200,
        pixel_height=400,
    )

    assert len(refs) == 1
    assert refs[0].ref == "R1"
    assert refs[0].bbox == pytest.approx((20, 340, 40, 360))
    assert refs[0].image_x == pytest.approx(30)
    assert refs[0].image_y == pytest.approx(350)
    assert all(searcher.closed for searcher in text_page.searchers)


def _coordinate_set() -> SmtCoordinateSet:
    points = {
        "R1": (0.0, 0.0),
        "R2": (10.0, 0.0),
        "R3": (0.0, 10.0),
        "R4": (10.0, 10.0),
    }
    return SmtCoordinateSet(
        coordinate_set_id="coords",
        source_asset_id="asset-coords",
        adapter_id="synthetic",
        sheet_or_section="",
        declared_unit="MM",
        normalized_unit="mm",
        unit_state="verified",
        scope_semantics="full_design_set",
        side_mapping={},
        rotation_semantics="degrees_ccw",
        quality_report=SmtCoordinateQuality(
            valid_rows=4,
            rejected_rows=0,
            unnamed_rows=0,
            duplicate_refs=[],
            issues=[],
        ),
        occurrences=[
            SmtCoordinateOccurrence(
                occurrence_id=f"occ-{ref}",
                raw_ref=ref,
                ref=ref,
                raw_x=str(x),
                raw_y=str(y),
                normalized_x=x,
                normalized_y=y,
                raw_side="N",
                side="top",
                raw_rotation="0",
                normalized_rotation=0,
                footprint="R0402",
                source_line=index,
                warnings=[],
            )
            for index, (ref, (x, y)) in enumerate(points.items(), start=1)
        ],
    )


def _drawing_page(refs=("R1", "R2", "R3", "R4")) -> SmtDrawingPage:
    points = {
        "R1": (100.0, 50.0),
        "R2": (200.0, 50.0),
        "R3": (100.0, 150.0),
        "R4": (200.0, 150.0),
    }
    return SmtDrawingPage(
        page_id="page",
        source_asset_id="asset-page",
        page_number=1,
        pixel_width=400,
        pixel_height=300,
        page_rotation=0,
        crop_rect=None,
        side_candidate="top",
        drawing_role="board_top_candidate",
        preview_url="/preview",
        tile_manifest_url=None,
        extracted_refs=list(refs),
        positioned_refs=[
            SmtExtractedRef(
                extracted_ref_id=f"text-{ref}",
                ref=ref,
                image_x=points[ref][0],
                image_y=points[ref][1],
                bbox=(
                    points[ref][0] - 2,
                    points[ref][1] - 2,
                    points[ref][0] + 2,
                    points[ref][1] + 2,
                ),
                source="vector_text",
                source_index=index,
            )
            for index, ref in enumerate(refs)
        ],
        evidence=[],
    )


def test_shared_vector_refs_create_review_only_registration_candidate() -> None:
    result = propose_vector_registration(
        coordinate_set=_coordinate_set(),
        page=_drawing_page(),
        side="top",
    )

    assert result is not None
    assert result.model == "similarity"
    assert result.transform == pytest.approx((10, 0, 0, 10, 100, 50))
    assert result.confidence_state == "needs_confirmation"
    assert result.decision_source == "automatic"
    assert "registration_policy_unconfigured" in result.validation.blocking_reasons


def test_duplicate_physical_positions_are_omitted_without_rejecting_the_page() -> None:
    coordinate_set = _coordinate_set()
    coordinate_set.occurrences.append(
        SmtCoordinateOccurrence(
            occurrence_id="occ-R5",
            raw_ref="R5",
            ref="R5",
            raw_x="10",
            raw_y="10",
            normalized_x=10,
            normalized_y=10,
            raw_side="N",
            side="top",
            raw_rotation="0",
            normalized_rotation=0,
            footprint="R0402",
            source_line=5,
            warnings=[],
        )
    )
    page = _drawing_page()
    page.extracted_refs.append("R5")
    page.positioned_refs.append(
        SmtExtractedRef(
            extracted_ref_id="text-R5",
            ref="R5",
            image_x=250,
            image_y=150,
            bbox=(248, 148, 252, 152),
            source="vector_text",
            source_index=5,
        )
    )

    result = propose_vector_registration(
        coordinate_set=coordinate_set,
        page=page,
        side="top",
    )

    assert result is not None
    assert {anchor.ref for anchor in result.anchors} == {"R1", "R2", "R3"}
    assert result.transform == pytest.approx((10, 0, 0, 10, 100, 50))


def test_wrong_page_without_three_unique_shared_refs_is_not_registered() -> None:
    result = propose_vector_registration(
        coordinate_set=_coordinate_set(),
        page=_drawing_page(("R1", "R2")),
        side="top",
    )

    assert result is None
