from __future__ import annotations


MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    legacy_id TEXT UNIQUE,
    tool_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    params_json TEXT NOT NULL,
    decisions_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    input_names_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    format TEXT NOT NULL,
    display_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL CHECK (size >= 0),
    created_at TEXT NOT NULL,
    source_run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
    pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_inputs (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    PRIMARY KEY (run_id, ordinal),
    UNIQUE (run_id, asset_id)
);

CREATE TABLE IF NOT EXISTS run_outputs (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    PRIMARY KEY (run_id, ordinal),
    UNIQUE (run_id, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_assets_relative_path ON assets(relative_path);
CREATE INDEX IF NOT EXISTS idx_assets_source_run ON assets(source_run_id);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);
"""

MIGRATION_2 = """
CREATE TABLE IF NOT EXISTS repository_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

MIGRATIONS = (
    (1, MIGRATION_1),
    (2, MIGRATION_2),
)
