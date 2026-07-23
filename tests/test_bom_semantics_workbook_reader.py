from __future__ import annotations

import runpy
from pathlib import Path

from app.backend.bom_semantics.models import WorkbookProfile
from app.backend.bom_semantics.workbook_reader import read_workbook_envelope


BUILDER = Path(__file__).resolve().parent / "fixtures" / "bom_semantics" / "build_fixtures.py"


def _fixtures(tmp_path: Path) -> dict[str, Path]:
    return runpy.run_path(str(BUILDER))["build_all"](tmp_path)


def test_reader_detects_single_and_multi_parent_plm(tmp_path: Path) -> None:
    fixtures = _fixtures(tmp_path)

    single = read_workbook_envelope(fixtures["ordinary"])
    multi = read_workbook_envelope(fixtures["multi_parent"])

    assert single.profile == WorkbookProfile.PLM_SINGLE_BOARD
    assert single.data_sheet == "BOM导入模版"
    assert len(single.sheets) == 2
    assert multi.profile == WorkbookProfile.PLM_MULTI_BOARD
    data_sheet = next(sheet for sheet in multi.sheets if sheet.name == multi.data_sheet)
    assert len(data_sheet.header_rows) == 2


def test_reader_keeps_template_structure_metadata(tmp_path: Path) -> None:
    envelope = read_workbook_envelope(_fixtures(tmp_path)["substitutes"])

    assert envelope.preserved_metadata["sheet_names"] == ["BOM导入模版", "说明"]
    assert envelope.sheets[0].header_rows[0] == 2
    assert envelope.sheets[0].field_columns["substitute_priority"] == 16
