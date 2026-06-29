from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from app.backend.capture_fields import CAPTURE_VISIBLE_PROPERTIES, FIELD_DEFAULTS, PLM_TEMPLATE_HEADERS
from app.backend.tools import bom_process


class ChineseBomTextTests(unittest.TestCase):
    def test_capture_and_plm_field_names_are_readable_chinese(self) -> None:
        self.assertIn("PCB封装", CAPTURE_VISIBLE_PROPERTIES)
        self.assertIn("等级", CAPTURE_VISIBLE_PROPERTIES)
        self.assertIn("规格型号", CAPTURE_VISIBLE_PROPERTIES)
        self.assertIn("器件描述（新整理）", CAPTURE_VISIBLE_PROPERTIES)
        self.assertIn("物料名称", CAPTURE_VISIBLE_PROPERTIES)

        self.assertEqual(
            PLM_TEMPLATE_HEADERS,
            [
                "父项编码",
                "描述",
                "子项编码",
                "名称",
                "型号",
                "描述",
                "单位",
                "数量",
                "位号",
                "备注",
                "物料优选等级",
                "物料优选等级备注",
                "替代组编码",
                "替代策略",
                "替代方式",
                "替代优先级",
                "发料方式",
                "是否参与MRP运算",
                "是否跳层",
            ],
        )
        self.assertEqual(FIELD_DEFAULTS["issue_method"], "直接发料")
        self.assertEqual(FIELD_DEFAULTS["mrp"], "是")
        self.assertEqual(FIELD_DEFAULTS["jump_level"], "否")

    def test_bom_process_outputs_readable_nc_summary_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Item", "Quantity", "Reference", "Part Number", "Value", "规格型号", "器件描述（新整理）", "物料名称", "等级"])
            ws.append([1, 1, "R1", "PN-001", "10K", "10K", "10K resistor", "电阻", "优选"])
            ws.append([2, 1, "TP1", "PN-TP", "TP", "TP", "测试点", "测试点", "正常"])
            wb.save(source)

            result = bom_process.process(source, ["plm"], "PARENT", "Parent desc", "TEST", [], tmp_path, "STAMP")

            self.assertEqual(Path(result["nc_summary"]).name, "TEST_STAMP_NC未贴汇总.xlsx")
            self.assertEqual(Path(result["outputs"][0]).name, "TEST_STAMP_PLM_BOM.xlsx")


if __name__ == "__main__":
    unittest.main()
