from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.backend.contracts.smt_analysis import SmtAnalysisRunResponse


FIXTURE = Path(__file__).parent / "fixtures" / "smt" / "contracts" / "analysis_run_v2.json"


def load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_smt_analysis_v2_fixture_round_trips() -> None:
    raw = load_fixture()
    parsed = SmtAnalysisRunResponse.model_validate(raw)

    assert parsed.schema_version == 2
    assert parsed.state == "review"
    assert parsed.coordinate_sets[0].scope_semantics == "unknown"
    assert parsed.registrations[0].confidence_state == "needs_calibration"
    assert parsed.placements[0].assembly_state == "installed"
    assert parsed.model_dump(mode="json") == raw


def test_smt_analysis_contract_rejects_unknown_fields() -> None:
    raw = load_fixture()
    raw["silent_guess"] = True

    with pytest.raises(ValidationError, match="silent_guess"):
        SmtAnalysisRunResponse.model_validate(raw)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("coordinate_sets", 0, "scope_semantics"), "complete_enough"),
        (("registrations", 0, "confidence_state"), "probably_ok"),
        (("placements", 0, "assembly_state"), "maybe_nc"),
    ],
)
def test_smt_analysis_contract_rejects_unversioned_states(
    path: tuple[object, ...],
    value: str,
) -> None:
    raw: object = load_fixture()
    cursor = raw
    for key in path[:-1]:
        cursor = cursor[key]  # type: ignore[index]
    cursor[path[-1]] = value  # type: ignore[index]

    with pytest.raises(ValidationError):
        SmtAnalysisRunResponse.model_validate(raw)


def test_smt_analysis_contract_rejects_non_finite_transform() -> None:
    raw = load_fixture()
    raw["registrations"][0]["transform"][0] = float("nan")  # type: ignore[index]

    with pytest.raises(ValidationError):
        SmtAnalysisRunResponse.model_validate(raw)


def test_smt_analysis_contract_rejects_invalid_fingerprint() -> None:
    raw = load_fixture()
    raw["source_fingerprint"] = "not-a-sha256"

    with pytest.raises(ValidationError, match="source_fingerprint"):
        SmtAnalysisRunResponse.model_validate(raw)
