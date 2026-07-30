from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.backend.contracts.smt_analysis import (
    SmtAnalysisRunResponse,
    SmtAnalysisSummary,
    SmtPlacementDecision,
)
from app.backend.paths import AppPaths
from app.backend.repositories.smt_analysis_repository import SmtAnalysisRepository


def _snapshot(run_id: str, state: str = "review") -> SmtAnalysisRunResponse:
    now = datetime.now(timezone.utc)
    return SmtAnalysisRunResponse(
        schema_version=2,
        run_id=run_id,
        state=state,
        parser_version="parser-v2",
        rule_version="rules-v2",
        source_fingerprint="a" * 64,
        created_at=now,
        updated_at=now,
        sources=[],
        coordinate_sets=[],
        drawing_pages=[],
        registrations=[],
        placements=[],
        summary=SmtAnalysisSummary(
            source_count=0,
            coordinate_set_count=0,
            drawing_page_count=0,
            placement_count=0,
            installed_count=0,
            confirmed_nc_count=0,
            candidate_nc_count=0,
            unresolved_count=0,
            blocking_count=0,
        ),
        blocking_reasons=[],
    )


def _run(repository: SmtAnalysisRepository) -> str:
    run_id, reused = repository.create_or_reuse(
        source_fingerprint="a" * 64,
        parser_version="parser-v2",
        rule_version="rules-v2",
        source_relative_path="uploads/source",
        context={"source_relative_path": "uploads/source"},
    )
    assert reused is False
    return run_id


def test_snapshot_round_trip_and_cache_reuse(tmp_path: Path) -> None:
    repository = SmtAnalysisRepository(tmp_path)
    run_id = _run(repository)
    repository.save_snapshot(_snapshot(run_id))

    same_id, reused = repository.create_or_reuse(
        source_fingerprint="a" * 64,
        parser_version="parser-v2",
        rule_version="rules-v2",
        source_relative_path="uploads/source",
        context={"source_relative_path": "uploads/source"},
    )

    assert same_id == run_id
    assert reused is True
    assert repository.get_snapshot(run_id).state == "review"


def test_failure_does_not_replace_last_complete_snapshot(tmp_path: Path) -> None:
    repository = SmtAnalysisRepository(tmp_path)
    run_id = _run(repository)
    repository.save_snapshot(_snapshot(run_id))

    repository.record_failure(run_id, "render failed")

    assert repository.status(run_id)["state"] == "failed"
    assert repository.status(run_id)["last_error"] == "render failed"
    assert repository.get_snapshot(run_id).state == "review"


def test_decision_round_trip(tmp_path: Path) -> None:
    repository = SmtAnalysisRepository(tmp_path)
    run_id = _run(repository)
    decision = SmtPlacementDecision(
        decision_id="decision-R1",
        action="confirm_nc",
        role="smt_component",
        assembly_state="confirmed_nc",
        reason="人工确认",
        source="user",
        input_fingerprint="b" * 64,
        rule_version="rules-v2",
        operator="tester",
        created_at=datetime.now(timezone.utc),
    )

    repository.save_decision(run_id, "placement-R1", decision)

    assert repository.decisions(run_id)["placement-R1"] == decision


def test_delete_only_removes_unreferenced_owned_page_asset(tmp_path: Path) -> None:
    repository = SmtAnalysisRepository(tmp_path)
    first = _run(repository)
    repository.save_snapshot(_snapshot(first))
    second, _ = repository.create_or_reuse(
        source_fingerprint="b" * 64,
        parser_version="parser-v2",
        rule_version="rules-v2",
        source_relative_path="uploads/other",
        context={},
    )
    repository.save_snapshot(
        _snapshot(second).model_copy(update={"run_id": second, "source_fingerprint": "b" * 64})
    )
    cache = AppPaths(tmp_path).smt_analysis_cache_dir
    cache.mkdir(parents=True, exist_ok=True)
    shared = cache / "shared.png"
    shared.write_bytes(b"png")
    repository.register_page_asset(
        run_id=first,
        page_id="page-1",
        path=shared,
        media_type="image/png",
        pixel_width=10,
        pixel_height=10,
    )
    repository.register_page_asset(
        run_id=second,
        page_id="page-2",
        path=shared,
        media_type="image/png",
        pixel_width=10,
        pixel_height=10,
    )

    assert repository.remove(first) is True
    assert shared.exists()
    assert repository.remove(second) is True
    assert not shared.exists()


def test_page_asset_resolver_is_scoped_to_run(tmp_path: Path) -> None:
    repository = SmtAnalysisRepository(tmp_path)
    run_id = _run(repository)
    cache = AppPaths(tmp_path).smt_analysis_cache_dir
    preview = cache / "page.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"preview")
    repository.register_page_asset(
        run_id=run_id,
        page_id="page-1",
        path=preview,
        media_type="image/png",
        pixel_width=10,
        pixel_height=10,
    )

    resolved, media_type = repository.resolve_page_asset(run_id, "page-1")

    assert resolved == preview.resolve()
    assert media_type == "image/png"
