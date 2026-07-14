from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.backend.api.cadence import cadence_hot_reload_command, redeploy_cadence_loader
from app.backend.api.common import error_payload, is_user_input_error
from app.backend.api.context import AppContext, get_context
from app.backend.capabilities import load_capabilities, set_cadence_menu_visibility
from app.backend.plugins import load_plugins, set_plugin_cadence_menu_visibility


router = APIRouter(tags=["plugins"])


@router.get("/capabilities")
def capabilities(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return load_capabilities(context.root)


@router.get("/plugins")
def plugins(context: AppContext = Depends(get_context)) -> dict[str, object]:
    return load_plugins(context.root)


def _mutation_error(exc: Exception) -> JSONResponse:
    return JSONResponse(
        error_payload(str(exc), kind=type(exc).__name__),
        status_code=400 if is_user_input_error(exc) else 500,
    )


@router.post("/capabilities/{capability_id}/cadence-menu")
def update_capability_menu(
    capability_id: str,
    params: dict[str, object],
    context: AppContext = Depends(get_context),
):
    try:
        show = bool(params.get("show_in_cadence"))
        redeploy = bool(params.get("redeploy", True))
        capability = set_cadence_menu_visibility(context.root, capability_id, show)
        redeployed = redeploy_cadence_loader(context.root)[0] if redeploy else False
    except Exception as exc:  # noqa: BLE001
        return _mutation_error(exc)
    return {"status": "ok", "capability": capability, "redeployed": redeployed}


@router.post("/plugins/{plugin_id}/cadence-menu")
def update_plugin_menu(
    plugin_id: str,
    params: dict[str, object],
    context: AppContext = Depends(get_context),
):
    try:
        show = bool(params.get("show_in_cadence"))
        redeploy = bool(params.get("redeploy", True))
        plugin = set_plugin_cadence_menu_visibility(context.root, plugin_id, show)
        redeployed = redeploy_cadence_loader(context.root)[0] if redeploy else False
    except Exception as exc:  # noqa: BLE001
        return _mutation_error(exc)
    return {"status": "ok", "plugin": plugin, "redeployed": redeployed}


@router.post("/cadence/install")
def install_cadence(context: AppContext = Depends(get_context)):
    try:
        redeployed, installed, output = redeploy_cadence_loader(context.root)
    except Exception as exc:  # noqa: BLE001
        return _mutation_error(exc)
    return {
        "status": "ok",
        "redeployed": redeployed,
        "installed": installed,
        "output": output,
        "message": "Cadence 集成已重新安装",
        "hot_reload_command": cadence_hot_reload_command(installed),
    }

