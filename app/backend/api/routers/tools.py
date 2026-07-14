from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.backend import history
from app.backend.api.common import error_payload, is_user_input_error
from app.backend.api.context import AppContext, get_context
from app.backend.capabilities import load_capabilities


router = APIRouter(tags=["tools"])


def _validate_output_dir(context: AppContext, params: dict[str, object]) -> None:
    raw = params.get("output_dir")
    if not raw:
        return
    outputs = context.paths.outputs_dir.resolve()
    requested = Path(str(raw))
    if not requested.is_absolute():
        requested = outputs / requested
    try:
        requested.resolve().relative_to(outputs)
    except ValueError as exc:
        raise ValueError("bad_output_dir: output_dir must be inside data/outputs") from exc


@router.get("/tools")
def list_tools(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return {"tools": context.registry.list_tools()}


@router.get("/platform/status")
def platform_status(context: AppContext = Depends(get_context)) -> dict[str, object]:
    capabilities = load_capabilities(context.root)["capabilities"]
    scripts = [item for item in capabilities if item.get("type") == "cadence_tcl"]
    return {
        "status": "ok",
        "platform": "Insta360硬件提效平台",
        "tools": len(context.registry.list_tools()),
        "cadence_scripts": len(scripts),
        "enableable_scripts": len([item for item in scripts if item.get("can_enable") is True]),
        "enabled_scripts": len([item for item in scripts if item.get("show_in_cadence") is True]),
        "pending_scripts": len([item for item in scripts if item.get("can_enable") is not True]),
        "root": str(context.root),
    }


@router.post("/tools/{tool_id}/run")
def run_tool(
    tool_id: str,
    params: dict[str, object],
    context: AppContext = Depends(get_context),
):
    try:
        _validate_output_dir(context, params)
        result = context.registry.run_tool(tool_id, params)
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        kind = "bad_output_dir" if message.startswith("bad_output_dir") else "tool_error"
        status = 400 if is_user_input_error(exc) else 500
        return JSONResponse(error_payload(message, kind=kind), status_code=status)

    try:
        name = context.registry.get_tool(tool_id).get("name", tool_id)
        history.record(context.root, tool_id, name, params, result)
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse(result, status_code=400 if result.get("status") == "error" else 200)

