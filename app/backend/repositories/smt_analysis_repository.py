from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from uuid import UUID, uuid4

from app.backend.contracts.smt_analysis import (
    SmtAnalysisRunResponse,
    SmtPlacementDecision,
)
from app.backend.paths import AppPaths
from app.backend.repositories.database import PlatformDatabase


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dump(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )


def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _run_id(value: UUID | str) -> str:
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise ValueError("SMT 分析运行 ID 无效") from exc


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class SmtAnalysisRepository:
    def __init__(
        self,
        root: Path,
        *,
        database: PlatformDatabase | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.paths = AppPaths(self.root)
        self.paths.ensure_runtime_dirs()
        self.database = database or PlatformDatabase(self.root)

    def create_or_reuse(
        self,
        *,
        source_fingerprint: str,
        parser_version: str,
        rule_version: str,
        source_relative_path: str,
        context: Mapping[str, object],
    ) -> tuple[str, bool]:
        now = _utc_now()
        with self.database.transaction() as connection:
            connection.row_factory = sqlite3.Row
            existing = connection.execute(
                """
                SELECT id, active_revision
                FROM smt_analysis_runs
                WHERE source_fingerprint = ? AND parser_version = ? AND rule_version = ?
                LIMIT 1
                """,
                (source_fingerprint, parser_version, rule_version),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    """
                    UPDATE smt_analysis_runs
                    SET context_json = ?, source_relative_path = ?, updated_at = ?, last_error = ''
                    WHERE id = ?
                    """,
                    (_json_dump(dict(context)), source_relative_path, now, existing["id"]),
                )
                return str(existing["id"]), existing["active_revision"] is not None
            identifier = str(uuid4())
            connection.execute(
                """
                INSERT INTO smt_analysis_runs(
                    id, source_fingerprint, parser_version, rule_version, state,
                    source_relative_path, context_json, active_revision,
                    created_at, updated_at, last_error
                ) VALUES (?, ?, ?, ?, 'source', ?, ?, NULL, ?, ?, '')
                """,
                (
                    identifier,
                    source_fingerprint,
                    parser_version,
                    rule_version,
                    source_relative_path,
                    _json_dump(dict(context)),
                    now,
                    now,
                ),
            )
        return identifier, False

    def save_snapshot(
        self,
        snapshot: SmtAnalysisRunResponse,
        *,
        dependencies: Mapping[str, object] | None = None,
    ) -> int:
        identifier = _run_id(snapshot.run_id)
        payload = snapshot.model_dump(mode="json")
        now = _utc_now()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM smt_analysis_revisions WHERE run_id = ?",
                (identifier,),
            ).fetchone()
            if row is None:
                raise KeyError(f"SMT analysis run not found: {identifier}")
            revision = int(row[0]) + 1
            connection.execute(
                """
                INSERT INTO smt_analysis_revisions(
                    run_id, revision, state, dependencies_json, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    revision,
                    snapshot.state,
                    _json_dump(dict(dependencies or {})),
                    _json_dump(payload),
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE smt_analysis_runs
                SET state = ?, active_revision = ?, updated_at = ?, last_error = ''
                WHERE id = ?
                """,
                (snapshot.state, revision, now, identifier),
            )
        return revision

    def get_snapshot(self, run_id: UUID | str) -> SmtAnalysisRunResponse:
        identifier = _run_id(run_id)
        with self.database.connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT revision.payload_json
                FROM smt_analysis_runs AS run
                JOIN smt_analysis_revisions AS revision
                  ON revision.run_id = run.id AND revision.revision = run.active_revision
                WHERE run.id = ?
                """,
                (identifier,),
            ).fetchone()
        if row is None:
            raise KeyError(f"SMT analysis snapshot not found: {identifier}")
        return SmtAnalysisRunResponse.model_validate_json(row["payload_json"])

    def get_context(self, run_id: UUID | str) -> dict[str, object]:
        identifier = _run_id(run_id)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT context_json FROM smt_analysis_runs WHERE id = ?",
                (identifier,),
            ).fetchone()
        if row is None:
            raise KeyError(f"SMT analysis run not found: {identifier}")
        return _json_object(str(row[0]))

    def update_context(self, run_id: UUID | str, context: Mapping[str, object]) -> None:
        identifier = _run_id(run_id)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE smt_analysis_runs SET context_json = ?, updated_at = ? WHERE id = ?",
                (_json_dump(dict(context)), _utc_now(), identifier),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"SMT analysis run not found: {identifier}")

    def status(self, run_id: UUID | str) -> dict[str, object]:
        identifier = _run_id(run_id)
        with self.database.connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM smt_analysis_runs WHERE id = ?",
                (identifier,),
            ).fetchone()
        if row is None:
            raise KeyError(f"SMT analysis run not found: {identifier}")
        return {
            "run_id": row["id"],
            "state": row["state"],
            "active_revision": row["active_revision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_error": row["last_error"],
        }

    def record_failure(self, run_id: UUID | str, error: str) -> None:
        identifier = _run_id(run_id)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE smt_analysis_runs
                SET state = 'failed', last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(error), _utc_now(), identifier),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"SMT analysis run not found: {identifier}")

    def save_decision(
        self,
        run_id: UUID | str,
        placement_id: str,
        decision: SmtPlacementDecision,
    ) -> None:
        identifier = _run_id(run_id)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO smt_analysis_decisions(
                    run_id, placement_id, input_fingerprint, decision_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, placement_id) DO UPDATE SET
                    input_fingerprint = excluded.input_fingerprint,
                    decision_json = excluded.decision_json,
                    updated_at = excluded.updated_at
                """,
                (
                    identifier,
                    placement_id,
                    decision.input_fingerprint,
                    _json_dump(decision.model_dump(mode="json")),
                    _utc_now(),
                ),
            )

    def save_decisions(
        self,
        run_id: UUID | str,
        decisions: Mapping[str, SmtPlacementDecision],
    ) -> None:
        identifier = _run_id(run_id)
        if not decisions:
            return
        now = _utc_now()
        with self.database.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO smt_analysis_decisions(
                    run_id, placement_id, input_fingerprint, decision_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, placement_id) DO UPDATE SET
                    input_fingerprint = excluded.input_fingerprint,
                    decision_json = excluded.decision_json,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        identifier,
                        placement_id,
                        decision.input_fingerprint,
                        _json_dump(decision.model_dump(mode="json")),
                        now,
                    )
                    for placement_id, decision in decisions.items()
                ],
            )

    def decisions(self, run_id: UUID | str) -> dict[str, SmtPlacementDecision]:
        identifier = _run_id(run_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT placement_id, decision_json
                FROM smt_analysis_decisions
                WHERE run_id = ?
                """,
                (identifier,),
            ).fetchall()
        return {
            str(row[0]): SmtPlacementDecision.model_validate_json(row[1])
            for row in rows
        }

    def register_page_asset(
        self,
        *,
        run_id: UUID | str,
        page_id: str,
        path: Path,
        media_type: str,
        pixel_width: int,
        pixel_height: int,
    ) -> None:
        identifier = _run_id(run_id)
        source = Path(path).resolve()
        cache_root = self.paths.smt_analysis_cache_dir.resolve()
        try:
            relative = source.relative_to(cache_root).as_posix()
        except ValueError as exc:
            raise ValueError("SMT 页面资产不在受限缓存目录中") from exc
        if not source.is_file():
            raise FileNotFoundError(source)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO smt_analysis_page_assets(
                    run_id, page_id, cache_relative_path, sha256, media_type,
                    pixel_width, pixel_height, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, page_id) DO UPDATE SET
                    cache_relative_path = excluded.cache_relative_path,
                    sha256 = excluded.sha256,
                    media_type = excluded.media_type,
                    pixel_width = excluded.pixel_width,
                    pixel_height = excluded.pixel_height
                """,
                (
                    identifier,
                    page_id,
                    relative,
                    _file_sha256(source),
                    media_type,
                    pixel_width,
                    pixel_height,
                    _utc_now(),
                ),
            )

    def resolve_page_asset(
        self,
        run_id: UUID | str,
        page_id: str,
    ) -> tuple[Path, str]:
        identifier = _run_id(run_id)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT cache_relative_path, media_type
                FROM smt_analysis_page_assets
                WHERE run_id = ? AND page_id = ?
                """,
                (identifier, page_id),
            ).fetchone()
        if row is None:
            raise KeyError("SMT 页面预览不存在")
        root = self.paths.smt_analysis_cache_dir.resolve()
        path = (root / str(row[0])).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("SMT 页面缓存路径越界") from exc
        if not path.is_file():
            raise FileNotFoundError(path)
        return path, str(row[1])

    def remove(self, run_id: UUID | str) -> bool:
        identifier = _run_id(run_id)
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT cache_relative_path FROM smt_analysis_page_assets WHERE run_id = ?",
                (identifier,),
            ).fetchall()
            cursor = connection.execute(
                "DELETE FROM smt_analysis_runs WHERE id = ?",
                (identifier,),
            )
            removable: list[str] = []
            for row in rows:
                relative = str(row[0])
                remaining = connection.execute(
                    "SELECT 1 FROM smt_analysis_page_assets WHERE cache_relative_path = ? LIMIT 1",
                    (relative,),
                ).fetchone()
                if remaining is None:
                    removable.append(relative)
        cache_root = self.paths.smt_analysis_cache_dir.resolve()
        for relative in removable:
            path = (cache_root / relative).resolve()
            try:
                path.relative_to(cache_root)
            except ValueError:
                continue
            path.unlink(missing_ok=True)
            path.with_suffix(".json").unlink(missing_ok=True)
        return cursor.rowcount > 0
