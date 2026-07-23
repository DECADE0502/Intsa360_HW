from __future__ import annotations

import runpy
from pathlib import Path

from openpyxl import load_workbook


BUILDER = Path(__file__).resolve().parent / "fixtures" / "bom_semantics" / "build_fixtures.py"


def test_fixture_builder_creates_privacy_safe_workbooks(tmp_path: Path) -> None:
    module = runpy.run_path(str(BUILDER))
    outputs = module["build_all"](tmp_path)

    assert set(outputs) == {"ordinary", "substitutes", "multi_parent", "styled"}
    assert all(path.exists() for path in outputs.values())
    workbook = load_workbook(outputs["substitutes"], data_only=True, read_only=True)
    try:
        sheet = workbook["BOM导入模版"]
        assert sheet["C3"].value == "MAT-A"
        assert sheet["P3"].value == 0
        assert sheet["I5"].value == "60"
    finally:
        workbook.close()
