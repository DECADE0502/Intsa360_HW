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


api_router = APIRouter(tags=["files"])
output_router = APIRouter(tags=["files"])


def _timestamp_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _multipart_boundary(content_type_header: str) -> bytes:
    marker = "boundary="
    if marker not in content_type_header:
        raise ValueError("missing multipart boundary")
    boundary = content_type_header.split(marker, 1)[1].split(";", 1)[0].strip().strip('"')
    if not boundary:
        raise ValueError("missing multipart boundary")
    return ("--" + boundary).encode("utf-8")


def _parse_multipart_files_from_disk(
    body_path: Path,
    content_type_header: str,
    target_dir: Path,
) -> list[dict[str, str]]:
    boundary = _multipart_boundary(content_type_header)
    final_boundary = boundary + b"--"
    files: list[dict[str, str]] = []
    with body_path.open("rb") as handle:
        line = handle.readline()
        while line and line.rstrip(b"\r\n") != boundary:
            line = handle.readline()
        while line:
            headers: list[bytes] = []
            while True:
                line = handle.readline()
                if not line:
                    return files
                if line in (b"\r\n", b"\n"):
                    break
                headers.append(line)
            header_text = b"".join(headers).decode("utf-8", errors="ignore")
            filename = ""
            marker = 'filename="'
            if marker in header_text:
                filename = Path(header_text.split(marker, 1)[1].split('"', 1)[0]).name
            target = target_dir / filename if filename else None
            pending: bytes | None = None
            output = target.open("wb") if target else None
            try:
                while True:
                    line = handle.readline()
                    if not line:
                        if pending and output:
                            output.write(pending)
                        return files
                    stripped = line.rstrip(b"\r\n")
                    if stripped in (boundary, final_boundary):
                        if pending and output:
                            if pending.endswith(b"\r\n"):
                                pending = pending[:-2]
                            elif pending.endswith(b"\n"):
                                pending = pending[:-1]
                            output.write(pending)
                        if target:
                            files.append({"name": filename, "path": str(target)})
                        if stripped == final_boundary:
                            return files
                        break
                    if pending and output:
                        output.write(pending)
                    pending = line
            finally:
                if output:
                    output.close()


async def _stream_request_to_disk(request: Request, target: Path) -> int:
    copied = 0
    with target.open("wb") as handle:
        async for chunk in request.stream():
            if chunk:
                handle.write(chunk)
                copied += len(chunk)
    return copied


@api_router.post("/upload")
async def upload_files(request: Request, context: AppContext = Depends(get_context)):
    content_type_header = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type_header:
        return JSONResponse({"error": "multipart/form-data required"}, status_code=400)
    session = uuid.uuid4().hex[:12]
    target_dir = context.paths.uploads_dir / session
    target_dir.mkdir(parents=True, exist_ok=True)
    body_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=target_dir) as temporary:
            body_path = Path(temporary.name)
        copied = await _stream_request_to_disk(request, body_path)
        length_header = request.headers.get("content-length", "").strip()
        if length_header and copied != int(length_header):
            raise ValueError("upload truncated")
        files = _parse_multipart_files_from_disk(body_path, content_type_header, target_dir)
        body_path.unlink(missing_ok=True)
        return {"status": "ok", "session": session, "files": files, "folder": str(target_dir)}
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(target_dir, ignore_errors=True)
        message = str(exc) or type(exc).__name__
        return JSONResponse(error_payload(message, kind=type(exc).__name__), status_code=400)


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
