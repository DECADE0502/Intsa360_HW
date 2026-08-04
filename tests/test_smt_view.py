from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.backend.contracts.smt_view import SmtViewBoard, SmtViewBoardRequest
from app.backend.paths import AppPaths
from app.backend.smt_view.board import build_board_geometry
from app.backend.smt_view.discovery import discover_smt_directory
from app.backend.smt_view.service import SmtViewService


ROOT = Path(__file__).resolve().parents[1]


def _write_xy(path: Path, count: int = 3) -> None:
    rows = ["VERSION = 2.0", "UUNITS = MM", "# ref!x!y!rotation!mirror!symbol"]
    for index in range(count):
        side = "m" if index % 2 else ""
        rows.append(f"R{index + 1}!{index * 1.2:.3f}!{index * 0.8:.3f}!{index * 90}!{side}!R0201")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_bom(path: Path, refs: list[str]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["位号", "子项编码", "描述", "数量", "名称", "型号", "物料优选等级"])
    for index, ref in enumerate(refs, start=1):
        worksheet.append([ref, f"31{index:010d}", "电阻", 1, "电阻", "100K", "优选"])
    workbook.save(path)
    workbook.close()


def _write_nc(path: Path, ref: str, kind: str) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["位号", "子项编码", "描述", "过滤原因", "判定类型"])
    worksheet.append([ref, "", "", "原理图明确未贴", kind])
    workbook.save(path)
    workbook.close()


def test_discovery_uses_xy_content_and_ignores_schematic_pdf(tmp_path: Path) -> None:
    _write_xy(tmp_path / "coordinates.txt")
    (tmp_path / "board_SMD.pdf").write_bytes(b"%PDF-1.4\n")
    schematic = tmp_path / "原理图"
    schematic.mkdir()
    (schematic / "board_REF.pdf").write_bytes(b"%PDF-1.4\n")

    result = discover_smt_directory(tmp_path)

    assert result.xy_file.name == "coordinates.txt"
    assert result.reference_pdf is not None
    assert result.reference_pdf.name == "board_SMD.pdf"


def test_board_geometry_preserves_all_refs_and_sides(tmp_path: Path) -> None:
    xy = tmp_path / "XY.txt"
    _write_xy(xy, 4)

    board = build_board_geometry(xy)

    assert [item.ref for item in board.components] == ["R1", "R2", "R3", "R4"]
    assert sum(item.side == "top" for item in board.components) == 2
    assert sum(item.side == "bottom" for item in board.components) == 2
    assert board.bbox["width"] > board.source_span["width"]


def test_service_joins_bom_nc_and_persists_board(tmp_path: Path) -> None:
    paths = AppPaths(ROOT, state_root_override=tmp_path)
    paths.ensure_runtime_dirs()
    source = paths.uploads_dir / "tree"
    source.mkdir()
    _write_xy(source / "XY.txt", 3)
    (source / "board_SMD.pdf").write_bytes(b"%PDF-1.4\n")
    bom = paths.uploads_dir / "bom.xlsx"
    nc = paths.uploads_dir / "nc.xlsx"
    _write_bom(bom, ["R1"])
    _write_nc(nc, "R2", "system_nc")
    service = SmtViewService(paths)

    created = service.create(SmtViewBoardRequest(source_dir=str(source), bom_path=str(bom), nc_path=str(nc)))
    validated = SmtViewBoard.model_validate(created)

    assert {item.ref: item.status for item in validated.placements} == {"R1": "placed", "R2": "nc", "R3": "xy_only"}
    assert validated.reference_drawing_url
    assert service.get(validated.board_id) == created
    assert service.reference_drawing(validated.board_id).name == "board_SMD.pdf"


def test_real_sample_xy_contract_when_configured() -> None:
    configured = os.environ.get("SMT_REAL_SAMPLE_DIR", "").strip()
    if not configured:
        pytest.skip("SMT_REAL_SAMPLE_DIR is not configured")
    discovered = discover_smt_directory(Path(configured))
    board = build_board_geometry(discovered.xy_file)
    assert len(board.components) == 1037
    assert sum(item.side == "top" for item in board.components) == 450
    assert sum(item.side == "bottom" for item in board.components) == 587
