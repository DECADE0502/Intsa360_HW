from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from app.backend.config import load_config
from app.backend.parsers.refs import natural_key


DEFAULT_MATERIAL_CODE_SHAPES: tuple[dict[str, str], ...] = (
    {
        "id": "digits",
        "pattern": r"^\d{6,20}$",
        "note": "纯数字内部编码",
    },
    {
        "id": "dotted",
        "pattern": r"^[A-Za-z][A-Za-z0-9]{0,7}\.[A-Za-z0-9][A-Za-z0-9._-]{2,}$",
        "note": "带点分段编码",
    },
    {
        "id": "vendor_mpn",
        "pattern": r"^[A-Za-z][A-Za-z0-9]{1,15}[-_][A-Za-z0-9][A-Za-z0-9-_/.]{2,}$",
        "note": "厂商 MPN",
    },
)

DEFAULT_NC_KEYWORDS = ("NC", "DNP", "DNI", "No Load", "NOFIT", "不贴", "未贴", "空贴")

CODE_CANDIDATE_FIELDS = (
    "value",
    "model",
    "source_part",
    "desc",
    "name",
    "source_package",
    "part_number",
)

MATERIAL_ATTRIBUTE_FIELDS = (
    "value",
    "name",
    "model",
    "desc",
    "pcb_footprint",
    "pcb_package",
    "source_package",
    "source_part",
)

FIELD_DISPLAY_NAMES = {
    "part_number": "子项编码",
    "value": "器件值",
    "name": "物料名称",
    "model": "型号",
    "desc": "描述",
    "pcb_footprint": "PCB 封装",
    "pcb_package": "Capture PCB 封装",
    "source_package": "原理图封装",
    "source_part": "原理图库器件",
}

FINGERPRINT_FIELDS = (
    "part_number",
    "value",
    "name",
    "model",
    "desc",
    "pcb_footprint",
    "pcb_package",
    "source_package",
    "source_part",
    "grade",
    "unit",
)

_PROCESS_KEYWORDS_STRONG = (
    "测试点",
    "跳线",
    "短接",
    "安装孔",
    "定位孔",
)
_PROCESS_KEYWORDS_AMBIGUOUS = (
    "铜柱",
    "螺柱",
    "螺母柱",
    "支柱",
    "结构件",
    "螺丝",
    "螺钉",
    "螺母",
    "垫片",
    "华司",
    "散热片",
    "导热垫",
    "屏蔽罩",
)
_PROCESS_MATERIAL_PHRASES = (
    "跳线电阻",
    "零欧电阻",
    "JUMPER RESISTOR",
    "ZERO OHM RESISTOR",
)
_PROCESS_ENGLISH_RE = re.compile(
    r"(?:^|[\s,;/()（）_-])"
    r"(TEST\s*POINT|JUMPER|SHORT(?:ING)?|MOUNTING\s*HOLE|MOUNTINGHOLE|FIDUCIAL|SCREW)"
    r"(?=$|[\s,;/()（）_-])",
    re.IGNORECASE,
)
# Compatibility export for legacy callers. New classification code uses process_keyword(),
# which handles Chinese terms embedded in longer descriptions without relying on word boundaries.
PROCESS_MATERIAL_RE = re.compile(
    "|".join(
        re.escape(value)
        for value in (*_PROCESS_KEYWORDS_STRONG, *_PROCESS_KEYWORDS_AMBIGUOUS)
    )
    + r"|(?:^|[\s,;/()（）_-])(?:TEST\s*POINT|JUMPER|SHORT(?:ING)?|MOUNTING\s*HOLE|MOUNTINGHOLE|FIDUCIAL|SCREW)(?=$|[\s,;/()（）_-])",
    re.IGNORECASE,
)

_NUMERIC_SPEC_RE = re.compile(
    r"^\d+(?:\.\d+)?(?:\s*[RrKkMmGgTtUuNnPpFfHhVv]\d*)?"
    r"\s*(?:Ω|ohms?|%|℃|°C|[VvAaWwFfHh])?$",
    re.IGNORECASE,
)
_ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:[^/]+/)+)")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_REF_PREFIX_RE = re.compile(r"^([A-Za-z_]+)")
_CAPTURE_SOURCE_PART_SUFFIX_RE = re.compile(r"\.(?:NORMAL|DEMORGAN|CONVERT)$", re.IGNORECASE)


