from __future__ import annotations

import runpy
from pathlib import Path

from app.backend.bom_semantics.diff import compare_board_boms
from app.backend.bom_semantics.normalization import normalize_workbook
from app.backend.bom_semantics.serialization import (
    compare_result_json,
    read_compare_result_json,
    write_compare_result_json,
)
from app.backend.bom_semantics.substitutes import build_board_boms


BUILDER = Path(__file__).resolve().parent / "fixtures" / "bom_semantics" / "build_fixtures.py"


def test_compare_json_round_trip_preserves_payload(tmp_path: Path) -> None:
    paths = runpy.run_path(str(BUILDER))["build_all"](tmp_path)
    old = build_board_boms(normalize_workbook(paths["ordinary"]))
    new = build_board_boms(normalize_workbook(paths["substitutes"]))
    result = compare_board_boms(old, new)
    output = write_compare_result_json(result, tmp_path / "compare.json")

    assert read_compare_result_json(output) == result.payload()
    assert "BOARD-A" in compare_result_json(result)

