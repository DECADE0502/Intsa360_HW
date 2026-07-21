from __future__ import annotations

from app.backend.tools.smt_layout import _compute_sanity


def _component(ref: str, footprint: str = "R0402") -> dict[str, object]:
    return {"ref": ref, "footprint": footprint}


def _bom_row(ref: str, package: str = "R0402", description: str = "") -> dict[str, object]:
    return {
        "refs": [ref],
        "package": package,
        "description": description,
        "name": "",
        "model": "",
    }


def test_sanity_ref_in_all_three_is_ok() -> None:
    sanity = _compute_sanity([_component("R1")], [_bom_row("R1")], {"R1": "R0402"})

    assert sanity == {
        "missing_layout": [],
        "missing_bom": [],
        "missing_netlist": [],
        "footprint_conflicts": [],
    }


def test_sanity_ref_in_xy_only_marks_missing_bom_and_missing_netlist() -> None:
    sanity = _compute_sanity([_component("R1")], [], {})

    assert [item["ref"] for item in sanity["missing_bom"]] == ["R1"]
    assert sanity["missing_bom"][0]["severity"] == "high"
    assert [item["ref"] for item in sanity["missing_netlist"]] == ["R1"]
    assert sanity["missing_netlist"][0]["severity"] == "medium"


def test_sanity_ref_in_bom_only_marks_missing_layout_and_missing_netlist() -> None:
    sanity = _compute_sanity([], [_bom_row("C1")], {})

    assert [item["ref"] for item in sanity["missing_layout"]] == ["C1"]
    assert sanity["missing_layout"][0]["severity"] == "high"
    assert [item["ref"] for item in sanity["missing_netlist"]] == ["C1"]
    assert sanity["missing_netlist"][0]["severity"] == "low"


def test_sanity_footprint_conflict_between_xy_and_netlist_pstxprt() -> None:
    sanity = _compute_sanity(
        [_component("R1", "R0402")],
        [_bom_row("R1", "R0402")],
        {"R1": "R0603"},
    )

    assert len(sanity["footprint_conflicts"]) == 1
    conflict = sanity["footprint_conflicts"][0]
    assert conflict["xy_footprint"] == "R0402"
    assert conflict["netlist_footprint"] == "R0603"
    assert "网表" in conflict["note"]


def test_sanity_footprint_conflict_between_xy_and_bom_description() -> None:
    sanity = _compute_sanity(
        [_component("R1", "R0402")],
        [_bom_row("R1", package="", description="0603 resistor")],
        {"R1": "R0402"},
    )

    assert len(sanity["footprint_conflicts"]) == 1
    conflict = sanity["footprint_conflicts"][0]
    assert conflict["bom_footprint"] == "0603 resistor"
    assert "BOM" in conflict["note"]


def test_sanity_high_severity_first() -> None:
    sanity = _compute_sanity(
        [_component("R10")],
        [],
        {"R2": "R0402", "R10": "R0402"},
    )

    assert [(item["ref"], item["severity"]) for item in sanity["missing_bom"]] == [
        ("R10", "high"),
        ("R2", "medium"),
    ]
