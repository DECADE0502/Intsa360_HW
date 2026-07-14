from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from openpyxl import Workbook


FIXTURES = Path(__file__).parent / "fixtures"
PROCESSED_HEADERS = [
    "parent_code",
    "parent_description",
    "part_number",
    "name",
    "model",
    "description",
    "unit",
    "quantity",
    "reference",
    "remark",
    "grade",
    "grade_remark",
    "alternate_group",
    "alternate_strategy",
    "alternate_method",
    "alternate_priority",
    "issue_method",
    "mrp",
    "jump_level",
]


def _read_json(relative_path: str) -> dict[str, object]:
    return json.loads((FIXTURES / relative_path).read_text(encoding="utf-8"))


def build_capture_bom(path: Path, case_name: str) -> Path:
    data = _read_json("bom/conflict_cases.json")
    cases = data["cases"]
    rows = data["rows"]
    if case_name not in cases:
        raise ValueError(f"Unknown capture BOM case: {case_name}")

    columns = data["capture_columns"]
    selected = cases[case_name]["row_ids"]
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "CaptureBOM"
    sheet.append([column["header"] for column in columns])
    for row_id in selected:
        row = rows[row_id]
        sheet.append([row.get(column["field"], "") for column in columns])
    workbook.save(path)
    return path


def build_processed_bom(path: Path, template: Literal["plm", "oa"]) -> Path:
    if template not in ("plm", "oa"):
        raise ValueError(f"Unknown processed BOM template: {template}")

    data = _read_json("bom/conflict_cases.json")
    source = data["rows"]["c1105_primary"]
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = template.upper()
    sheet.append(PROCESSED_HEADERS)
    sheet.append([
        "PARENT.SANITIZED.01",
        "SANITIZED BOARD",
        source["Part Number"],
        source["Name"],
        source["Model"],
        source["Description"],
        source["Unit"],
        source["Quantity"],
        "C1105,C1106",
        "",
        source["Grade"],
        "",
        "",
        "",
        "",
        "",
        "DIRECT",
        "YES",
        "NO",
    ])
    workbook.save(path)
    return path
