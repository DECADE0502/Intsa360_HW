from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from app.backend.tools import analysis_tools


ROOT = Path(__file__).resolve().parents[1]


def write_bom(path: Path, rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Reference", "Part Number", "Value", "规格型号", "器件描述（新整理）", "物料名称", "等级", "Quantity"])
    for row in rows:
        ws.append(row)
    wb.save(path)


class BomCompareWorkbenchTests(unittest.TestCase):
    def test_bom_compare_classifies_review_cases_for_workbench(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "left.xlsx"
            right = root / "right.xlsx"
            write_bom(
                left,
                [
                    ["R1", "R.001", "10K", "10K", "电阻 10K", "电阻", "优选", 1],
                    ["R2", "R.002", "1K", "1K", "电阻 1K", "电阻", "优选", 1],
                    ["C1", "C.001", "1uF", "1uF", "电容 1uF", "电容", "优选", 1],
                    ["U1", "IC.001", "SOC", "A1", "主控 A1", "IC", "优选", 1],
                ],
            )
            write_bom(
                right,
                [
                    ["R1", "R.001", "10K", "10K", "电阻 10K", "电阻", "优选", 1],
                    ["R2", "R.003", "2K", "2K", "电阻 2K", "电阻", "优选", 1],
                    ["C2", "C.002", "2.2uF", "2.2uF", "电容 2.2uF", "电容", "优选", 1],
                    ["U1", "IC.001", "SOC", "A2", "主控 A2", "IC", "优选", 1],
                ],
            )

            result = analysis_tools.run_bom_compare(ROOT, {"bom1": str(left), "bom2": str(right), "output_dir": str(root)})

            self.assertEqual(result["status"], "ok")
            items = {item["key"]: item for item in result["compare"]["items"]}
            self.assertEqual(items["R2"]["status"], "换料")
            self.assertEqual(items["C1"]["status"], "删除/未贴")
            self.assertEqual(items["C2"]["status"], "新增贴装")
            self.assertEqual(items["U1"]["status"], "参数差异")
            self.assertEqual(items["R1"]["status"], "一致")
            self.assertEqual(result["summary"]["status_counts"]["swap"], 1)
            self.assertEqual(result["summary"]["status_counts"]["removed"], 1)
            self.assertEqual(result["summary"]["status_counts"]["added"], 1)
            self.assertEqual(result["summary"]["status_counts"]["param"], 1)
            self.assertEqual(result["summary"]["status_counts"]["same"], 1)
            self.assertIn("review_guide", result)
            self.assertIn("换料", result["review_guide"])
            self.assertIn("focus_items", result)
            self.assertEqual([item["key"] for item in result["focus_items"]], ["R2", "C1", "C2", "U1"])


if __name__ == "__main__":
    unittest.main()
