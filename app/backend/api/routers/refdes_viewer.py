from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse

from app.backend.api.common import error_payload, is_user_input_error
from app.backend.api.context import AppContext, get_context
from app.backend.contracts.refdes_viewer import RefdesDocument, RefdesOpenRequest


router = APIRouter(prefix="/refdes-viewer", tags=["refdes-viewer"])


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, KeyError):
        return JSONResponse(
            error_payload(str(exc).strip("'"), kind="not_found"),
            status_code=404,
        )
    status = 400 if is_user_input_error(exc) else 500
    return JSONResponse(
        error_payload(str(exc), kind="refdes_viewer_error"),
        status_code=status,
    )


@router.post("/docs", response_model=RefdesDocument)
def open_document(
    request: RefdesOpenRequest,
    context: AppContext = Depends(get_context),
):
    try:
        return context.refdes_viewer.open(request.path, label=request.label)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/docs/{doc_id}", response_model=RefdesDocument)
def get_document(doc_id: str, context: AppContext = Depends(get_context)):
    try:
        return context.refdes_viewer.get(doc_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/docs/{doc_id}/pages/{page_id}/preview")
def page_preview(
    doc_id: str,
    page_id: str,
    context: AppContext = Depends(get_context),
):
    try:
        path, media_type = context.refdes_viewer.preview(doc_id, page_id)
    except Exception as exc:  # noqa: BLE001
        return _error(exc)
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
