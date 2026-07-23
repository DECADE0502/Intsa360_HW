from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

from app.backend.bom_semantics.field_mapping import (
    apply_mapping_overrides,
    detect_header,
    infer_profile,
    normalize_header,
)
from app.backend.bom_semantics.models import SourceSheet, WorkbookEnvelope, WorkbookProfile
from app.backend.parsers._workbook import open_bom_workbook


def source_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _cell_text(value: object) -> str:
    return str(value or "").strip()


def _unique_parent_codes(
    worksheet: object,
    header_row: int,
    mapping: Mapping[str, int],
    repeated_rows: set[int],
) -> set[str]:
    parent_col = mapping.get("parent_code")
    material_col = mapping.get("material_code")
    if parent_col is None:
        return set()
    values: set[str] = set()
    for row in range(header_row + 1, int(worksheet.max_row or 0) + 1):
        if row in repeated_rows:
            continue
        parent = _cell_text(worksheet.cell(row, parent_col).value)
        material = _cell_text(worksheet.cell(row, material_col).value) if material_col else ""
        if parent and normalize_header(parent) != normalize_header("父项编码") and material:
            values.add(parent)
    return values


def _data_end_row(
    worksheet: object,
    header_row: int,
    mapping: Mapping[str, int],
    repeated_rows: set[int],
) -> int:
    columns = {
        mapping[field]
        for field in ("material_code", "parent_code", "level", "change_status")
        if field in mapping
    }
    last = header_row
    for row in range(header_row + 1, int(worksheet.max_row or 0) + 1):
        if row in repeated_rows:
            last = row
            continue
        if any(_cell_text(worksheet.cell(row, col).value) for col in columns):
            last = row
    return last


def read_workbook_envelope(
    path: Path,
    mapping_overrides: Mapping[str, Mapping[str, int]] | None = None,
) -> WorkbookEnvelope:
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    sheets: list[SourceSheet] = []
    profiles: list[tuple[int, WorkbookProfile, str]] = []
    envelope_candidates: dict[str, tuple[int, ...]] = {}
    with open_bom_workbook(path, data_only=False, read_only=False) as workbook:
        for index, worksheet in enumerate(workbook.worksheets):
            detection = detect_header(worksheet)
            if detection is None:
                sheets.append(
                    SourceSheet(
                        name=worksheet.title,
                        index=index,
                        state=worksheet.sheet_state,
                        max_row=int(worksheet.max_row or 0),
                        max_column=int(worksheet.max_column or 0),
                        merged_ranges=tuple(str(item) for item in worksheet.merged_cells.ranges),
                        freeze_panes=str(worksheet.freeze_panes or ""),
                    )
                )
                continue
            overrides = (mapping_overrides or {}).get(worksheet.title)
            mapping = apply_mapping_overrides(
                detection.field_columns,
                overrides,
                int(worksheet.max_column or 0),
            )
            repeated = set(detection.repeated_header_rows)
            parents = _unique_parent_codes(worksheet, detection.row, mapping, repeated)
            profile = infer_profile(mapping, len(parents))
            profiles.append((detection.score, profile, worksheet.title))
            if not envelope_candidates or detection.score > max((score for score, _, _ in profiles[:-1]), default=-1):
                envelope_candidates = dict(detection.mapping_candidates)
            sheets.append(
                SourceSheet(
                    name=worksheet.title,
                    index=index,
                    state=worksheet.sheet_state,
                    max_row=int(worksheet.max_row or 0),
                    max_column=int(worksheet.max_column or 0),
                    merged_ranges=tuple(str(item) for item in worksheet.merged_cells.ranges),
                    freeze_panes=str(worksheet.freeze_panes or ""),
                    header_rows=(detection.row, *detection.repeated_header_rows),
                    data_start_row=detection.row + 1,
                    data_end_row=_data_end_row(worksheet, detection.row, mapping, repeated),
                    field_columns=mapping,
                )
            )

        if profiles:
            _, profile, data_sheet = max(profiles, key=lambda item: item[0])
        else:
            profile, data_sheet = WorkbookProfile.UNKNOWN, ""
        return WorkbookEnvelope(
            source_path=str(path.resolve()),
            source_fingerprint=source_fingerprint(path),
            profile=profile,
            sheets=tuple(sheets),
            data_sheet=data_sheet,
            mapping_candidates=envelope_candidates,
            preserved_metadata={
                "sheet_names": list(workbook.sheetnames),
                "sheet_count": len(workbook.sheetnames),
            },
        )
