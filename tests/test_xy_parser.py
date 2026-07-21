from __future__ import annotations

from pathlib import Path

import pytest

from app.backend.parsers.xy import parse_xy_file


FIXTURE = Path(__file__).parent / "fixtures" / "smt" / "synthetic" / "xy_basic.txt"


def test_xy_parses_header_and_units_declaration(tmp_path: Path) -> None:
    units, components = parse_xy_file(FIXTURE)

    assert units.version == "2.0"
    assert units.units == "mils"
    assert len(components) == 2

    missing = tmp_path / "missing-units.txt"
    missing.write_text("VERSION = 2.0\nR1 ! 1 ! 2 ! 0 ! ! R0402\n", encoding="utf-8")
    with pytest.raises(ValueError, match="XY 文件缺少 UUNITS 声明"):
        parse_xy_file(missing)


def test_xy_converts_mils_to_mm() -> None:
    _, components = parse_xy_file(FIXTURE)

    assert components[0].x_mm == pytest.approx(25.4, abs=1e-6)
    assert components[0].y_mm == pytest.approx(50.8, abs=1e-6)


def test_xy_mirror_m_maps_to_bottom_side() -> None:
    _, components = parse_xy_file(FIXTURE)

    assert components[0].side == "bottom"
    assert components[1].side == "top"


def test_xy_ignores_comments_and_blank_lines() -> None:
    _, components = parse_xy_file(FIXTURE)

    assert [component.ref for component in components] == ["C1", "R1"]
    assert components[0].source_line == 5


def test_xy_rejects_malformed_row_with_line_number(tmp_path: Path) -> None:
    source = tmp_path / "bad.txt"
    source.write_text("VERSION=2.0\nUUNITS=MM\nR1 ! 1 ! 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="XY 第 3 行字段数不符"):
        parse_xy_file(source)


def test_xy_rotation_normalized_to_int_range_0_359(tmp_path: Path) -> None:
    _, components = parse_xy_file(FIXTURE)

    assert [component.rotation for component in components] == [270, 90]

    source = tmp_path / "bad-rotation.txt"
    source.write_text("VERSION=2.0\nUUNITS=MM\nR1 ! 1 ! 2 ! right ! ! R0402\n", encoding="utf-8")
    with pytest.raises(ValueError, match="XY 第 3 行旋转角度无效"):
        parse_xy_file(source)
