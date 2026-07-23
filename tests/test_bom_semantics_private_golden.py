from __future__ import annotations

import os
from pathlib import Path

import pytest


PRIVATE_ROOT = os.environ.get("HWAGENT_BOM_COMPARE_SAMPLES_ROOT", "").strip()


@pytest.mark.skipif(not PRIVATE_ROOT, reason="private BOM golden directory is not configured")
def test_private_bom_golden_directory_is_readable() -> None:
    root = Path(PRIVATE_ROOT)
    assert root.is_dir()
    assert len(list(root.glob("*.xlsx"))) >= 7
