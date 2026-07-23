from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from app.backend.contracts.assets import Asset, AssetKind
from app.backend.paths import AppPaths
from app.backend.repositories.database import PlatformDatabase


_HASH_CHUNK = 1024 * 1024


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_bom_decision_manifest(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(payload, dict)
        and not payload.get("manifest_kind")
        and payload.get("schema_version") == 2
        and isinstance(payload.get("placements"), list)
        and bool(str(payload.get("rule_version") or "").strip())
    )


def _is_bom_semantic_manifest(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("manifest_kind") == "bom_process_semantic_manifest"
        and payload.get("schema_version") == 2
        and isinstance(payload.get("boards"), list)
        and isinstance(payload.get("placements"), list)
    )


def _asset_from_row(row: sqlite3.Row) -> Asset:
    return Asset(
        id=row["id"],
        kind=row["kind"],
        format=row["format"],
        display_name=row["display_name"],
        relative_path=row["relative_path"],
        sha256=row["sha256"],
        size=row["size"],
        created_at=row["created_at"],
        source_run_id=row["source_run_id"],
        pinned=bool(row["pinned"]),
        metadata=_json_object(row["metadata_json"]),
    )


def _fingerprint(path: Path) -> tuple[str, int, bool]:
    digest = hashlib.sha256()
    if path.is_file():
        size = 0
        with path.open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size, False
    if not path.is_dir():
        raise FileNotFoundError(path)

    size = 0
    for child in sorted(path.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if child.is_symlink() or not child.is_file():
            continue
        relative = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with child.open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK):
                digest.update(chunk)
                size += len(chunk)
        digest.update(b"\0")
    return digest.hexdigest(), size, True


def _infer_kind(path: Path) -> AssetKind:
    suffix = path.suffix.lower()
    if path.is_dir() or suffix == ".dat":
        return AssetKind.NETLIST
    if suffix in {".xlsx", ".xls", ".csv"}:
        return AssetKind.BOM
    if suffix in {".json", ".txt", ".html", ".pdf"}:
        return AssetKind.REPORT
    return AssetKind.OUTPUT


def _infer_format(path: Path) -> str:
    if path.is_dir():
        return "directory"
    return path.suffix.lower().lstrip(".") or "file"


