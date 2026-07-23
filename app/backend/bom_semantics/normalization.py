from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from app.backend.bom_semantics.field_mapping import normalize_header
from app.backend.bom_semantics.models import (
    CanonicalRow,
    FindingSeverity,
    ValidationFinding,
    WorkbookEnvelope,
    WorkbookProfile,
)
from app.backend.bom_semantics.references import parse_references
from app.backend.bom_semantics.workbook_reader import read_workbook_envelope
from app.backend.parsers._workbook import build_merged_cell_lookup, open_bom_workbook


NC_RE = re.compile(r"^(?:NC|DNP|DNI|N/?A|未贴|不贴)$", re.IGNORECASE)
NC_PREFIX_RE = re.compile(r"^(?:NC|DNP|DNI)(?:[/_\-\s]|$)", re.IGNORECASE)


@dataclass(frozen=True)
class NormalizedSource:
    envelope: WorkbookEnvelope
    rows: tuple[CanonicalRow, ...]
    findings: tuple[ValidationFinding, ...]

    @property
    def has_blockers(self) -> bool:
        return any(finding.severity == FindingSeverity.BLOCKER for finding in self.findings)

    def payload(self) -> dict[str, object]:
        return {
            "envelope": self.envelope.payload(),
            "rows": [row.payload() for row in self.rows],
            "findings": [finding.payload() for finding in self.findings],
            "has_blockers": self.has_blockers,
        }


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        if value.is_integer():
            return str(int(value))
        return format(value, ".15g")
    return str(value).strip()


def _identifier_text(value: object, number_format: str) -> tuple[str, tuple[str, ...]]:
    flags: list[str] = []
    text = _text(value)
    if isinstance(value, float) and (abs(value) >= 10**15 or "e" in text.casefold()):
        flags.append("identifier_precision_risk")
    if isinstance(value, (int, float)) and re.fullmatch(r"0+", str(number_format or "")):
        try:
            text = f"{int(value):0{len(number_format)}d}"
        except (ValueError, OverflowError):
            flags.append("identifier_format_invalid")
    return text, tuple(flags)


