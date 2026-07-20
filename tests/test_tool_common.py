from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import Workbook

from app.backend.tools import common


class ToolCommonTests(unittest.TestCase):
    def test_workbook_writers_always_close_created_workbooks(self) -> None:
        created: list[Workbook] = []
        original_workbook = Workbook

        def tracked_workbook() -> Workbook:
            workbook = original_workbook()
            workbook.close = mock.Mock(wraps=workbook.close)
            created.append(workbook)
            return workbook

        with tempfile.TemporaryDirectory() as tmp, mock.patch("openpyxl.Workbook", side_effect=tracked_workbook):
            root = Path(tmp)
            common._write_table(root / "table.xlsx", "Table", ["A"], [[1]])
            common._write_sheets(root / "sheets.xlsx", [("Sheet", ["A"], [[1]])])

        self.assertEqual(len(created), 2)
        for workbook in created:
            self.assertEqual(workbook.close.call_count, 1)


if __name__ == "__main__":
    unittest.main()
