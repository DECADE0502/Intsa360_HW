from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from app.backend.parsers.xy import parse_xy_file


BASELINE = (
    Path(__file__).parent
    / "fixtures"
    / "smt"
    / "contracts"
    / "iac4_v05_local_baseline.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.mark.slow
def test_opt_in_iac4_v05_local_sample_matches_recorded_baseline() -> None:
    root_value = os.environ.get("SMT_REAL_SAMPLE_DIR", "").strip()
    if not root_value:
        pytest.skip("set SMT_REAL_SAMPLE_DIR to run the local real-sample baseline")

    root = Path(root_value)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    for source in baseline["sources"]:
        path = root / Path(source["relative_path"])
        assert path.is_file(), path
        assert path.stat().st_size == source["size"]
        assert _sha256(path) == source["sha256"]

    _, components = parse_xy_file(root / "XY.txt")
    assert len(components) == baseline["expected_counts"]["placements"]
    assert sum(component.side == "top" for component in components) == baseline["expected_counts"]["top"]
    assert sum(component.side == "bottom" for component in components) == baseline["expected_counts"]["bottom"]
