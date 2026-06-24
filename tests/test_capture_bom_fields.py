from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from app.backend.tools import bom_process


ROOT = Path(__file__).resolve().parents[1]
CONVERTER = ROOT / "tools" / "bom" / "convert_cadence_bom.py"
TCL_TEMPLATE = ROOT / "cadence" / "iac_bom_tool.tcl"
FRONTEND_WIZARD = ROOT / "frontend" / "src" / "tools" / "BomProcessWizard.tsx"

VISIBLE_CAPTURE_FIELDS = [
    "Color", "Designator", "Graphic", "ID", "Implementation", "Implementation Path", "Implementation Type",
    "Location X-Coordinate", "Location Y-Coordinate", "Name", "Part Number", "Part Reference", "Part Type",
    "PCB Footprint", "PCB封装", "Power Pins Visible", "Primitive", "Reference", "Source Library",
    "Source Package", "Source Part", "SPLIT_INST", "SWAP_INFO", "Value", "等级", "规格型号",
    "器件描述（新整理）", "物料名称",
]

PLM_HEADERS = [
    "父项编码", "描述", "子项编码", "名称", "型号", "描述", "单位", "数量", "位号", "备注",
    "物料优选等级", "物料优选等级备注", "替代组编码", "替代策略", "替代方式", "替代优先级",
    "发料方式", "是否参与MRP运算", "是否跳层",
]


class CaptureBomFieldTests(unittest.TestCase):
    def test_capture_fields_constant_contains_all_visible_properties(self) -> None:
        from app.backend.capture_fields import CAPTURE_VISIBLE_PROPERTIES

        for field in VISIBLE_CAPTURE_FIELDS:
            self.assertIn(field, CAPTURE_VISIBLE_PROPERTIES)

    def test_tcl_prop_names_includes_visible_capture_properties(self) -> None:
        text = TCL_TEMPLATE.read_text(encoding="utf-8")
        start = text.index("variable PROP_NAMES")
        end = text.index("proc shouldProcess")
        prop_block = text[start:end]
        for field in VISIBLE_CAPTURE_FIELDS:
            expected = field if " " not in field and field.isascii() else f"{{{field}}}"
            self.assertIn(expected, prop_block)
        self.assertIn("NewEffectivePropsIter", text)

    def test_frontend_capture_config_contains_practical_fields(self) -> None:
        text = FRONTEND_WIZARD.read_text(encoding="utf-8")
        expected = (
            "{Item}\\\\t{Quantity}\\\\t{Reference}\\\\t{Part Number}\\\\t{Value}\\\\t{规格型号}"
            "\\\\t{器件描述（新整理）}\\\\t{物料名称}\\\\t{等级}\\\\t{PCB Footprint}\\\\t{PCB封装}"
            "\\\\t{Part Type}\\\\t{Part Reference}\\\\t{Source Package}\\\\t{Source Part}"
        )
        self.assertIn(expected, text)

    def test_converter_preserves_visible_capture_properties_in_raw_xlsx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "parts.json"
            out = tmp_path / "bom.xlsx"
            part = {field: f"{field}-value" for field in VISIBLE_CAPTURE_FIELDS}
            part.update({
                "Reference": "U1",
                "Part Number": "PN-001",
                "Value": "IC",
                "规格型号": "MODEL-A",
                "器件描述（新整理）": "main chip",
                "物料名称": "SoC",
                "PCB封装": "BGA",
                "Source Package": "PKG-A",
                "SPLIT_INST": "1",
            })
            src.write_text(json.dumps([part], ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(CONVERTER), str(src), str(out)], check=True)

            wb = load_workbook(out, read_only=True, data_only=True)
            ws = wb.active
            headers = [ws.cell(1, col).value for col in range(1, ws.max_column + 1)]
            row = [ws.cell(2, col).value for col in range(1, ws.max_column + 1)]
            wb.close()

            for field in VISIBLE_CAPTURE_FIELDS:
                if field != "Reference":
                    self.assertIn(field, headers)
            self.assertEqual(row[headers.index("PCB封装")], "BGA")
            self.assertEqual(row[headers.index("Source Package")], "PKG-A")
            self.assertEqual(row[headers.index("SPLIT_INST")], "1")

    def test_bom_process_outputs_19_plm_columns_with_fallbacks_and_preserved_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append([
                "Item", "Quantity", "Reference", "Part Number", "Value", "规格型号", "器件描述（新整理）",
                "物料名称", "等级", "单位", "备注", "物料优选等级备注", "替代组编码", "替代策略",
                "替代方式", "替代优先级", "发料方式", "是否参与MRP运算", "是否跳层",
                "PCB Footprint", "PCB封装", "Part Type", "Source Package", "SPLIT_INST",
            ])
            ws.append([
                1, 2, "R1 R2", "PN-001", "10K", "", "", "", "优选", "pcs", "keep remark",
                "grade note", "ALT-1", "可替代", "手工替代", "2", "寄售发料", "否", "是",
                "R0402", "0402", "Resistor", "CAPTURE-PKG", "split-a",
            ])
            ws.append([2, 1, "C1", "PN-002", "1uF", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "0603", "Capacitor"])
            wb.save(source)

            result = bom_process.process(source, ["plm"], "PARENT", "Parent desc", "TEST", [], tmp_path, "STAMP")
            wb = load_workbook(result["outputs"][0], read_only=True, data_only=True)
            ws = wb.active
            headers = [ws.cell(2, col).value for col in range(1, ws.max_column + 1)]
            first = [ws.cell(3, col).value for col in range(1, ws.max_column + 1)]
            second = [ws.cell(4, col).value for col in range(1, ws.max_column + 1)]
            wb.close()

            self.assertEqual(headers, PLM_HEADERS)
            self.assertEqual(first, ["PARENT", "Parent desc", "PN-001", "Resistor", "10K", "10K", "pcs", 2, "R1,R2", "keep remark", "优选", "grade note", "ALT-1", "可替代", "手工替代", "2", "寄售发料", "否", "是"])
            self.assertEqual(second[3:9], ["Capacitor", "1uF", "1uF", "ea", 1, "C1"])
            self.assertEqual(second[16:19], ["直接发料", "是", "否"])

    def test_trace_fields_do_not_create_part_conflicts(self) -> None:
        rows = [
            {"reference": "R1", "part_number": "PN-001", "name": "Resistor", "model": "10K", "desc": "10K", "grade": "优选", "source_package": "PKG-A"},
            {"reference": "R2", "part_number": "PN-001", "name": "Resistor", "model": "10K", "desc": "10K", "grade": "优选", "source_package": "PKG-B"},
        ]
        self.assertEqual(bom_process.detect_part_conflicts(rows), [])

    def test_bom_process_sanitizes_output_filename_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Item", "Quantity", "Reference", "Part Number", "Value"])
            ws.append([1, 1, "R1", "PN-001", "10K"])
            wb.save(source)

            result = bom_process.process(source, ["plm"], "PARENT", "Parent desc", "BAD?NAME", [], tmp_path, "STAMP?")

            self.assertTrue(Path(result["outputs"][0]).exists())
            self.assertNotIn("?", Path(result["outputs"][0]).name)


if __name__ == "__main__":
    unittest.main()
