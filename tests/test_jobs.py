from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backend.contracts.api import ApiError
from app.backend.contracts.jobs import JobPhase, JobStatus
from app.backend.main import create_app
from app.backend.services.jobs import (
    DuplicateWorkerError,
    JobCancellationError,
    PersistentJobService,
    TerminalJobError,
)


BASE_URL = "http://127.0.0.1:8765"


def _service(tmp_path: Path) -> PersistentJobService:
    return PersistentJobService(tmp_path / "jobs", recover_interrupted=False)


def test_job_create_and_transition_are_persisted_atomically(tmp_path: Path) -> None:
    service = _service(tmp_path)

    created = service.create(kind="bom_process", message="等待处理")
    running = service.transition(
        created.id,
        status=JobStatus.RUNNING,
        phase=JobPhase.PROCESSING,
        progress=25,
        message="正在处理",
    )

    assert created.status is JobStatus.QUEUED
    assert running.status is JobStatus.RUNNING
    assert running.progress == 25
    assert running.updated_at >= created.updated_at
    assert service.get(created.id) == running
    stored = json.loads((tmp_path / "jobs" / f"{created.id}.json").read_text(encoding="utf-8"))
    assert stored["id"] == str(created.id)
    assert stored["phase"] == "processing"
    assert not list((tmp_path / "jobs").glob("*.tmp"))


def test_terminal_job_state_is_immutable(tmp_path: Path) -> None:
    service = _service(tmp_path)
    job = service.create(kind="bom_process")
    service.transition(
        job.id,
        status=JobStatus.SUCCEEDED,
        phase=JobPhase.SUCCEEDED,
        progress=100,
        message="处理完成",
        result={"output": "bom/main.xlsx"},
    )

    with pytest.raises(TerminalJobError):
        service.transition(job.id, message="不应覆盖")

    assert service.get(job.id).message == "处理完成"


def test_cancellation_is_allowed_before_commit_but_rejected_from_commit_onward(tmp_path: Path) -> None:
    service = _service(tmp_path)
    cancellable = service.create(kind="update")
    service.transition(
        cancellable.id,
        status=JobStatus.RUNNING,
        phase=JobPhase.STAGING,
        progress=60,
        message="正在暂存",
    )

    cancelled = service.request_cancel(cancellable.id)

    assert cancelled.status is JobStatus.CANCELLED
    assert cancelled.phase is JobPhase.CANCELLED
    assert cancelled.cancellable is False

    committed = service.create(kind="update")
    committed = service.transition(
        committed.id,
        status=JobStatus.RUNNING,
        phase=JobPhase.COMMITTING,
        progress=75,
        message="正在提交",
    )
    assert committed.cancellable is False

    after_commit = service.transition(
        committed.id,
        phase=JobPhase.VERIFYING,
        progress=90,
        message="正在验证提交结果",
        cancellable=True,
    )
    assert after_commit.cancellable is False

    with pytest.raises(JobCancellationError):
        service.request_cancel(committed.id)


def test_one_job_cannot_start_two_workers(tmp_path: Path) -> None:
    service = _service(tmp_path)
    job = service.create(kind="bom_process")
    entered = threading.Event()
    release = threading.Event()

    def worker(control):
        entered.set()
        assert release.wait(timeout=3)
        control.update(progress=80, message="即将完成")
        return {"output": "bom/result.xlsx"}

    thread = service.start_worker(job.id, worker, phase=JobPhase.PROCESSING, message="开始处理")
    assert entered.wait(timeout=2)

    with pytest.raises(DuplicateWorkerError):
        service.start_worker(job.id, worker)

    release.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
    completed = service.get(job.id)
    assert completed.status is JobStatus.SUCCEEDED
    assert completed.progress == 100
    assert completed.result == {"output": "bom/result.xlsx"}


def test_restart_recovers_nonterminal_jobs_without_mutating_completed_jobs(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    service = PersistentJobService(jobs_dir, recover_interrupted=False)
    queued = service.create(kind="bom_process")
    running = service.create(kind="update")
    service.transition(
        running.id,
        status=JobStatus.RUNNING,
        phase=JobPhase.VERIFYING,
        progress=50,
        message="正在校验",
    )
    completed = service.create(kind="bom_compare")
    service.transition(
        completed.id,
        status=JobStatus.SUCCEEDED,
        phase=JobPhase.SUCCEEDED,
        progress=100,
        message="已完成",
    )

    restarted = PersistentJobService(jobs_dir)

    for interrupted_id in (queued.id, running.id):
        recovered = restarted.get(interrupted_id)
        assert recovered.status is JobStatus.FAILED
        assert recovered.phase is JobPhase.FAILED
        assert recovered.cancellable is False
        assert recovered.error == ApiError(code="job_interrupted", message="平台重启，任务已中断，请重新执行。")
    assert restarted.get(completed.id).status is JobStatus.SUCCEEDED
    assert restarted.get(completed.id).message == "已完成"


def test_jobs_router_lists_reads_and_cancels_persisted_jobs(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "VERSION").write_text("0.4.0\n", encoding="utf-8")
    app = create_app(root)
    job = app.state.context.jobs.create(kind="bom_process", message="等待处理")

    with TestClient(app, base_url=BASE_URL) as client:
        listed = client.get("/api/v1/jobs")
        detail = client.get(f"/api/v1/jobs/{job.id}")
        session = client.get("/api/v1/session").json()["token"]
        cancelled = client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"X-Insta360-Session": session, "Origin": BASE_URL},
        )

    assert listed.status_code == 200
    assert listed.json()["jobs"][0]["id"] == str(job.id)
    assert detail.status_code == 200
    assert detail.json()["job"]["kind"] == "bom_process"
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"
