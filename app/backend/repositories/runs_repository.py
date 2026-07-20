from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.backend.paths import AppPaths
from app.backend.repositories.assets_repository import AssetsRepository
from app.backend.repositories.database import PlatformDatabase


INPUT_KEYS = ("source_bom", "bom1", "bom2", "bom", "netlist", "netlist1", "netlist2")
MAX_RUNS = 500
_MIGRATION_LOCK = threading.Lock()


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_load(value: str, fallback: object) -> object:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def output_relative_path(root: Path, value: object) -> Optional[str]:
    outputs_root = AppPaths(root).outputs_dir.resolve()
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        candidate = path
    else:
        parts = [part for part in text.replace("\\", "/").split("/") if part and part != "."]
        if not parts or ".." in parts:
            return None
        for index in range(len(parts) - 1):
            if [part.lower() for part in parts[index:index + 2]] == ["data", "outputs"]:
                parts = parts[index + 2:]
                break
        if not parts:
            return None
        candidate = outputs_root.joinpath(*parts)
    try:
        return candidate.resolve().relative_to(outputs_root).as_posix()
    except (OSError, ValueError):
        return None


def _output_values(result: dict[str, object]) -> list[object]:
    outputs = result.get("outputs") or []
    if not outputs and isinstance(result.get("result"), dict):
        nested = result["result"].get("outputs")
        if isinstance(nested, dict):
            outputs = (
                list(nested.get("main_boms") or [])
                + list(nested.get("nc_summaries") or [])
                + ([nested["summary"]] if nested.get("summary") else [])
            )
    return list(outputs) if isinstance(outputs, list) else []


def _input_values(params: dict[str, object]) -> tuple[list[str], list[Path]]:
    names: list[str] = []
    paths: list[Path] = []
    for key in INPUT_KEYS:
        raw = params.get(key)
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if not value:
                continue
            path = Path(str(value))
            names.append(path.name)
            paths.append(path)
    return names, paths


def _display_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


def _legacy_datetime(value: object) -> str:
    text = str(value or "").strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def _run_reference(value: object) -> str:
    text = str(value or "")
    if not text:
        raise ValueError("invalid run_id")
    try:
        return str(UUID(text))
    except ValueError:
        if all(character.isalnum() or character == "_" for character in text):
            return text
        raise ValueError(f"invalid run_id: {text!r}")


