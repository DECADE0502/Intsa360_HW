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
from app.backend.tools.smt_package import _is_high_risk_package, _package_matches


_SANITY_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


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


def _component_value(component: object, field: str) -> object:
    if isinstance(component, dict):
        return component.get(field, "")
    return getattr(component, field, "")


def _bom_footprint_text(row: dict[str, object]) -> str:
    return " ".join(
        str(row.get(field) or "").strip()
        for field in ("package", "description", "name", "model")
        if str(row.get(field) or "").strip()
    )


def _package_compatible(left: str, right: str) -> tuple[bool, str]:
    normalized_left = "".join(char for char in left.casefold() if char not in "-_")
    normalized_right = "".join(char for char in right.casefold() if char not in "-_")
    if normalized_left and normalized_left == normalized_right:
        return True, "封装规范化后完全一致"
    return _package_matches(left, right)


def _sort_sanity_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        items,
        key=lambda item: (
            _SANITY_SEVERITY_ORDER.get(str(item.get("severity") or "low"), 3),
            natural_key(str(item.get("ref") or "")),
        ),
    )


def _compute_sanity(
    components: list[object],
    bom_rows: list[dict[str, object]],
    netlist_parts: dict[str, str],
) -> dict[str, list[dict[str, object]]]:
    component_by_ref = {
        str(_component_value(component, "ref")).strip().upper(): component
        for component in components
        if str(_component_value(component, "ref")).strip()
    }
    bom_by_ref = {
        str(ref).strip().upper(): row
        for row in bom_rows
        for ref in row.get("refs", [])
        if str(ref).strip()
    }
    netlist_by_ref = {
        str(ref).strip().upper(): str(package or "").strip()
        for ref, package in netlist_parts.items()
        if str(ref).strip()
    }
    xy_refs = set(component_by_ref)
    bom_refs = set(bom_by_ref)
    netlist_refs = set(netlist_by_ref)

    missing_layout = [
        {
            "ref": ref,
            "note": f"{ref} 在 BOM 或网表中存在，但 XY 布局中没有坐标，可能漏放。",
            "severity": "high",
        }
        for ref in (bom_refs | netlist_refs) - xy_refs
    ]
    missing_bom = [
        {
            "ref": ref,
            "note": f"{ref} 在 {'XY 布局' if ref in xy_refs else '网表'}中存在，但处理后 BOM 中没有记录。",
            "severity": "high" if ref in xy_refs else "medium",
        }
        for ref in (xy_refs | netlist_refs) - bom_refs
    ]
    missing_netlist = [
        {
            "ref": ref,
            "note": f"{ref} 在 {'XY 布局' if ref in xy_refs else 'BOM'}中存在，但 pstxprt.dat 中没有记录。",
            "severity": "medium" if ref in xy_refs else "low",
        }
        for ref in (xy_refs | bom_refs) - netlist_refs
    ]

    footprint_conflicts: list[dict[str, object]] = []
    for ref in sorted(xy_refs & (bom_refs | netlist_refs), key=natural_key):
        xy_footprint = str(_component_value(component_by_ref[ref], "footprint") or "").strip()
        netlist_footprint = netlist_by_ref.get(ref, "")
        bom_footprint = _bom_footprint_text(bom_by_ref[ref]) if ref in bom_by_ref else ""
        notes: list[str] = []
        if xy_footprint and netlist_footprint:
            matches, detail = _package_compatible(xy_footprint, netlist_footprint)
            if not matches:
                notes.append(f"XY 与网表封装不一致：{detail}")
        if xy_footprint and bom_footprint:
            matches, detail = _package_compatible(xy_footprint, bom_footprint)
            if not matches:
                notes.append(f"XY 与 BOM 封装信息不一致：{detail}")
        if notes:
            footprint_conflicts.append(
                {
                    "ref": ref,
                    "xy_footprint": xy_footprint,
                    "netlist_footprint": netlist_footprint,
                    "bom_footprint": bom_footprint,
                    "note": "；".join(notes),
                }
            )

    return {
        "missing_layout": _sort_sanity_items(missing_layout),
        "missing_bom": _sort_sanity_items(missing_bom),
        "missing_netlist": _sort_sanity_items(missing_netlist),
        "footprint_conflicts": footprint_conflicts,
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
        netlist_parts = parse_part_file(netlist_folder)
        sanity = _compute_sanity(components, list(bom_by_ref.values()), netlist_parts)

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
