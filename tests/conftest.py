"""Pytest configuration + shared setup for all tests.

- Adds project root to sys.path so ``from app.backend...`` imports work
  without each test file needing its own ``sys.path.insert`` block.
- pytest auto-loads this module before collecting tests, so the path
  manipulation happens exactly once per session regardless of how
  many test files import backend modules.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _retry_directory_not_empty(remove, path: str, attempts: int = 8) -> None:
    for attempt in range(attempts):
        try:
            remove(path)
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) != 145 or attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


if os.name == "nt":
    _original_temporary_directory_rmtree = tempfile.TemporaryDirectory._rmtree.__func__

    @classmethod
    def _retrying_temporary_directory_rmtree(cls, name: str) -> None:
        _retry_directory_not_empty(lambda path: _original_temporary_directory_rmtree(cls, path), name)

    tempfile.TemporaryDirectory._rmtree = _retrying_temporary_directory_rmtree
