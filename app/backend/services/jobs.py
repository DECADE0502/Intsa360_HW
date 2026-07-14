from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional
from uuid import UUID, uuid4

from pydantic import JsonValue, ValidationError

from app.backend.contracts.api import ApiError
from app.backend.contracts.jobs import Job, JobPhase, JobStatus


TERMINAL_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})
COMMIT_PHASES = frozenset({JobPhase.COMMITTING, JobPhase.RESTARTING})
TERMINAL_PHASE_BY_STATUS = {
    JobStatus.SUCCEEDED: JobPhase.SUCCEEDED,
    JobStatus.FAILED: JobPhase.FAILED,
    JobStatus.CANCELLED: JobPhase.CANCELLED,
}
_UNSET = object()


class JobServiceError(RuntimeError):
    pass


class JobNotFoundError(JobServiceError):
    pass


class DuplicateWorkerError(JobServiceError):
    pass


class JobCancellationError(JobServiceError):
    pass


class TerminalJobError(JobServiceError):
    pass


class JobCancelledError(JobServiceError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _job_id(value: UUID | str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise JobNotFoundError("任务编号无效") from exc


class JobControl:
    def __init__(self, service: "PersistentJobService", job_id: UUID, cancelled: threading.Event) -> None:
        self._service = service
        self.job_id = job_id
        self._cancelled = cancelled

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelledError("任务已取消")

    def update(
        self,
        *,
        phase: JobPhase | str | None = None,
        progress: float | int | None = None,
        message: str | None = None,
        cancellable: bool | None = None,
    ) -> Job:
        self.raise_if_cancelled()
        return self._service.transition(
            self.job_id,
            status=JobStatus.RUNNING,
            phase=phase,
            progress=progress,
            message=message,
            cancellable=cancellable,
        )


Worker = Callable[[JobControl], Optional[Mapping[str, JsonValue]]]


class PersistentJobService:
    def __init__(self, jobs_dir: Path, *, recover_interrupted: bool = True) -> None:
        self.jobs_dir = Path(jobs_dir).resolve()
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._state_lock = threading.RLock()
        self._worker_lock = threading.Lock()
        self._workers: dict[UUID, threading.Thread] = {}
        self._cancel_events: dict[UUID, threading.Event] = {}
        if recover_interrupted:
            self._recover_interrupted_jobs()

    def _path(self, job_id: UUID | str) -> Path:
        return self.jobs_dir / f"{_job_id(job_id)}.json"

    def _persist(self, job: Job) -> None:
        path = self._path(job.id)
        temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(job.model_dump_json(indent=2))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            for attempt in range(8):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == 7:
                        raise
                    time.sleep(0.025 * (attempt + 1))
        finally:
            temporary.unlink(missing_ok=True)

    def _read_path(self, path: Path) -> Job:
        try:
            return Job.model_validate_json(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValidationError, ValueError) as exc:
            raise JobNotFoundError("任务记录不存在或已损坏") from exc

    def create(self, *, kind: str, message: str = "等待执行", cancellable: bool = True) -> Job:
        now = _utc_now()
        job = Job(
            id=uuid4(),
            kind=kind,
            status=JobStatus.QUEUED,
            phase=JobPhase.QUEUED,
            progress=0,
            message=message,
            cancellable=cancellable,
            created_at=now,
            updated_at=now,
        )
        with self._state_lock:
            self._persist(job)
        return job

    def get(self, job_id: UUID | str) -> Job:
        with self._state_lock:
            path = self._path(job_id)
            if not path.is_file():
                raise JobNotFoundError("任务不存在")
            return self._read_path(path)

    def list(self) -> list[Job]:
        jobs: list[Job] = []
        with self._state_lock:
            for path in self.jobs_dir.glob("*.json"):
                try:
                    jobs.append(self._read_path(path))
                except JobNotFoundError:
                    continue
        return sorted(jobs, key=lambda item: item.updated_at, reverse=True)

    def transition(
        self,
        job_id: UUID | str,
        *,
        status: JobStatus | str | None = None,
        phase: JobPhase | str | None = None,
        progress: float | int | None = None,
        message: str | None = None,
        cancellable: bool | None = None,
        result: Mapping[str, JsonValue] | None | object = _UNSET,
        error: ApiError | Mapping[str, JsonValue] | None | object = _UNSET,
    ) -> Job:
        with self._state_lock:
            current = self.get(job_id)
            if current.status in TERMINAL_STATUSES:
                raise TerminalJobError("终态任务不可修改")

            next_status = JobStatus(status) if status is not None else current.status
            next_phase = JobPhase(phase) if phase is not None else current.phase
            next_progress = progress if progress is not None else current.progress
            if next_progress < current.progress:
                raise ValueError("任务进度不可回退")
            expected_terminal_phase = TERMINAL_PHASE_BY_STATUS.get(next_status)
            if expected_terminal_phase is not None and next_phase is not expected_terminal_phase:
                raise ValueError("终态状态与阶段不一致")
            if next_phase in TERMINAL_PHASE_BY_STATUS.values() and expected_terminal_phase is not next_phase:
                raise ValueError("终态阶段与状态不一致")

            payload = current.model_dump()
            payload.update(
                status=next_status,
                phase=next_phase,
                progress=100 if next_status is JobStatus.SUCCEEDED else next_progress,
                message=current.message if message is None else message,
                cancellable=False
                if next_phase in COMMIT_PHASES or next_status in TERMINAL_STATUSES
                else current.cancellable and (True if cancellable is None else cancellable),
                updated_at=_utc_now(),
            )
            if result is not _UNSET:
                payload["result"] = result
            if error is not _UNSET:
                payload["error"] = error
            updated = Job.model_validate(payload)
            self._persist(updated)
            return updated

    def request_cancel(self, job_id: UUID | str) -> Job:
        canonical_id = _job_id(job_id)
        with self._state_lock:
            job = self.get(canonical_id)
            if job.status is JobStatus.CANCELLED:
                return job
            if job.status in TERMINAL_STATUSES:
                raise JobCancellationError("已结束的任务不能取消")
            if job.phase in COMMIT_PHASES or not job.cancellable:
                raise JobCancellationError("任务已进入提交阶段，不能取消")
            event = self._cancel_events.setdefault(canonical_id, threading.Event())
            event.set()
            return self.transition(
                canonical_id,
                status=JobStatus.CANCELLED,
                phase=JobPhase.CANCELLED,
                message="任务已取消",
                cancellable=False,
            )

    def start_worker(
        self,
        job_id: UUID | str,
        worker: Worker,
        *,
        phase: JobPhase | str = JobPhase.PROCESSING,
        message: str = "任务已开始",
    ) -> threading.Thread:
        canonical_id = _job_id(job_id)
        with self._worker_lock:
            existing = self._workers.get(canonical_id)
            if existing is not None and existing.is_alive():
                raise DuplicateWorkerError("同一任务已有执行线程")
            current = self.get(canonical_id)
            if current.status in TERMINAL_STATUSES:
                raise TerminalJobError("终态任务不能重新启动")
            cancel_event = self._cancel_events.setdefault(canonical_id, threading.Event())
            cancel_event.clear()
            self.transition(
                canonical_id,
                status=JobStatus.RUNNING,
                phase=phase,
                message=message,
            )
            control = JobControl(self, canonical_id, cancel_event)

            def run() -> None:
                try:
                    result = worker(control)
                    current_job = self.get(canonical_id)
                    if current_job.status not in TERMINAL_STATUSES:
                        self.transition(
                            canonical_id,
                            status=JobStatus.SUCCEEDED,
                            phase=JobPhase.SUCCEEDED,
                            progress=100,
                            message="任务已完成",
                            cancellable=False,
                            result=dict(result) if result is not None else None,
                        )
                except JobCancelledError:
                    current_job = self.get(canonical_id)
                    if current_job.status not in TERMINAL_STATUSES:
                        self.transition(
                            canonical_id,
                            status=JobStatus.CANCELLED,
                            phase=JobPhase.CANCELLED,
                            message="任务已取消",
                            cancellable=False,
                        )
                except BaseException as exc:  # noqa: BLE001
                    current_job = self.get(canonical_id)
                    if current_job.status not in TERMINAL_STATUSES:
                        message_text = str(exc).strip() or type(exc).__name__
                        self.transition(
                            canonical_id,
                            status=JobStatus.FAILED,
                            phase=JobPhase.FAILED,
                            message="任务执行失败",
                            cancellable=False,
                            error=ApiError(code="worker_failed", message=message_text),
                        )
                finally:
                    with self._worker_lock:
                        if self._workers.get(canonical_id) is threading.current_thread():
                            self._workers.pop(canonical_id, None)

            thread = threading.Thread(target=run, name=f"platform-job-{str(canonical_id)[:8]}", daemon=True)
            self._workers[canonical_id] = thread
            thread.start()
            return thread

    def _recover_interrupted_jobs(self) -> None:
        with self._state_lock:
            for path in self.jobs_dir.glob("*.json"):
                try:
                    job = self._read_path(path)
                except JobNotFoundError:
                    continue
                if job.status in TERMINAL_STATUSES:
                    continue
                payload = job.model_dump()
                payload.update(
                    status=JobStatus.FAILED,
                    phase=JobPhase.FAILED,
                    message="平台重启，任务已中断，请重新执行。",
                    cancellable=False,
                    error=ApiError(code="job_interrupted", message="平台重启，任务已中断，请重新执行。"),
                    updated_at=_utc_now(),
                )
                self._persist(Job.model_validate(payload))
