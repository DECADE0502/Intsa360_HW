from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from openpyxl import load_workbook


@contextmanager
def open_bom_workbook(path: Path, **kwargs: object) -> Iterator[object]:
    workbook = load_workbook(path, **kwargs)
    try:
        yield workbook
    finally:
        workbook.close()
