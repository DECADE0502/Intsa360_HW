from __future__ import annotations

from pathlib import Path

from app.backend.repositories.assets_repository import AssetsRepository
from app.backend.repositories.runs_repository import RunsRepository


def list_assets(root: Path) -> dict[str, object]:
    RunsRepository(root)
    processed_boms = AssetsRepository(root).list_processed_boms()
    return {
        "status": "ok",
        "groups": {"processed_bom": processed_boms},
        "summary": {"processed_bom": len(processed_boms)},
    }
