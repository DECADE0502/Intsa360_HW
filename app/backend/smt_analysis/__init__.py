"""SMT assembly analysis domain services.

The package is intentionally independent from the legacy ``smt_layout`` tool.
Pure parsing, registration, and assembly decisions live here so they can be
tested without FastAPI, SQLite, or frontend state.
"""

from .ingest import scan_source_directory, source_fingerprint

__all__ = ["scan_source_directory", "source_fingerprint"]
