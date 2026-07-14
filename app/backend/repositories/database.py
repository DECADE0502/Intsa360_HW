from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.backend.paths import AppPaths
from app.backend.repositories.migrations import MIGRATIONS


_SCHEMA_LOCK = threading.Lock()


class PlatformDatabase:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.path = AppPaths(self.root).platform_database_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _ensure_schema(self) -> None:
        with _SCHEMA_LOCK:
            connection = self._open()
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
                for version, script in MIGRATIONS:
                    if version in applied:
                        continue
                    connection.executescript(script)
                    connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
                connection.commit()
            finally:
                connection.close()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = self._open()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()
