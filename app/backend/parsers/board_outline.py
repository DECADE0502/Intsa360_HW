from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence


Point = tuple[float, float]
BBox = tuple[float, float, float, float]
_PREFERRED_LAYERS = ("OUTLINE", "BOARD_OUTLINE", "BORD", "BOARD")
_GERBER_EXTENSIONS = (".art", ".gbr", ".ger")


@dataclass(frozen=True)
class BoardOutline:
    rings: list[list[Point]]
    bbox: BBox
    source: Literal["dxf", "gerber_bbox", "explicit"]


def _rectangle(bbox: BBox) -> list[Point]:
    xmin, ymin, xmax, ymax = bbox
    return [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]


def _validate_bbox(value: Sequence[float]) -> BBox:
    if len(value) != 4:
        raise ValueError("outline_bbox_mm 必须包含 xmin、ymin、xmax、ymax")
    bbox = tuple(float(item) for item in value)
    xmin, ymin, xmax, ymax = bbox
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("outline_bbox_mm 范围无效")
    return bbox  # type: ignore[return-value]


def _bbox(rings: list[list[Point]]) -> BBox:
    points = [point for ring in rings for point in ring]
    if not points:
        raise ValueError("板轮廓没有有效顶点")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _area(ring: list[Point]) -> float:
    return abs(
        sum(
            ring[index][0] * ring[(index + 1) % len(ring)][1]
            - ring[(index + 1) % len(ring)][0] * ring[index][1]
            for index in range(len(ring))
        )
        / 2.0
    )


def _dedupe_points(points: list[Point], tolerance: float = 1e-6) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if result and abs(result[-1][0] - point[0]) <= tolerance and abs(result[-1][1] - point[1]) <= tolerance:
            continue
        result.append(point)
    if len(result) > 1 and abs(result[0][0] - result[-1][0]) <= tolerance and abs(result[0][1] - result[-1][1]) <= tolerance:
        result.pop()
    return result


def _dxf_scale(document: object) -> float:
    units = getattr(document, "header", {}).get("$INSUNITS")
    return 25.4 if units == 1 else 1.0


def _flatten_entity(entity: object, scale: float, reverse: bool = False) -> list[Point]:
    from ezdxf.path import make_path

    path = make_path(entity)
    points = [(float(vertex.x) * scale, float(vertex.y) * scale) for vertex in path.flattening(distance=0.1 / scale)]
    if reverse:
        points.reverse()
    return _dedupe_points(points)


def _closed_entity_rings(entities: list[object], scale: float) -> list[list[Point]]:
    rings: list[list[Point]] = []
    for entity in entities:
        entity_type = entity.dxftype()
        closed = entity_type in {"CIRCLE", "ELLIPSE"} or bool(getattr(entity, "closed", False))
        if not closed:
            continue
        try:
            ring = _flatten_entity(entity, scale)
        except (TypeError, ValueError):
            continue
        if len(ring) >= 3 and _area(ring) > 1e-6:
            rings.append(ring)
    return rings


def _stitched_rings(entities: list[object], scale: float) -> list[list[Point]]:
    from ezdxf import edgeminer, edgesmith

    supported = [
        entity
        for entity in entities
        if entity.dxftype() in {"LINE", "ARC", "ELLIPSE", "SPLINE", "LWPOLYLINE", "POLYLINE"}
    ]
    edges = list(edgesmith.edges_from_entities(supported, gap_tol=1e-5 / scale))
    if not edges:
        return []
    try:
        loops = edgeminer.find_all_loops(edgeminer.Deposit(edges, gap_tol=1e-5 / scale), timeout=8.0)
    except edgeminer.TimeoutError:
        return []
    rings: list[list[Point]] = []
    for loop in loops:
        points: list[Point] = []
        for edge in loop:
            try:
                segment = _flatten_entity(edge.payload, scale, reverse=edge.is_reverse)
            except (TypeError, ValueError):
                segment = [(float(edge.start.x) * scale, float(edge.start.y) * scale), (float(edge.end.x) * scale, float(edge.end.y) * scale)]
            if points and segment:
                segment = segment[1:]
            points.extend(segment)
        ring = _dedupe_points(points)
        if len(ring) >= 3 and _area(ring) > 1e-6:
            rings.append(ring)
    return rings


def _layer_rings(modelspace: object, layer: str, scale: float) -> list[list[Point]]:
    entities = [entity for entity in modelspace if str(entity.dxf.layer).casefold() == layer.casefold()]
    rings = _closed_entity_rings(entities, scale)
    if not rings:
        rings = _stitched_rings(entities, scale)
    return rings


