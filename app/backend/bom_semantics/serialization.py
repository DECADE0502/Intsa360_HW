from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from app.backend.bom_semantics.contracts import (
    BOM_COMPARE_SCHEMA_VERSION,
    BOM_SEMANTIC_MODEL_VERSION,
    CompareResult,
)


def compare_result_json(result: CompareResult, *, indent: int | None = 2) -> str:
    return json.dumps(
        result.payload(),
        ensure_ascii=False,
        sort_keys=True,
        indent=indent,
        allow_nan=False,
    )


def write_compare_result_json(result: CompareResult, path: Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(compare_result_json(result) + "\n", encoding="utf-8")
    temporary.replace(destination)
    verify_compare_result_json(destination, result.analysis_fingerprint)
    return destination


def read_compare_result_json(path: Path) -> Mapping[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("BOM 对比 JSON 顶层必须是对象。")
    if payload.get("schema_version") != BOM_COMPARE_SCHEMA_VERSION:
        raise ValueError("BOM 对比 JSON schema 版本不受支持。")
    if payload.get("model_version") != BOM_SEMANTIC_MODEL_VERSION:
        raise ValueError("BOM 对比语义模型版本不受支持。")
    return payload


def verify_compare_result_json(path: Path, expected_fingerprint: str) -> None:
    payload = read_compare_result_json(path)
    if payload.get("analysis_fingerprint") != expected_fingerprint:
        raise ValueError("BOM 对比 JSON 回读指纹不一致。")
    summary = payload.get("summary")
    events = payload.get("events")
    if not isinstance(summary, dict) or not isinstance(events, list):
        raise ValueError("BOM 对比 JSON 缺少摘要或事件。")
    if int(summary.get("changed_event_count", -1)) != len(events):
        raise ValueError("BOM 对比 JSON 事件数量与摘要不一致。")

