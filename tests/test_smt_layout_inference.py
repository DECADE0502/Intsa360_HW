from __future__ import annotations

from app.backend.tools.smt_layout import _infer_nc_evidence


def test_with_netlist_separates_confirmed_nc_from_xy_only_anomaly() -> None:
    evidence = _infer_nc_evidence(
        xy_refs={"R1", "R2", "R3"},
        bom_refs={"R1"},
        netlist_refs={"R1", "R2"},
        explicit_nc_refs=set(),
        explicit_non_nc_refs=set(),
        decision_manifest_used=False,
    )

    assert evidence.confirmed_refs == {"R2"}
    assert evidence.candidate_refs == set()
    assert evidence.unverified_refs == {"R3"}
    assert evidence.conflict_refs == set()
    assert evidence.inference_mode == "with_netlist"
    assert evidence.decision_manifest_used is False


def test_without_netlist_treats_xy_minus_bom_as_candidate_nc() -> None:
    evidence = _infer_nc_evidence(
        xy_refs={"R1", "R2"},
        bom_refs={"R1"},
        netlist_refs=None,
        explicit_nc_refs=set(),
        explicit_non_nc_refs=set(),
        decision_manifest_used=False,
    )

    assert evidence.confirmed_refs == set()
    assert evidence.candidate_refs == {"R2"}
    assert evidence.unverified_refs == set()
    assert evidence.inference_mode == "without_netlist"


def test_explicit_nc_is_confirmed_without_netlist_and_other_refs_remain_candidates() -> None:
    evidence = _infer_nc_evidence(
        xy_refs={"C1", "C2", "C3"},
        bom_refs={"C1"},
        netlist_refs=None,
        explicit_nc_refs={"C2"},
        explicit_non_nc_refs=set(),
        decision_manifest_used=True,
    )

    assert evidence.confirmed_refs == {"C2"}
    assert evidence.candidate_refs == {"C3"}
    assert evidence.decision_manifest_used is True


def test_processed_bom_wins_when_explicit_nc_summary_conflicts() -> None:
    evidence = _infer_nc_evidence(
        xy_refs={"U1", "U2"},
        bom_refs={"U1"},
        netlist_refs={"U1", "U2"},
        explicit_nc_refs={"U1", "U2"},
        explicit_non_nc_refs=set(),
        decision_manifest_used=True,
    )

    assert evidence.conflict_refs == {"U1"}
    assert evidence.confirmed_refs == {"U2"}
    assert "U1" not in evidence.confirmed_refs


def test_manifest_non_nc_exclusions_are_not_reported_as_candidate_nc() -> None:
    evidence = _infer_nc_evidence(
        xy_refs={"R1", "TP1", "SH1"},
        bom_refs={"R1"},
        netlist_refs=None,
        explicit_nc_refs=set(),
        explicit_non_nc_refs={"TP1", "SH1"},
        decision_manifest_used=True,
    )

    assert evidence.candidate_refs == set()
    assert evidence.non_nc_refs == {"TP1", "SH1"}
