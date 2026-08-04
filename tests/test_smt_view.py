from __future__ import annotations

import os
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.backend.smt_view.board import build_board_geometry
from app.backend.smt_view.discovery import discover_smt_directory
from app.backend.smt_view.drawing import _locate_refs, crop_for_xy, open_pdf_drawing
from app.backend.smt_view.registration import RegistrationAnchor, fit_affine_registration
from app.backend.smt_view.state import load_bom_state


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


def test_registration_rejects_an_outlier_and_recovers_affine_transform() -> None:
    anchors = []
    for index in range(30):
        x = float(index % 6)
        y = float(index // 6)
        pdf_x = 2.0 * x + 0.25 * y + 40.0
        pdf_y = -0.1 * x + 1.8 * y + 70.0
        anchors.append(RegistrationAnchor(f"R{index + 1}", x, y, pdf_x, pdf_y))
    anchors[-1] = RegistrationAnchor("R30", 5.0, 4.0, 500.0, 500.0)

    result = fit_affine_registration(anchors)

    assert result.trusted is True
    assert result.rejected_count == 1
    assert result.median_mm < 1e-8
    assert result.transform(3.0, 2.0) == pytest.approx((46.5, 73.3), abs=1e-8)


def test_finished_bom_is_the_only_source_of_placed_refs(tmp_path: Path) -> None:
    bom = tmp_path / "finished.xlsx"
    _write_bom(bom, ["R1,R3"])

    state = load_bom_state(bom)
    xy_refs = {"R1", "R2", "R3", "R4"}

    assert set(state.installed) == {"R1", "R3"}
    assert xy_refs - set(state.installed) == {"R2", "R4"}


def test_crop_uses_registered_xy_envelope_and_stays_inside_page() -> None:
    anchors = [
        RegistrationAnchor(f"R{index}", float(index % 5), float(index // 5), 10 + 2 * (index % 5), 20 + 2 * (index // 5))
        for index in range(20)
    ]
    registration = fit_affine_registration(anchors)

    left, bottom, right, top = crop_for_xy(
        registration,
        [(0, 0), (4, 3)],
        page_width=100,
        page_height=100,
    )

    assert 0 <= left < right <= 100
    assert 0 <= bottom < top <= 100
    assert left < 10 < right
    assert bottom < 20 < top


def test_pdf_refs_are_normalized_to_the_zero_based_render_canvas() -> None:
    class Searcher:
        remaining = [(0, 2)]

        def get_next(self):
            return self.remaining.pop(0) if self.remaining else None

        def close(self):
            return None

    class TextPage:
        boxes = [(-20.0, -10.0, -19.0, -9.0), (-18.0, -10.0, -17.0, -9.0)]

        def search(self, *_args, **_kwargs):
            return Searcher()

        def get_charbox(self, position, **_kwargs):
            return self.boxes[position]

    refs = _locate_refs(TextPage(), "R1", page_origin_x=-31.0, page_origin_y=-30.0)

    assert len(refs) == 1
    assert refs[0].x == pytest.approx(12.5)
    assert refs[0].y == pytest.approx(20.5)


def test_real_sample_pdf_and_xy_contract_when_configured() -> None:
    configured = os.environ.get("SMT_REAL_SAMPLE_DIR", "").strip()
    if not configured:
        pytest.skip("SMT_REAL_SAMPLE_DIR is not configured")
    discovered = discover_smt_directory(Path(configured))
    assert discovered.reference_pdf is not None
    board = build_board_geometry(discovered.xy_file)
    drawing = open_pdf_drawing(discovered.reference_pdf)

    assert len(board.components) == 1037
    assert sum(item.side == "top" for item in board.components) == 450
    assert sum(item.side == "bottom" for item in board.components) == 587
    assert len(drawing.pages) == 2
    assert sorted(len(page.refs) for page in drawing.pages) == [359, 444]
