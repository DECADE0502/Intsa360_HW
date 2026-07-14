from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.backend.api.common import error_payload
from app.backend.api.context import AppContext, get_context
from app.backend.services.jobs import JobCancellationError, JobNotFoundError


router = APIRouter(tags=["jobs"])


def _payload(job) -> dict[str, object]:
    return job.model_dump(mode="json")


@router.get("/jobs")
def list_jobs(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return {"status": "ok", "jobs": [_payload(job) for job in context.jobs.list()]}


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID, context: AppContext = Depends(get_context)):
    try:
        job = context.jobs.get(job_id)
    except JobNotFoundError as exc:
        return JSONResponse(error_payload(str(exc), kind="job_not_found"), status_code=404)
    return {"status": "ok", "job": _payload(job)}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: UUID, context: AppContext = Depends(get_context)):
    try:
        job = context.jobs.request_cancel(job_id)
    except JobNotFoundError as exc:
        return JSONResponse(error_payload(str(exc), kind="job_not_found"), status_code=404)
    except JobCancellationError as exc:
        return JSONResponse(error_payload(str(exc), kind="job_not_cancellable"), status_code=409)
    return {"status": "ok", "job": _payload(job)}
