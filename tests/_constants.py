"""Shared constants for the test suite.

Sole source of truth for names / paths that would otherwise drift between
code, tests, and docs. Tests should import from here instead of
hard-coding the strings.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Brand names — MUST NOT drift across code, tests, docs.
BRAND_NAME_CANONICAL = "Insta360 硬件提效平台"
BRAND_NAME_LEGACY = "硬件效率工具集"  # deprecated; presence in current shipping text is a bug

# Repository coordinates for update/release tooling.
# Note: repo name is spelled "Intsa360_HW" upstream — the typo is preserved intentionally.
REPO_OWNER = "DECADE0502"
REPO_NAME = "Intsa360_HW"
