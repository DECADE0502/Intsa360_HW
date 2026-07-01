"""Pytest configuration + shared setup for all tests.

- Adds project root to sys.path so ``from app.backend...`` imports work
  without each test file needing its own ``sys.path.insert`` block.
- pytest auto-loads this module before collecting tests, so the path
  manipulation happens exactly once per session regardless of how
  many test files import backend modules.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
