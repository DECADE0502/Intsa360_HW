from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import re

from app.backend.config import load_config
from app.backend.bom_semantics.models import FindingSeverity, WorkbookProfile
from app.backend.tools.bom_classify import default_nc_value_re
from app.backend.tools.bom_risk_model import RiskModel, RiskRow


NC_VALUE_RE = default_nc_value_re()
DEFAULT_MECHANICAL_KEYWORDS = (
    "螺丝", "螺钉", "螺母", "螺柱", "螺母柱", "垫片", "华司", "铜柱",
    "支柱", "散热片", "导热垫", "结构件", "定位柱", "STANDOFF", "SCREW",
)
DEFAULT_SHIELD_KEYWORDS = ("屏蔽支架", "屏蔽罩", "SHIELD BRACKET", "SHIELD COVER")
DEFAULT_PROCESS_KEYWORDS = (
    "测试点", "跳线", "短接", "基准", "工艺边", "MARK点", "FIDUCIAL",
    "MOUNTINGHOLE", "MOUNTING HOLE",
)
DEFAULT_PROCESS_PREFIXES = ("TP", "JP", "FID", "MK", "MH", "Z_TP")
DEFAULT_GRADE_OK = ("优选", "正常")
DEFAULT_VERSION_SENSITIVE = ("EMMC", "DDR", "LPDDR", "UFS", "NAND", "SOC", "WIFI", "加密")
DEFAULT_EXPECTED_TYPES = {"C": "电容", "R": "电阻", "L": "电感"}
DEFAULT_NORMAL_UNITS = ("EA",)
_REF_PREFIX_RE = re.compile(r"^([A-Za-z_]+)")
_PCB_RE = re.compile(r"PCB|PCBA|HDI|印制板|覆铜板|\d+\s*层", re.IGNORECASE)


@dataclass(frozen=True)
class RiskRuleConfig:
    mechanical_keywords: tuple[str, ...] = DEFAULT_MECHANICAL_KEYWORDS
    shield_keywords: tuple[str, ...] = DEFAULT_SHIELD_KEYWORDS
    process_keywords: tuple[str, ...] = DEFAULT_PROCESS_KEYWORDS
    process_ref_prefixes: tuple[str, ...] = DEFAULT_PROCESS_PREFIXES
    grade_ok: tuple[str, ...] = DEFAULT_GRADE_OK
    version_sensitive: tuple[str, ...] = DEFAULT_VERSION_SENSITIVE
    expected_prefix_type: Mapping[str, str] = None  # type: ignore[assignment]
    code_prefix_type: Mapping[str, str] = None  # type: ignore[assignment]
    normal_units: tuple[str, ...] = DEFAULT_NORMAL_UNITS

    def __post_init__(self) -> None:
        if self.expected_prefix_type is None:
            object.__setattr__(self, "expected_prefix_type", DEFAULT_EXPECTED_TYPES)
        if self.code_prefix_type is None:
            object.__setattr__(self, "code_prefix_type", DEFAULT_EXPECTED_TYPES)


