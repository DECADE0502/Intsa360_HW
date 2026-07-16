from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path

from app.backend.paths import AppPaths
from app.backend.repositories.runs_repository import RunsRepository, output_relative_path


_MIRROR_LOCK = threading.Lock()


def _history_dir(root: Path) -> Path:
    path = AppPaths(root).history_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    try:
        if path.read_text(encoding="utf-8-sig") == serialized:
            return
    except OSError:
        pass
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _mirror_index(root: Path, runs: list[dict[str, object]]) -> None:
    try:
        with _MIRROR_LOCK:
            _atomic_json(_history_dir(root) / "index.json", runs)
    except OSError:
        pass


def record(
    root: Path,
    tool_id: str,
    tool_name: str,
    params: dict[str, object] | None,
    result: dict[str, object],
) -> str | None:
    if result.get("status") != "ok":
        return None
    repository = RunsRepository(root)
    run_id = repository.record_success(tool_id, tool_name, params or {}, result)
    detail = repository.get_run(run_id)
    if detail is not None:
        try:
            with _MIRROR_LOCK:
                _atomic_json(_history_dir(root) / "runs" / f"{run_id}.json", detail)
        except OSError:
            pass
    _mirror_index(root, repository.list_runs())
    return run_id


def list_runs(root: Path) -> list[dict[str, object]]:
    runs = RunsRepository(root).list_runs()
    _mirror_index(root, runs)
    return runs


def remove_run(root: Path, run_id: str) -> bool:
    repository = RunsRepository(root)
    removed = repository.remove_run(str(run_id))
    runs_dir = _history_dir(root) / "runs"
    for path in runs_dir.glob("*.json") if runs_dir.exists() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        meta = payload.get("_meta") if isinstance(payload, dict) else None
        identifiers = {str(meta.get("id") or ""), str(meta.get("legacy_id") or "")} if isinstance(meta, dict) else set()
        if str(run_id) in identifiers:
            path.unlink(missing_ok=True)
    _mirror_index(root, repository.list_runs())
    return removed


def clear_runs(root: Path) -> bool:
    RunsRepository(root).clear_runs()
    runs_dir = _history_dir(root) / "runs"
    if runs_dir.exists():
        shutil.rmtree(runs_dir, ignore_errors=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    _mirror_index(root, [])
    return True


def get_run(root: Path, run_id: str) -> dict[str, object] | None:
    return RunsRepository(root).get_run(str(run_id))
