from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.backend.contracts.smt_analysis import (
    ClassificationState,
    SmtEvidence,
    SourceRole,
)


_REF_RE = re.compile(r"(?<![A-Z0-9_])(?:[A-Z]{1,4})\d{1,6}(?![A-Z0-9_])", re.IGNORECASE)
_CADENCE_XY_ROW_RE = re.compile(
    r"^\s*[^!\r\n]+\s*!\s*[-+]?\d+(?:\.\d+)?\s*!\s*[-+]?\d+(?:\.\d+)?\s*!",
    re.MULTILINE,
)
_COORDINATE_HEADER_RE = re.compile(
    r"\b(?:ref(?:erence|des)?|designator|位号)\b.*\b(?:x|x\s*coordinate|x坐标)\b.*"
    r"\b(?:y|y\s*coordinate|y坐标)\b",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class Classification:
    roles: tuple[SourceRole, ...]
    state: ClassificationState
    media_type: str
    evidence: tuple[SmtEvidence, ...]


def sniff_media_type(path: Path, prefix: bytes) -> str:
    """Return a conservative media type using signatures before extensions."""
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith(b"PK\x03\x04"):
        suffix = path.suffix.casefold()
        if suffix == ".xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if suffix in {".zip", ".rar"}:
            return "application/zip"
    if prefix.startswith(b"Rar!\x1a\x07"):
        return "application/vnd.rar"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def decode_text_sample(prefix: bytes) -> tuple[str, str] | None:
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            text = prefix.decode(encoding)
        except UnicodeError:
            continue
        if "\x00" in text and encoding != "utf-16":
            continue
        return text, encoding
    return None


def _evidence(
    kind: str,
    message: str,
    *,
    weight: str,
    value: str | None = None,
) -> SmtEvidence:
    return SmtEvidence(
        kind=kind,
        value=value,
        weight=weight,
        message=message,
    )


def _filename_tokens(path: Path) -> str:
    return " ".join(part.casefold() for part in path.parts)


def _classify_text(path: Path, text: str, media_type: str) -> Classification:
    evidence: list[SmtEvidence] = []
    upper = text.upper()
    if "UUNITS=" in upper and _CADENCE_XY_ROW_RE.search(text):
        evidence.append(
            _evidence(
                "content_signature",
                "内容包含 Cadence 坐标单位声明和坐标记录。",
                weight="strong",
            )
        )
        return Classification(
            roles=("placement_coordinate",),
            state="classified",
            media_type="text/plain",
            evidence=tuple(evidence),
        )

    if _COORDINATE_HEADER_RE.search(text[:32768]):
        evidence.append(
            _evidence(
                "tabular_headers",
                "表头同时包含位号、X 和 Y 坐标候选字段。",
                weight="supporting",
            )
        )
        return Classification(
            roles=("placement_coordinate",),
            state="candidate",
            media_type=media_type,
            evidence=tuple(evidence),
        )

    extension = path.suffix.casefold()
    if extension in {".dxf"} or "SECTION" in upper[:4096] and "ENTITIES" in upper[:32768]:
        return _classify_drawing_name(path, media_type)
    if extension in {".art", ".gbr", ".ger", ".pho"} or upper.startswith("G04"):
        evidence.append(
            _evidence(
                "gerber_signature",
                "内容或格式符合 Gerber/ART 制造数据，只作为钢网或板框候选。",
                weight="supporting",
            )
        )
        tokens = _filename_tokens(path)
        roles: tuple[SourceRole, ...] = (
            ("stencil_data",)
            if any(token in tokens for token in ("stencil", "paste", "钢网", "soldermask", "sm_", "pm_"))
            else ("stencil_data", "board_outline")
        )
        return Classification(
            roles=roles,
            state="candidate",
            media_type="application/x-gerber",
            evidence=tuple(evidence),
        )
    return Classification(
        roles=("unknown",),
        state="unresolved",
        media_type=media_type,
        evidence=(
            _evidence(
                "unrecognized_content",
                "文本内容未匹配已注册的坐标或制造资料格式，文件仍保留供人工确认。",
                weight="weak",
            ),
        ),
    )


def _classify_drawing_name(path: Path, media_type: str) -> Classification:
    tokens = _filename_tokens(path)
    evidence: list[SmtEvidence] = [
        _evidence(
            "drawing_format",
            "文件内容或扩展名表明它是二维工程图候选。",
            weight="supporting",
        )
    ]
    roles: list[SourceRole] = []
    if any(token in tokens for token in ("panel", "拼板", "array")):
        roles.append("panel_drawing")
        evidence.append(
            _evidence(
                "filename_hint",
                "路径名称包含拼板语义；该证据只用于排序候选。",
                weight="weak",
            )
        )
    if any(token in tokens for token in ("asm", "assembly", "assy", "装配", "贴片", "smd")):
        roles.append("assembly_drawing")
        evidence.append(
            _evidence(
                "filename_hint",
                "路径名称包含装配语义；仍需结合页面或图层内容确认。",
                weight="weak",
            )
        )
    roles.append("board_outline")
    return Classification(
        roles=tuple(dict.fromkeys(roles)),
        state="candidate",
        media_type=media_type,
        evidence=tuple(evidence),
    )


def classify_pdf(
    path: Path,
    *,
    extracted_text: str = "",
    page_count: int | None = None,
) -> Classification:
    tokens = _filename_tokens(path)
    evidence: list[SmtEvidence] = [
        _evidence("pdf_signature", "文件签名确认为 PDF。", weight="supporting")
    ]
    roles: list[SourceRole] = []
    ref_count = len(_REF_RE.findall(extracted_text))
    text_upper = extracted_text.upper()

    assembly_name = any(
        token in tokens for token in ("smd", "assembly", "assy", "贴片", "位号", "装配")
    )
    schematic_name = any(token in tokens for token in ("schematic", "原理图", "sch"))
    schematic_text = any(
        marker in text_upper
        for marker in ("SCHEMATIC", "POWER TREE", "NET NAME", "SHEET ", "PAGE ")
    )
    assembly_text = any(
        marker in text_upper
        for marker in ("ART FILM", "ASSEMBLY", "COMPONENT SIDE", "SOLDER SIDE")
    )

    if assembly_text or (ref_count >= 20 and page_count is not None and page_count <= 4):
        roles.append("assembly_drawing")
        evidence.append(
            _evidence(
                "page_text",
                f"抽样页面包含密集位号或装配图标识（位号候选 {ref_count} 个）。",
                weight="strong" if assembly_text else "supporting",
                value=str(ref_count),
            )
        )
    elif assembly_name:
        roles.append("assembly_drawing")
        evidence.append(
            _evidence(
                "filename_hint",
                "文件名包含装配/位号图语义，但页面内容证据不足。",
                weight="weak",
            )
        )

    if schematic_text or (schematic_name and (page_count or 0) > 2):
        roles.append("schematic_drawing")
        evidence.append(
            _evidence(
                "page_text",
                "页面文本或多页结构符合原理图候选。",
                weight="supporting" if schematic_text else "weak",
            )
        )
    elif schematic_name:
        roles.append("schematic_drawing")
        evidence.append(
            _evidence(
                "filename_hint",
                "文件名包含原理图语义。",
                weight="weak",
            )
        )

    if not roles:
        roles.append("unknown")
        evidence.append(
            _evidence(
                "page_content_unresolved",
                "PDF 页面尚不能确定为位号图或原理图，需要用户确认。",
                weight="weak",
            )
        )
    state: ClassificationState
    if roles == ["assembly_drawing"] and any(item.weight == "strong" for item in evidence):
        state = "classified"
    elif roles == ["schematic_drawing"] and schematic_text:
        state = "classified"
    else:
        state = "candidate" if roles != ["unknown"] else "unresolved"
    return Classification(
        roles=tuple(roles),
        state=state,
        media_type="application/pdf",
        evidence=tuple(evidence),
    )


def classify_source(
    path: Path,
    *,
    media_type: str,
    prefix: bytes,
    extracted_text: str = "",
    page_count: int | None = None,
    sheet_headers: Iterable[str] = (),
) -> Classification:
    suffix = path.suffix.casefold()
    if suffix in {".rar", ".zip", ".7z", ".stp", ".step"}:
        return Classification(
            roles=("unrelated",),
            state="rejected",
            media_type=media_type,
            evidence=(
                _evidence(
                    "unsupported_for_review",
                    "该资料会被保留，但当前装配审查不解析压缩包或 3D 模型。",
                    weight="supporting",
                ),
            ),
        )
    if media_type == "application/pdf":
        return classify_pdf(path, extracted_text=extracted_text, page_count=page_count)
    if media_type in {"image/png", "image/jpeg"}:
        return Classification(
            roles=("assembly_drawing",),
            state="candidate",
            media_type=media_type,
            evidence=(
                _evidence(
                    "image_format",
                    "图片可作为板面底图候选，需要用户确认面别和配准。",
                    weight="supporting",
                ),
            ),
        )
    if suffix == ".xlsx":
        normalized_headers = " ".join(sheet_headers).casefold()
        has_ref = any(token in normalized_headers for token in ("reference", "designator", "位号"))
        has_xy = (
            any(token in normalized_headers for token in ("x coordinate", "x坐标", "x(mm)", "x(mil)"))
            and any(token in normalized_headers for token in ("y coordinate", "y坐标", "y(mm)", "y(mil)"))
        )
        has_bom = any(
            token in normalized_headers
            for token in ("part number", "子项编码", "物料编码", "料号")
        )
        roles: list[SourceRole] = []
        if has_ref and has_xy:
            roles.append("placement_coordinate")
        if has_ref and has_bom:
            roles.append("bom")
        if roles:
            return Classification(
                roles=tuple(roles),
                state="classified" if len(roles) == 1 else "candidate",
                media_type=media_type,
                evidence=(
                    _evidence(
                        "worksheet_headers",
                        "工作表字段匹配坐标或 BOM 数据结构。",
                        weight="strong" if len(roles) == 1 else "supporting",
                    ),
                ),
            )
        return Classification(
            roles=("unknown",),
            state="unresolved",
            media_type=media_type,
            evidence=(
                _evidence(
                    "worksheet_headers",
                    "工作簿表头未匹配坐标或 BOM 字段，仍保留供人工确认。",
                    weight="weak",
                ),
            ),
        )
    decoded = decode_text_sample(prefix)
    if decoded is not None:
        return _classify_text(path, decoded[0], media_type)
    if suffix in {".dxf"}:
        return _classify_drawing_name(path, media_type)
    return Classification(
        roles=("unknown",),
        state="unresolved",
        media_type=media_type,
        evidence=(
            _evidence(
                "unrecognized_format",
                "当前未注册该格式的解析器，文件不会被静默丢弃。",
                weight="weak",
            ),
        ),
    )
