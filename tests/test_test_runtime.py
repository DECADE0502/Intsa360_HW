from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import _retry_directory_not_empty


def test_windows_temp_cleanup_retries_directory_not_empty_once(tmp_path: Path) -> None:
    target = tmp_path / "fixture"
    target.mkdir()
    calls = 0

    def remove(path: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            error = OSError("directory not empty")
            error.winerror = 145
            raise error
        shutil.rmtree(path)

    _retry_directory_not_empty(remove, str(target))

    assert calls == 2
    assert not target.exists()


def test_windows_temp_cleanup_does_not_hide_persistent_failures(tmp_path: Path) -> None:
    target = tmp_path / "fixture"
    target.mkdir()

    def remove(_path: str) -> None:
        error = OSError("directory not empty")
        error.winerror = 145
        raise error

    with pytest.raises(OSError, match="directory not empty"):
        _retry_directory_not_empty(remove, str(target), attempts=2)
