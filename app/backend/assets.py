from __future__ import annotations

from pathlib import Path

from app.backend import history


def _format_for_bom(path: Path) -> str:
    name = path.name.upper()
    if "_PLM_" in name or name.endswith("_PLM_BOM.XLSX"):
        return "PLM"
    if "_OA_" in name or name.endswith("_OA_BOM.XLSX"):
        return "OA"
    return "BOM"


def _is_processed_bom(path: Path) -> bool:
    name = path.name.upper()
    if path.suffix.lower() not in {".xlsx", ".xls"}:
        return False
    if "NC" in name and ("未贴" in path.name or "NC" in name):
        return False
    return "_PLM_BOM" in name or "_OA_BOM" in name


def _output_path(root: Path, value: str) -> Path | None:
    relative = history.output_relative_path(root, value)
    if relative is None:
        return None
    outputs_root = root / "data" / "outputs"
    candidate = outputs_root / relative
    if candidate.is_file():
        return candidate
    if "/" in relative:
        return None
    matches = [path for path in outputs_root.rglob(relative) if path.is_file()]
    return matches[0] if len(matches) == 1 else None


def list_assets(root: Path) -> dict[str, object]:
    processed_boms: list[dict[str, object]] = []
    seen: set[str] = set()

    for run in history.list_runs(root):
        outputs = run.get("outputs") or []
        for output_name in outputs:
            output_path = _output_path(root, str(output_name))
            if output_path is None or not _is_processed_bom(output_path):
                continue
            resolved = str(output_path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            processed_boms.append(
                {
                    "id": f"{run.get('id', '')}:{output_path.name}",
                    "kind": "processed_bom",
                    "name": output_path.name,
                    "path": str(output_path),
                    "format": _format_for_bom(output_path),
                    "run_id": run.get("id", ""),
                    "source_tool": run.get("tool", ""),
                    "source_tool_name": run.get("tool_name", ""),
                    "time": run.get("time", ""),
                    "summary": run.get("summary") or {},
                }
            )

    return {
        "status": "ok",
        "groups": {
            "processed_bom": processed_boms,
        },
        "summary": {
            "processed_bom": len(processed_boms),
        },
    }
