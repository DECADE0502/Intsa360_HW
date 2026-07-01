from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

# 运行历史：每次成功运行都把完整结果落盘，可在前端回溯重渲染。
# - data/history/runs/<id>.json  完整结果（含 table / compare，用于回溯重渲染）
# - data/history/index.json      轻量索引（时间、工具、摘要、输出文件名），倒序

_LOCK = threading.Lock()
_MAX_INDEX = 500
INPUT_KEYS = ("source_bom", "bom1", "bom2", "bom", "netlist", "netlist1", "netlist2")


def _dirs(root: Path) -> tuple[Path, Path]:
    base = root / "data" / "history"
    runs = base / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    return base, runs


def _index_path(root: Path) -> Path:
    return root / "data" / "history" / "index.json"


def _sanitize_run_id(run_id: str) -> str:
    safe = "".join(ch for ch in str(run_id or "") if ch.isalnum() or ch == "_")
    if not safe or safe != run_id:
        raise ValueError(f"invalid run_id: {run_id!r}")
    return safe


def _input_names(params: dict[str, object]) -> list[str]:
    names: list[str] = []
    for key in INPUT_KEYS:
        value = params.get(key)
        if value:
            names.append(Path(str(value)).name)
    return names


def _extract_summary(result: dict[str, object]) -> object:
    summary = result.get("summary")
    if summary is None and isinstance(result.get("result"), dict):
        summary = result["result"].get("summary")
    return summary if summary is not None else {}


def _extract_output_names(result: dict[str, object]) -> list[str]:
    outputs = result.get("outputs") or []
    if not outputs and isinstance(result.get("result"), dict):
        nested = result["result"].get("outputs")
        if isinstance(nested, dict):
            outputs = (
                (nested.get("main_boms") or [])
                + (nested.get("nc_summaries") or [])
                + ([nested["summary"]] if nested.get("summary") else [])
            )
    return [Path(str(path)).name for path in outputs]


def _entry_from_payload(payload: dict[str, object]) -> dict[str, object] | None:
    meta = payload.get("_meta")
    if not isinstance(meta, dict) or not meta.get("id"):
        return None
    return {
        **meta,
        "summary": _extract_summary(payload),
        "outputs": _extract_output_names(payload),
    }


def _rebuild_index_from_runs(root: Path) -> list[dict[str, object]]:
    _, runs = _dirs(root)
    entries: list[dict[str, object]] = []
    for path in sorted(runs.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if isinstance(payload, dict):
            entry = _entry_from_payload(payload)
            if entry is not None:
                entries.append(entry)
    entries.sort(key=lambda item: str(item.get("time", "")), reverse=True)
    del entries[_MAX_INDEX:]
    _index_path(root).write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return entries


def _read_index(root: Path) -> list[dict[str, object]]:
    path = _index_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else _rebuild_index_from_runs(root)
    except (FileNotFoundError, ValueError, OSError):
        return _rebuild_index_from_runs(root)


def record(
    root: Path,
    tool_id: str,
    tool_name: str,
    params: dict[str, object] | None,
    result: dict[str, object],
) -> str | None:
    if result.get("status") != "ok":
        return None

    _, runs = _dirs(root)
    now = datetime.now()
    run_id = now.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    meta = {
        "id": run_id,
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "tool": tool_id,
        "tool_name": tool_name,
        "inputs": _input_names(params or {}),
    }

    payload = dict(result)
    payload["_meta"] = meta
    (runs / f"{run_id}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    entry = {
        **meta,
        "summary": _extract_summary(result),
        "outputs": _extract_output_names(result),
    }
    with _LOCK:
        path = _index_path(root)
        index: list[dict[str, object]] = []
        if path.exists():
            try:
                index = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                index = []
        index.insert(0, entry)
        del index[_MAX_INDEX:]
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_id


def list_runs(root: Path) -> list[dict[str, object]]:
    return _read_index(root)


def remove_run(root: Path, run_id: str) -> bool:
    safe_id = _sanitize_run_id(run_id)
    path = _index_path(root)
    runs_ok = False
    with _LOCK:
        if path.exists():
            try:
                index = _read_index(root)
                index = [e for e in index if e.get("id") != safe_id]
                path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
                runs_ok = True
            except (ValueError, OSError):
                pass
    _, runs = _dirs(root)
    entry = runs / f"{safe_id}.json"
    if entry.exists():
        entry.unlink()
    return runs_ok


def clear_runs(root: Path) -> bool:
    path = _index_path(root)
    base, runs = _dirs(root)
    with _LOCK:
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    import shutil
    if runs.exists():
        shutil.rmtree(runs, ignore_errors=True)
        runs.mkdir(parents=True, exist_ok=True)
    return True


def get_run(root: Path, run_id: str) -> dict[str, object] | None:
    safe = _sanitize_run_id(run_id)
    _, runs = _dirs(root)
    path = runs / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