def _decimal(value: object) -> Decimal | None:
    text = _text(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _cell_value(
    worksheet: object,
    merged_lookup: Mapping[tuple[int, int], object],
    row: int,
    column: int | None,
) -> object:
    if column is None:
        return None
    value = worksheet.cell(row, column).value
    if value is None:
        value = merged_lookup.get((row, column))
    return value


def _source_id(fingerprint: str, sheet: str, row: int) -> str:
    return f"{fingerprint[:16]}:{sheet}:{row}"


def _looks_like_template_instruction(raw_fields: Mapping[str, object]) -> bool:
    material_text = _text(raw_fields.get("material_code"))
    if not material_text:
        return False
    instruction_text = " ".join(
        _text(raw_fields.get(field))
        for field in (
            "material_code",
            "parent_code",
            "description",
            "remark",
            "quantity",
        )
    )
    if (
        _decimal(raw_fields.get("quantity")) is None
        and re.search(r"(?:INSTRUCTION|GUIDE|填写说明|填表说明|示例行|模板说明)", instruction_text, re.IGNORECASE)
    ):
        return True
    repeated_fields = (
        "parent_code",
        "material_code",
        "quantity",
        "reference",
        "substitute_group_code",
        "substitute_priority",
    )
    repeated_count = sum(
        1
        for field in repeated_fields
        if _text(raw_fields.get(field)) == material_text
    )
    return repeated_count >= 3 and _decimal(raw_fields.get("quantity")) is None


def normalize_workbook(
    path: Path,
    mapping_overrides: Mapping[str, Mapping[str, int]] | None = None,
    reference_resolutions: Mapping[str, Mapping[str, object] | str] | None = None,
    default_parent_code: str = "",
) -> NormalizedSource:
    envelope = read_workbook_envelope(path, mapping_overrides)
    rows: list[CanonicalRow] = []
    findings: list[ValidationFinding] = []
    if envelope.profile == WorkbookProfile.UNKNOWN or not envelope.data_sheet:
        findings.append(
            ValidationFinding(
                code="workbook_profile_unknown",
                severity=FindingSeverity.BLOCKER,
                message="无法识别 BOM 工作表或表头。",
            )
        )
        return NormalizedSource(envelope, (), tuple(findings))

    source_sheet = next(sheet for sheet in envelope.sheets if sheet.name == envelope.data_sheet)
    mapping = dict(source_sheet.field_columns)
    missing = [field for field in ("material_code", "quantity") if field not in mapping]
    for field in missing:
        findings.append(
            ValidationFinding(
                code="required_field_missing",
                severity=FindingSeverity.BLOCKER,
                message=f"缺少必需字段：{field}",
                details={"field": field},
            )
        )
    if missing:
        return NormalizedSource(envelope, (), tuple(findings))

    repeated_rows = set(source_sheet.header_rows[1:])
    for row_number in sorted(repeated_rows):
        findings.append(
            ValidationFinding(
                code="repeated_header_skipped",
                severity=FindingSeverity.INFO,
                message=f"已跳过重复表头第 {row_number} 行。",
                source_ids=(_source_id(envelope.source_fingerprint, source_sheet.name, row_number),),
            )
        )

    current_parent_code = ""
    current_parent_description = ""
    with open_bom_workbook(Path(envelope.source_path), data_only=True, read_only=False) as workbook:
        worksheet = workbook[source_sheet.name]
        merged_lookup = build_merged_cell_lookup(worksheet)
        for row_number in range(source_sheet.data_start_row, source_sheet.data_end_row + 1):
            if row_number in repeated_rows:
                continue
            source_id = _source_id(envelope.source_fingerprint, source_sheet.name, row_number)
            raw_material = _cell_value(worksheet, merged_lookup, row_number, mapping.get("material_code"))
            material_cell = worksheet.cell(row_number, mapping["material_code"])
            material_code, code_flags = _identifier_text(raw_material, material_cell.number_format)
            raw_fields = {
                field: _cell_value(worksheet, merged_lookup, row_number, column)
                for field, column in mapping.items()
            }
            raw_reference = _text(raw_fields.get("reference"))
            if _looks_like_template_instruction(raw_fields):
                findings.append(
                    ValidationFinding(
                        code="template_instruction_skipped",
                        severity=FindingSeverity.INFO,
                        message=f"已跳过模板说明行第 {row_number} 行。",
                        source_ids=(source_id,),
                        details={"text": material_code},
                    )
                )
                continue
            level = _text(_cell_value(worksheet, merged_lookup, row_number, mapping.get("level")))

            if envelope.profile == WorkbookProfile.OA_BOM and level == "0" and material_code:
                current_parent_code = material_code
                current_parent_description = _text(
                    _cell_value(worksheet, merged_lookup, row_number, mapping.get("description"))
                )
                continue
            if normalize_header(material_code) == normalize_header("子项编码"):
                continue
            has_material_evidence = bool(
                raw_reference
                or any(
                    _text(raw_fields.get(field))
                    for field in (
                        "value",
                        "model",
                        "description",
                        "name",
                        "pcb_footprint",
                        "pcb_package",
                    )
                )
            )
            if not material_code and not has_material_evidence:
                continue

            parent_value = _cell_value(worksheet, merged_lookup, row_number, mapping.get("parent_code"))
            if mapping.get("parent_code"):
                parent_cell = worksheet.cell(row_number, mapping["parent_code"])
                parent_code, parent_flags = _identifier_text(parent_value, parent_cell.number_format)
            else:
                parent_code, parent_flags = current_parent_code, ()
            parent_description = _text(
                _cell_value(worksheet, merged_lookup, row_number, mapping.get("parent_description"))
            ) or current_parent_description
            if not parent_code and envelope.profile == WorkbookProfile.CAPTURE_RAW:
                parent_code = default_parent_code or Path(envelope.source_path).stem
                parent_description = parent_description or parent_code

            resolution = (reference_resolutions or {}).get(source_id)
            parsed_references = parse_references(raw_reference, resolution)
            row_flags = set(code_flags) | set(parent_flags) | set(parsed_references.flags)

            if "numeric_reference_suspected" in row_flags:
                findings.append(
                    ValidationFinding(
                        code="numeric_reference_suspected",
                        severity=FindingSeverity.BLOCKER,
                        message="检测到纯数字位号，请确认它是空位号、真实位号还是需要替换。",
                        source_ids=(source_id,),
                        parent_code=parent_code,
                        references=parsed_references.references,
                        details={"raw_reference": raw_reference},
                    )
                )
            if "identifier_precision_risk" in row_flags:
                findings.append(
                    ValidationFinding(
                        code="identifier_precision_risk",
                        severity=FindingSeverity.BLOCKER,
                        message="物料编码或父项编码可能已被 Excel 转成科学计数法或丢失精度。",
                        source_ids=(source_id,),
                        parent_code=parent_code,
                        details={"material_code": material_code},
                    )
                )

            raw_priority = _text(
                _cell_value(worksheet, merged_lookup, row_number, mapping.get("substitute_priority"))
            )
            priority: int | None = None
            if raw_priority:
                try:
                    priority = int(Decimal(raw_priority))
                except (InvalidOperation, ValueError, OverflowError):
                    row_flags.add("substitute_priority_invalid")
                    findings.append(
                        ValidationFinding(
                            code="substitute_priority_invalid",
                            severity=FindingSeverity.BLOCKER,
                            message="替代优先级不是有效整数。",
                            source_ids=(source_id,),
                            parent_code=parent_code,
                            details={"value": raw_priority},
                        )
                    )

            quantity = _decimal(raw_fields.get("quantity"))
            if raw_fields.get("quantity") not in (None, "") and quantity is None:
                row_flags.add("quantity_invalid")
                findings.append(
                    ValidationFinding(
                        code="quantity_invalid",
                        severity=FindingSeverity.BLOCKER,
                        message="数量不是有效数值。",
                        source_ids=(source_id,),
                        parent_code=parent_code,
                        details={"value": _text(raw_fields.get("quantity"))},
                    )
                )

            extra_fields = {
                field: _text(raw_fields.get(field))
                for field in ("manufacturer", "pcb_footprint", "pcb_package", "change_type", "change_status", "affected_bom", "highest_bom", "project")
                if field in raw_fields
            }
            is_nc = bool(
                NC_RE.fullmatch(raw_reference)
                or NC_RE.fullmatch(_text(raw_fields.get("remark")))
                or NC_RE.fullmatch(_text(raw_fields.get("value")))
                or NC_PREFIX_RE.match(_text(raw_fields.get("value")))
            )
            rows.append(
                CanonicalRow(
                    source_id=source_id,
                    sheet_name=source_sheet.name,
                    row_number=row_number,
                    item=_text(raw_fields.get("item")),
                    parent_code=parent_code,
                    parent_description=parent_description,
                    hardware_version=_text(raw_fields.get("hardware_version")),
                    material_code=material_code,
                    name=_text(raw_fields.get("name")),
                    value=_text(raw_fields.get("value")),
                    model=_text(raw_fields.get("model")),
                    description=_text(raw_fields.get("description")),
                    unit=_text(raw_fields.get("unit")),
                    quantity=quantity,
                    references=parsed_references.references,
                    raw_reference=raw_reference,
                    is_nc=is_nc,
                    remark=_text(raw_fields.get("remark")),
                    grade=_text(raw_fields.get("grade")),
                    grade_remark=_text(raw_fields.get("grade_remark")),
                    substitute_group_code=_text(raw_fields.get("substitute_group_code")),
                    substitute_strategy=_text(raw_fields.get("substitute_strategy")),
                    substitute_mode=_text(raw_fields.get("substitute_mode")),
                    substitute_priority=priority,
                    issue_method=_text(raw_fields.get("issue_method")),
                    mrp=_text(raw_fields.get("mrp")),
                    jump_level=_text(raw_fields.get("jump_level")),
                    extra_fields=extra_fields,
                    raw_fields=raw_fields,
                    quality_flags=tuple(sorted(row_flags)),
                )
            )

    return NormalizedSource(envelope=envelope, rows=tuple(rows), findings=tuple(findings))
