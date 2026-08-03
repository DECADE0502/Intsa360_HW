from __future__ import annotations

from pathlib import Path

from app.backend.services.refdes_viewer_service import RefdesViewerService
from app.backend.tools.common import USER_INPUT_EXCEPTIONS, _error, _user_error


def _run_refdes_viewer_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    source = str(params.get("drawing") or params.get("pdf") or "").strip()
    if not source:
        return _error("refdes_viewer", "缺少必填输入：位号图文件")
    document = RefdesViewerService(root).open(source)
    return {
        "status": "ok",
        "tool": "refdes_viewer",
        "outputs": [],
        "summary": {
            "页面数": document.page_count,
            "位号数": document.ref_count,
        },
        "document": document.model_dump(),
    }


def run_refdes_viewer(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_refdes_viewer_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("refdes_viewer", exc)