class AssetsRepository:
    def __init__(self, root: Path, *, database: Optional[PlatformDatabase] = None) -> None:
        self.display_root = Path(root).absolute()
        self.root = Path(root).resolve()
        self.paths = AppPaths(self.root)
        self.display_data_dir = self.display_root / "data"
        self.database = database or PlatformDatabase(self.root)

    def data_relative_path(self, path: Path) -> Optional[str]:
        try:
            return path.resolve().relative_to(self.paths.data_dir.resolve()).as_posix()
        except (OSError, ValueError):
            return None

    def resolve(self, relative_path: str) -> Optional[Path]:
        candidate = (self.paths.data_dir / relative_path).resolve()
        try:
            candidate.relative_to(self.paths.data_dir.resolve())
        except ValueError:
            return None
        return candidate

    def promote(
        self,
        connection: sqlite3.Connection,
        path: Path,
        *,
        source_run_id: Optional[UUID] = None,
        reuse_existing: bool = False,
        asset_id: Optional[UUID] = None,
        created_at: Optional[str] = None,
    ) -> Optional[Asset]:
        relative = self.data_relative_path(path)
        if relative is None or not path.exists():
            return None
        sha256, size, is_directory = _fingerprint(path)
        connection.row_factory = sqlite3.Row
        if reuse_existing:
            existing = connection.execute(
                "SELECT * FROM assets WHERE relative_path = ? AND sha256 = ? ORDER BY created_at DESC LIMIT 1",
                (relative, sha256),
            ).fetchone()
            if existing is not None:
                return _asset_from_row(existing)

        identifier = asset_id or uuid4()
        metadata = {"is_directory": is_directory, "missing": False}
        connection.execute(
            """
            INSERT OR IGNORE INTO assets(
                id, kind, format, display_name, relative_path, sha256, size,
                created_at, source_run_id, pinned, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                str(identifier),
                _infer_kind(path).value,
                _infer_format(path),
                path.name,
                relative,
                sha256,
                size,
                created_at or _utc_now_text(),
                str(source_run_id) if source_run_id else None,
                json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        row = connection.execute("SELECT * FROM assets WHERE id = ?", (str(identifier),)).fetchone()
        return _asset_from_row(row) if row is not None else None

    def get(self, asset_id: UUID | str) -> Asset:
        identifier = str(UUID(str(asset_id)))
        with self.database.connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM assets WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(f"asset not found: {identifier}")
        return _asset_from_row(row)

    def list(self) -> list[Asset]:
        with self.database.connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM assets ORDER BY created_at DESC, rowid DESC").fetchall()
        return [_asset_from_row(row) for row in rows]

    def rebuild_metadata(self, asset_id: UUID | str | None = None) -> dict[str, int]:
        identifier = str(UUID(str(asset_id))) if asset_id is not None else None
        updated = 0
        missing = 0
        with self.database.transaction() as connection:
            connection.row_factory = sqlite3.Row
            if identifier is None:
                rows = connection.execute("SELECT * FROM assets").fetchall()
            else:
                rows = connection.execute("SELECT * FROM assets WHERE id = ?", (identifier,)).fetchall()
                if not rows:
                    raise KeyError(f"asset not found: {identifier}")
            for row in rows:
                path = self.resolve(row["relative_path"])
                metadata = _json_object(row["metadata_json"])
                if path is None or not path.exists():
                    metadata["missing"] = True
                    missing += 1
                    connection.execute(
                        "UPDATE assets SET metadata_json = ? WHERE id = ?",
                        (json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), row["id"]),
                    )
                else:
                    sha256, size, is_directory = _fingerprint(path)
                    metadata.update({"is_directory": is_directory, "missing": False})
                    connection.execute(
                        "UPDATE assets SET sha256 = ?, size = ?, metadata_json = ? WHERE id = ?",
                        (
                            sha256,
                            size,
                            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                            row["id"],
                        ),
                    )
                updated += 1
        result = {"updated": updated}
        if missing:
            result["missing"] = missing
        return result

    def list_processed_boms(self) -> list[dict[str, object]]:
        with self.database.connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT a.*, r.id AS run_id, r.tool_id, r.tool_name, r.created_at AS run_created_at,
                       r.summary_json
                FROM assets a
                LEFT JOIN runs r ON r.id = a.source_run_id
                LEFT JOIN run_outputs ro ON ro.asset_id = a.id AND ro.run_id = a.source_run_id
                WHERE a.kind = 'bom'
                ORDER BY a.created_at DESC, ro.ordinal ASC, a.rowid DESC
                """
            ).fetchall()
            candidate_manifests = connection.execute(
                """
                SELECT ro.run_id, a.relative_path
                FROM run_outputs ro
                JOIN assets a ON a.id = ro.asset_id
                WHERE LOWER(a.format) = 'json'
                ORDER BY ro.ordinal ASC
                """
            ).fetchall()

        manifest_by_run: dict[str, str] = {}
        semantic_manifest_by_run: dict[str, str] = {}
        for candidate in candidate_manifests:
            run_id = str(candidate["run_id"] or "")
            if not run_id:
                continue
            relative = str(candidate["relative_path"] or "")
            path = self.resolve(relative)
            if path is None or not path.is_file():
                continue
            if run_id not in manifest_by_run and _is_bom_decision_manifest(path):
                manifest_by_run[run_id] = str(self.display_data_dir / relative)
            if run_id not in semantic_manifest_by_run and _is_bom_semantic_manifest(path):
                semantic_manifest_by_run[run_id] = str(self.display_data_dir / relative)

        results: list[dict[str, object]] = []
        seen: set[str] = set()
        for row in rows:
            name = str(row["display_name"])
            upper = name.upper()
            if not (upper.endswith(".XLSX") or upper.endswith(".XLS")):
                continue
            if "_PLM_BOM" not in upper and "_OA_BOM" not in upper:
                continue
            if "NC" in upper:
                continue
            relative = str(row["relative_path"])
            if relative in seen:
                continue
            path = self.resolve(relative)
            if path is None or not path.is_file():
                continue
            seen.add(relative)
            if "_PLM_" in upper or upper.endswith("_PLM_BOM.XLSX"):
                format_name = "PLM"
            elif "_OA_" in upper or upper.endswith("_OA_BOM.XLSX"):
                format_name = "OA"
            else:
                format_name = "BOM"
            run_summary = _json_object(row["summary_json"] or "{}")
            semantic = run_summary.get("semantic")
            if not isinstance(semantic, dict):
                semantic = {}
            results.append(
                {
                    "id": row["id"],
                    "kind": "processed_bom",
                    "name": name,
                    "path": str(self.display_data_dir / relative),
                    "relative_path": relative,
                    "format": format_name,
                    "run_id": row["run_id"] or "",
                    "source_tool": row["tool_id"] or "",
                    "source_tool_name": row["tool_name"] or "",
                    "time": row["run_created_at"] or row["created_at"],
                    "summary": run_summary,
                    "semantic": semantic,
                    "decision_manifest": manifest_by_run.get(str(row["run_id"] or ""), ""),
                    "semantic_manifest": semantic_manifest_by_run.get(str(row["run_id"] or ""), ""),
                }
            )
        return results
