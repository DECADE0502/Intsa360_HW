from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.backend.contracts.smt_view import SmtViewBoardRequest
from app.backend.parsers.refs import natural_key
from app.backend.paths import AppPaths
from app.backend.smt_view.board import BoardGeometry, build_board_geometry
from app.backend.smt_view.discovery import discover_smt_directory
from app.backend.smt_view.drawing import DrawingRenderer, PdfDrawing, PdfDrawingPage, crop_for_xy, open_pdf_drawing
from app.backend.smt_view.registration import AffineRegistration, RegistrationAnchor, fit_affine_registration
from app.backend.smt_view.state import load_bom_state
from app.backend.tools.smt_package import run_smt_package_check


SCHEMA_VERSION = 2


def _fingerprint(paths: list[Path], label: str) -> str:
    digest = hashlib.sha256(f"smt-view:{SCHEMA_VERSION}:{label}".encode("utf-8"))
    for path in paths:
        digest.update(path.name.encode("utf-8", errors="replace"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()[:24]


def _anchors_for_page(
    page: PdfDrawingPage,
    components: list[object],
) -> list[RegistrationAnchor]:
    pdf_by_ref: dict[str, object] = {}
    for item in page.refs:
        pdf_by_ref.setdefault(item.ref, item)
    anchors: list[RegistrationAnchor] = []
    for component in components:
        ref = str(getattr(component, "ref"))
        pdf_ref = pdf_by_ref.get(ref)
        if pdf_ref is None:
            continue
        anchors.append(
            RegistrationAnchor(
                ref=ref,
                xy_x=float(getattr(component, "x_mm")),
                xy_y=float(getattr(component, "y_mm")),
                pdf_x=float(getattr(pdf_ref, "x")),
                pdf_y=float(getattr(pdf_ref, "y")),
            )
        )
    return anchors


def _match_pages(
    drawing: PdfDrawing,
    geometry: BoardGeometry,
) -> dict[str, tuple[PdfDrawingPage, AffineRegistration]]:
    by_side = {
        side: [component for component in geometry.components if component.side == side]
        for side in ("top", "bottom")
    }
    candidates: dict[str, list[tuple[PdfDrawingPage, AffineRegistration]]] = {"top": [], "bottom": []}
    failures: list[str] = []
    for side, components in by_side.items():
        if not components:
            continue
        for page in drawing.pages:
            anchors = _anchors_for_page(page, components)
            if len(anchors) < 20:
                continue
            try:
                registration = fit_affine_registration(anchors)
            except ValueError as exc:
                failures.append(f"第 {page.page_number} 页/{side}: {exc}")
                continue
            candidates[side].append((page, registration))

    top_candidates = candidates["top"] or [(None, None)]
    bottom_candidates = candidates["bottom"] or [(None, None)]
    combinations: list[tuple[tuple[int, int, float], object, object]] = []
    for top in top_candidates:
        for bottom in bottom_candidates:
            top_page, top_registration = top
            bottom_page, bottom_registration = bottom
            if top_page is not None and bottom_page is not None and top_page.page_number == bottom_page.page_number:
                continue
            registrations = [value for value in (top_registration, bottom_registration) if value is not None]
            score = (
                sum(bool(value.trusted) for value in registrations),
                sum(int(value.anchor_count) for value in registrations),
                -sum(float(value.median_mm) for value in registrations),
            )
            combinations.append((score, top, bottom))
    if not combinations:
        raise ValueError("SMD/REF PDF 页面无法与 XY 正反面自动配对。")
    _, selected_top, selected_bottom = max(combinations, key=lambda item: item[0])
    selected = {"top": selected_top, "bottom": selected_bottom}

    result: dict[str, tuple[PdfDrawingPage, AffineRegistration]] = {}
    for side, components in by_side.items():
        if not components:
            continue
        page, registration = selected[side]
        if page is None or registration is None:
            detail = "；".join(failures[:3])
            raise ValueError(f"{side} 面没有找到至少 20 个共有位号，无法可靠配准。{detail}")
        if not registration.trusted:
            raise ValueError(
                f"{side} 面位号图配准不可信：{registration.anchor_count} 个锚点，"
                f"中位残差 {registration.median_mm:.3f} mm，超过 0.500 mm 阈值。"
            )
        result[side] = (page, registration)
    return result


def _registration_payload(registration: AffineRegistration) -> dict[str, object]:
    return {
        "anchor_count": registration.anchor_count,
        "rejected_count": registration.rejected_count,
        "median_mm": round(registration.median_mm, 4),
        "p90_mm": round(registration.p90_mm, 4),
        "max_mm": round(registration.max_mm, 4),
        "trusted": registration.trusted,
    }


_PACKAGE_PRIORITY = {
    "同料多封装": 0,
    "BOM 缺位号": 1,
    "需要确认": 2,
    "BOM 多余位号": 3,
    "近似通过": 4,
    "通过": 5,
    "高风险封装": 6,
    "NC 未贴跳过": 7,
    "非贴片对象跳过": 8,
}


def _package_review_by_ref(result: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not result:
        return {}
    review = result.get("smt_package_review")
    if not isinstance(review, dict):
        return {}
    output: dict[str, dict[str, object]] = {}
    for raw in review.get("items") or []:
        if not isinstance(raw, dict):
            continue
        refs = raw.get("refs") or str(raw.get("ref") or "").split(",")
        for value in refs:
            ref = str(value or "").strip().upper()
            if not ref:
                continue
            current = output.get(ref)
            if current is None or _PACKAGE_PRIORITY.get(str(raw.get("status")), 99) < _PACKAGE_PRIORITY.get(str(current.get("status")), 99):
                output[ref] = raw
    return output


class SmtViewService:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.boards_dir = paths.smt_view_boards_dir
        self.boards_dir.mkdir(parents=True, exist_ok=True)
        self.renderer = DrawingRenderer(paths.smt_view_drawings_dir)

    def _resolve_data_path(self, value: str, *, directory: bool = False) -> Path:
        path = Path(value).expanduser().resolve()
        try:
            path.relative_to(self.paths.data_dir.resolve())
        except ValueError as exc:
            raise ValueError("只能使用通过平台上传或历史记录选择的文件。") from exc
        expected = path.is_dir() if directory else path.is_file()
        if not expected:
            kind = "目录" if directory else "文件"
            raise ValueError(f"所选{kind}不存在或已被移除：{path.name}")
        return path

    def create(self, request: SmtViewBoardRequest) -> dict[str, object]:
        source_dir = self._resolve_data_path(request.source_dir, directory=True)
        bom_path = self._resolve_data_path(request.bom_path)
        semantic_path = self._resolve_data_path(request.semantic_manifest_path) if request.semantic_manifest_path else None
        netlist_dir = self._resolve_data_path(request.netlist_dir, directory=True) if request.netlist_dir else None

        discovered = discover_smt_directory(source_dir)
        if discovered.reference_pdf is None:
            raise ValueError("所选 SMT 资料目录中没有识别到 SMD/REF 位号图 PDF。")
        identity_files = [discovered.xy_file, discovered.reference_pdf, bom_path]
        if semantic_path is not None:
            identity_files.append(semantic_path)
        if netlist_dir is not None:
            identity_files.extend(sorted(path for path in netlist_dir.rglob("*.dat") if path.is_file()))
        board_id = _fingerprint(identity_files, request.label or source_dir.name)
        cached = self.boards_dir / f"{board_id}.json"
        if cached.is_file():
            return self.get(board_id)

        geometry = build_board_geometry(discovered.xy_file)
        state = load_bom_state(bom_path)
        drawing = open_pdf_drawing(discovered.reference_pdf)
        matched = _match_pages(drawing, geometry)

        drawing_payload: dict[str, dict[str, object]] = {}
        drawing_internal: dict[str, str] = {}
        side_resources: dict[str, tuple[PdfDrawingPage, AffineRegistration, tuple[float, float, float, float]]] = {}
        for side, (page, registration) in matched.items():
            side_components = [component for component in geometry.components if component.side == side]
            crop = crop_for_xy(
                registration,
                [(component.x_mm, component.y_mm) for component in side_components],
                page_width=page.width,
                page_height=page.height,
            )
            rendered = self.renderer.render(drawing, page_number=page.page_number, crop=crop)
            drawing_payload[side] = {
                "page_number": page.page_number,
                "image_url": f"/api/v1/smt-view/boards/{board_id}/drawing/{side}",
                "pixel_width": rendered.pixel_width,
                "pixel_height": rendered.pixel_height,
                "registration": _registration_payload(registration),
            }
            drawing_internal[side] = rendered.cache_key
            side_resources[side] = (page, registration, crop)

        package_result: dict[str, object] | None = None
        if netlist_dir is not None:
            params: dict[str, object] = {
                "netlist": str(netlist_dir),
                "bom": str(bom_path),
                "output_dir": str(self.paths.outputs_dir / "smt"),
            }
            if semantic_path is not None:
                params["semantic_manifest"] = str(semantic_path)
            package_result = run_smt_package_check(self.paths.root, params)
            if package_result.get("status") != "ok":
                raise ValueError(str(package_result.get("error") or "封装一致性检查失败。"))
        package_by_ref = _package_review_by_ref(package_result)

        xy_refs = {component.ref for component in geometry.components}
        bom_refs = set(state.installed)
        placements: list[dict[str, object]] = []
        for component in geometry.components:
            material = state.installed.get(component.ref) or {}
            status = "placed" if component.ref in bom_refs else "nc"
            page, registration, crop = side_resources[component.side]
            side_drawing = drawing_payload[component.side]
            left, bottom, right, top = crop
            pdf_x, pdf_y = registration.transform(component.x_mm, component.y_mm)
            drawing_x = (pdf_x - left) / (right - left) * int(side_drawing["pixel_width"])
            drawing_y = (top - pdf_y) / (top - bottom) * int(side_drawing["pixel_height"])
            package = package_by_ref.get(component.ref) or {}
            package_status = str(package.get("status") or "")
            placements.append(
                {
                    "ref": component.ref,
                    "x_mm": round(component.x_mm, 6),
                    "y_mm": round(component.y_mm, 6),
                    "drawing_x": round(drawing_x, 3),
                    "drawing_y": round(drawing_y, 3),
                    "rotation": component.rotation,
                    "side": component.side,
                    "footprint": component.footprint,
                    "status": status,
                    "material_code": str(material.get("material_code") or ""),
                    "name": str(material.get("name") or ""),
                    "model": str(material.get("model") or ""),
                    "description": str(material.get("description") or ""),
                    "grade": str(material.get("grade") or ""),
                    "package": str(material.get("package") or ""),
                    "reason": "成品 BOM 中存在" if status == "placed" else "XY 坐标存在、成品 BOM 中不存在",
                    "package_status": package_status,
                    "package_kind": str(package.get("kind") or ""),
                    "net_package": str(package.get("net_package") or ""),
                    "package_note": str(package.get("note") or ""),
                }
            )

        bom_only = []
        for ref in sorted(bom_refs - xy_refs, key=natural_key):
            material = state.installed[ref]
            bom_only.append(
                {
                    "ref": ref,
                    "status": "bom_only",
                    "material_code": str(material.get("material_code") or ""),
                    "name": str(material.get("name") or ""),
                    "model": str(material.get("model") or ""),
                    "description": str(material.get("description") or ""),
                    "reason": "成品 BOM 中存在，但 XY 坐标文件中没有该位号",
                }
            )

        outputs = [str(value) for value in (package_result or {}).get("outputs", [])]
        summary = {
            "total": len(placements),
            "top": sum(item["side"] == "top" for item in placements),
            "bottom": sum(item["side"] == "bottom" for item in placements),
            "placed": sum(item["status"] == "placed" for item in placements),
            "nc": sum(item["status"] == "nc" for item in placements),
            "bom_only": len(bom_only),
            "package_checked": int(package_result is not None),
            "package_issues": sum(
                bool(item["package_status"]) and item["package_status"] not in {"通过", "近似通过", "NC 未贴跳过", "非贴片对象跳过"}
                for item in placements
            ),
        }
        payload: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "board_id": board_id,
            "label": (request.label or source_dir.name).strip() or source_dir.name,
            "xy_file_name": discovered.xy_file.relative_to(source_dir).as_posix(),
            "xy_version": geometry.units.version,
            "xy_units": geometry.units.units,
            "placements": placements,
            "bom_only": bom_only,
            "summary": summary,
            "drawings": drawing_payload,
            "reference_drawing_name": discovered.reference_pdf.name,
            "reference_drawing_url": f"/api/v1/smt-view/boards/{board_id}/reference-drawing",
            "package_report_outputs": outputs,
            "notices": list(state.notices),
            "_reference_drawing_path": str(discovered.reference_pdf),
            "_drawing_cache_keys": drawing_internal,
        }
        self._write(board_id, payload)
        return self._public(payload)

    def _write(self, board_id: str, payload: dict[str, object]) -> None:
        destination = self.boards_dir / f"{board_id}.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(destination)

    def _load(self, board_id: str) -> dict[str, object]:
        if not board_id or any(character not in "0123456789abcdef" for character in board_id.lower()):
            raise KeyError("贴片位号视图不存在。")
        path = self.boards_dir / f"{board_id}.json"
        if not path.is_file():
            raise KeyError("贴片位号视图不存在或已被清理。")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _public(payload: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in payload.items() if not key.startswith("_")}

    def get(self, board_id: str) -> dict[str, object]:
        return self._public(self._load(board_id))

    def reference_drawing(self, board_id: str) -> Path:
        payload = self._load(board_id)
        path = Path(str(payload.get("_reference_drawing_path") or ""))
        if not path.is_file():
            raise KeyError("该资料目录没有可打开的原始位号图。")
        try:
            path.resolve().relative_to(self.paths.data_dir.resolve())
        except ValueError as exc:
            raise KeyError("原始位号图路径无效。") from exc
        return path

    def drawing_image(self, board_id: str, side: str) -> Path:
        payload = self._load(board_id)
        keys = payload.get("_drawing_cache_keys")
        if side not in {"top", "bottom"} or not isinstance(keys, dict) or side not in keys:
            raise KeyError("当前面没有可用的配准位号图。")
        return self.renderer.resolve(str(keys[side]))
