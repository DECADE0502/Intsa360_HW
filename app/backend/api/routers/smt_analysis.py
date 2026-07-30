from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import Field

from app.backend.api.common import error_payload, is_user_input_error
from app.backend.api.context import AppContext, get_context
from app.backend.contracts.api import ContractModel
from app.backend.contracts.smt_analysis import (
    BoardSide,
    CoordinateScope,
    PlacementRole,
    RegistrationModel,
    SmtAnalysisRunResponse,
    SmtRegistrationAnchor,
)


router = APIRouter(prefix="/smt-analysis", tags=["smt-analysis"])


class StartRunRequest(ContractModel):
    smt_folder: str = Field(min_length=1, max_length=1000)
    processed_bom: str = Field(min_length=1, max_length=1000)
    netlist_folder: str = Field(default="", max_length=1000)
    decision_manifest: str = Field(default="", max_length=1000)
    semantic_manifest: str = Field(default="", max_length=1000)


class ConfirmSourcesRequest(ContractModel):
    coordinate_set_id: str = Field(min_length=1, max_length=160)
    scope_semantics: CoordinateScope
    pages: dict[str, BoardSide]
    unit: Optional[Literal["mm", "mil", "inch"]] = None
    side_mapping: dict[str, BoardSide] = Field(default_factory=dict)


class RegistrationRequest(ContractModel):
    coordinate_set_id: str = Field(min_length=1, max_length=160)
    page_id: str = Field(min_length=1, max_length=160)
    side: Literal["top", "bottom"]
    model: RegistrationModel
    anchors: list[SmtRegistrationAnchor] = Field(min_length=3)
    confirmed: bool = False


class PlacementDecisionRequest(ContractModel):
    action: Literal[
        "confirm_installed",
        "confirm_nc",
        "mark_process",
        "mark_non_smt",
        "leave_unresolved",
        "change_role",
    ]
    role: Optional[PlacementRole] = None
    reason: str = Field(default="", max_length=1000)
    operator: Optional[str] = Field(default=None, max_length=160)


class BatchPlacementDecisionRequest(PlacementDecisionRequest):
    placement_ids: list[str] = Field(min_length=1, max_length=5000)


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, KeyError):
        return JSONResponse(
            error_payload(str(exc), kind="not_found"),
            status_code=404,
        )
    status = 400 if is_user_input_error(exc) else 500
    return JSONResponse(
        error_payload(str(exc), kind="smt_analysis_error"),
        status_code=status,
    )


@router.post("/runs", response_model=SmtAnalysisRunResponse)
def start_run(
    request: StartRunRequest,
    context: AppContext = Depends(get_context),
):
    try:
        return context.smt_analysis.start(**request.model_dump())
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/runs/{run_id}", response_model=SmtAnalysisRunResponse)
def get_run(run_id: str, context: AppContext = Depends(get_context)):
    try:
        return context.smt_analysis.get(run_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/runs/{run_id}/status")
def get_run_status(run_id: str, context: AppContext = Depends(get_context)):
    try:
        return context.smt_analysis.status(run_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.post("/runs/{run_id}/sources/confirm", response_model=SmtAnalysisRunResponse)
def confirm_sources(
    run_id: str,
    request: ConfirmSourcesRequest,
    context: AppContext = Depends(get_context),
):
    try:
        return context.smt_analysis.confirm_sources(run_id, **request.model_dump())
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.post("/runs/{run_id}/registrations", response_model=SmtAnalysisRunResponse)
def create_registration(
    run_id: str,
    request: RegistrationRequest,
    context: AppContext = Depends(get_context),
):
    try:
        return context.smt_analysis.register(
            run_id,
            coordinate_set_id=request.coordinate_set_id,
            page_id=request.page_id,
            side=request.side,
            model=request.model,
            anchors=request.anchors,
            confirmed=request.confirmed,
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.post(
    "/runs/{run_id}/placements/{placement_id}/decision",
    response_model=SmtAnalysisRunResponse,
)
def decide_placement(
    run_id: str,
    placement_id: str,
    request: PlacementDecisionRequest,
    context: AppContext = Depends(get_context),
):
    try:
        return context.smt_analysis.decide(
            run_id,
            placement_id=placement_id,
            **request.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.post(
    "/runs/{run_id}/placements/decisions",
    response_model=SmtAnalysisRunResponse,
)
def decide_placements(
    run_id: str,
    request: BatchPlacementDecisionRequest,
    context: AppContext = Depends(get_context),
):
    try:
        return context.smt_analysis.decide_many(
            run_id,
            **request.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.post("/runs/{run_id}/finalize", response_model=SmtAnalysisRunResponse)
def finalize_run(run_id: str, context: AppContext = Depends(get_context)):
    try:
        return context.smt_analysis.finalize(run_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.post("/runs/{run_id}/export")
def export_run(run_id: str, context: AppContext = Depends(get_context)):
    try:
        return context.smt_analysis.export(run_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/runs/{run_id}/pages/{page_id}/preview")
def page_preview(
    run_id: str,
    page_id: str,
    context: AppContext = Depends(get_context),
):
    try:
        path, media_type = context.smt_analysis.preview(run_id, page_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.delete("/runs/{run_id}")
def delete_run(run_id: str, context: AppContext = Depends(get_context)):
    try:
        removed = context.smt_analysis.delete(run_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)
    if not removed:
        return JSONResponse(
            error_payload("SMT 分析运行不存在", kind="not_found"),
            status_code=404,
        )
    return {"status": "ok", "run_id": run_id}
