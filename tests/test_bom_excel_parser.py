from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from app.backend.parsers.bom_excel import read_bom_rows


class BomExcelParserTests(unittest.TestCase):
    def test_read_bom_rows_prefers_child_columns_after_part_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bom.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["父项编码", "描述", "子项编码", "名称", "型号", "描述", "单位", "数量", "位号", "物料优选等级"])
            ws.append(["PARENT", "整机", "R.001", "电阻", "10K", "贴片电阻", "ea", 2, "R1,R2", "优选"])
            wb.save(path)

            rows = read_bom_rows(path)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["part_number"], "R.001")
            self.assertEqual(rows[0]["description"], "贴片电阻")
            self.assertEqual(rows[0]["quantity"], 2)
            self.assertEqual(rows[0]["refs"], ["R1", "R2"])
            self.assertEqual(rows[0]["name"], "电阻")
            self.assertEqual(rows[0]["model"], "10K")
            self.assertEqual(rows[0]["grade"], "优选")

    def test_read_bom_rows_can_keep_no_ref_board_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bom.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Reference", "Part Number", "Description", "Quantity"])
            ws.append(["", "PCB.001", "PCB board", 1])
            wb.save(path)

            self.assertEqual(read_bom_rows(path), [])
            self.assertEqual(read_bom_rows(path, require_refs=False)[0]["part_number"], "PCB.001")

    def test_read_bom_rows_closes_workbook_when_header_detection_fails(self) -> None:
        class TrackingWorkbook:
            def __init__(self, worksheet) -> None:
                self.active = worksheet
                self.closed = False

            def close(self) -> None:
                self.closed = True

        source = Workbook()
        source.active.append(["unexpected header"])
        workbook = TrackingWorkbook(source.active)

        with patch("openpyxl.load_workbook", return_value=workbook):
            with self.assertRaises(ValueError):
                read_bom_rows(Path("missing.xlsx"))

        self.assertTrue(workbook.closed)


if __name__ == "__main__":
    unittest.main()
