from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from app.backend.paths import AppPaths


TERMINAL_PHASES = {"completed", "failed", "cancelled"}
PRECOMMIT_PHASES = {"queued", "downloading", "verifying", "staging"}
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_JOB_LOCK = threading.Lock()


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.025 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def valid_job_id(job_id: str) -> bool:
    return bool(_JOB_ID_RE.fullmatch(job_id))


def job_path(root: Path, job_id: str) -> Path:
    if not valid_job_id(job_id):
        raise ValueError("更新任务编号无效")
    return AppPaths(root).lifecycle_v3_jobs_dir / f"{job_id}.json"


def latest_path(root: Path) -> Path:
    return AppPaths(root).lifecycle_v3_jobs_dir / "latest.json"


def write_job(root: Path, job_id: str, **updates: object) -> dict[str, object]:
    path = job_path(root, job_id)
    with _JOB_LOCK:
        try:
            current = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            current = {}
        if not isinstance(current, dict):
            current = {}
        current.update(updates)
        current.update(
            {
                "schema": 3,
                "job_id": job_id,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        phase = str(current.get("phase") or "queued")
        current["running"] = phase not in TERMINAL_PHASES
        current["done"] = phase == "completed"
        current["failed"] = phase == "failed"
        atomic_json(path, current)
        atomic_json(latest_path(root), {"schema": 3, "job_id": job_id})
        return current


def read_job(root: Path, job_id: str) -> dict[str, object] | None:
    try:
        raw = json.loads(job_path(root, job_id).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return raw if isinstance(raw, dict) and raw.get("schema") == 3 else None


def latest_job_id(root: Path) -> str:
    try:
        raw = json.loads(latest_path(root).read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict) or raw.get("schema") != 3:
            return ""
        value = str(raw.get("job_id") or "")
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""
    return value if valid_job_id(value) else ""
