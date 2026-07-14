from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.backend import assets, history
from app.backend.api.common import error_payload
from app.backend.api.context import AppContext, get_context
from app.backend.repositories.assets_repository import AssetsRepository


router = APIRouter(tags=["history"])


@router.get("/history")
def list_history(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return {"runs": history.list_runs(context.root)}


@router.delete("/history")
def clear_history(context: AppContext = Depends(get_context)) -> dict[str, str]:
    history.clear_runs(context.root)
    return {"status": "ok"}


@router.get("/history/{run_id:path}")
def get_history(run_id: str, context: AppContext = Depends(get_context)):
    try:
        run = history.get_run(context.root, unquote(run_id))
    except ValueError as exc:
        return JSONResponse(error_payload(str(exc), kind=type(exc).__name__), status_code=400)
    if run is None:
        return JSONResponse({"error": "history not found"}, status_code=404)
    return run


@router.delete("/history/{run_id:path}")
def delete_history(run_id: str, context: AppContext = Depends(get_context)):
    try:
        history.remove_run(context.root, unquote(run_id))
    except ValueError as exc:
        return JSONResponse(error_payload(str(exc), kind=type(exc).__name__), status_code=400)
    return {"status": "ok"}


@router.get("/assets")
def list_assets(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return assets.list_assets(context.root)


@router.post("/assets/rebuild")
def rebuild_assets(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return {"status": "ok", **AssetsRepository(context.root).rebuild_metadata()}
