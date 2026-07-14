from __future__ import annotations

import io
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.backend.api.common import content_disposition, content_type, error_payload, resolve_output_member, safe_child
from app.backend.api.context import AppContext, get_context
from app.backend.api.uploads import (
    UploadLimitError,
    UploadLimits,
    parse_multipart_files_from_disk,
    stream_request_to_disk,
)


api_router = APIRouter(tags=["files"])
output_router = APIRouter(tags=["files"])


def _timestamp_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


@api_router.post("/upload")
async def upload_files(request: Request, context: AppContext = Depends(get_context)):
    content_type_header = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type_header:
        return JSONResponse({"error": "multipart/form-data required"}, status_code=400)
    limits: UploadLimits = request.app.state.upload_limits
    session = uuid.uuid4().hex[:12]
    target_dir = context.paths.uploads_dir / session
    target_dir.mkdir(parents=True, exist_ok=True)
    body_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=target_dir) as temporary:
            body_path = Path(temporary.name)
        copied = await stream_request_to_disk(request, body_path, request_limit=limits.request_bytes)
        length_header = request.headers.get("content-length", "").strip()
        if length_header and copied != int(length_header):
            raise ValueError("upload truncated")
        files = parse_multipart_files_from_disk(
            body_path,
            content_type_header,
            target_dir,
            file_limit=limits.file_bytes,
        )
        return {"status": "ok", "session": session, "files": files, "folder": str(target_dir)}
    except UploadLimitError as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        return JSONResponse(error_payload(str(exc), kind=exc.kind), status_code=413)
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(target_dir, ignore_errors=True)
        message = str(exc) or type(exc).__name__
        return JSONResponse(error_payload(message, kind=type(exc).__name__), status_code=400)
    finally:
        if body_path is not None:
            body_path.unlink(missing_ok=True)


@api_router.post("/package")
def package_outputs(params: dict[str, object], context: AppContext = Depends(get_context)):
    name = str(params.get("name") or "BOM导出").strip() or "BOM导出"
    members: list[Path] = []
    seen: set[str] = set()
    try:
        for requested in params.get("files") or []:
            target = resolve_output_member(context.paths.outputs_dir, requested)
            if target.is_file() and str(target) not in seen:
                seen.add(str(target))
                members.append(target)
    except ValueError as exc:
        return JSONResponse(error_payload(str(exc), kind="bad_package_path"), status_code=400)
    if not members:
        return JSONResponse({"error": "no files to package"}, status_code=404)

    buffer = io.BytesIO()
    outputs_dir = context.paths.outputs_dir.resolve()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for member in members:
            archive.write(member, arcname=member.relative_to(outputs_dir).as_posix())
    stamp = _timestamp_for_filename()
    filename = f"{name}_{stamp}.zip"
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@output_router.get("/outputs/{requested:path}", include_in_schema=False)
def download_output(requested: str, context: AppContext = Depends(get_context)):
    target = safe_child(context.paths.outputs_dir, requested)
    if target is None or not target.is_file():
        return JSONResponse({"error": "output not found"}, status_code=404)
    return FileResponse(
        target,
        media_type=content_type(target),
        filename=target.name,
        headers={"Cache-Control": "no-store"},
    )
