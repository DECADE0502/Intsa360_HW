from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse

from app.backend.api.common import error_payload, is_user_input_error
from app.backend.api.context import AppContext, get_context
from app.backend.contracts.smt_view import SmtViewBoard, SmtViewBoardRequest


router = APIRouter(prefix="/smt-view", tags=["smt-view"])


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, KeyError):
        return JSONResponse(error_payload(str(exc).strip("'"), kind="not_found"), status_code=404)
    status = 400 if is_user_input_error(exc) else 500
    return JSONResponse(error_payload(str(exc), kind="smt_view_error"), status_code=status)


@router.post("/boards", response_model=SmtViewBoard)
def create_board(request: SmtViewBoardRequest, context: AppContext = Depends(get_context)):
    try:
        return context.smt_view.create(request)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/boards/{board_id}", response_model=SmtViewBoard)
def get_board(board_id: str, context: AppContext = Depends(get_context)):
    try:
        return context.smt_view.get(board_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/boards/{board_id}/reference-drawing")
def open_reference_drawing(board_id: str, context: AppContext = Depends(get_context)):
    try:
        path = context.smt_view.reference_drawing(board_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)
    return FileResponse(path, media_type="application/pdf", filename=path.name, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/boards/{board_id}/drawing/{side}")
def open_registered_drawing(board_id: str, side: str, context: AppContext = Depends(get_context)):
    try:
        path = context.smt_view.drawing_image(board_id, side)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=31536000, immutable"})
