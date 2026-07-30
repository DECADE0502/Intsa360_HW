from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.backend.contracts.smt_analysis import (
    SmtCoordinateOccurrence,
    SmtCoordinateQuality,
    SmtCoordinateSet,
    SmtQualityIssue,
)
from app.backend.parsers.xy import parse_xy_file
from app.backend.smt_analysis.coordinates.base import CoordinateProbe


_ROW_RE = re.compile(
    r"^\s*[^!\r\n]+\s*!\s*[-+]?\d+(?:\.\d+)?\s*!\s*[-+]?\d+(?:\.\d+)?\s*!",
    re.MULTILINE,
)


def _set_id(path: Path, adapter_id: str) -> str:
    digest = hashlib.sha256()
    digest.update(str(path.resolve()).casefold().encode("utf-8"))
    digest.update(b"\0")
    digest.update(adapter_id.encode("ascii"))
    return f"coords-{digest.hexdigest()[:24]}"


def _source_id(path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()
    return f"source-local-{digest[:20]}"


class CadenceXYAdapter:
    adapter_id = "cadence_xy_v1"

    def probe(self, path: Path) -> list[CoordinateProbe]:
        if not path.is_file():
            return []
        try:
            raw = path.read_bytes()[:262144]
        except OSError:
            return []
        text = ""
        for encoding in ("utf-8-sig", "utf-16", "gb18030"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeError:
                continue
        if not text:
            return []
        has_units = re.search(r"^\s*UUNITS\s*=\s*(?:MM|MILS)\s*$", text, re.I | re.M)
        row_count = len(_ROW_RE.findall(text))
        if not has_units or row_count == 0:
            return []
        confidence = 100 if row_count >= 2 else 90
        return [
            CoordinateProbe(
                adapter_id=self.adapter_id,
                confidence=confidence,
                reasons=(
                    "包含 UUNITS 单位声明",
                    f"抽样内容识别到 {row_count} 行 Cadence 坐标记录",
                ),
            )
        ]

    def parse(self, path: Path, probe: CoordinateProbe) -> SmtCoordinateSet:
        unit_info, components = parse_xy_file(path)
        refs: dict[str, int] = {}
        occurrences: list[SmtCoordinateOccurrence] = []
        for component in components:
            normalized_ref = component.ref.strip().upper()
            refs[normalized_ref] = refs.get(normalized_ref, 0) + 1
            occurrences.append(
                SmtCoordinateOccurrence(
                    occurrence_id=f"{_set_id(path, self.adapter_id)}-{component.source_line}",
                    raw_ref=component.ref,
                    ref=normalized_ref,
                    raw_x=format(component.x_mm / unit_info.scale, ".15g"),
                    raw_y=format(component.y_mm / unit_info.scale, ".15g"),
                    normalized_x=component.x_mm,
                    normalized_y=component.y_mm,
                    raw_side="m" if component.side == "bottom" else "",
                    side=component.side,
                    raw_rotation=str(component.rotation),
                    normalized_rotation=float(component.rotation),
                    footprint=component.footprint,
                    source_line=component.source_line,
                    warnings=[],
                )
            )
        duplicates = sorted(ref for ref, count in refs.items() if count > 1)
        issues = [
            SmtQualityIssue(
                code="duplicate_coordinate_ref",
                severity="blocking",
                message=f"位号 {ref} 在坐标数据中出现多次。",
            )
            for ref in duplicates
        ]
        return SmtCoordinateSet(
            coordinate_set_id=_set_id(path, self.adapter_id),
            source_asset_id=_source_id(path),
            adapter_id=self.adapter_id,
            sheet_or_section=probe.sheet_or_section,
            declared_unit=unit_info.units,
            normalized_unit="mil" if unit_info.units == "mils" else "mm",
            unit_state="verified",
            scope_semantics="unknown",
            side_mapping={"": "top", "m": "bottom"},
            rotation_semantics="degrees_ccw",
            quality_report=SmtCoordinateQuality(
                valid_rows=len(occurrences),
                rejected_rows=0,
                unnamed_rows=0,
                duplicate_refs=duplicates,
                issues=issues,
            ),
            occurrences=occurrences,
        )
