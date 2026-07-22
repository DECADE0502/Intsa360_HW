from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.backend.tools.bom_classify import analyze_placement, classification_config
from app.backend.tools.bom_decisions import load_decision_manifest
from app.backend.tools.bom_process import detect_part_conflicts, parse_source
from app.backend.tools.bom_process_adapter import run_bom_process


SAMPLE_ROOT = Path(r"D:\desktop\工具集")
IAC4_V05 = SAMPLE_ROOT / "IAC4_MB_V05_20260507.xlsx"
POWER_V2 = SAMPLE_ROOT / "功耗版V2.xlsx"
IAC3A_V08 = SAMPLE_ROOT / "IAC3A_MB_V08_20250326.xlsx"


def _analysis(path: Path):
    if not path.is_file():
        pytest.skip(f"real BOM unavailable: {path}")
    parsed = parse_source(path)
    analysis = analyze_placement(
        parsed.normalized_rows,
        classification_config(),
        source_fingerprint=parsed.source_fingerprint,
        quality_report=parsed.quality_report,
    )
    return parsed, analysis


def _classified_for_ref(analysis, ref: str):
    return [item for item in analysis.rows if ref in item.row.refs]


def _only_classification(analysis, ref: str):
    matches = _classified_for_ref(analysis, ref)
    assert matches, f"missing reference: {ref}"
    signatures = {
        (
            item.classification.state,
            item.classification.rule_id,
            item.classification.identity_status,
            item.classification.role,
            item.classification.suggested_destination,
        )
        for item in matches
    }
    assert len(signatures) == 1, (ref, signatures)
    return matches[0].classification


@pytest.mark.slow
def test_iac4_v05_golden_classification() -> None:
    parsed, analysis = _analysis(IAC4_V05)

    assert len(parsed.physical_parts) == 1037
    for ref in ("H1", "H2", "H3", "H4"):
        result = _only_classification(analysis, ref)
        assert result.state == "suspected_material"
        assert result.identity_status == "identity_candidate_internal"
        assert result.role == "smt_mechanical"
        assert result.suggested_destination == "smt"

    shield = _only_classification(analysis, "SH1")
    assert shield.role == "shield"
    assert shield.rule_id == "R3C"
    assert shield.suggested_destination is None

    u400 = next(part for part in parsed.physical_parts if part.reference == "U400")
    assert u400.occurrence_count == 13
    assert u400.conflicts == ()
    assert sum(part.reference == "U400" for part in parsed.physical_parts) == 1

    conflict = next(item for item in detect_part_conflicts(parsed.raw_rows) if item["code"] == "C.C1105M21")
    assert conflict["high_confidence"] is False
    assert conflict["reason"] == "numeric_or_version_conflict"


@pytest.mark.slow
def test_power_v2_golden_classification() -> None:
    parsed, analysis = _analysis(POWER_V2)

    assert len(parsed.physical_parts) == 1315
    for ref in ("H1", "H2", "H3", "H4"):
        result = _only_classification(analysis, ref)
        assert result.rule_id == "R5"
        assert result.role == "smt_mechanical"
        assert result.suggested_destination == "smt"

    for ref in ("MTG5400", "MTG5401", "MTG5402", "MTG5403"):
        result = _only_classification(analysis, ref)
        assert result.state == "suspected_material"
        assert result.identity_status == "identity_candidate_mpn"
        assert result.role == "smt_mechanical"
        assert result.suggested_destination is None

    jp_refs = {
        ref
        for item in analysis.rows
        for ref in item.row.refs
        if ref.upper().startswith("JP") and ref[2:].isdigit()
    }
    assert len(jp_refs) == 178
    assert {
        item.classification.role
        for item in analysis.rows
        if any(ref in jp_refs for ref in item.row.refs)
    } == {"short_symbol"}
    assert {
        item.classification.suggested_destination
        for item in analysis.rows
        if any(ref in jp_refs for ref in item.row.refs)
    } == {"non_smt"}


