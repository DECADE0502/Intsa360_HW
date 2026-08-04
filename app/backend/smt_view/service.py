from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.backend.contracts.smt_view import SmtViewBoardRequest
from app.backend.parsers.refs import natural_key
from app.backend.paths import AppPaths
from app.backend.smt_view.board import build_board_geometry
from app.backend.smt_view.discovery import discover_smt_directory
from app.backend.smt_view.state import baseline_by_ref, load_bom_state


def _fingerprint(paths: list[Path], label: str) -> str:
    digest = hashlib.sha256(label.encode("utf-8"))
    for path in paths:
        digest.update(path.name.encode("utf-8", errors="replace"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()[:24]


class SmtViewService:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.boards_dir = paths.smt_view_boards_dir
        self.boards_dir.mkdir(parents=True, exist_ok=True)

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
        optional_values = (
            request.nc_path,
            request.semantic_manifest_path,
            request.decision_manifest_path,
            request.baseline_bom_path,
        )
        optional_paths = [self._resolve_data_path(value) if value else None for value in optional_values]
        nc_path, semantic_path, decision_path, baseline_path = optional_paths

        discovered = discover_smt_directory(source_dir)
        geometry = build_board_geometry(discovered.xy_file)
        state = load_bom_state(
            bom_path,
            semantic_manifest_path=semantic_path,
            decision_manifest_path=decision_path,
            nc_path=nc_path,
        )
        baseline = baseline_by_ref(baseline_path)
        all_state_refs = set(state.installed) | set(state.excluded)
        xy_refs = {component.ref for component in geometry.components}
        notices = list(state.notices)

        placements: list[dict[str, object]] = []
        for component in geometry.components:
            material = state.excluded.get(component.ref) or state.installed.get(component.ref) or {}
            if component.ref in state.excluded:
                status = str(material.get("status") or "nc")
            elif component.ref in state.installed:
                status = "placed"
            else:
                status = "xy_only"
            current_code = str(material.get("material_code") or "")
            baseline_code = str(baseline.get(component.ref, {}).get("material_code") or "")
            version_change = "none"
            if baseline_path is not None:
                if component.ref not in baseline and component.ref in all_state_refs:
                    version_change = "added"
                elif component.ref in baseline and component.ref not in all_state_refs:
                    version_change = "removed"
                elif baseline_code != current_code and component.ref in all_state_refs:
                    version_change = "replaced"
            placements.append(
                {
                    "ref": component.ref,
                    "x_mm": round(component.x_mm, 6),
                    "y_mm": round(component.y_mm, 6),
                    "rotation": component.rotation,
                    "side": component.side,
                    "footprint": component.footprint,
                    "status": status,
                    "material_code": current_code,
                    "name": str(material.get("name") or ""),
                    "model": str(material.get("model") or ""),
                    "description": str(material.get("description") or ""),
                    "grade": str(material.get("grade") or ""),
                    "package": str(material.get("package") or ""),
                    "reason": str(material.get("reason") or ""),
                    "decision_kind": str(material.get("decision_kind") or ""),
                    "version_change": version_change,
                    "baseline_material_code": baseline_code,
                }
            )

        bom_only: list[dict[str, object]] = []
        for ref in sorted(all_state_refs - xy_refs, key=natural_key):
            material = state.excluded.get(ref) or state.installed.get(ref) or {}
            bom_only.append(
                {
                    "ref": ref,
                    "status": "bom_only",
                    "material_code": str(material.get("material_code") or ""),
                    "name": str(material.get("name") or ""),
                    "model": str(material.get("model") or ""),
                    "description": str(material.get("description") or ""),
                    "reason": str(material.get("reason") or "坐标文件中没有该位号"),
                    "version_change": "added" if baseline_path is not None and ref not in baseline else "none",
                }
            )
        if baseline_path is not None:
            for ref in sorted(set(baseline) - all_state_refs - xy_refs, key=natural_key):
                material = baseline[ref]
                bom_only.append(
                    {
                        "ref": ref,
                        "status": "bom_only",
                        "material_code": "",
                        "name": str(material.get("name") or ""),
                        "model": str(material.get("model") or ""),
                        "description": str(material.get("description") or ""),
                        "reason": "仅旧版 BOM 存在",
                        "version_change": "removed",
                    }
                )

        files_for_id = [discovered.xy_file, bom_path]
        files_for_id.extend(path for path in optional_paths if path is not None)
        board_id = _fingerprint(files_for_id, request.label or source_dir.name)
        reference_url = f"/api/v1/smt-view/boards/{board_id}/reference-drawing" if discovered.reference_pdf else None
        summary = {
            "total": len(placements),
            "top": sum(item["side"] == "top" for item in placements),
            "bottom": sum(item["side"] == "bottom" for item in placements),
            "placed": sum(item["status"] == "placed" for item in placements),
            "nc": sum(item["status"] == "nc" for item in placements),
            "non_smt": sum(item["status"] == "non_smt" for item in placements),
            "xy_only": sum(item["status"] == "xy_only" for item in placements),
            "bom_only": len(bom_only),
            "version_changes": sum(item["version_change"] != "none" for item in placements) + sum(item["version_change"] != "none" for item in bom_only),
        }
        payload: dict[str, object] = {
            "schema_version": 1,
            "board_id": board_id,
            "label": (request.label or source_dir.name).strip() or source_dir.name,
            "xy_file_name": discovered.xy_file.relative_to(source_dir).as_posix(),
            "xy_version": geometry.units.version,
            "xy_units": geometry.units.units,
            "bbox": geometry.bbox,
            "source_span": geometry.source_span,
            "placements": placements,
            "bom_only": bom_only,
            "xy_only": [item["ref"] for item in placements if item["status"] == "xy_only"],
            "summary": summary,
            "reference_drawing_name": discovered.reference_pdf.name if discovered.reference_pdf else None,
            "reference_drawing_url": reference_url,
            "notices": notices,
            "_reference_drawing_path": str(discovered.reference_pdf) if discovered.reference_pdf else "",
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
