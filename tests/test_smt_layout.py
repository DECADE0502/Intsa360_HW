from __future__ import annotations

import shutil
from pathlib import Path

from openpyxl import Workbook

from app.backend.capabilities import load_capabilities
from app.backend.tools.smt_layout import run_smt_layout


FIXTURES = Path(__file__).parent / "fixtures" / "smt" / "synthetic"


def _write_bom(path: Path, refs: list[str]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Reference", "Part Number", "Description", "Quantity", "Name", "Model", "PCB Footprint", "Grade"])
    for index, ref in enumerate(refs, start=1):
        sheet.append([ref, f"PN-{index}", f"Description {ref}", 1, "Component", f"MODEL-{index}", "R0402", "优选"])
    workbook.save(path)
    workbook.close()


def _write_xy(path: Path, top: int, bottom: int) -> list[str]:
    rows = ["VERSION=2.0", "UUNITS=MM", ""]
    refs: list[str] = []
    for index in range(top + bottom):
        ref = f"R{index + 1}"
        refs.append(ref)
        mirror = "m" if index >= top else ""
        rows.append(f"{ref} ! {index + 1} ! {index + 2} ! 0 ! {mirror} ! R0402")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return refs


def _inputs(tmp_path: Path, *, top: int = 1, bottom: int = 1) -> tuple[Path, Path, list[str]]:
    smt = tmp_path / "smt"
    smt.mkdir()
    refs = _write_xy(smt / "XY.txt", top, bottom)
    shutil.copy2(FIXTURES / "outline_rect.dxf", smt / "outline.dxf")
    bom = tmp_path / "processed.xlsx"
    _write_bom(bom, refs)
    return smt, bom, refs


def test_smt_layout_requires_smt_folder(tmp_path: Path) -> None:
    result = run_smt_layout(tmp_path, {})

    assert result["status"] == "error"
    assert "SMT 资料文件夹" in result["message"]


def test_smt_layout_accepts_bom_only(tmp_path: Path) -> None:
    smt, bom, _ = _inputs(tmp_path)

    result = run_smt_layout(tmp_path, {"smt_folder": str(smt), "processed_bom": str(bom)})

    assert result["status"] == "ok"
    assert result["components"]
    assert "nc_summary" in result
    assert "fai_table" in result
    assert result["sanity"]["status"] == "skipped_no_netlist"


def test_smt_layout_full_inputs_returns_sanity(tmp_path: Path) -> None:
    smt, bom, _ = _inputs(tmp_path)
    netlist = tmp_path / "netlist"
    netlist.mkdir()
    (netlist / "pstxnet.dat").write_text("NET N1 R1.1 R2.1\n", encoding="utf-8")
    (netlist / "pstxprt.dat").write_text("R1 'R0402'\nR2 'R0402'\n", encoding="utf-8")

    result = run_smt_layout(
        tmp_path,
        {"smt_folder": str(smt), "processed_bom": str(bom), "netlist_folder": str(netlist)},
    )

    assert result["status"] == "ok"
    assert set(result["sanity"]) == {"missing_layout", "missing_bom", "missing_netlist", "footprint_conflicts"}


def test_smt_layout_wraps_user_input_errors(tmp_path: Path) -> None:
    smt, bom, _ = _inputs(tmp_path)
    (smt / "XY.txt").write_text("VERSION=2.0\nUUNITS=MM\nR1 ! broken\n", encoding="utf-8")

    result = run_smt_layout(tmp_path, {"smt_folder": str(smt), "processed_bom": str(bom)})

    assert result["status"] == "error"
    assert "XY 第 3 行" in result["message"]


def test_smt_layout_component_side_split(tmp_path: Path) -> None:
    smt, bom, _ = _inputs(tmp_path, top=20, bottom=10)

    result = run_smt_layout(tmp_path, {"smt_folder": str(smt), "processed_bom": str(bom)})

    assert result["summary"]["top_count"] == 20
    assert result["summary"]["bottom_count"] == 10


def test_smt_layout_registered_in_capabilities() -> None:
    root = Path(__file__).resolve().parents[1]
    item = next(item for item in load_capabilities(root)["capabilities"] if item["id"] == "smt_layout")

    assert item["type"] == "web_tool"
    assert item["status"] == "available"
    assert item["show_in_platform"] is True
    assert item["show_in_cadence"] is False