class RunsRepository:
    def __init__(self, root: Path, *, database: Optional[PlatformDatabase] = None) -> None:
        self.root = Path(root).resolve()
        self.paths = AppPaths(self.root)
        self.database = database or PlatformDatabase(self.root)
        self.assets = AssetsRepository(self.root, database=self.database)
        self._migrate_legacy_history()

    def _legacy_entries(self) -> list[dict[str, object]]:
        history_dir = self.paths.history_dir
        entries: dict[str, dict[str, object]] = {}
        runs_dir = history_dir / "runs"
        if runs_dir.is_dir():
            for path in sorted(runs_dir.glob("*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8-sig"))
                except (OSError, ValueError):
                    continue
                if not isinstance(payload, dict):
                    continue
                meta = payload.get("_meta")
                if not isinstance(meta, dict) or not meta.get("id"):
                    continue
                legacy_id = str(meta["id"])
                entries[legacy_id] = {**meta, "payload": payload}
        index_path = history_dir / "index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            index = []
        if isinstance(index, list):
            for entry in index:
                if not isinstance(entry, dict) or not entry.get("id"):
                    continue
                legacy_id = str(entry["id"])
                entries.setdefault(legacy_id, dict(entry))
        return list(entries.values())

    def _legacy_source_fingerprint(self) -> str:
        history_dir = self.paths.history_dir
        index_path = history_dir / "index.json"
        runs_dir = history_dir / "runs"
        return f"index_file={int(index_path.is_file())};runs_dir={int(runs_dir.is_dir())}"

    def _legacy_migration_done(self) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value FROM repository_state WHERE key = 'legacy_history_migration_done'"
            ).fetchone()
        return row is not None and str(row[0]) == "1"

    def _legacy_output(self, value: object) -> Optional[tuple[str, Path]]:
        relative = output_relative_path(self.root, value)
        if relative is None:
            return None
        direct = self.paths.outputs_dir / relative
        if direct.is_file():
            return relative, direct
        if "/" in relative:
            return None
        matches = [path for path in self.paths.outputs_dir.rglob(relative) if path.is_file()]
        if len(matches) != 1:
            return None
        matched = matches[0]
        return matched.relative_to(self.paths.outputs_dir).as_posix(), matched

    def _migrate_legacy_history(self) -> None:
        if self._legacy_migration_done():
            return
        with _MIGRATION_LOCK:
            if self._legacy_migration_done():
                return
            fingerprint = self._legacy_source_fingerprint()
            entries = self._legacy_entries()
            with self.database.transaction() as connection:
                for entry in entries:
                    legacy_id = str(entry.get("id") or "").strip()
                    if not legacy_id:
                        continue
                    try:
                        run_id = UUID(legacy_id)
                    except ValueError:
                        run_id = uuid5(NAMESPACE_URL, f"insta360-hw-history:{legacy_id}")
                    exists = connection.execute(
                        "SELECT 1 FROM runs WHERE id = ? OR legacy_id = ? LIMIT 1",
                        (str(run_id), legacy_id),
                    ).fetchone()
                    if exists is not None:
                        continue

                    payload_value = entry.get("payload")
                    payload = dict(payload_value) if isinstance(payload_value, dict) else {
                        "status": "ok",
                        "summary": entry.get("summary") or {},
                        "outputs": entry.get("outputs") or [],
                    }
                    raw_outputs = entry.get("outputs")
                    if not isinstance(raw_outputs, list):
                        raw_outputs = _output_values(payload)
                    resolved_outputs = [
                        resolved for value in raw_outputs
                        if (resolved := self._legacy_output(value)) is not None
                    ]
                    output_relatives = [relative for relative, _ in resolved_outputs]
                    payload["outputs"] = output_relatives
                    summary = entry.get("summary")
                    if summary is None:
                        summary = payload.get("summary") or {}
                    inputs = entry.get("inputs") if isinstance(entry.get("inputs"), list) else []
                    created_at = _legacy_datetime(entry.get("time"))
                    connection.execute(
                        """
                        INSERT INTO runs(
                            id, legacy_id, tool_id, tool_name, status, params_json, decisions_json,
                            summary_json, result_json, input_names_json, created_at, completed_at
                        ) VALUES (?, ?, ?, ?, 'succeeded', '{}', '{}', ?, ?, ?, ?, ?)
                        """,
                        (
                            str(run_id),
                            legacy_id,
                            str(entry.get("tool") or "legacy"),
                            str(entry.get("tool_name") or entry.get("tool") or "历史任务"),
                            _json_dump(summary),
                            _json_dump(payload),
                            _json_dump(inputs),
                            created_at,
                            created_at,
                        ),
                    )
                    for ordinal, (relative, path) in enumerate(resolved_outputs):
                        asset_id = uuid5(
                            NAMESPACE_URL,
                            f"insta360-hw-history-asset:{legacy_id}:{relative}",
                        )
                        asset = self.assets.promote(
                            connection,
                            path,
                            source_run_id=run_id,
                            asset_id=asset_id,
                            created_at=created_at,
                        )
                        if asset is not None:
                            connection.execute(
                                "INSERT OR IGNORE INTO run_outputs(run_id, asset_id, ordinal) VALUES (?, ?, ?)",
                                (str(run_id), str(asset.id), ordinal),
                            )
                connection.execute(
                    """
                    INSERT INTO repository_state(key, value, updated_at)
                    VALUES ('legacy_history_fingerprint', ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                    """,
                    (fingerprint,),
                )
                connection.execute(
                    """
                    INSERT INTO repository_state(key, value, updated_at)
                    VALUES ('legacy_history_migration_done', '1', CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                    """
                )

    def record_success(
        self,
        tool_id: str,
        tool_name: str,
        params: dict[str, object],
        result: dict[str, object],
    ) -> str:
        run_id = uuid4()
        created_at = datetime.now(timezone.utc).isoformat()
        input_names, input_paths = _input_values(params)
        output_relatives = [
            relative for value in _output_values(result)
            if (relative := output_relative_path(self.root, value)) is not None
        ]
        normalized_result = dict(result)
        normalized_result["outputs"] = output_relatives
        summary = result.get("summary")
        if summary is None and isinstance(result.get("result"), dict):
            summary = result["result"].get("summary")
        if summary is None:
            summary = {}
        decisions = result.get("decisions") if isinstance(result.get("decisions"), dict) else {}

        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs(
                    id, legacy_id, tool_id, tool_name, status, params_json, decisions_json,
                    summary_json, result_json, input_names_json, created_at, completed_at
                ) VALUES (?, NULL, ?, ?, 'succeeded', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(run_id),
                    tool_id,
                    tool_name,
                    _json_dump(params),
                    _json_dump(decisions),
                    _json_dump(summary),
                    _json_dump(normalized_result),
                    _json_dump(input_names),
                    created_at,
                    created_at,
                ),
            )
            input_ordinal = 0
            for path in input_paths:
                asset = self.assets.promote(connection, path, reuse_existing=True, created_at=created_at)
                if asset is None:
                    continue
                connection.execute(
                    "INSERT OR IGNORE INTO run_inputs(run_id, asset_id, ordinal) VALUES (?, ?, ?)",
                    (str(run_id), str(asset.id), input_ordinal),
                )
                input_ordinal += 1
            for ordinal, relative in enumerate(output_relatives):
                path = self.paths.outputs_dir / relative
                asset = self.assets.promote(
                    connection,
                    path,
                    source_run_id=run_id,
                    created_at=created_at,
                )
                if asset is None:
                    continue
                connection.execute(
                    "INSERT INTO run_outputs(run_id, asset_id, ordinal) VALUES (?, ?, ?)",
                    (str(run_id), str(asset.id), ordinal),
                )
        return str(run_id)

    def _row(self, run_id: str) -> Optional[sqlite3.Row]:
        reference = _run_reference(run_id)
        with self.database.connect() as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                "SELECT * FROM runs WHERE id = ? OR legacy_id = ? LIMIT 1",
                (reference, reference),
            ).fetchone()

    def _outputs(self, connection: sqlite3.Connection, run_id: str) -> list[str]:
        rows = connection.execute(
            """
            SELECT a.relative_path FROM run_outputs ro
            JOIN assets a ON a.id = ro.asset_id
            WHERE ro.run_id = ? ORDER BY ro.ordinal
            """,
            (run_id,),
        ).fetchall()
        outputs: list[str] = []
        for row in rows:
            relative = str(row[0]).replace("\\", "/")
            outputs.append(relative[len("outputs/"):] if relative.startswith("outputs/") else relative)
        return outputs

    def list_runs(self, limit: int = MAX_RUNS) -> list[dict[str, object]]:
        with self.database.connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "time": _display_time(row["created_at"]),
                    "tool": row["tool_id"],
                    "tool_name": row["tool_name"],
                    "inputs": _json_load(row["input_names_json"], []),
                    "outputs": self._outputs(connection, row["id"]),
                    "summary": _json_load(row["summary_json"], {}),
                    "status": row["status"],
                }
                for row in rows
            ]

    def get_run(self, run_id: str) -> Optional[dict[str, object]]:
        row = self._row(run_id)
        if row is None:
            return None
        result = _json_load(row["result_json"], {})
        payload = dict(result) if isinstance(result, dict) else {}
        with self.database.connect() as connection:
            outputs = self._outputs(connection, row["id"])
        payload["outputs"] = outputs
        payload["_meta"] = {
            "id": row["id"],
            "legacy_id": row["legacy_id"] or "",
            "time": _display_time(row["created_at"]),
            "tool": row["tool_id"],
            "tool_name": row["tool_name"],
            "inputs": _json_load(row["input_names_json"], []),
        }
        return payload

    def remove_run(self, run_id: str) -> bool:
        reference = _run_reference(run_id)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM runs WHERE id = ? OR legacy_id = ?",
                (reference, reference),
            )
        return cursor.rowcount > 0

    def clear_runs(self) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM runs")
