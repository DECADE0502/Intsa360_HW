from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse

from app.backend.api.common import error_payload, is_user_input_error
from app.backend.api.context import AppContext, get_context
from app.backend.contracts.refdes import RefdesDrawing, RefdesOpenRequest


router = APIRouter(prefix="/refdes", tags=["refdes"])


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, KeyError):
        return JSONResponse(
            error_payload(str(exc).strip("'"), kind="not_found"),
            status_code=404,
        )
    status = 400 if is_user_input_error(exc) else 500
    return JSONResponse(
        error_payload(str(exc), kind="refdes_error"),
        status_code=status,
    )


@router.post("/drawings", response_model=RefdesDrawing)
def open_drawing(
    request: RefdesOpenRequest,
    context: AppContext = Depends(get_context),
):
    try:
        return context.refdes.open(request.path, label=request.label)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/drawings/{drawing_id}", response_model=RefdesDrawing)
def get_drawing(drawing_id: str, context: AppContext = Depends(get_context)):
    try:
        return context.refdes.get(drawing_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/drawings/{drawing_id}/pages/{page_number}/image")
def page_image(
    drawing_id: str,
    page_number: int,
    context: AppContext = Depends(get_context),
):
    try:
        path, media_type = context.refdes.page_image(drawing_id, page_number)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
