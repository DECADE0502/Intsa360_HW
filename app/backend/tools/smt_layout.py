from __future__ import annotations

from pathlib import Path

from app.backend.parsers.board_outline import resolve_board_outline
from app.backend.parsers.cadence_pst import parse_net_file, parse_part_file
from app.backend.parsers.refs import natural_key
from app.backend.parsers.xy import parse_xy_file
from app.backend.tools import bom_process
from app.backend.tools.common import (
    USER_INPUT_EXCEPTIONS,
    _read_bom_rows,
    _required_file,
    _required_folder,
    _user_error,
)
from app.backend.tools.smt_package import _is_high_risk_package


def _find_xy_file(folder: Path) -> Path:
    for path in folder.iterdir():
        if path.is_file() and path.name.casefold() == "xy.txt":
            return path
    raise ValueError("SMT 文件夹缺少 XY.txt")


def _find_nc_summary(processed_bom: Path) -> Path | None:
    candidates = [
        path
        for path in processed_bom.parent.glob("*.xlsx")
        if path != processed_bom and "nc未贴" in path.name.casefold()
    ]
    return sorted(candidates, key=lambda path: path.name.casefold())[0] if candidates else None


def _bom_by_ref(processed_bom: Path) -> tuple[dict[str, dict[str, object]], set[str]]:
    rows = _read_bom_rows(processed_bom)
    by_ref = {
        str(ref).upper(): row
        for row in rows
        for ref in row.get("refs", [])
        if str(ref).strip()
    }
    nc_refs: set[str] = set()
    nc_summary = _find_nc_summary(processed_bom)
    if nc_summary:
        parsed = bom_process.parse_source(nc_summary)
        for row in parsed.raw_rows:
            nc_refs.update(ref.upper() for ref in bom_process.split_refs(row.get("reference")))
    return by_ref, nc_refs


def _component_payload(component: object, bom_row: dict[str, object] | None, nc_refs: set[str]) -> dict[str, object]:
    ref = str(component.ref)
    row = bom_row or {}
    status = "nc" if ref.upper() in nc_refs else ("installed" if bom_row else "missing_bom")
    description = str(row.get("description") or "")
    model = str(row.get("model") or "")
    footprint = str(component.footprint)
    return {
        "ref": ref,
        "x_mm": float(component.x_mm),
        "y_mm": float(component.y_mm),
        "rotation": int(component.rotation),
        "side": str(component.side),
        "footprint": footprint,
        "part_number": str(row.get("part_number") or ""),
        "description": description,
        "model": model,
        "grade": str(row.get("grade") or ""),
        "status": status,
        "high_risk": _is_high_risk_package(footprint, description, model),
    }


def _run_smt_layout_impl(root: Path, params: dict[str, object]) -> dict[str, object]:
    smt_folder, error = _required_folder(params, "smt_folder", "SMT 资料文件夹")
    if error:
        raise ValueError(error)
    processed_bom, error = _required_file(params, "processed_bom", "处理后 BOM")
    if error:
        raise ValueError(error)
    assert smt_folder is not None and processed_bom is not None

    netlist_folder: Path | None = None
    if str(params.get("netlist_folder") or "").strip() or isinstance(params.get("netlist_folder"), list):
        netlist_folder, error = _required_folder(params, "netlist_folder", "Cadence 网表文件夹")
        if error:
            raise ValueError(error)

    _, parsed_components = parse_xy_file(_find_xy_file(smt_folder))
    outline_bbox = params.get("outline_bbox_mm")
    if outline_bbox is not None and not isinstance(outline_bbox, (list, tuple)):
        raise ValueError("outline_bbox_mm 必须是四个毫米坐标")
    outline = resolve_board_outline(
        smt_folder,
        outline_bbox_mm=outline_bbox,
        outline_dxf_layer=str(params.get("outline_dxf_layer") or "").strip() or None,
    )
    bom_by_ref, nc_refs = _bom_by_ref(processed_bom)
    components = [
        _component_payload(component, bom_by_ref.get(component.ref.upper()), nc_refs)
        for component in parsed_components
    ]
    components.sort(key=lambda item: natural_key(str(item["ref"])))

    if netlist_folder is None:
        sanity: dict[str, object] = {"status": "skipped_no_netlist"}
    else:
        parse_net_file(netlist_folder)
        parse_part_file(netlist_folder)
        sanity = {
            "missing_layout": [],
            "missing_bom": [],
            "missing_netlist": [],
            "footprint_conflicts": [],
        }

    fai_headers = ["序号", "位号", "面", "X(mm)", "Y(mm)", "角度", "封装", "物料编码", "型号", "描述", "状态"]
    fai_rows = [
        [
            index,
            item["ref"],
            item["side"],
            item["x_mm"],
            item["y_mm"],
            item["rotation"],
            item["footprint"],
            item["part_number"],
            item["model"],
            item["description"],
            item["status"],
        ]
        for index, item in enumerate(components, start=1)
    ]
    return {
        "status": "ok",
        "tool": "smt_layout",
        "outputs": [],
        "board": {
            "outline_rings": outline.rings,
            "bbox_mm": outline.bbox,
            "source": outline.source,
        },
        "components": components,
        "nc_summary": {"total": len(nc_refs), "refs": sorted(nc_refs, key=natural_key)},
        "sanity": sanity,
        "fai_table": {"headers": fai_headers, "rows": fai_rows},
        "summary": {
            "total_components": len(components),
            "top_count": sum(item["side"] == "top" for item in components),
            "bottom_count": sum(item["side"] == "bottom" for item in components),
            "nc_count": sum(item["status"] == "nc" for item in components),
            "high_risk_count": sum(bool(item["high_risk"]) for item in components),
        },
    }


def run_smt_layout(root: Path, params: dict[str, object]) -> dict[str, object]:
    try:
        return _run_smt_layout_impl(root, params)
    except USER_INPUT_EXCEPTIONS as exc:
        return _user_error("smt_layout", exc)