def _read_dxf(path: Path, requested_layer: str | None) -> BoardOutline:
    import ezdxf

    document = ezdxf.readfile(path)
    modelspace = document.modelspace()
    scale = _dxf_scale(document)
    available_layers = {str(entity.dxf.layer) for entity in modelspace}
    if requested_layer:
        candidates = [requested_layer]
    else:
        candidates = [
            preferred
            for preferred in _PREFERRED_LAYERS
            if any(layer.casefold() == preferred.casefold() for layer in available_layers)
        ]
        candidates.extend(sorted(layer for layer in available_layers if layer not in candidates))

    best: list[list[Point]] = []
    best_area = 0.0
    for layer in candidates:
        rings = _layer_rings(modelspace, layer, scale)
        if not rings:
            continue
        largest = max(_area(ring) for ring in rings)
        if requested_layer or layer.upper() in _PREFERRED_LAYERS:
            best = rings
            break
        if largest > best_area:
            best, best_area = rings, largest
    if not best:
        raise ValueError("未在 DXF 中定位板轮廓层，请指定 outline_dxf_layer")
    best.sort(key=_area, reverse=True)
    return BoardOutline(rings=best, bbox=_bbox(best), source="dxf")


def _gerber_coordinate(value: str, decimal_places: int, scale: float) -> float:
    return int(value) / (10**decimal_places) * scale


def _read_gerber_bbox(path: Path) -> BoardOutline:
    decimal_places = 4
    scale = 1.0
    current_x = 0.0
    current_y = 0.0
    points: list[Point] = []
    format_re = re.compile(r"%FSLA?X\d(\d)Y\d(\d)\*%", re.IGNORECASE)
    coordinate_re = re.compile(r"(?:X(?P<x>[+-]?\d+))?(?:Y(?P<y>[+-]?\d+))?D0?[123]\*", re.IGNORECASE)
    for raw_line in path.read_text(encoding="ascii", errors="ignore").splitlines():
        line = raw_line.strip()
        format_match = format_re.fullmatch(line)
        if format_match:
            x_decimals, y_decimals = int(format_match.group(1)), int(format_match.group(2))
            if x_decimals != y_decimals:
                raise ValueError("Gerber X/Y 小数位声明不一致")
            decimal_places = x_decimals
            continue
        if line.upper() == "%MOIN*%":
            scale = 25.4
            continue
        if line.upper() == "%MOMM*%":
            scale = 1.0
            continue
        match = coordinate_re.search(line)
        if not match or (match.group("x") is None and match.group("y") is None):
            continue
        if match.group("x") is not None:
            current_x = _gerber_coordinate(match.group("x"), decimal_places, scale)
        if match.group("y") is not None:
            current_y = _gerber_coordinate(match.group("y"), decimal_places, scale)
        points.append((current_x, current_y))
    if len(points) < 2:
        raise ValueError("Gerber 未包含可用于轮廓包围盒的坐标")
    bbox = _bbox([points])
    if bbox[0] == bbox[2] or bbox[1] == bbox[3]:
        raise ValueError("Gerber 轮廓包围盒无效")
    return BoardOutline(rings=[_rectangle(bbox)], bbox=bbox, source="gerber_bbox")


def resolve_board_outline(
    smt_folder: Path,
    *,
    outline_bbox_mm: Sequence[float] | None = None,
    outline_dxf_layer: str | None = None,
) -> BoardOutline:
    if outline_bbox_mm is not None:
        bbox = _validate_bbox(outline_bbox_mm)
        return BoardOutline(rings=[_rectangle(bbox)], bbox=bbox, source="explicit")

    folder = Path(smt_folder)
    if not folder.is_dir():
        raise ValueError("SMT 文件夹未找到 DXF 或 Gerber，且未指定 outline_bbox_mm")
    dxf_files = sorted(folder.glob("*.dxf"), key=lambda path: (path.stat().st_size, path.name.casefold()))
    gerber_files = sorted(
        (path for path in folder.iterdir() if path.is_file() and path.suffix.casefold() in _GERBER_EXTENSIONS),
        key=lambda path: path.name.casefold(),
    )
    if not dxf_files and not gerber_files:
        raise ValueError("SMT 文件夹未找到 DXF 或 Gerber，且未指定 outline_bbox_mm")

    dxf_error: ValueError | None = None
    if dxf_files:
        try:
            import ezdxf  # noqa: F401
        except ImportError:
            pass
        else:
            for dxf_path in dxf_files:
                try:
                    return _read_dxf(dxf_path, outline_dxf_layer)
                except (OSError, ValueError) as exc:
                    dxf_error = ValueError(str(exc))
            if outline_dxf_layer or not gerber_files:
                raise dxf_error or ValueError("未在 DXF 中定位板轮廓层，请指定 outline_dxf_layer")

    for gerber_path in gerber_files:
        try:
            return _read_gerber_bbox(gerber_path)
        except (OSError, ValueError):
            continue
    if dxf_error:
        raise dxf_error
    raise ValueError("SMT 文件夹未找到 DXF 或 Gerber，且未指定 outline_bbox_mm")
