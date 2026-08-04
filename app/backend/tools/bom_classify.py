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
from app.backend.tools.bom_domain import (
    BOM_RULE_VERSION,
    BOM_SCHEMA_VERSION,
    DecisionRecord,
    MaterialIdentity,
    PlacementResolution as DomainPlacementResolution,
    RoleDecision,
    SourceQualityReport,
    stable_fingerprint,
)


DEFAULT_MATERIAL_CODE_SHAPES: tuple[dict[str, str], ...] = (
    {
        "id": "digits",
        "kind": "internal",
        "pattern": r"^\d{6,20}$",
        "note": "纯数字内部编码",
    },
    {
        "id": "dotted",
        "kind": "internal",
        "pattern": r"^[A-Za-z][A-Za-z0-9]{0,7}\.[A-Za-z0-9][A-Za-z0-9._-]{2,}$",
        "note": "带点分段编码",
    },
    {
        "id": "vendor_mpn",
        "kind": "mpn",
        "pattern": r"^(?=.*\d)[A-Za-z][A-Za-z0-9]{1,15}[-_][A-Za-z0-9][A-Za-z0-9-_/.]{2,}$",
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

# Paths are expected in Capture diagnostic fields such as Source Library,
# Implementation Path and datasheet. They are a placement error only when they
# appear in fields that define the material itself.
PATH_MISPLACEMENT_FIELDS = frozenset({
    "part_number",
    "value",
    "name",
    "model",
    "desc",
    "grade",
    "unit",
    "pcb_footprint",
    "pcb_package",
    "source_package",
    "source_part",
})

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

DEFAULT_FORCED_REVIEW_ROLES = (("SH", "shield"),)
DEFAULT_ROLE_REFERENCE_PREFIXES = {
    "test_point": ("TP", "Z_TP"),
    "short_symbol": ("JP",),
    "mounting_hole": ("H", "MH"),
    "fiducial": ("FID", "MARK", "MK"),
    "smt_mechanical": ("MTG", "H", "MH"),
}
DEFAULT_ROLE_LIBRARY_KEYWORDS = {
    "test_point": ("TESTPOINT", "TEST POINT", "TP0P", "测试点"),
    "short_symbol": ("SHORT_", "SHORTING", "SHORT", "SHOR", "JUMPER"),
    "mounting_hole": ("MOUNTINGHOLE", "MOUNTING HOLE", "HOLE", "GND孔", "安装孔", "定位孔"),
    "fiducial": ("FIDUCIAL", "MARK点", "光学定位点", "基准点"),
    "smt_mechanical": ("SMTSO", "SMT NUT", "SMT_NUT", "STANDOFF", "铜柱", "螺柱", "螺母柱"),
}
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
    kind: str = "internal"


@dataclass(frozen=True)
class ClassificationConfig:
    code_shapes: tuple[CodeShape, ...]
    nc_keywords: tuple[str, ...]
    process_strong: tuple[str, ...] = _PROCESS_KEYWORDS_STRONG
    process_ambiguous: tuple[str, ...] = _PROCESS_KEYWORDS_AMBIGUOUS
    process_material_whitelist: tuple[str, ...] = _PROCESS_MATERIAL_PHRASES
    forced_review_roles: tuple[tuple[str, str], ...] = DEFAULT_FORCED_REVIEW_ROLES
    role_reference_prefixes: Mapping[str, tuple[str, ...]] = None  # type: ignore[assignment]
    role_library_keywords: Mapping[str, tuple[str, ...]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.role_reference_prefixes is None:
            object.__setattr__(self, "role_reference_prefixes", DEFAULT_ROLE_REFERENCE_PREFIXES)
        if self.role_library_keywords is None:
            object.__setattr__(self, "role_library_keywords", DEFAULT_ROLE_LIBRARY_KEYWORDS)


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
    source_refs: tuple[str, ...] = ()
    quantity: str = ""
    physical_conflicts: tuple[str, ...] = ()

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
            "priority": str(_evidence_priority(self)),
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
    identity_status: str = "identity_missing"
    role: str = "unknown"
    role_confidence: str = "weak"
    suggested_destination: str | None = None
    exclusion_kind: str = ""
    blocking_reasons: tuple[str, ...] = ()
    suggested_mpn: str = ""
    decision_fingerprint: str = ""
    shield_subtype: str = ""

    @property
    def requires_review(self) -> bool:
        if self.state == "confirmed_nc":
            return False
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
    def group_id(self) -> str:
        return self.key

    @property
    def category(self) -> str:
        if self.classification.sh_review:
            return "shield"
        return self.classification.state

    def payload(self) -> dict[str, object]:
        classification = self.classification
        return {
            "key": self.key,
            "group_id": self.key,
            "row_numbers": list(self.row_numbers),
            "source_rows": list(self.row_numbers),
            "refs": list(self.refs),
            "physical_refs": list(self.refs),
            "position_count": len(self.refs),
            "state": classification.state,
            "category": self.category,
            "confidence": classification.confidence,
            "recommended_action": classification.recommended_action,
            "suggested_code": classification.suggested_code,
            "sh_review": classification.sh_review,
            "rule_id": classification.rule_id,
            "rule_version": BOM_RULE_VERSION,
            "identity_status": classification.identity_status,
            "role": classification.role,
            "role_confidence": classification.role_confidence,
            "suggested_destination": classification.suggested_destination,
            "exclusion_kind": classification.exclusion_kind,
            "shield_subtype": classification.shield_subtype,
            "blocking_reasons": list(classification.blocking_reasons),
            "suggested_mpn": classification.suggested_mpn,
            "decision_fingerprint": classification.decision_fingerprint,
            "evidence": [item.payload() for item in classification.evidence],
            "original_fields": dict(self.original_fields),
            "inferred_fields": dict(self.inferred_fields),
        }


@dataclass(frozen=True)
class PlacementAnalysis:
    rows: tuple[ClassifiedRow, ...]
    review_groups: tuple[ReviewGroup, ...]
    readonly_nc: tuple[dict[str, object], ...]
    readonly_groups: tuple[dict[str, object], ...] = ()
    source_fingerprint: str = ""
    quality_report: SourceQualityReport = SourceQualityReport()
    code_verification: tuple[dict[str, object], ...] = ()

    def payload(self) -> dict[str, object]:
        state_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        for item in self.rows:
            state = item.classification.state
            state_counts[state] = state_counts.get(state, 0) + 1
        for group in self.review_groups:
            category_counts[group.category] = category_counts.get(group.category, 0) + 1
        return {
            "schema_version": BOM_SCHEMA_VERSION,
            "rule_version": BOM_RULE_VERSION,
            "source_fingerprint": self.source_fingerprint,
            "quality_report": self.quality_report.payload(),
            "groups": [group.payload() for group in self.review_groups],
            "readonly_groups": list(self.readonly_groups),
            "readonly_nc": {
                "count": len(self.readonly_nc),
                "items": list(self.readonly_nc[:50]),
            },
            "code_verification": list(self.code_verification),
            "summary": {
                "review_groups": len(self.review_groups),
                "review_positions": sum(len(group.refs) for group in self.review_groups),
                "readonly_nc": len(self.readonly_nc),
                "code_verification": len(self.code_verification),
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
        kind = str(item.get("kind") or ("mpn" if identifier == "vendor_mpn" else "internal")).strip().lower()
        if kind not in {"internal", "mpn"}:
            kind = "internal"
        if not identifier or not pattern:
            continue
        try:
            compiled.append(CodeShape(identifier, re.compile(pattern, re.IGNORECASE), note, kind))
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
    process_mapping = mapping.get("process_keywords")
    process_mapping = process_mapping if isinstance(process_mapping, Mapping) else {}

    def configured_words(key: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
        raw_values = process_mapping.get(key)
        if not isinstance(raw_values, list):
            return fallback
        values = tuple(str(value).strip() for value in raw_values if str(value).strip())
        return values or fallback

    raw_forced_roles = mapping.get("forced_review_roles")
    forced_roles: list[tuple[str, str]] = []
    if isinstance(raw_forced_roles, list):
        for item in raw_forced_roles:
            if not isinstance(item, Mapping):
                continue
            prefix = str(item.get("prefix") or "").strip().upper()
            role = str(item.get("role") or "").strip()
            if prefix and role:
                forced_roles.append((prefix, role))

    raw_role_hints = mapping.get("role_hints")
    role_hints = raw_role_hints if isinstance(raw_role_hints, Mapping) else {}
    reference_prefixes: dict[str, tuple[str, ...]] = {}
    library_keywords: dict[str, tuple[str, ...]] = {}
    for role in set(DEFAULT_ROLE_REFERENCE_PREFIXES) | set(DEFAULT_ROLE_LIBRARY_KEYWORDS) | set(role_hints):
        raw_hint = role_hints.get(role)
        hint = raw_hint if isinstance(raw_hint, Mapping) else {}
        raw_prefixes = hint.get("reference_prefixes")
        raw_library = hint.get("library_keywords")
        reference_prefixes[str(role)] = tuple(
            str(value).strip().upper()
            for value in raw_prefixes
            if str(value).strip()
        ) if isinstance(raw_prefixes, list) else DEFAULT_ROLE_REFERENCE_PREFIXES.get(str(role), ())
        library_keywords[str(role)] = tuple(
            str(value).strip()
            for value in raw_library
            if str(value).strip()
        ) if isinstance(raw_library, list) else DEFAULT_ROLE_LIBRARY_KEYWORDS.get(str(role), ())


    return ClassificationConfig(
        code_shapes=_compiled_shapes(mapping.get("material_code_shapes")),
        nc_keywords=keywords or DEFAULT_NC_KEYWORDS,
        process_strong=configured_words("strong", _PROCESS_KEYWORDS_STRONG),
        process_ambiguous=configured_words("ambiguous", _PROCESS_KEYWORDS_AMBIGUOUS),
        process_material_whitelist=configured_words("material_whitelist", _PROCESS_MATERIAL_PHRASES),
        forced_review_roles=tuple(forced_roles) or DEFAULT_FORCED_REVIEW_ROLES,
        role_reference_prefixes=reference_prefixes or DEFAULT_ROLE_REFERENCE_PREFIXES,
        role_library_keywords=library_keywords or DEFAULT_ROLE_LIBRARY_KEYWORDS,
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
    *,
    source_refs: Iterable[str] | None = None,
    quantity: object = "",
    physical_conflicts: Iterable[str] = (),
) -> NormalizedBomRow:
    normalized_refs = tuple(sorted({str(ref).strip() for ref in refs if str(ref).strip()}, key=natural_key))
    original_refs = tuple(
        sorted(
            {str(ref).strip() for ref in (source_refs if source_refs is not None else normalized_refs) if str(ref).strip()},
            key=natural_key,
        )
    )
    source = provenance or {}
    fields = {
        field: make_field_value(values.get(field), str(source.get(field) or "cell"))
        for field in values
    }
    for field in FINGERPRINT_FIELDS:
        fields.setdefault(field, make_field_value(""))
    return NormalizedBomRow(
        row_number,
        normalized_refs,
        fields,
        _fingerprint(normalized_refs, fields),
        original_refs,
        clean_field_text(quantity),
        tuple(sorted({str(value) for value in physical_conflicts if str(value)})),
    )


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


def process_keyword(value: str, config: ClassificationConfig | None = None) -> str:
    config = config or classification_config()
    text = clean_field_text(value)
    probe = text
    for phrase in config.process_material_whitelist:
        probe = re.sub(re.escape(phrase), " ", probe, flags=re.IGNORECASE)
    for keyword in (*config.process_strong, *config.process_ambiguous):
        if _CJK_RE.search(keyword):
            matched = keyword in probe
        else:
            escaped = re.escape(keyword).replace(r"\ ", r"\s*")
            matched = bool(re.search(rf"(?:^|[\s,;/()（）_-]){escaped}(?=$|[\s,;/()（）_-])", probe, re.IGNORECASE))
        if matched:
            return keyword
    return ""


def _process_keyword_strength(keyword: str, config: ClassificationConfig) -> str:
    return "medium" if keyword in config.process_ambiguous else "strong"


def _enrich_row(row: NormalizedBomRow, config: ClassificationConfig) -> NormalizedBomRow:
    fields: dict[str, FieldValue] = {}
    for field, item in row.fields.items():
        flags = set(item.flags)
        if any(
            code_shape_matches(candidate, config) and not process_keyword(candidate, config)
            for candidate in _candidate_code_values(field, item.cleaned)
        ):
            flags.add("code_shape")
        if contains_nc_keyword(item.cleaned, config):
            flags.add("nc_keyword")
        if process_keyword(item.cleaned, config):
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


def _evidence_priority(item: MaterialEvidence) -> int:
    if item.kind in {"physical_conflict", "field_misplacement", "identity"}:
        return 10
    if item.kind in {"forced_role", "role_reference"}:
        return 20
    if item.kind in {"role_library", "library_info"} or item.field in {
        "pcb_footprint", "pcb_package", "source_package", "source_part", "source_library"
    }:
        return 30
    if item.field in {"value", "model", "name", "part_number"}:
        return 40
    if item.field == "desc":
        return 50
    return 60


def _row_prefixes(row: NormalizedBomRow) -> tuple[str, ...]:
    return tuple(sorted({match.group(1).upper() for ref in row.refs if (match := _REF_PREFIX_RE.match(ref))}))


def _contains_configured_keyword(text: str, keywords: Sequence[str]) -> str:
    probe = clean_field_text(text)
    for keyword in keywords:
        if keyword and keyword.casefold() in probe.casefold():
            return keyword
    return ""


def collect_evidence(
    row: NormalizedBomRow,
    config: ClassificationConfig,
    *,
    is_enriched: bool = False,
) -> tuple[MaterialEvidence, ...]:
    enriched = row if is_enriched else _enrich_row(row, config)
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
        if "path_like" in item.flags and field in PATH_MISPLACEMENT_FIELDS:
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
                if process_keyword(candidate, config):
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
        keyword = process_keyword(item.cleaned, config)
        if keyword and field in {
            "value", "name", "model", "desc", "pcb_package", "pcb_footprint", "source_package", "source_part"
        }:
            evidence.append(MaterialEvidence(
                "process_keyword",
                field,
                keyword,
                "process",
                _process_keyword_strength(keyword, config),
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

    prefixes = list(_row_prefixes(row))
    if prefixes:
        evidence.append(MaterialEvidence(
            "ref_prefix",
            "refs",
            ",".join(prefixes),
            "neutral",
            "weak",
            f"位号前缀 {','.join(prefixes)} 仅作为排序提示，不参与装机结论",
        ))
    for prefix, role in config.forced_review_roles:
        if prefix.upper() in prefixes:
            evidence.append(MaterialEvidence(
                "forced_role",
                "refs",
                prefix.upper(),
                "role",
                "strong",
                f"位号进入强制审查类别：{role}",
                role,
            ))
    library_blob = " ".join(
        row.value(field)
        for field in (
            "pcb_footprint",
            "pcb_package",
            "source_package",
            "source_part",
            "source_library",
        )
    )
    descriptive_blob = " ".join(row.value(field) for field in ("desc", "name", "model"))
    for role, role_prefixes in config.role_reference_prefixes.items():
        matched_prefix = next((prefix for prefix in role_prefixes if prefix.upper() in prefixes), "")
        if matched_prefix:
            evidence.append(MaterialEvidence(
                "role_reference",
                "refs",
                matched_prefix,
                "role",
                "medium",
                f"位号提示器件角色：{role}",
                role,
            ))
        matched_library = _contains_configured_keyword(library_blob, config.role_library_keywords.get(role, ()))
        if matched_library:
            evidence.append(MaterialEvidence(
                "role_library",
                "package/library",
                matched_library,
                "role",
                "strong",
                f"封装或库信息提示器件角色：{role}",
                role,
            ))
        matched_text = _contains_configured_keyword(descriptive_blob, config.role_library_keywords.get(role, ()))
        if matched_text:
            evidence.append(MaterialEvidence(
                "role_text",
                "desc/name/model",
                matched_text,
                "role",
                "medium",
                f"名称、型号或描述提示器件角色：{role}",
                role,
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
    if row.physical_conflicts:
        evidence.append(MaterialEvidence(
            "physical_conflict",
            "reference",
            ",".join(row.physical_conflicts),
            "neutral",
            "strong",
            "同一物理位号存在不可消解的料号或封装冲突",
        ))
    return tuple(sorted(evidence, key=lambda item: (_evidence_priority(item), item.kind, item.field, item.value)))


def _candidate_for_kind(
    evidence: Sequence[MaterialEvidence],
    config: ClassificationConfig,
    kind: str,
) -> str:
    priority = {field: index for index, field in enumerate(CODE_CANDIDATE_FIELDS)}
    shape_kinds = {shape.id: shape.kind for shape in config.code_shapes}
    candidates = [
        item
        for item in evidence
        if item.kind == "code_shape"
        and item.field != "part_number"
        and shape_kinds.get(item.shape_id, "internal") == kind
    ]
    if not candidates:
        return ""
    return min(candidates, key=lambda item: (priority.get(item.field, 99), -len(item.value))).value


def _suggested_code(
    evidence: Sequence[MaterialEvidence],
    config: ClassificationConfig | None = None,
) -> str:
    return _candidate_for_kind(evidence, config or classification_config(), "internal")


def identify_material(
    row: NormalizedBomRow,
    config: ClassificationConfig,
    evidence: Sequence[MaterialEvidence] | None = None,
) -> MaterialIdentity:
    collected = tuple(evidence) if evidence is not None else collect_evidence(row, config)
    item = row.fields.get("part_number")
    raw_part_number = row.value("part_number")
    if row.physical_conflicts:
        return MaterialIdentity(
            "identity_conflict",
            raw_part_number,
            strength="strong",
            reasons=tuple(row.physical_conflicts),
        )
    if raw_part_number:
        invalid_reasons: list[str] = []
        if not _valid_value(item):
            invalid_reasons.append("invalid_text")
        if item is not None and "path_like" in item.flags:
            invalid_reasons.append("path_like")
        if contains_nc_keyword(raw_part_number, config):
            invalid_reasons.append("nc_marker_in_part_number")
        if _looks_like_description_in_part_number(raw_part_number):
            invalid_reasons.append("description_in_part_number")
        if invalid_reasons:
            return MaterialIdentity(
                "identity_conflict",
                raw_part_number,
                strength="strong",
                reasons=tuple(invalid_reasons),
            )
        # A non-empty code column means this row is a material. Code schemes change
        # between projects, so the tool never judges a code by its shape; codes
        # that look wrong are surfaced for human verification instead.
        return MaterialIdentity(
            "identity_confirmed",
            raw_part_number,
            strength="strong",
            reasons=("formal_part_number",),
        )

    internal_candidate = _candidate_for_kind(collected, config, "internal")
    mpn_candidate = _candidate_for_kind(collected, config, "mpn")
    if internal_candidate:
        return MaterialIdentity(
            "identity_candidate_internal",
            internal_candidate=internal_candidate,
            mpn_candidate=mpn_candidate,
            strength="medium",
            reasons=("internal_code_shape",),
        )
    if mpn_candidate:
        return MaterialIdentity(
            "identity_candidate_mpn",
            mpn_candidate=mpn_candidate,
            strength="medium",
            reasons=("manufacturer_part_number_shape",),
        )
    return MaterialIdentity("identity_missing", strength="weak", reasons=("no_material_identity",))


def _has_valid_part_number(row: NormalizedBomRow, config: ClassificationConfig) -> bool:
    return identify_material(row, config).status == "identity_confirmed"


def infer_role(
    row: NormalizedBomRow,
    identity: MaterialIdentity,
    evidence: Sequence[MaterialEvidence],
    config: ClassificationConfig,
) -> RoleDecision:
    forced = next((item for item in evidence if item.kind == "forced_role"), None)
    if forced is not None:
        return RoleDecision(forced.shape_id or "unknown", "strong", True, (forced.display,))

    material_blob = " ".join(row.value(field) for field in ("value", "name", "model", "desc"))
    protected_material = bool(_contains_configured_keyword(material_blob, config.process_material_whitelist))
    reference_roles = {item.shape_id for item in evidence if item.kind == "role_reference"}
    library_roles = {item.shape_id for item in evidence if item.kind == "role_library"}
    text_roles = {item.shape_id for item in evidence if item.kind == "role_text"}
    for role in ("test_point", "short_symbol", "fiducial", "smt_mechanical", "mounting_hole"):
        if role == "short_symbol" and protected_material:
            continue
        if role in reference_roles and role in library_roles:
            if role == "mounting_hole" and identity.status in {
                "identity_confirmed",
                "identity_candidate_internal",
                "identity_candidate_mpn",
            }:
                return RoleDecision(
                    "smt_mechanical",
                    "medium",
                    False,
                    ("hole_like_reference_has_material_identity",),
                )
            return RoleDecision(
                role,
                "strong",
                False,
                ("reference_and_package_corroborate",),
            )

    ambiguous = next(
        (
            item for item in evidence
            if item.kind == "process_keyword" and item.strength == "medium"
        ),
        None,
    )
    if ambiguous is not None:
        return RoleDecision("smt_mechanical", "medium", False, (ambiguous.display,))
    # Type is read from what the row says about itself, but naming a type and
    # dropping a material are different acts. Only a reference prefix and the
    # package/library agreeing is strong enough to drive automatic exclusion; text
    # on its own names a candidate type and nothing more.
    for role in ("test_point", "short_symbol", "fiducial", "mounting_hole", "smt_mechanical"):
        if role == "short_symbol" and protected_material:
            continue
        if role in library_roles or role in reference_roles or role in text_roles:
            corroborated = role in library_roles and role in reference_roles
            return RoleDecision(
                role,
                "strong" if corroborated else "medium",
                False,
                ("reference_and_package_corroborate",)
                if corroborated
                else ("role_named_by_single_source",),
            )
    if identity.status == "identity_confirmed":
        return RoleDecision("electronic", "strong", False, ("formal_part_number_without_role_conflict",))
    return RoleDecision("unknown", "weak", False, ("role_not_corroborated",))


def _identity_evidence(identity: MaterialIdentity) -> MaterialEvidence:
    labels = {
        "identity_confirmed": "正式料号有效，物料身份成立",
        "identity_weak": "料号是库占位名或工艺符号，不能直接作为正式物料身份",
        "identity_candidate_internal": "物料字段命中内部编码形态，等待补全正式料号",
        "identity_candidate_mpn": "物料字段仅命中厂商 MPN，不能冒充内部料号",
        "identity_missing": "未找到正式料号或可信编码候选",
        "identity_conflict": "物料身份字段存在冲突或错位",
    }
    value = identity.part_number or identity.internal_candidate or identity.mpn_candidate
    return MaterialEvidence(
        "identity",
        "part_number",
        value,
        "material+" if identity.status != "identity_conflict" else "neutral",
        identity.strength,
        labels[identity.status],
        identity.status,
    )


def _decision_fingerprint(row: NormalizedBomRow, identity: MaterialIdentity, role: RoleDecision) -> str:
    return stable_fingerprint("bom-placement-decision", {
        "rule_version": BOM_RULE_VERSION,
        "part_number": identity.part_number,
        "identity_status": identity.status,
        "role": role.role,
        "value": row.value("value"),
        "model": row.value("model"),
        "name": row.value("name"),
        "pcb_footprint": row.value("pcb_footprint"),
        "pcb_package": row.value("pcb_package"),
        "source_package": row.value("source_package"),
        "source_part": row.value("source_part"),
        "desc": row.value("desc"),
        "manufacturer": row.value("manufacturer"),
        "grade": row.value("grade"),
        "unit": row.value("unit"),
    })


def _result(
    row: NormalizedBomRow,
    identity: MaterialIdentity,
    role: RoleDecision,
    evidence: Sequence[MaterialEvidence],
    state: str,
    confidence: str,
    recommended_action: str | None,
    suggested_destination: str | None,
    exclusion_kind: str,
    rule_id: str,
    *,
    blocking_reasons: Sequence[str] = (),
    shield_subtype: str = "",
) -> ClassificationResult:
    ordered = tuple(sorted((*evidence, _identity_evidence(identity)), key=lambda item: (_evidence_priority(item), item.kind, item.field)))
    return ClassificationResult(
        state,
        confidence,
        ordered,
        recommended_action,
        identity.internal_candidate,
        role.forced_review,
        rule_id,
        identity.status,
        role.role,
        role.confidence,
        suggested_destination,
        exclusion_kind,
        tuple(blocking_reasons),
        identity.mpn_candidate,
        _decision_fingerprint(row, identity, role),
        shield_subtype,
    )


def classify(
    row: NormalizedBomRow,
    config: ClassificationConfig,
    *,
    is_enriched: bool = False,
) -> ClassificationResult:
    row = row if is_enriched else _enrich_row(row, config)
    evidence = collect_evidence(row, config, is_enriched=True)
    identity = identify_material(row, config, evidence)
    role = infer_role(row, identity, evidence, config)
    valid_part_number = identity.status == "identity_confirmed"
    nc_items = [item for item in evidence if item.kind == "nc_keyword"]
    nc_signal = bool(nc_items)
    pure_nc = is_pure_nc_marker(row.value("value"), config)
    process_items = [item for item in evidence if item.kind == "process_keyword"]
    strong_process_signal = any(item.strength == "strong" for item in process_items)
    ambiguous_process_signal = any(item.strength == "medium" for item in process_items)
    corroborated_process_role = role.role in {
        "test_point", "short_symbol", "mounting_hole", "fiducial"
    } and role.confidence == "strong"
    misplaced_path = any(
        item.kind == "field_misplacement" and item.shape_id == "path_like"
        for item in evidence
    )
    substantive = any(
        _valid_value(row.fields.get(field))
        for field in MATERIAL_ATTRIBUTE_FIELDS
    )

    if identity.status == "identity_conflict" or misplaced_path:
        return _result(row, identity, role, evidence, "conflicting", "strong", None, None, "", "R7", blocking_reasons=identity.reasons or ("field_misplacement",))

    # Order is fixed: identity, then whether it is installed, then what kind of
    # thing it is. Nothing later may reopen an earlier answer.
    if nc_signal:
        if pure_nc:
            return _result(
                row,
                identity,
                role,
                evidence,
                "confirmed_nc",
                "strong",
                "exclude",
                "non_smt",
                "nc",
                "R2C" if valid_part_number else "R2",
            )
        return _result(row, identity, role, evidence, "conflicting", "strong", None, None, "", "R7", blocking_reasons=("embedded_nc_marker",))

    if role.role == "shield":
        # Type decides where a shield goes, and a shield defaults to a cover:
        # covers are purchased materials that never enter the placement BOM, so
        # scope exclusion is the answer for the operator to accept or change.
        state = "confirmed_material" if valid_part_number else "suspected_material"
        return _result(
            row, identity, role, evidence,
            state, identity.strength, "exclude", "non_smt", "scope_excluded",
            "R3", blocking_reasons=("shield_type_and_destination_required",),
            shield_subtype="cover",
        )

    # A coded row is a material. Process-sounding text never demotes it into an
    # adjudication queue; the contradiction is reported in the verification list
    # instead. Type may still steer where it goes, which is handled per type.
    if valid_part_number and corroborated_process_role:
        return _result(row, identity, role, evidence, "confirmed_material", "strong", "exclude", "non_smt", "process_only", "R4")
    if valid_part_number:
        return _result(row, identity, role, evidence, "confirmed_material", "strong", "keep", "smt", "", "R1")

    if identity.status == "identity_candidate_internal":
        if corroborated_process_role:
            return _result(row, identity, role, evidence, "suspected_process", "strong", "exclude", "non_smt", "process_only", "R6P")
        return _result(row, identity, role, evidence, "suspected_material", "medium", "keep", "smt", "", "R5")
    if identity.status == "identity_candidate_mpn":
        return _result(row, identity, role, evidence, "suspected_material", "medium", None, None, "", "R6M", blocking_reasons=("internal_part_number_required",))
    if corroborated_process_role:
        return _result(row, identity, role, evidence, "suspected_process", "strong", "exclude", "non_smt", "process_only", "R6P")
    if substantive or identity.status == "identity_weak":
        return _result(row, identity, role, evidence, "suspected_material", "weak", None, None, "", "R6M")
    return _result(row, identity, role, evidence, "insufficient_data", "weak", None, None, "", "R8", blocking_reasons=("insufficient_material_data",))


def _code_verification(classified: Sequence[ClassifiedRow]) -> tuple[dict[str, object], ...]:
    """List coded rows whose own text describes a process item.

    The code column is trusted, so these rows are materials and stay in the BOM.
    A code that turns out to be a library placeholder can only be recognised by a
    person, so the contradiction is reported rather than decided. This never gates
    the flow.
    """
    grouped: "OrderedDict[tuple[str, str], dict[str, object]]" = OrderedDict()
    for item in classified:
        result = item.classification
        if result.identity_status != "identity_confirmed":
            continue
        code = item.row.value("part_number")
        if not code:
            continue
        keyword = next(
            (
                evidence.value
                for evidence in result.evidence
                if evidence.kind == "process_keyword"
            ),
            "",
        )
        if not keyword:
            continue
        key = (code.casefold(), keyword)
        entry = grouped.get(key)
        if entry is None:
            entry = {
                "part_number": code,
                "keyword": keyword,
                "reason": f"编码 {code} 已按物料纳入，但描述含工艺词「{keyword}」，请查验该编码是否为库占位名",
                "description": item.row.value("desc"),
                "refs": [],
                "row_numbers": [],
            }
            grouped[key] = entry
        entry["refs"].extend(item.row.refs)  # type: ignore[union-attr]
        entry["row_numbers"].append(item.row.row_number)  # type: ignore[union-attr]
    return tuple(grouped.values())


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
        result.identity_status,
        result.role,
        result.suggested_code.casefold(),
        result.suggested_mpn.casefold(),
        result.sh_review,
        *field_signature,
        None if stable_group else row.row_number,
    )


def _group_key(items: Sequence[ClassifiedRow]) -> str:
    first = items[0]
    refs = sorted({ref for item in items for ref in item.row.refs}, key=natural_key)
    values = [
        BOM_RULE_VERSION,
        first.classification.state,
        first.classification.identity_status,
        first.classification.role,
        *(ref.casefold() for ref in refs),
    ]
    values.extend(first.row.value(field).casefold() for field in FINGERPRINT_FIELDS)
    return hashlib.sha1("\x1f".join(values).encode("utf-8")).hexdigest()[:16]


def analyze_placement(
    rows: Sequence[NormalizedBomRow],
    config: ClassificationConfig,
    *,
    source_fingerprint: str = "",
    quality_report: SourceQualityReport | None = None,
) -> PlacementAnalysis:
    classified_rows: list[ClassifiedRow] = []
    for row in rows:
        enriched_row = _enrich_row(row, config)
        classified_rows.append(ClassifiedRow(
            enriched_row,
            classify(enriched_row, config, is_enriched=True),
        ))
    classified = tuple(classified_rows)
    grouped: "OrderedDict[tuple[object, ...], list[ClassifiedRow]]" = OrderedDict()
    readonly_nc: list[dict[str, object]] = []
    readonly_groups: list[dict[str, object]] = []
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
        if not result.requires_review:
            readonly_groups.append({
                "group_id": item.row.fingerprint,
                "source_rows": [item.row.row_number],
                "physical_refs": list(item.row.refs),
                "position_count": len(item.row.refs),
                "identity_status": result.identity_status,
                "classification_state": result.state,
                "state": result.state,
                "role": result.role,
                "role_confidence": result.role_confidence,
                "suggested_destination": result.suggested_destination,
                "recommended_action": result.recommended_action,
                "exclusion_kind": result.exclusion_kind,
                "rule_id": result.rule_id,
                "decision_fingerprint": result.decision_fingerprint,
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
        if first.classification.suggested_mpn and not inferred.get("model"):
            inferred["model"] = first.classification.suggested_mpn
        review_groups.append(ReviewGroup(
            _group_key(items),
            rows_in_group,
            refs,
            first.classification,
            original,
            inferred,
        ))
    return PlacementAnalysis(
        classified,
        tuple(review_groups),
        tuple(readonly_nc),
        tuple(readonly_groups),
        source_fingerprint,
        quality_report or SourceQualityReport(
            parsed_rows=len(rows),
            occurrence_count=sum(len(row.refs) for row in rows),
            physical_part_count=len({ref for row in rows for ref in row.refs}),
        ),
        _code_verification(classified),
    )


def _resolution_patch(resolution: Mapping[str, object]) -> dict[str, str]:
    raw_patch = resolution.get("field_patch")
    patch = raw_patch if isinstance(raw_patch, Mapping) else resolution
    cleaned: dict[str, str] = {}
    for field in (
        "name",
        "model",
        "desc",
        "grade",
        "unit",
        "manufacturer",
        "pcb_footprint",
        "pcb_package",
    ):
        value = make_field_value(patch.get(field))
        if _valid_value(value):
            cleaned[field] = value.cleaned
    return cleaned


def _exclude_reason(exclusion_kind: str) -> str:
    return {
        "nc": "明确 NC/未贴",
        "process_only": "非贴片工艺项",
        "scope_excluded": "不属于当前 PCBA/SMT 范围",
        "user_excluded": "用户确认移出贴片 BOM",
    }.get(exclusion_kind, "用户确认移出贴片 BOM")


def _normalize_resolution(
    group: ReviewGroup | None,
    result: ClassificationResult,
    raw: Mapping[str, object] | None,
) -> DomainPlacementResolution:
    if raw is None:
        if result.suggested_destination is None:
            raise ValueError("review decision is required")
        resolution = DomainPlacementResolution(
            destination=result.suggested_destination,
            exclusion_kind=result.exclusion_kind,
            role=result.role,
            decision_source="rule",
        )
        resolution.validate()
        return resolution

    destination = str(raw.get("destination") or "").strip().lower()
    legacy_action = str(raw.get("action") or "").strip().lower()
    if not destination and legacy_action:
        destination = "smt" if legacy_action in {"keep", "keep_as_is"} else "non_smt"
    exclusion_kind = str(raw.get("exclusion_kind") or "").strip().lower()
    if destination == "non_smt" and not exclusion_kind:
        exclusion_kind = result.exclusion_kind or (
            "process_only" if result.state == "suspected_process" else "user_excluded"
        )
    role = str(raw.get("role") or result.role or "unknown").strip()
    subtype = str(raw.get("subtype") or "").strip().lower()
    if role == "shield" and exclusion_kind != "nc" and not subtype:
        subtype = "bracket" if destination == "smt" else result.shield_subtype or "cover"
    if role == "shield" and subtype == "cover":
        exclusion_kind = "scope_excluded"
    source = str(raw.get("decision_source") or "user").strip().lower()
    if source in {"manual", "recommendation", "default"}:
        source = "user" if source == "manual" else "rule"
    raw_override = raw.get("part_number_override")
    if raw_override is None:
        raw_override = raw.get("part_number")
    override = make_field_value(raw_override)
    resolution = DomainPlacementResolution(
        destination=destination,
        exclusion_kind=exclusion_kind,
        role=role,
        subtype=subtype,
        part_number_override=override.cleaned if _valid_value(override) else "",
        field_patch=_resolution_patch(raw),
        decision_source=source,
    )
    try:
        resolution.validate()
    except ValueError as exc:
        refs = ",".join(group.refs) if group is not None else "自动判定项"
        raise ValueError(f"装机审查组 {refs} 的决议无效：{exc}") from exc
    return resolution


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
        "schema_version": BOM_SCHEMA_VERSION,
        "rule_version": BOM_RULE_VERSION,
        "source_fingerprint": analysis.source_fingerprint,
        "groups": len(analysis.review_groups),
        "positions": sum(len(group.refs) for group in analysis.review_groups),
        "reviewed_groups": len(analysis.review_groups),
        "kept_groups": 0,
        "excluded_groups": 0,
        "user_touched_groups": 0,
        "state_counts": {},
        "category_counts": {},
        "reason_counts": {},
        "destination_counts": {},
        "role_counts": {},
        "decision_records": [],
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
    recorded_decisions: set[str] = set()
    for index, row_num in enumerate(parsed.row_numbers):
        classified_row = classified_by_row[row_num]
        result = classified_row.classification
        group = group_by_row.get(row_num)
        raw_resolution = supplied.get(group.key) if group is not None else None
        resolution = _normalize_resolution(
            group,
            result,
            raw_resolution if isinstance(raw_resolution, Mapping) else None,
        )
        action = "keep" if resolution.destination == "smt" else "exclude"
        patch = dict(resolution.field_patch)
        part_number = classified_row.row.value("part_number")
        touched: set[str] = set()
        if resolution.part_number_override:
            part_number = resolution.part_number_override
        elif not part_number and group is not None:
            part_number = group.classification.suggested_code
        if action == "keep":
            if not part_number:
                refs = ",".join(group.refs) if group is not None else ",".join(classified_row.row.refs)
                raise ValueError(f"装机审查组 {refs} 选择纳入贴片 BOM 时必须填写内部子项编码。")
            if group is not None:
                attributes = {
                    field: patch.get(field) or classified_row.row.value(field)
                    for field in ("name", "model", "desc")
                }
                if not any(attributes.values()):
                    refs = ",".join(group.refs)
                    raise ValueError(f"装机审查组 {refs} 至少需要填写名称、型号或描述之一。")
        if group is not None:
            if group.key not in counted_groups:
                counted_groups.add(group.key)
                if action == "keep":
                    summary["kept_groups"] = int(summary["kept_groups"]) + 1
                else:
                    summary["excluded_groups"] = int(summary["excluded_groups"]) + 1
                summary["user_touched_groups"] = int(summary["user_touched_groups"]) + 1

        effective = rows[index]
        effective["_placement_action"] = action
        effective["_placement_destination"] = resolution.destination
        effective["_placement_exclusion_kind"] = resolution.exclusion_kind
        effective["_placement_role"] = resolution.role
        effective["_placement_subtype"] = resolution.subtype
        effective["_decision_source"] = resolution.decision_source
        effective["_decision_fingerprint"] = result.decision_fingerprint
        effective["_placement_state"] = result.state
        effective["_placement_rule_id"] = result.rule_id
        effective["_placement_key"] = group.key if group is not None else classified_row.row.fingerprint
        effective["_field_flags"] = {
            field: sorted(value.flags)
            for field, value in classified_row.row.fields.items()
        }
        destination_counts = summary["destination_counts"]
        assert isinstance(destination_counts, dict)
        destination_counts[resolution.destination] = int(destination_counts.get(resolution.destination, 0)) + 1
        role_counts = summary["role_counts"]
        assert isinstance(role_counts, dict)
        role_counts[resolution.role] = int(role_counts.get(resolution.role, 0)) + 1
        decision_key = group.key if group is not None else classified_row.row.fingerprint
        if decision_key not in recorded_decisions:
            recorded_decisions.add(decision_key)
            record = DecisionRecord(
                decision_key,
                result.decision_fingerprint,
                group.refs if group is not None else classified_row.row.refs,
                result.identity_status,
                result.state,
                result.rule_id,
                BOM_RULE_VERSION,
                resolution,
                tuple(item.payload() for item in result.evidence),
                {
                    "part_number": part_number,
                    "value": classified_row.row.value("value"),
                    "model": patch.get("model") or classified_row.row.value("model"),
                    "name": patch.get("name") or classified_row.row.value("name"),
                    "desc": patch.get("desc") or classified_row.row.value("desc"),
                    "pcb_footprint": patch.get("pcb_footprint") or classified_row.row.value("pcb_footprint"),
                    "pcb_package": patch.get("pcb_package") or classified_row.row.value("pcb_package"),
                    "manufacturer": patch.get("manufacturer") or classified_row.row.value("manufacturer"),
                    "grade": patch.get("grade") or classified_row.row.value("grade"),
                    "unit": patch.get("unit") or classified_row.row.value("unit"),
                },
            )
            decision_records = summary["decision_records"]
            assert isinstance(decision_records, list)
            decision_records.append(record.payload())
        if action == "exclude":
            reason = _exclude_reason(resolution.exclusion_kind)
            effective["_placement_reason"] = reason
            effective["_placement_reason_kind"] = resolution.exclusion_kind
            reason_counts = summary["reason_counts"]
            assert isinstance(reason_counts, dict)
            reason_counts[resolution.exclusion_kind] = int(reason_counts.get(resolution.exclusion_kind, 0)) + 1
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

    return replace(parsed, raw_rows=rows, row_numbers=list(parsed.row_numbers)), summary


def default_nc_value_re() -> re.Pattern[str]:
    return _nc_value_pattern(classification_config().nc_keywords)