@dataclass(frozen=True)
class CodeShape:
    id: str
    pattern: re.Pattern[str]
    note: str


@dataclass(frozen=True)
class ClassificationConfig:
    code_shapes: tuple[CodeShape, ...]
    nc_keywords: tuple[str, ...]


@dataclass(frozen=True)
class FieldValue:
    raw: str
    cleaned: str
    flags: frozenset[str]
    provenance: str = "cell"

    def payload(self) -> dict[str, object]:
        return {
            "raw": self.raw,
            "cleaned": self.cleaned,
            "flags": sorted(self.flags),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class NormalizedBomRow:
    row_number: int
    refs: tuple[str, ...]
    fields: dict[str, FieldValue]
    fingerprint: str

    def value(self, field: str) -> str:
        item = self.fields.get(field)
        return item.cleaned if item is not None else ""


@dataclass(frozen=True)
class MaterialEvidence:
    kind: str
    field: str
    value: str
    polarity: str
    strength: str
    display: str
    shape_id: str = ""

    def payload(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "field": self.field,
            "value": self.value,
            "polarity": self.polarity,
            "strength": self.strength,
            "display": self.display,
            "shape_id": self.shape_id,
        }


@dataclass(frozen=True)
class ClassificationResult:
    state: str
    confidence: str
    evidence: tuple[MaterialEvidence, ...]
    recommended_action: str | None
    suggested_code: str
    sh_review: bool
    rule_id: str

    @property
    def requires_review(self) -> bool:
        return self.sh_review or self.state in {
            "suspected_material",
            "suspected_process",
            "insufficient_data",
            "conflicting",
        }


@dataclass(frozen=True)
class ClassifiedRow:
    row: NormalizedBomRow
    classification: ClassificationResult


@dataclass(frozen=True)
class ReviewGroup:
    key: str
    row_numbers: tuple[int, ...]
    refs: tuple[str, ...]
    classification: ClassificationResult
    original_fields: dict[str, str]
    inferred_fields: dict[str, str]

    @property
    def category(self) -> str:
        if self.classification.sh_review:
            return "shield"
        return self.classification.state

    def payload(self) -> dict[str, object]:
        classification = self.classification
        return {
            "key": self.key,
            "row_numbers": list(self.row_numbers),
            "refs": list(self.refs),
            "position_count": len(self.refs),
            "state": classification.state,
            "category": self.category,
            "confidence": classification.confidence,
            "recommended_action": classification.recommended_action,
            "suggested_code": classification.suggested_code,
            "sh_review": classification.sh_review,
            "rule_id": classification.rule_id,
            "evidence": [item.payload() for item in classification.evidence],
            "original_fields": dict(self.original_fields),
            "inferred_fields": dict(self.inferred_fields),
        }


@dataclass(frozen=True)
class PlacementAnalysis:
    rows: tuple[ClassifiedRow, ...]
    review_groups: tuple[ReviewGroup, ...]
    readonly_nc: tuple[dict[str, object], ...]

    def payload(self) -> dict[str, object]:
        state_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        for item in self.rows:
            state = item.classification.state
            state_counts[state] = state_counts.get(state, 0) + 1
        for group in self.review_groups:
            category_counts[group.category] = category_counts.get(group.category, 0) + 1
        return {
            "groups": [group.payload() for group in self.review_groups],
            "readonly_nc": {
                "count": len(self.readonly_nc),
                "items": list(self.readonly_nc[:50]),
            },
            "summary": {
                "review_groups": len(self.review_groups),
                "review_positions": sum(len(group.refs) for group in self.review_groups),
                "readonly_nc": len(self.readonly_nc),
                "state_counts": state_counts,
                "category_counts": category_counts,
            },
        }


def _compiled_shapes(raw_shapes: object) -> tuple[CodeShape, ...]:
    shapes = raw_shapes if isinstance(raw_shapes, list) else list(DEFAULT_MATERIAL_CODE_SHAPES)
    compiled: list[CodeShape] = []
    for item in shapes:
        if not isinstance(item, Mapping):
            continue
        identifier = str(item.get("id") or "").strip()
        pattern = str(item.get("pattern") or "").strip()
        note = str(item.get("note") or identifier).strip()
        if not identifier or not pattern:
            continue
        try:
            compiled.append(CodeShape(identifier, re.compile(pattern, re.IGNORECASE), note))
        except re.error:
            continue
    if compiled:
        return tuple(compiled)
    return _compiled_shapes(list(DEFAULT_MATERIAL_CODE_SHAPES))


def classification_config(mapping: Mapping[str, object] | None = None) -> ClassificationConfig:
    mapping = mapping or {}
    raw_keywords = mapping.get("nc_keywords")
    keywords = tuple(
        str(value).strip()
        for value in (raw_keywords if isinstance(raw_keywords, list) else DEFAULT_NC_KEYWORDS)
        if str(value).strip()
    )
    return ClassificationConfig(
        code_shapes=_compiled_shapes(mapping.get("material_code_shapes")),
        nc_keywords=keywords or DEFAULT_NC_KEYWORDS,
    )


def load_classification_config(root: Path) -> ClassificationConfig:
    try:
        config = load_config(root)
    except (OSError, ValueError):
        return classification_config()
    bom_config = config.get("bom") if isinstance(config, Mapping) else None
    return classification_config(bom_config if isinstance(bom_config, Mapping) else None)


def clean_field_text(value: object) -> str:
    text = str(value or "").lstrip("\ufeff")
    return unicodedata.normalize("NFKC", text).strip()


def _generic_flags(raw: str, cleaned: str) -> set[str]:
    flags: set[str] = set()
    if not cleaned:
        flags.add("empty")
        return flags
    if cleaned.startswith("{") or re.fullmatch(r"\{[^}]*\}?", cleaned):
        flags.add("placeholder_residue")
    if "\ufffd" in raw or "锟斤拷" in raw:
        flags.add("mojibake")
    if _NUMERIC_SPEC_RE.fullmatch(cleaned):
        flags.add("numeric_spec")
    if _ABSOLUTE_PATH_RE.search(cleaned) or "\\" in cleaned:
        flags.add("path_like")
    return flags


def make_field_value(value: object, provenance: str = "cell") -> FieldValue:
    raw = str(value or "")
    cleaned = clean_field_text(raw)
    return FieldValue(raw, cleaned, frozenset(_generic_flags(raw, cleaned)), provenance)


def _fingerprint(refs: Sequence[str], fields: Mapping[str, FieldValue], prefix: str = "row") -> str:
    values = [prefix, *(ref.casefold() for ref in sorted(set(refs), key=natural_key))]
    values.extend(fields.get(field, make_field_value("")).cleaned.casefold() for field in FINGERPRINT_FIELDS)
    return hashlib.sha1("\x1f".join(values).encode("utf-8")).hexdigest()[:16]


def build_normalized_row(
    row_number: int,
    refs: Iterable[str],
    values: Mapping[str, object],
    provenance: Mapping[str, str] | None = None,
) -> NormalizedBomRow:
    normalized_refs = tuple(sorted({str(ref).strip() for ref in refs if str(ref).strip()}, key=natural_key))
    source = provenance or {}
    fields = {
        field: make_field_value(values.get(field), str(source.get(field) or "cell"))
        for field in values
    }
    for field in FINGERPRINT_FIELDS:
        fields.setdefault(field, make_field_value(""))
    return NormalizedBomRow(row_number, normalized_refs, fields, _fingerprint(normalized_refs, fields))


def _nc_pattern(keyword: str) -> str:
    escaped = re.escape(keyword.strip()).replace(r"\ ", r"\s+")
    return rf"(?:^|[\s,;/()（）]){escaped}(?=$|[\s,;/()（）])"


def contains_nc_keyword(value: str, config: ClassificationConfig) -> str:
    text = clean_field_text(value)
    for keyword in config.nc_keywords:
        if re.search(_nc_pattern(keyword), text, re.IGNORECASE):
            return keyword
    return ""


def _nc_value_pattern(keywords: tuple[str, ...]) -> re.Pattern[str]:
    choices = "|".join(re.escape(keyword).replace(r"\ ", r"\s+") for keyword in keywords)
    return re.compile(rf"^(?:{choices})(?:\s*[/,，(（].*)?$", re.IGNORECASE)


def is_pure_nc_marker(value: str, config: ClassificationConfig) -> bool:
    """整格内容就是 NC/DNP 标记本身（Capture 里最常见的 NC 表达），而非嵌在描述文本里。"""
    text = clean_field_text(value)
    return bool(text) and bool(_nc_value_pattern(config.nc_keywords).fullmatch(text))


def code_shape_matches(value: str, config: ClassificationConfig) -> tuple[CodeShape, ...]:
    text = clean_field_text(value)
    return tuple(shape for shape in config.code_shapes if shape.pattern.fullmatch(text))


def _candidate_code_values(field: str, value: str) -> tuple[str, ...]:
    text = clean_field_text(value)
    if not text:
        return ()
    if field == "source_part" and _CAPTURE_SOURCE_PART_SUFFIX_RE.search(text):
        base = _CAPTURE_SOURCE_PART_SUFFIX_RE.sub("", text).strip()
        return (base,) if base else ()
    return (text,)


def process_keyword(value: str) -> str:
    text = clean_field_text(value)
    probe = text
    for phrase in _PROCESS_MATERIAL_PHRASES:
        probe = re.sub(re.escape(phrase), " ", probe, flags=re.IGNORECASE)
    for keyword in (*_PROCESS_KEYWORDS_STRONG, *_PROCESS_KEYWORDS_AMBIGUOUS):
        if keyword in probe:
            return keyword
    match = _PROCESS_ENGLISH_RE.search(probe)
    return match.group(1) if match else ""


def _process_keyword_strength(keyword: str) -> str:
    return "medium" if keyword in _PROCESS_KEYWORDS_AMBIGUOUS else "strong"


def _enrich_row(row: NormalizedBomRow, config: ClassificationConfig) -> NormalizedBomRow:
    fields: dict[str, FieldValue] = {}
    for field, item in row.fields.items():
        flags = set(item.flags)
        if any(
            code_shape_matches(candidate, config) and not process_keyword(candidate)
            for candidate in _candidate_code_values(field, item.cleaned)
        ):
            flags.add("code_shape")
        if contains_nc_keyword(item.cleaned, config):
            flags.add("nc_keyword")
        if process_keyword(item.cleaned):
            flags.add("process_keyword")
        fields[field] = replace(item, flags=frozenset(flags))
    return replace(row, fields=fields)


def _valid_value(item: FieldValue | None) -> bool:
    return bool(item and item.cleaned and not {"placeholder_residue", "mojibake"}.intersection(item.flags))


def _looks_like_description_in_part_number(value: str) -> bool:
    text = clean_field_text(value)
    if not text:
        return False
    if _CJK_RE.search(text) and len(text) >= 6:
        return True
    return len(text) >= 20 and bool(re.search(r"\s", text))


def collect_evidence(row: NormalizedBomRow, config: ClassificationConfig) -> tuple[MaterialEvidence, ...]:
    enriched = _enrich_row(row, config)
    evidence: list[MaterialEvidence] = []
    for field, item in enriched.fields.items():
        field_name = FIELD_DISPLAY_NAMES.get(field, field)
        if "placeholder_residue" in item.flags:
            evidence.append(MaterialEvidence(
                "placeholder_residue",
                field,
                item.raw[:80],
                "neutral",
                "strong",
                f"{field_name} 含 Capture 占位残渣",
            ))
        if "mojibake" in item.flags:
            evidence.append(MaterialEvidence(
                "mojibake",
                field,
                item.raw[:80],
                "neutral",
                "strong",
                f"{field_name} 含异常字符",
            ))
        if "path_like" in item.flags:
            evidence.append(MaterialEvidence(
                "field_misplacement",
                field,
                item.cleaned[:80],
                "neutral",
                "strong",
                f"{field_name} 疑似填入了文件路径",
                "path_like",
            ))
        if field in CODE_CANDIDATE_FIELDS:
            for candidate in _candidate_code_values(field, item.cleaned):
                if process_keyword(candidate):
                    continue
                for shape in code_shape_matches(candidate, config):
                    evidence.append(MaterialEvidence(
                        "code_shape",
                        field,
                        candidate[:80],
                        "material+",
                        "strong" if field in {"value", "model", "source_part"} else "medium",
                        f"{field_name} 命中编码形状（{shape.note}）",
                        shape.id,
                    ))
        keyword = contains_nc_keyword(item.cleaned, config)
        if keyword and field in {"value", "desc"}:
            evidence.append(MaterialEvidence(
                "nc_keyword",
                field,
                keyword,
                "nc",
                "strong",
                f"{field_name} 命中不装标记（{keyword}）",
            ))
        keyword = process_keyword(item.cleaned)
        if keyword and field in {"value", "name", "model", "desc", "pcb_package", "pcb_footprint"}:
            evidence.append(MaterialEvidence(
                "process_keyword",
                field,
                keyword,
                "process",
                _process_keyword_strength(keyword),
                f"{field_name} 命中工艺关键词（{keyword}）",
            ))

    material_fields = [
        field
        for field in ("name", "model", "desc", "value")
        if _valid_value(enriched.fields.get(field))
    ]
    if material_fields:
        evidence.append(MaterialEvidence(
            "material_attrs",
            ",".join(material_fields),
            "",
            "material+",
            "medium",
            "存在名称、型号、描述或 Value 物料属性",
        ))
    library_fields = [
        field
        for field in ("pcb_footprint", "pcb_package", "source_package", "source_part")
        if _valid_value(enriched.fields.get(field))
    ]
    if library_fields:
        evidence.append(MaterialEvidence(
            "library_info",
            ",".join(library_fields),
            "",
            "material+",
            "medium",
            "存在封装或原理图库信息",
        ))

    prefixes = sorted({match.group(1).upper() for ref in row.refs if (match := _REF_PREFIX_RE.match(ref))})
    if prefixes:
        evidence.append(MaterialEvidence(
            "ref_prefix",
            "refs",
            ",".join(prefixes),
            "neutral",
            "weak",
            f"位号前缀 {','.join(prefixes)} 仅作为排序提示，不参与装机结论",
        ))

    part_number = enriched.value("part_number")
    if part_number and _looks_like_description_in_part_number(part_number):
        evidence.append(MaterialEvidence(
            "field_misplacement",
            "part_number",
            part_number[:80],
            "neutral",
            "strong",
            "子项编码列疑似填入了描述文本",
        ))
    if not part_number:
        for item in tuple(evidence):
            if item.kind == "code_shape" and item.field in {"desc", "name", "source_part", "source_package"}:
                evidence.append(MaterialEvidence(
                    "field_misplacement",
                    item.field,
                    item.value,
                    "material+",
                    "medium",
                    f"{FIELD_DISPLAY_NAMES.get(item.field, item.field)} 中疑似存在错位物料编码",
                ))
    return tuple(evidence)


def _suggested_code(evidence: Sequence[MaterialEvidence]) -> str:
    priority = {field: index for index, field in enumerate(CODE_CANDIDATE_FIELDS)}
    candidates = [item for item in evidence if item.kind == "code_shape" and item.field != "part_number"]
    if not candidates:
        return ""
    return min(candidates, key=lambda item: (priority.get(item.field, 99), -len(item.value))).value


def _has_valid_part_number(row: NormalizedBomRow, config: ClassificationConfig) -> bool:
    item = row.fields.get("part_number")
    if not _valid_value(item):
        return False
    assert item is not None
    if "path_like" in item.flags:
        return False
    if contains_nc_keyword(item.cleaned, config):
        return False
    return not _looks_like_description_in_part_number(item.cleaned)


def classify(row: NormalizedBomRow, config: ClassificationConfig) -> ClassificationResult:
    row = _enrich_row(row, config)
    evidence = collect_evidence(row, config)
    valid_part_number = _has_valid_part_number(row, config)
    raw_part_number = row.value("part_number")
    nc_signal = any(item.kind == "nc_keyword" for item in evidence)
    process_signal = any(item.kind == "process_keyword" for item in evidence)
    strong_process_signal = any(
        item.kind == "process_keyword" and item.strength == "strong"
        for item in evidence
    )
    misplaced_part_number = any(
        item.kind == "field_misplacement" and item.field == "part_number"
        for item in evidence
    )
    misplaced_path = any(
        item.kind == "field_misplacement" and item.shape_id == "path_like"
        for item in evidence
    )
    suggested_code = _suggested_code(evidence)
    has_sh_ref = any(ref.upper().startswith("SH") for ref in row.refs)
    sh_review = has_sh_ref and not nc_signal
    substantive = any(
        _valid_value(row.fields.get(field))
        for field in MATERIAL_ATTRIBUTE_FIELDS
    )

    if raw_part_number and (not valid_part_number or misplaced_part_number):
        return ClassificationResult("conflicting", "strong", evidence, None, suggested_code, sh_review, "R7")
    if misplaced_path:
        return ClassificationResult("conflicting", "strong", evidence, None, suggested_code, sh_review, "R7")
    if valid_part_number and nc_signal:
        # Value 整格就是 NC 标记时（器件库自带编码 + Value=NC）是 Capture 的标准 NC 表达，
        # 按系统明确 NC 处理；只有 NC 词嵌在更长文本里才构成需要人工裁决的属性冲突。
        # SH 位号例外：屏蔽支架即使标了 NC 也必须经人工审查确认，不允许静默排除。
        if is_pure_nc_marker(row.value("value"), config) and not has_sh_ref:
            return ClassificationResult("confirmed_nc", "strong", evidence, "exclude", "", False, "R2C")
        return ClassificationResult("conflicting", "strong", evidence, None, "", sh_review, "R7")
    if not valid_part_number and nc_signal:
        return ClassificationResult("confirmed_nc", "strong", evidence, "exclude", "", False, "R2")
    if valid_part_number and process_signal:
        return ClassificationResult("suspected_process", "strong", evidence, "exclude", "", sh_review, "R4")
    if valid_part_number and sh_review:
        return ClassificationResult("confirmed_material", "strong", evidence, "keep", "", True, "R3")
    if valid_part_number:
        return ClassificationResult("confirmed_material", "strong", evidence, "keep", "", False, "R1")
    if suggested_code:
        if strong_process_signal:
            return ClassificationResult("suspected_process", "strong", evidence, "exclude", suggested_code, sh_review, "R6P")
        return ClassificationResult("suspected_material", "strong", evidence, "keep", suggested_code, sh_review, "R5")
    if substantive:
        if strong_process_signal:
            return ClassificationResult("suspected_process", "weak", evidence, "exclude", "", sh_review, "R6P")
        return ClassificationResult("suspected_material", "weak", evidence, None, "", sh_review, "R6M")
    return ClassificationResult("insufficient_data", "weak", evidence, "exclude", "", sh_review, "R8")


def _group_signature(item: ClassifiedRow) -> tuple[object, ...]:
    row = item.row
    result = item.classification
    field_signature = tuple(row.value(field).casefold() for field in FINGERPRINT_FIELDS)
    substantive_count = sum(_valid_value(row.fields.get(field)) for field in MATERIAL_ATTRIBUTE_FIELDS)
    corroborated_code = bool(result.suggested_code) and substantive_count >= 2
    stable_group = corroborated_code or substantive_count >= 2 or result.state == "suspected_process" or result.sh_review
    return (
        result.state,
        result.confidence,
        result.suggested_code.casefold(),
        result.sh_review,
        *field_signature,
        None if stable_group else row.row_number,
    )


def _group_key(items: Sequence[ClassifiedRow]) -> str:
    first = items[0]
    refs = sorted({ref for item in items for ref in item.row.refs}, key=natural_key)
    values = [first.classification.state, *(ref.casefold() for ref in refs)]
    values.extend(first.row.value(field).casefold() for field in FINGERPRINT_FIELDS)
    return hashlib.sha1("\x1f".join(values).encode("utf-8")).hexdigest()[:16]


def analyze_placement(rows: Sequence[NormalizedBomRow], config: ClassificationConfig) -> PlacementAnalysis:
    classified = tuple(ClassifiedRow(_enrich_row(row, config), classify(row, config)) for row in rows)
    grouped: "OrderedDict[tuple[object, ...], list[ClassifiedRow]]" = OrderedDict()
    readonly_nc: list[dict[str, object]] = []
    for item in classified:
        result = item.classification
        if result.state == "confirmed_nc":
            readonly_nc.append({
                "row_number": item.row.row_number,
                "refs": list(item.row.refs),
                "value": item.row.value("value"),
                "description": item.row.value("desc"),
                "rule_id": result.rule_id,
                "evidence": [e.payload() for e in result.evidence],
            })
        if result.requires_review:
            grouped.setdefault(_group_signature(item), []).append(item)

    review_groups: list[ReviewGroup] = []
    for items in grouped.values():
        first = items[0]
        refs = tuple(sorted({ref for item in items for ref in item.row.refs}, key=natural_key))
        rows_in_group = tuple(sorted(item.row.row_number for item in items))
        original = {field: first.row.fields[field].raw for field in FINGERPRINT_FIELDS if field in first.row.fields}
        inferred = {
            field: first.row.value(field) if _valid_value(first.row.fields.get(field)) else ""
            for field in FINGERPRINT_FIELDS
        }
        if first.classification.suggested_code:
            inferred["part_number"] = first.classification.suggested_code
        review_groups.append(ReviewGroup(
            _group_key(items),
            rows_in_group,
            refs,
            first.classification,
            original,
            inferred,
        ))
    return PlacementAnalysis(classified, tuple(review_groups), tuple(readonly_nc))


def _resolution_patch(resolution: Mapping[str, object]) -> dict[str, str]:
    raw_patch = resolution.get("field_patch")
    patch = raw_patch if isinstance(raw_patch, Mapping) else resolution
    cleaned: dict[str, str] = {}
    for field in ("name", "model", "desc", "grade", "unit"):
        value = make_field_value(patch.get(field))
        if _valid_value(value):
            cleaned[field] = value.cleaned
    return cleaned


def _exclude_reason(state: str) -> tuple[str, str]:
    mapping = {
        "confirmed_nc": ("NC/未贴（系统明确判定）", "system_nc"),
        "suspected_process": ("用户确认不装（疑似工艺件）", "process_default"),
        "insufficient_data": ("用户确认不装（数据不足）", "insufficient_default"),
        "conflicting": ("用户确认不装（属性冲突）", "user_excluded"),
        "suspected_material": ("用户确认不装（疑似物料）", "user_excluded"),
        "confirmed_material": ("用户确认不装（屏蔽支架复核）", "user_excluded"),
    }
    return mapping.get(state, ("用户确认不装", "user_excluded"))


def apply_resolutions(
    parsed,
    analysis: PlacementAnalysis,
    resolutions: Mapping[str, object] | None,
):
    from app.backend.tools.bom_process import ParsedSource

    supplied = resolutions if isinstance(resolutions, Mapping) else {}
    missing = [group for group in analysis.review_groups if not isinstance(supplied.get(group.key), Mapping)]
    if missing:
        refs = "；".join(",".join(group.refs[:4]) or f"原始行 {group.row_numbers[0]}" for group in missing[:5])
        raise ValueError(f"仍有 {len(missing)} 组装机判定未确认：{refs}")

    group_by_row = {
        row_number: group
        for group in analysis.review_groups
        for row_number in group.row_numbers
    }
    classified_by_row = {item.row.row_number: item for item in analysis.rows}
    rows = [dict(row) for row in parsed.raw_rows]
    summary: dict[str, object] = {
        "groups": len(analysis.review_groups),
        "positions": sum(len(group.refs) for group in analysis.review_groups),
        "reviewed_groups": len(analysis.review_groups),
        "kept_groups": 0,
        "excluded_groups": 0,
        "user_touched_groups": 0,
        "state_counts": {},
        "category_counts": {},
        "reason_counts": {},
    }
    for item in analysis.rows:
        state_counts = summary["state_counts"]
        assert isinstance(state_counts, dict)
        state = item.classification.state
        state_counts[state] = int(state_counts.get(state, 0)) + 1
    for group in analysis.review_groups:
        category_counts = summary["category_counts"]
        assert isinstance(category_counts, dict)
        category_counts[group.category] = int(category_counts.get(group.category, 0)) + 1

    counted_groups: set[str] = set()
    for index, row_num in enumerate(parsed.row_numbers):
        classified_row = classified_by_row[row_num]
        result = classified_row.classification
        group = group_by_row.get(row_num)
        resolution = supplied.get(group.key) if group is not None else None
        action = "keep"
        patch: dict[str, str] = {}
        part_number = classified_row.row.value("part_number")
        touched: set[str] = set()
        if result.state == "confirmed_nc" and group is None:
            action = "exclude"
        elif group is not None:
            assert isinstance(resolution, Mapping)
            action = str(resolution.get("action") or "").strip().lower()
            if action not in {"keep", "exclude", "keep_as_is"}:
                raise ValueError(f"装机审查组 {','.join(group.refs)} 的处理动作无效。")
            if action == "keep_as_is":
                action = "keep"
            patch = _resolution_patch(resolution)
            requested_code_value = make_field_value(resolution.get("part_number"))
            requested_code = requested_code_value.cleaned if _valid_value(requested_code_value) else ""
            if requested_code:
                part_number = requested_code
            elif not part_number:
                part_number = group.classification.suggested_code
            if action == "keep":
                if not part_number:
                    raise ValueError(f"装机审查组 {','.join(group.refs)} 选择纳入 BOM 时必须填写子项编码。")
                attributes = {
                    field: patch.get(field) or classified_row.row.value(field)
                    for field in ("name", "model", "desc")
                }
                if not any(attributes.values()):
                    raise ValueError(f"装机审查组 {','.join(group.refs)} 至少需要填写名称、型号或描述之一。")
            if group.key not in counted_groups:
                counted_groups.add(group.key)
                if action == "keep":
                    summary["kept_groups"] = int(summary["kept_groups"]) + 1
                else:
                    summary["excluded_groups"] = int(summary["excluded_groups"]) + 1
                summary["user_touched_groups"] = int(summary["user_touched_groups"]) + 1

        effective = rows[index]
        effective["_placement_action"] = action
        effective["_placement_state"] = result.state
        effective["_placement_rule_id"] = result.rule_id
        effective["_placement_key"] = group.key if group is not None else classified_row.row.fingerprint
        effective["_field_flags"] = {
            field: sorted(value.flags)
            for field, value in classified_row.row.fields.items()
        }
        if action == "exclude":
            reason, reason_kind = _exclude_reason(result.state)
            effective["_placement_reason"] = reason
            effective["_placement_reason_kind"] = reason_kind
            reason_counts = summary["reason_counts"]
            assert isinstance(reason_counts, dict)
            reason_counts[reason_kind] = int(reason_counts.get(reason_kind, 0)) + 1
            continue

        if part_number and part_number != str(effective.get("part_number") or "").strip():
            effective["part_number"] = part_number
            touched.add("part_number")
        for field, value in patch.items():
            if value != str(effective.get(field) or "").strip():
                effective[field] = value
                touched.add(field)
        if str(effective.get("value") or "").strip() == part_number and part_number:
            effective["value"] = ""
            touched.add("value")

        sanitized_fields: list[str] = []
        for field, source_value in classified_row.row.fields.items():
            if field in touched:
                continue
            if not {"placeholder_residue", "mojibake"}.intersection(source_value.flags):
                continue
            if not str(effective.get(field) or "").strip():
                continue
            effective[field] = ""
            sanitized_fields.append(field)
        if sanitized_fields:
            effective["_sanitized_fields"] = sorted(sanitized_fields)
        if touched:
            effective["_user_touched"] = sorted(touched)

    return ParsedSource(parsed.source_path, rows, list(parsed.row_numbers), parsed.normalized_rows), summary


def default_nc_value_re() -> re.Pattern[str]:
    return _nc_value_pattern(classification_config().nc_keywords)
