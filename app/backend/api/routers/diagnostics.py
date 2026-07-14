from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.backend.api.common import content_disposition, error_payload
from app.backend.api.context import AppContext, get_context
from app.backend.services.diagnostics import build_diagnostic_package


router = APIRouter(tags=["diagnostics"])


def _package_response(context: AppContext, request: Request, asset_ids: list[object]) -> Response:
    try:
        package = build_diagnostic_package(
            context.root,
            selected_asset_ids=asset_ids,
            secrets=[str(request.app.state.session_token)],
        )
    except (KeyError, ValueError, FileNotFoundError) as exc:
        return JSONResponse(error_payload(str(exc), kind="diagnostic_selection_error"), status_code=400)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        package,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition(f"insta360_hw_diagnostic_{stamp}.zip"),
            "Cache-Control": "no-store",
        },
    )


@router.get("/diagnostics/package")
def diagnostic_package(request: Request, context: AppContext = Depends(get_context)) -> Response:
    return _package_response(context, request, [])


@router.post("/diagnostics/package")
def diagnostic_package_with_assets(
    params: dict[str, object],
    request: Request,
    context: AppContext = Depends(get_context),
) -> Response:
    asset_ids = params.get("asset_ids") or []
    if not isinstance(asset_ids, list):
        return JSONResponse(error_payload("asset_ids 必须是列表", kind="diagnostic_selection_error"), status_code=400)
    return _package_response(context, request, asset_ids)
