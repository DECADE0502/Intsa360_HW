from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.backend.contracts.api import SmtLayoutResponse


def _full_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "tool": "smt_layout",
        "outputs": [],
        "board": {
            "outline_rings": [[(0.0, 0.0), (100.0, 0.0), (100.0, 80.0), (0.0, 80.0)]],
            "bbox_mm": (0.0, 0.0, 100.0, 80.0),
            "source": "dxf",
        },
        "components": [
            {
                "ref": "R1",
                "x_mm": 10.0,
                "y_mm": 20.0,
                "rotation": 90,
                "side": "top",
                "footprint": "R0402",
                "part_number": "PN-1",
                "description": "Resistor",
                "model": "10K",
                "grade": "preferred",
                "status": "installed",
                "high_risk": False,
            }
        ],
        "nc_summary": {
            "total": 1,
            "refs": ["R2"],
            "confirmed_refs": [],
            "candidate_refs": ["R2"],
            "unverified_refs": ["R3"],
            "conflict_refs": [],
            "non_nc_refs": [],
            "inference_mode": "without_netlist",
            "decision_manifest_used": False,
            "explicit_summary_used": False,
        },
        "sanity": {
            "missing_layout": [],
            "missing_bom": [],
            "missing_netlist": [],
            "footprint_conflicts": [],
        },
        "fai_table": {"headers": ["Reference"], "rows": [["R1"]]},
        "summary": {
            "total_components": 1,
            "top_count": 1,
            "bottom_count": 0,
            "nc_count": 0,
            "high_risk_count": 0,
        },
    }


def test_smt_layout_response_schema_validates_full_payload() -> None:
    response = SmtLayoutResponse.model_validate(_full_payload())

    assert response.tool == "smt_layout"
    assert response.components[0].ref == "R1"
    assert response.summary is not None
    assert response.summary.total_components == 1


def test_smt_layout_response_schema_accepts_skipped_netlist_sanity() -> None:
    payload = _full_payload()
    payload["sanity"] = {"status": "skipped_no_netlist"}

    response = SmtLayoutResponse.model_validate(payload)

    assert response.sanity is not None
    assert response.sanity.status == "skipped_no_netlist"


@pytest.mark.parametrize("status", ["candidate_nc", "unverified"])
def test_smt_layout_response_schema_accepts_inferred_component_statuses(status: str) -> None:
    payload = _full_payload()
    payload["components"][0]["status"] = status

    response = SmtLayoutResponse.model_validate(payload)

    assert response.components[0].status == status


def test_smt_layout_response_schema_rejects_extra_fields() -> None:
    payload = deepcopy(_full_payload())
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        SmtLayoutResponse.model_validate(payload)
