from __future__ import annotations

import sys
from pathlib import Path

import ezdxf
import pytest

from app.backend.parsers.board_outline import resolve_board_outline


FIXTURES = Path(__file__).parent / "fixtures" / "smt" / "synthetic"


def test_outline_dxf_rectangular_board(tmp_path: Path) -> None:
    target = tmp_path / "outline_rect.dxf"
    target.write_bytes((FIXTURES / "outline_rect.dxf").read_bytes())

    outline = resolve_board_outline(tmp_path)

    assert outline.source == "dxf"
    assert outline.bbox == pytest.approx((0, 0, 100, 80))
    assert len(outline.rings) == 1
    assert len(outline.rings[0]) == 4


def test_outline_dxf_l_shape_board(tmp_path: Path) -> None:
    target = tmp_path / "outline_lshape.dxf"
    target.write_bytes((FIXTURES / "outline_lshape.dxf").read_bytes())

    outline = resolve_board_outline(tmp_path)

    assert len(outline.rings[0]) == 6
    assert outline.bbox == pytest.approx((0, 0, 100, 80))


def test_outline_dxf_layer_selection(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("MECHANICAL")
    document.layers.add("OUTLINE")
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={"layer": "MECHANICAL"})
    modelspace.add_lwpolyline([(0, 0), (50, 0), (50, 40), (0, 40)], close=True, dxfattribs={"layer": "OUTLINE"})
    document.saveas(tmp_path / "layers.dxf")

    explicit = resolve_board_outline(tmp_path, outline_dxf_layer="MECHANICAL")
    automatic = resolve_board_outline(tmp_path)

    assert explicit.bbox == pytest.approx((0, 0, 10, 10))
    assert automatic.bbox == pytest.approx((0, 0, 50, 40))

    empty = tmp_path / "empty"
    empty.mkdir()
    other = ezdxf.new("R2010")
    other.layers.add("NOT_OUTLINE")
    other.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "NOT_OUTLINE"})
    other.saveas(empty / "empty.dxf")
    with pytest.raises(ValueError, match="未在 DXF 中定位板轮廓层，请指定 outline_dxf_layer"):
        resolve_board_outline(empty)


def test_outline_selects_single_panel_ring_and_aligns_to_xy_coordinates(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    for offset_x in (400.0, 450.0, 500.0):
        modelspace.add_lwpolyline(
            [(offset_x, -200), (offset_x + 40, -200), (offset_x + 40, -160), (offset_x, -160)],
            close=True,
        )
    document.saveas(tmp_path / "panel.dxf")

    outline = resolve_board_outline(
        tmp_path,
        component_bbox_mm=(2.5, 3.0, 40.0, 40.5),
    )

    assert outline.source == "dxf"
    assert len(outline.rings) == 1
    assert outline.bbox == pytest.approx((1.25, 1.75, 41.25, 41.75))


def test_outline_falls_back_to_component_bbox_when_sources_do_not_match(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.modelspace().add_lwpolyline(
        [(0, 0), (200, 0), (200, 100), (0, 100)],
        close=True,
    )
    document.saveas(tmp_path / "unrelated-panel.dxf")

    outline = resolve_board_outline(
        tmp_path,
        component_bbox_mm=(5.0, 8.0, 45.0, 48.0),
    )

    assert outline.source == "component_bbox"
    assert outline.bbox == pytest.approx((3.4, 6.4, 46.6, 49.6))


def test_outline_preserves_existing_xy_alignment(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.modelspace().add_lwpolyline(
        [(0, 0), (100, 0), (100, 80), (0, 80)],
        close=True,
    )
    document.saveas(tmp_path / "aligned.dxf")

    outline = resolve_board_outline(
        tmp_path,
        component_bbox_mm=(10.0, 5.0, 80.0, 70.0),
    )

    assert outline.source == "dxf"
    assert outline.bbox == pytest.approx((0.0, 0.0, 100.0, 80.0))


def test_outline_explicit_bbox_overrides_all(tmp_path: Path) -> None:
    (tmp_path / "broken.dxf").write_text("not a dxf", encoding="ascii")

    outline = resolve_board_outline(tmp_path, outline_bbox_mm=(0, 0, 50, 40))

    assert outline.source == "explicit"
    assert outline.bbox == (0, 0, 50, 40)
    assert outline.rings == [[(0, 0), (50, 0), (50, 40), (0, 40)]]


def test_outline_falls_back_to_gerber_bbox_when_ezdxf_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "outline.dxf").write_bytes((FIXTURES / "outline_rect.dxf").read_bytes())
    (tmp_path / "outline.art").write_bytes((FIXTURES / "outline_bbox.art").read_bytes())
    monkeypatch.setitem(sys.modules, "ezdxf", None)

    outline = resolve_board_outline(tmp_path)

    assert outline.source == "gerber_bbox"
    assert outline.bbox == pytest.approx((0, 0, 100, 80))


def test_outline_reports_missing_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SMT 文件夹未找到 DXF 或 Gerber，且未指定 outline_bbox_mm"):
        resolve_board_outline(tmp_path)
