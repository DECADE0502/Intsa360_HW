from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from app.backend.tools.analysis_tools import run_bom_risk_check


def _write_bom(path: Path, rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Reference", "Part Number", "Description", "Quantity", "Name", "Model", "Grade"])
    for row in rows:
        ws.append(row)
    wb.save(path)


class BomRiskCheckTests(unittest.TestCase):
    def test_confirmed_sh_bracket_satisfies_shield_bracket_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bom = root / "processed.xlsx"
            _write_bom(
                bom,
                [
                    ["SH1", "SH-PN", "屏蔽支架", 1, "屏蔽支架", "shield bracket", "正常"],
                    ["R1", "R-PN", "电阻", 1, "电阻", "10K", "正常"],
                ],
            )

            result = run_bom_risk_check(root, {"bom": str(bom)})

            finding = next(item for item in result["risk_report"]["findings"] if item["name"] == "屏蔽支架")
            self.assertEqual(finding["status"], "ok")
            self.assertIn("SH-PN", finding["message"])

    def test_emmc_and_ddr_warn_about_hardware_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bom = root / "processed.xlsx"
            _write_bom(
                bom,
                [
                    ["U1", "EMMC-PN", "eMMC 128GB", 1, "eMMC", "KLMAG1JETD", "正常"],
                    ["U2", "DDR-PN", "LPDDR4X 8Gb", 1, "DDR", "MT53", "正常"],
                ],
            )

            result = run_bom_risk_check(root, {"bom": str(bom)})

            finding = next(item for item in result["risk_report"]["findings"] if item["name"] == "硬件版本敏感物料")
            self.assertEqual(finding["status"], "info")
            self.assertIn("EMMC-PN", finding["message"])
            self.assertIn("DDR-PN", finding["message"])
            self.assertIn("硬件版本号", finding["message"])


if __name__ == "__main__":
    unittest.main()
