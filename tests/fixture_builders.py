from __future__ import annotations

from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook


FIXTURES = Path(__file__).parent / "fixtures"
CORE_XML_PATH = "docProps/core.xml"
CORE_XML_TAGS = {
    "creator": "{http://purl.org/dc/elements/1.1/}creator",
    "last_modified_by": "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}lastModifiedBy",
    "created": "{http://purl.org/dc/terms/}created",
    "modified": "{http://purl.org/dc/terms/}modified",
}


def _read_json(relative_path: str) -> dict[str, object]:
    return json.loads((FIXTURES / relative_path).read_text(encoding="utf-8"))


def _write_deterministic_workbook(workbook: Workbook, path: Path, expectations: dict[str, object]) -> None:
    core_properties = expectations["core_properties"]
    timestamp = datetime.fromisoformat(str(core_properties["created"]).removesuffix("Z"))
    workbook.properties.creator = str(core_properties["creator"])
    workbook.properties.lastModifiedBy = str(core_properties["last_modified_by"])
    workbook.properties.created = timestamp
    workbook.properties.modified = timestamp

    buffer = BytesIO()
    workbook.save(buffer)
    path.parent.mkdir(parents=True, exist_ok=True)
    zip_timestamp = tuple(expectations["zip_timestamp"])
    with ZipFile(buffer, "r") as source, ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as target:
        for name in sorted(source.namelist()):
            content = source.read(name)
            if name == CORE_XML_PATH:
                root = ElementTree.fromstring(content)
                for field, tag in CORE_XML_TAGS.items():
                    root.find(tag).text = str(core_properties[field])
                content = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
            entry = ZipInfo(name, date_time=zip_timestamp)
            entry.compress_type = ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o600 << 16
            target.writestr(entry, content, compress_type=ZIP_DEFLATED, compresslevel=9)


def build_capture_bom(path: Path, case_name: str) -> Path:
    data = _read_json("bom/conflict_cases.json")
    expected = _read_json("bom/expected_recommendations.json")
    cases = data["cases"]
    rows = data["rows"]
    if case_name not in cases:
        raise ValueError(f"Unknown capture BOM case: {case_name}")

    columns = data["capture_columns"]
    selected = cases[case_name]["row_ids"]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "CaptureBOM"
    sheet.append([column["header"] for column in columns])
    for row_id in selected:
        row = rows[row_id]
        sheet.append([row.get(column["field"], "") for column in columns])
    _write_deterministic_workbook(workbook, path, expected["workbook_expectations"])
    return path


def build_processed_bom(path: Path, template: Literal["plm", "oa"]) -> Path:
    if template not in ("plm", "oa"):
        raise ValueError(f"Unknown processed BOM template: {template}")

    expected = _read_json("bom/expected_recommendations.json")
    oracle = expected["processed_templates"][template]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = str(oracle["sheet_title"])
    if "group_header" in oracle:
        sheet.append(oracle["group_header"])
    sheet.append(oracle["headers"])
    sheet.append(oracle["row"])
    _write_deterministic_workbook(workbook, path, expected["workbook_expectations"])
    return path