def _words(mapping: Mapping[str, object], key: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    raw = mapping.get(key)
    if not isinstance(raw, list):
        return fallback
    values = tuple(str(value).strip() for value in raw if str(value).strip())
    return values or fallback


def risk_rule_config(mapping: Mapping[str, object] | None = None) -> RiskRuleConfig:
    mapping = mapping or {}
    expected = mapping.get("expected_prefix_type")
    code_types = mapping.get("code_prefix_type")
    return RiskRuleConfig(
        mechanical_keywords=_words(mapping, "mechanical_keywords", DEFAULT_MECHANICAL_KEYWORDS),
        shield_keywords=_words(mapping, "shield_keywords", DEFAULT_SHIELD_KEYWORDS),
        process_keywords=_words(mapping, "process_keywords", DEFAULT_PROCESS_KEYWORDS),
        process_ref_prefixes=tuple(
            value.upper()
            for value in _words(mapping, "process_ref_prefixes", DEFAULT_PROCESS_PREFIXES)
        ),
        grade_ok=_words(mapping, "grade_ok", DEFAULT_GRADE_OK),
        version_sensitive=_words(mapping, "version_sensitive", DEFAULT_VERSION_SENSITIVE),
        expected_prefix_type={
            str(key).upper(): str(value)
            for key, value in (
                expected.items()
                if isinstance(expected, Mapping)
                else DEFAULT_EXPECTED_TYPES.items()
            )
        },
        code_prefix_type={
            str(key).upper(): str(value)
            for key, value in (
                code_types.items()
                if isinstance(code_types, Mapping)
                else DEFAULT_EXPECTED_TYPES.items()
            )
        },
        normal_units=tuple(
            value.upper()
            for value in _words(mapping, "normal_units", DEFAULT_NORMAL_UNITS)
        ),
    )


def load_risk_rule_config(root: Path) -> RiskRuleConfig:
    try:
        config = load_config(root)
    except (OSError, ValueError):
        return risk_rule_config()
    bom = config.get("bom") if isinstance(config, Mapping) else None
    risk = bom.get("risk") if isinstance(bom, Mapping) else None
    return risk_rule_config(risk if isinstance(risk, Mapping) else None)


def _contains(text: str, words: Iterable[str]) -> bool:
    upper = text.upper()
    return any(word.upper() in upper for word in words)


def _ref_prefix(ref: str) -> str:
    match = _REF_PREFIX_RE.match(ref)
    return match.group(1).upper() if match else ""


def _row_detail(row: RiskRow, **extra: object) -> dict[str, object]:
    return {
        "source_row": row.source_row,
        "parent_code": row.parent_code,
        "code": row.part_number,
        "name": row.name,
        "model": row.model,
        "desc": row.description,
        "quantity": str(row.quantity) if row.quantity is not None else "",
        "refs": ",".join(row.refs),
        "grade": row.grade,
        **extra,
    }


def _finding(
    code: str,
    name: str,
    level: str,
    message: str,
    details: Sequence[Mapping[str, object]] = (),
    *,
    applicable: bool = True,
) -> dict[str, object]:
    status = "warn" if level in {"blocker", "warn"} else level
    return {
        "code": code,
        "name": name,
        "level": level,
        "status": status,
        "message": message,
        "details": [dict(item) for item in details],
        "detail_count": len(details),
        "applicable": applicable,
    }


def _decimal_equal(quantity: Decimal | None, expected: int) -> bool:
    return quantity is None or quantity == Decimal(expected)


def _actual_type(row: RiskRow, config: RiskRuleConfig) -> str | None:
    text = f"{row.name} {row.description}".upper()
    for value in set(config.expected_prefix_type.values()):
        if value.upper() in text:
            return value
    match = re.match(r"^([A-Za-z]+)\.", row.part_number)
    if match:
        value = config.code_prefix_type.get(match.group(1).upper())
        if value:
            return value
    if re.search(r"\d\s*[MUNPΜµ]?H\b", row.model, re.IGNORECASE):
        return "电感"
    if re.search(r"\d\s*[MUNPΜµ]?F\b", row.model, re.IGNORECASE):
        return "电容"
    return None


def find_type_mismatches(
    rows: Sequence[RiskRow] | Sequence[Mapping[str, object]],
    config: RiskRuleConfig | None = None,
) -> list[dict[str, object]]:
    config = config or risk_rule_config()
    risk_rows = tuple(
        row if isinstance(row, RiskRow) else _legacy_row(row, index)
        for index, row in enumerate(rows, start=1)
    )
    result: list[dict[str, object]] = []
    for row in risk_rows:
        if not row.is_placement or row.is_nc:
            continue
        actual = _actual_type(row, config)
        if not actual:
            continue
        for ref in row.refs:
            prefix = _ref_prefix(ref)
            expected = config.expected_prefix_type.get(prefix)
            if expected and expected != actual:
                result.append(
                    {
                        **_row_detail(row),
                        "ref": ref,
                        "expected": expected,
                        "actual": actual,
                        "note": f"位号 {prefix}（通常为{expected}）实为{actual}",
                    }
                )
    return result


def _legacy_decimal(value: object) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def _legacy_row(row: Mapping[str, object], index: int) -> RiskRow:
    refs = tuple(str(ref).strip().upper() for ref in row.get("refs") or () if str(ref).strip())
    part_number = str(row.get("part_number") or row.get("material_code") or "").strip()
    description = str(row.get("description") or row.get("desc") or "").strip()
    is_parent = bool(
        not refs
        and _PCB_RE.search(
            f"{row.get('name','')} {row.get('model','')} {description}"
        )
    )
    priority = row.get("substitute_priority")
    try:
        normalized_priority = int(priority) if priority not in (None, "") else None
    except (TypeError, ValueError):
        normalized_priority = None
    group_code = str(row.get("substitute_group_code") or "").strip()
    nc_text = " ".join(
        str(row.get(field) or "")
        for field in ("value", "name", "description", "model")
    )
    is_nc = bool(
        row.get("is_nc")
        or re.search(
            r"(?:^|[\s,;/()（）_-])(?:NC|DNP|DNI|NO\s*LOAD|NOFIT|未贴|不贴|空贴)(?:$|[\s,;/()（）_-])",
            nc_text,
            re.IGNORECASE,
        )
    )
    return RiskRow(
        source_id=f"legacy:{index}",
        source_row=int(row.get("source_row") or index),
        parent_code=str(row.get("parent_code") or "").strip(),
        hardware_version=str(row.get("hardware_version") or "").strip(),
        part_number=part_number,
        name=str(row.get("name") or "").strip(),
        value=str(row.get("value") or "").strip(),
        model=str(row.get("model") or row.get("package") or "").strip(),
        description=description,
        unit=str(row.get("unit") or "").strip(),
        quantity=_legacy_decimal(row.get("quantity")),
        refs=refs,
        grade=str(row.get("grade") or "").strip(),
        remark=str(row.get("remark") or "").strip(),
        issue_method=str(row.get("issue_method") or "").strip(),
        mrp=str(row.get("mrp") or "").strip(),
        jump_level=str(row.get("jump_level") or "").strip(),
        substitute_group_code=group_code,
        substitute_strategy=str(row.get("substitute_strategy") or "").strip(),
        substitute_mode=str(row.get("substitute_mode") or "").strip(),
        substitute_priority=normalized_priority,
        is_nc=is_nc,
        is_parent=is_parent,
        is_substitute_main=bool(group_code and normalized_priority == 0),
        is_substitute_alternative=bool(group_code and normalized_priority is not None and normalized_priority > 0),
        quality_flags=tuple(str(value) for value in row.get("quality_flags") or ()),
        extra_fields={},
    )


def _legacy_model(rows: Sequence[Mapping[str, object]]) -> RiskModel:
    risk_rows = tuple(_legacy_row(row, index) for index, row in enumerate(rows, start=1))
    return RiskModel(
        source_path=Path(""),
        source_fingerprint="legacy",
        profile=WorkbookProfile.UNKNOWN,
        rows=risk_rows,
        substitute_groups=(),
        normalization_findings=(),
        parent_codes=tuple(sorted({row.parent_code for row in risk_rows if row.parent_code})),
    )


def _substitute_details(model: RiskModel) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    details: list[dict[str, object]] = []
    invalid: list[dict[str, object]] = []
    for group in model.substitute_groups:
        members = group.members
        priorities = [item.substitute_priority for item in members]
        strategies = {
            row.substitute_strategy.strip()
            for item in members for row in item.source_rows
            if row.substitute_strategy.strip()
        }
        modes = {
            row.substitute_mode.strip()
            for item in members for row in item.source_rows
            if row.substitute_mode.strip()
        }
        issues: list[str] = []
        if group.main_item is None:
            issues.append("缺少唯一优先级0主料")
        if not group.alternative_items:
            issues.append("没有替代料")
        if any(priority is None for priority in priorities):
            issues.append("优先级缺失")
        elif sorted(int(value) for value in priorities if value is not None) != list(range(len(members))):
            issues.append("优先级不连续")
        if group.main_item and not group.main_item.references:
            issues.append("主料缺少实际位号")
        if any(item.references for item in group.alternative_items):
            issues.append("替代料错误占用位号")
        quantities = {item.quantity for item in members}
        if len(quantities) > 1:
            issues.append("组内数量不一致")
        if not strategies:
            issues.append("替代策略未提供")
        if not modes:
            issues.append("替代方式未提供")
        item = {
            "parent_code": group.parent_code,
            "group_code": group.group_code,
            "main_code": group.main_item.material_code if group.main_item else "",
            "alternative_codes": ",".join(item.material_code for item in group.alternative_items),
            "priorities": ",".join(
                f"{item.substitute_priority}:{item.material_code}" for item in members
            ),
            "quantity": str(group.quantity) if group.quantity is not None else "",
            "refs": ",".join(group.physical_references),
            "strategy": " / ".join(sorted(strategies)),
            "mode": " / ".join(sorted(modes)),
            "issues": "；".join(issues),
        }
        details.append(item)
        if issues:
            invalid.append(item)
    return details, invalid


def evaluate_bom_risk_report(
    model: RiskModel,
    review_summary: Mapping[str, object] | None = None,
    placement_decisions: Sequence[Mapping[str, object]] | None = None,
    config: RiskRuleConfig | None = None,
) -> dict[str, object]:
    config = config or risk_rule_config()
    rows = model.rows
    placements = tuple(row for row in rows if row.is_placement)
    installed = tuple(row for row in placements if not row.is_nc)
    findings: list[dict[str, object]] = []

    profile_ok = model.profile != WorkbookProfile.UNKNOWN
    findings.append(_finding(
        "workbook_profile",
        "工作表格式识别",
        "ok" if profile_ok else "blocker",
        f"已识别为 {model.profile.value}" if profile_ok else "无法识别 BOM 工作表或表头。",
    ))
    normalization_problems = [
        finding for finding in model.normalization_findings
        if finding.severity in {FindingSeverity.BLOCKER, FindingSeverity.WARNING}
    ]
    findings.append(_finding(
        "required_fields",
        "必填字段/表头完整",
        "blocker" if any(item.severity == FindingSeverity.BLOCKER for item in normalization_problems) else ("warn" if normalization_problems else "ok"),
        "字段完整" if not normalization_problems else f"语义解析发现 {len(normalization_problems)} 项问题。",
        [item.payload() for item in normalization_problems],
    ))
    precision_rows = [row for row in rows if "identifier_precision_risk" in row.quality_flags]
    findings.append(_finding(
        "identifier_precision",
        "编码精度",
        "blocker" if precision_rows else "ok",
        f"{len(precision_rows)} 行编码可能已被科学计数法或浮点格式破坏。" if precision_rows else "编码按文本语义读取，未发现精度风险。",
        [_row_detail(row) for row in precision_rows],
    ))

    parents = [row for row in rows if row.is_parent]
    findings.append(_finding(
        "parent_pcb",
        "父项 PCB 裸板",
        "ok" if parents else "warn",
        f"识别到 {len(parents)} 条父项 PCB，自身不参与贴装数量统计。" if parents else "未识别到父项 PCB 行，请确认 BOM 范围。",
        [_row_detail(row) for row in parents],
    ))
    findings.append(_finding(
        "placement_scope",
        "位号/数量口径",
        "info",
        f"排除父项和替代料后，共 {len(installed)} 行、{len({ref for row in installed for ref in row.refs})} 个实际贴装位号。",
    ))

    by_ref: dict[str, list[RiskRow]] = defaultdict(list)
    for row in placements:
        for ref in row.refs:
            by_ref[ref].append(row)
    duplicates = [
        {"ref": ref, "codes": ",".join(sorted({row.part_number for row in owners}))}
        for ref, owners in by_ref.items() if len(owners) > 1
    ]
    findings.append(_finding(
        "duplicate_references", "重复位号",
        "blocker" if duplicates else "ok",
        f"发现 {len(duplicates)} 个重复位号。" if duplicates else "未发现重复位号。",
        duplicates,
    ))
    empty_codes = [row for row in placements if not row.part_number]
    findings.append(_finding(
        "empty_material_code", "空编码行",
        "blocker" if empty_codes else "ok",
        f"{len(empty_codes)} 行有位号但子项编码为空。" if empty_codes else "所有贴装行均有子项编码。",
        [_row_detail(row) for row in empty_codes],
    ))
    quantity_mismatches = [
        row for row in placements
        if not _decimal_equal(row.quantity, len(row.refs))
    ]
    findings.append(_finding(
        "quantity_reference_mismatch", "数量=位号数",
        "blocker" if quantity_mismatches else "ok",
        f"{len(quantity_mismatches)} 行数量与位号数不一致。" if quantity_mismatches else "所有适用行数量与位号数一致。",
        [_row_detail(row, reference_count=len(row.refs)) for row in quantity_mismatches],
    ))

    nc_items = [_row_detail(row) for row in placements if row.is_nc]
    findings.append(_finding(
        "nc_in_finished_bom", "NC/未贴器件",
        "warn" if nc_items else "ok",
        f"成品 BOM 中仍有 {len(nc_items)} 行 NC/未贴。" if nc_items else "未发现 NC/未贴，当前成品 BOM 已清洗。",
        nc_items,
    ))

    shield_rows: list[tuple[RiskRow, str]] = []
    mechanical_rows: list[RiskRow] = []
    process_rows: list[RiskRow] = []
    for row in placements:
        text = row.searchable_text
        has_sh_ref = any(ref.startswith("SH") for ref in row.refs)
        if has_sh_ref or _contains(text, config.shield_keywords):
            subtype = (
                "屏蔽支架" if "屏蔽支架" in text.upper() or "SHIELD BRACKET" in text.upper()
                else "屏蔽罩" if "屏蔽罩" in text.upper() or "SHIELD COVER" in text.upper()
                else "屏蔽类型待确认"
            )
            shield_rows.append((row, subtype))
        if _contains(text, config.mechanical_keywords):
            mechanical_rows.append(row)
        prefix_hit = any(
            any(ref.startswith(prefix) for prefix in config.process_ref_prefixes)
            for ref in row.refs
        )
        keyword_hit = _contains(text, config.process_keywords)
        protected_material = _contains(text, ("跳线电阻", "零欧电阻", "JUMPER RESISTOR", "ZERO OHM RESISTOR"))
        if keyword_hit or (prefix_hit and not protected_material):
            process_rows.append(row)
    shield_items = [_row_detail(row, subtype=subtype) for row, subtype in shield_rows]
    shield_unknown = [item for item in shield_items if item["subtype"] != "屏蔽支架"]
    decision_brackets = [
        item for item in placement_decisions or ()
        if str(item.get("role") or "") == "shield"
        and str(item.get("subtype") or "") == "bracket"
        and str(item.get("destination") or "") == "smt"
    ]
    decision_covers = [
        item for item in placement_decisions or ()
        if str(item.get("role") or "") == "shield"
        and str(item.get("subtype") or "") == "cover"
    ]
    if decision_brackets:
        codes = sorted({
            str((item.get("material_snapshot") or {}).get("part_number") or "")
            for item in decision_brackets
            if isinstance(item.get("material_snapshot"), Mapping)
        })
        shield_level = "ok"
        shield_message = "决策清单已确认屏蔽支架：" + "，".join(code for code in codes if code)
    elif decision_covers and not shield_items:
        shield_level = "info"
        shield_message = "决策清单仅包含屏蔽罩；屏蔽罩不会通过屏蔽支架检查。"
    else:
        shield_level = "warn" if shield_unknown else ("info" if shield_items else "ok")
        shield_message = (
            f"依据 BOM 属性识别到 {len(shield_items)} 行屏蔽类物料，其中 {len(shield_unknown)} 行类型待确认。"
            if shield_items else "未发现屏蔽支架。"
        )
    findings.append(_finding(
        "shield_items", "屏蔽支架",
        shield_level,
        shield_message,
        shield_items,
    ))
    mechanical_items = [_row_detail(row) for row in mechanical_rows]
    findings.append(_finding(
        "mechanical_items", "机构件",
        "info" if mechanical_items else "ok",
        f"识别到 {len(mechanical_items)} 行机构/贴片机械物料，请确认装配范围。" if mechanical_items else "未发现机构件。",
        mechanical_items,
    ))
    process_items = [_row_detail(row) for row in process_rows]
    findings.append(_finding(
        "process_items", "测试点/工艺项",
        "warn" if process_items else "ok",
        f"识别到 {len(process_items)} 行测试点或工艺项，请确认是否应进入成品 BOM。" if process_items else "未发现测试点或工艺项。",
        process_items,
    ))

    type_flags = find_type_mismatches(placements, config)
    findings.append(_finding(
        "reference_type_mismatch", "位号/器件类型",
        "warn" if type_flags else "ok",
        f"{len(type_flags)} 处位号与物料类型不一致。" if type_flags else "未发现位号与器件类型冲突。",
        type_flags,
    ))
    grade_flags = [
        _row_detail(row) for row in rows
        if row.grade and row.grade not in config.grade_ok
    ]
    grade_dist = Counter(row.grade for row in rows if row.grade)
    findings.append(_finding(
        "material_grade", "物料优选等级",
        "warn" if grade_flags else ("ok" if grade_dist else "info"),
        (
            f"{len(grade_flags)} 项非优选/正常："
            + "，".join(f"{key}×{value}" for key, value in Counter(row["grade"] for row in grade_flags).most_common())
            if grade_flags else ("均为优选/正常。" if grade_dist else "来源未提供物料等级。")
        ),
        grade_flags,
    ))

    substitute_groups, invalid_groups = _substitute_details(model)
    findings.append(_finding(
        "substitute_groups", "替代组结构",
        "warn" if invalid_groups else ("info" if substitute_groups else "ok"),
        (
            f"共 {len(substitute_groups)} 个替代组，{len(invalid_groups)} 个需要确认。"
            if substitute_groups else "当前 BOM 没有替代组。"
        ),
        invalid_groups,
    ))

    issue_dist = Counter(row.issue_method or "未提供" for row in rows)
    known_issue = {"直接领料", "直接发料", "未提供"}
    unusual_issue = [value for value in issue_dist if value not in known_issue]
    findings.append(_finding(
        "issue_method", "发料方式分布",
        "warn" if unusual_issue else "info",
        "，".join(f"{key}×{value}" for key, value in issue_dist.most_common()),
        [{"value": key, "count": value} for key, value in issue_dist.items()],
    ))
    mrp_dist = Counter(row.mrp or "未提供" for row in rows)
    jump_dist = Counter(row.jump_level or "未提供" for row in rows)
    findings.append(_finding(
        "mrp_jump_level", "MRP/跳层",
        "info",
        "MRP：" + "，".join(f"{key}×{value}" for key, value in mrp_dist.items())
        + "；跳层：" + "，".join(f"{key}×{value}" for key, value in jump_dist.items()),
    ))

    version_sensitive = [
        _row_detail(row) for row in rows
        if _contains(row.searchable_text, config.version_sensitive)
    ]
    findings.append(_finding(
        "version_sensitive", "硬件版本敏感物料",
        "info" if version_sensitive else "ok",
        (
            f"发现 {len(version_sensitive)} 项版本敏感物料："
            + "，".join(str(item.get("code") or "") for item in version_sensitive[:10])
            + "；请核对硬件版本号、容量/速率和替代关系。"
            if version_sensitive else "未发现配置中的版本敏感物料。"
        ),
        version_sensitive,
    ))
    remark_items = [_row_detail(row, remark=row.remark) for row in rows if row.remark]
    findings.append(_finding(
        "remarks", "备注/工程编号",
        "info",
        f"{len(remark_items)} 行包含备注或工程编号。" if remark_items else "没有非空备注。",
        remark_items,
    ))
    unit_flags = [
        _row_detail(row) for row in rows
        if not row.unit or row.unit.upper() not in config.normal_units
    ]
    findings.append(_finding(
        "unit_consistency", "单位一致性",
        "warn" if unit_flags else "ok",
        f"{len(unit_flags)} 行单位为空或不在允许值中。" if unit_flags else "单位一致。",
        unit_flags,
    ))

    decisions = [item for item in placement_decisions or () if isinstance(item, Mapping)]
    if placement_decisions is None:
        findings.append(_finding(
            "decision_manifest_consistency", "BOM/决策清单一致性",
            "info", "独立检查未提供决策清单，本项不适用。",
            applicable=False,
        ))
    else:
        bom_refs = {ref for row in placements for ref in row.refs}
        smt_refs = {
            str(ref).strip().upper()
            for item in decisions if str(item.get("destination") or "") == "smt"
            for ref in item.get("refs") or () if str(ref).strip()
        }
        non_smt_refs = {
            str(ref).strip().upper()
            for item in decisions if str(item.get("destination") or "") == "non_smt"
            for ref in item.get("refs") or () if str(ref).strip()
        }
        leaked = sorted(bom_refs & non_smt_refs)
        missing = sorted(smt_refs - bom_refs)
        decision_issues = [
            *({"kind": "非贴片位号混入", "ref": ref} for ref in leaked),
            *({"kind": "贴片位号缺失", "ref": ref} for ref in missing),
        ]
        findings.append(_finding(
            "decision_manifest_consistency", "BOM/决策清单一致性",
            "warn" if decision_issues else "ok",
            f"发现 {len(decision_issues)} 项不一致。" if decision_issues else "BOM 与决策清单一致。",
            decision_issues,
        ))

    if review_summary:
        findings.append(_finding(
            "manual_review", "装机人工审查", "info",
            f"已人工确认纳入 {int(review_summary.get('kept_groups') or 0)} 组、确认不装 {int(review_summary.get('excluded_groups') or 0)} 组。",
        ))

    counts = Counter(str(item["level"]) for item in findings)
    stats = {
        "数据行": len(rows),
        "有效贴装行": len(installed),
        "位号数": len({ref for row in installed for ref in row.refs}),
        "料号数": len({row.part_number for row in installed if row.part_number}),
        "替代组数": len(model.substitute_groups),
        "父项数": len(parents),
    }
    return {
        "profile": model.profile.value,
        "stats": stats,
        "findings": findings,
        "counts_by_level": {
            level: counts.get(level, 0) for level in ("blocker", "warn", "info", "ok")
        },
        "grade_flags": grade_flags,
        "type_flags": type_flags,
        "substitute_groups": substitute_groups,
        "shield_items": shield_items,
        "mechanical_items": mechanical_items,
        "process_items": process_items,
        "nc_items": nc_items,
        "issue_method_dist": dict(issue_dist),
        "mrp_dist": dict(mrp_dist),
        "jump_level_dist": dict(jump_dist),
        "version_sensitive": version_sensitive,
        "remark_items": remark_items,
        "unit_flags": unit_flags,
    }


def evaluate_bom_risks(
    rows: RiskModel | Sequence[Mapping[str, object]],
    review_summary: Mapping[str, object] | None = None,
    placement_decisions: Sequence[Mapping[str, object]] | None = None,
    config: RiskRuleConfig | None = None,
) -> list[dict[str, object]]:
    model = rows if isinstance(rows, RiskModel) else _legacy_model(rows)
    return list(
        evaluate_bom_risk_report(
            model,
            review_summary,
            placement_decisions,
            config,
        )["findings"]
    )