@pytest.mark.slow
def test_iac3a_v08_golden_classification() -> None:
    parsed, analysis = _analysis(IAC3A_V08)

    assert len(parsed.physical_parts) == 1208
    for ref in ("D4", "D5"):
        result = _only_classification(analysis, ref)
        assert result.state == "suspected_material"
        assert result.identity_status == "identity_candidate_mpn"
        assert result.suggested_destination is None
    for ref in ("LED1", "LED2", "LED3", "U16"):
        result = _only_classification(analysis, ref)
        assert result.state == "suspected_material"
        assert result.suggested_destination is None

    d8 = _only_classification(analysis, "D8")
    assert d8.state == "confirmed_nc"
    assert d8.suggested_destination == "non_smt"

    for ref in ("H1", "H2", "H4", "H5", "H6"):
        result = _only_classification(analysis, ref)
        assert result.role == "mounting_hole"
        assert result.state == "suspected_process"
        assert result.suggested_destination == "non_smt"


def _golden_resolution(group: dict[str, object], index: int) -> dict[str, object]:
    original = group.get("original_fields") if isinstance(group.get("original_fields"), dict) else {}
    inferred = group.get("inferred_fields") if isinstance(group.get("inferred_fields"), dict) else {}
    evidence = group.get("evidence") if isinstance(group.get("evidence"), list) else []
    role = str(group.get("role") or "unknown")
    if role == "shield":
        return {
            "destination": "non_smt",
            "exclusion_kind": "scope_excluded",
            "role": "shield",
            "subtype": "cover",
            "decision_source": "user",
        }
    if any(isinstance(item, dict) and item.get("kind") == "nc_keyword" for item in evidence):
        return {
            "destination": "non_smt",
            "exclusion_kind": "nc",
            "role": role,
            "decision_source": "user",
        }
    if group.get("suggested_destination") == "non_smt":
        return {
            "destination": "non_smt",
            "exclusion_kind": str(group.get("exclusion_kind") or "process_only"),
            "role": role,
            "decision_source": "user",
        }
    part_number = str(
        inferred.get("part_number")
        or original.get("part_number")
        or group.get("suggested_code")
        or f"GOLDEN-{index:04d}"
    )
    description = str(
        inferred.get("desc")
        or inferred.get("name")
        or inferred.get("model")
        or original.get("desc")
        or original.get("name")
        or original.get("model")
        or "Golden sample material"
    )
    return {
        "destination": "smt",
        "exclusion_kind": "",
        "role": role,
        "part_number_override": part_number,
        "field_patch": {"desc": description},
        "decision_source": "user",
    }


@pytest.mark.slow
@pytest.mark.parametrize("source", [IAC4_V05, POWER_V2, IAC3A_V08])
def test_real_bom_full_output_partition_and_manifest(tmp_path: Path, source: Path) -> None:
    if not source.is_file():
        pytest.skip(f"real BOM unavailable: {source}")
    root = tmp_path / source.stem
    root.mkdir()
    initial = run_bom_process(root, {
        "source_bom": str(source),
        "formats": ["plm", "oa"],
        "name": source.stem,
    })
    assert initial["reason"] == "placement_review"
    resolutions = {
        str(group["group_id"]): _golden_resolution(group, index)
        for index, group in enumerate(initial["groups"], start=1)
    }
    params = {
        "source_bom": str(source),
        "formats": ["plm", "oa"],
        "name": source.stem,
        "placement_resolutions": resolutions,
    }
    processed = run_bom_process(root, params)
    if processed.get("reason") == "part_property_conflicts":
        params["merge_conflicts"] = True
        params["conflict_choices"] = {
            str(conflict["code"]): {"action": "select_variant", "variant_index": 0}
            for conflict in processed["conflicts"]
        }
        processed = run_bom_process(root, params)

    assert processed["status"] == "ok", processed
    assert len(processed["outputs"]) == 6
    assert all(Path(path).is_file() for path in processed["outputs"])

    manifest = load_decision_manifest(Path(processed["decision_manifest"]))
    smt = {
        ref
        for decision in manifest.placements
        if decision["destination"] == "smt"
        for ref in decision["refs"]
    }
    non_smt = {
        ref
        for decision in manifest.placements
        if decision["destination"] == "non_smt"
        for ref in decision["refs"]
    }
    expected = {part.reference for part in parse_source(source).physical_parts}
    assert smt.isdisjoint(non_smt)
    assert smt | non_smt == expected
    assert processed["summary"]["total_positions"] == len(smt)

    raw_manifest = json.loads(Path(processed["decision_manifest"]).read_text(encoding="utf-8"))
    assert raw_manifest["schema_version"] == 2
    assert raw_manifest["rule_version"] == processed["rule_version"]
