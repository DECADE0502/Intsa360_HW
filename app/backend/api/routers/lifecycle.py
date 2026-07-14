from __future__ import annotations

import io
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response

from app.backend import lifecycle, update_api
from app.backend.api.common import content_disposition, error_payload, is_user_input_error
from app.backend.api.context import AppContext, get_context


router = APIRouter(tags=["lifecycle"])


@router.get("/lifecycle/check")
def lifecycle_check(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return lifecycle.run_self_check(context.root)


@router.get("/logs")
def list_logs(context: AppContext = Depends(get_context)) -> dict[str, object]:
    log_dir = context.paths.runtime_log_dir
    files = (
        sorted(
            [
                {"name": item.name, "size": item.stat().st_size, "mtime": item.stat().st_mtime}
                for item in log_dir.iterdir()
                if item.is_file()
            ],
            key=lambda item: item["mtime"],
            reverse=True,
        )
        if log_dir.exists()
        else []
    )
    return {"files": files}


@router.get("/logs/download")
def download_logs(context: AppContext = Depends(get_context)) -> Response:
    buffer = io.BytesIO()
    log_dir = context.paths.runtime_log_dir
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(log_dir.iterdir()) if log_dir.exists() else []:
            if item.is_file():
                archive.write(item, arcname=item.name)
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition("platform_logs.zip")},
    )


@router.get("/version")
def version(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return update_api.version_payload(context.root)


@router.get("/diagnostic/report")
def diagnostic_report(context: AppContext = Depends(get_context)):
    try:
        report = update_api.collect_diagnostic_report(context.root)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=500)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        report.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": content_disposition(f"insta360_hw_diagnostic_{stamp}.txt"),
            "Cache-Control": "no-store",
        },
    )


@router.get("/update/check")
def update_check(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return update_api.check_update(context.root)


@router.get("/update/status")
def update_status(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return update_api.update_status(context.root)


@router.get("/update/reconnect")
def update_reconnect(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return update_api.reconnect_update(context.root)


@router.post("/update/run")
def update_run(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return update_api.run_update(context.root)


@router.post("/update/cancel")
def update_cancel(params: dict[str, object], context: AppContext = Depends(get_context)) -> dict[str, object]:
    return update_api.cancel_update(context.root, str(params.get("job_id") or ""))


@router.get("/uninstall/check")
def uninstall_check(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return update_api.check_uninstall(context.root)


@router.get("/uninstall/status")
def uninstall_status(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return update_api.uninstall_status(context.root)


@router.post("/uninstall/run")
def uninstall_run(params: dict[str, object], context: AppContext = Depends(get_context)):
    try:
        result = update_api.run_uninstall(context.root, str(params.get("mode") or "detach"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            error_payload(str(exc), kind=type(exc).__name__),
            status_code=400 if is_user_input_error(exc) else 500,
        )
    return JSONResponse(result, status_code=200 if result.get("status") == "ok" else 400)

