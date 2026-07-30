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

MIGRATION_3 = """
CREATE TABLE IF NOT EXISTS smt_analysis_runs (
    id TEXT PRIMARY KEY,
    source_fingerprint TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    state TEXT NOT NULL,
    source_relative_path TEXT NOT NULL,
    context_json TEXT NOT NULL,
    active_revision INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_error TEXT NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_smt_analysis_cache_key
ON smt_analysis_runs(source_fingerprint, parser_version, rule_version);

CREATE TABLE IF NOT EXISTS smt_analysis_revisions (
    run_id TEXT NOT NULL REFERENCES smt_analysis_runs(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CHECK (revision > 0),
    state TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, revision)
);

CREATE TABLE IF NOT EXISTS smt_analysis_decisions (
    run_id TEXT NOT NULL REFERENCES smt_analysis_runs(id) ON DELETE CASCADE,
    placement_id TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, placement_id)
);

CREATE TABLE IF NOT EXISTS smt_analysis_page_assets (
    run_id TEXT NOT NULL REFERENCES smt_analysis_runs(id) ON DELETE CASCADE,
    page_id TEXT NOT NULL,
    cache_relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    media_type TEXT NOT NULL,
    pixel_width INTEGER NOT NULL CHECK (pixel_width > 0),
    pixel_height INTEGER NOT NULL CHECK (pixel_height > 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, page_id)
);

CREATE INDEX IF NOT EXISTS idx_smt_analysis_page_path
ON smt_analysis_page_assets(cache_relative_path);
"""

MIGRATIONS = (
    (1, MIGRATION_1),
    (2, MIGRATION_2),
    (3, MIGRATION_3),
)
