from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
CONVERTER = ROOT / "tools" / "bom" / "convert_cadence_bom.py"
TCL_TEMPLATE = ROOT / "cadence" / "iac_bom_tool.tcl"


class CadenceIntegrationTests(unittest.TestCase):
    def test_cadence_converter_preserves_all_extra_properties(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "parts.json"
            out = tmp_path / "bom.xlsx"
            src.write_text(
                json.dumps(
                    [
                        {
                            "Reference": "R1",
                            "Part Number": "R.001",
                            "Value": "10K",
                            "PCB Footprint": "R0402",
                            "Part Type": "Resistor",
                            "Manufacturer": "VendorA",
                            "Custom中文属性": "保留我",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            subprocess.run([sys.executable, str(CONVERTER), str(src), str(out)], check=True)

            wb = load_workbook(out, read_only=True, data_only=True)
            ws = wb.active
            headers = [ws.cell(1, col).value for col in range(1, ws.max_column + 1)]
            row = [ws.cell(2, col).value for col in range(1, ws.max_column + 1)]
            wb.close()

            self.assertIn("Manufacturer", headers)
            self.assertIn("Custom中文属性", headers)
            self.assertEqual(row[headers.index("Manufacturer")], "VendorA")
            self.assertEqual(row[headers.index("Custom中文属性")], "保留我")

    def test_cadence_converter_uses_union_of_group_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "parts.json"
            out = tmp_path / "bom.xlsx"
            src.write_text(
                json.dumps(
                    [
                        {"Reference": "R1", "Part Number": "R.001", "Part Type": "Resistor", "Description": "10K"},
                        {
                            "Reference": "C1",
                            "Part Number": "C.001",
                            "Part Type": "Capacitor",
                            "Description": "0.1uF",
                            "SecondOnly": "kept",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            subprocess.run([sys.executable, str(CONVERTER), str(src), str(out)], check=True)

            wb = load_workbook(out, read_only=True, data_only=True)
            ws = wb.active
            headers = [ws.cell(1, col).value for col in range(1, ws.max_column + 1)]
            second = [ws.cell(3, col).value for col in range(1, ws.max_column + 1)]
            wb.close()

            self.assertIn("SecondOnly", headers)
            self.assertEqual(second[headers.index("SecondOnly")], "kept")

    def test_cadence_converter_keeps_capture_bom_header_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "parts.json"
            out = tmp_path / "bom.xlsx"
            src.write_text(
                json.dumps(
                    [
                        {
                            "Reference": "C1",
                            "Part Number": "C.001",
                            "Value": "0.1uF",
                            "规格型号": "0402X104K160",
                            "器件描述（新整理）": "陶瓷电容,0.1uF",
                            "物料名称": "电容",
                            "等级": "优选",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            subprocess.run([sys.executable, str(CONVERTER), str(src), str(out)], check=True)

            wb = load_workbook(out, read_only=True, data_only=True)
            ws = wb.active
            headers = [ws.cell(1, col).value for col in range(1, ws.max_column + 1)]
            row = [ws.cell(2, col).value for col in range(1, ws.max_column + 1)]
            wb.close()

            self.assertEqual(
                headers[:9],
                ["Item", "Quantity", "Reference", "Part Number", "Value", "规格型号", "器件描述（新整理）", "物料名称", "等级"],
            )
            self.assertEqual(row[headers.index("规格型号")], "0402X104K160")
            self.assertEqual(row[headers.index("器件描述（新整理）")], "陶瓷电容,0.1uF")
            self.assertEqual(row[headers.index("物料名称")], "电容")
            self.assertEqual(row[headers.index("等级")], "优选")

    def test_tcl_template_serializes_all_dict_properties(self) -> None:
        text = TCL_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("foreach key [dict keys $row]", text)
        self.assertNotIn("foreach key {Reference {Part Number} Value {PCB Footprint} {Part Type}}", text)

    def test_tcl_template_gets_design_name_from_effective_props(self) -> None:
        text = TCL_TEMPLATE.read_text(encoding="utf-8")
        start = text.index("proc GetDsnName")
        end = text.index("proc PartsToJson")
        proc = text[start:end]

        self.assertIn("NewEffectivePropsIter", proc)
        self.assertIn('if {$propname eq "Name"}', proc)
        self.assertNotIn('if {$ret ne ""} { return $ret }', proc)
        self.assertIn("return [::IAC::CleanDesignName $ret]", proc)

    def test_tcl_template_sanitizes_full_dsn_path_before_inbox_filename(self) -> None:
        text = TCL_TEMPLATE.read_text(encoding="utf-8")
        clean_start = text.index("proc CleanDesignName")
        clean_end = text.index("proc GetDsnName")
        clean_proc = text[clean_start:clean_end]
        export_start = text.index("proc ExportAndProcess")
        export_end = text.index("# ----", export_start)
        export_proc = text[export_start:export_end]

        self.assertIn("file tail", clean_proc)
        self.assertIn("file rootname", clean_proc)
        self.assertIn('regsub -all {[\\\\/:*?"<>|]}', clean_proc)
        self.assertIn("set dsnRaw [::IAC::GetDsnName]", export_proc)
        self.assertIn("set dsn [::IAC::CleanDesignName $dsnRaw]", export_proc)
        self.assertIn('${dsn}.xlsx', export_proc)

    def test_tcl_template_uses_capture_sample_property_accessors(self) -> None:
        text = TCL_TEMPLATE.read_text(encoding="utf-8")
        start = text.index("proc GetReference")
        end = text.index("proc CleanDesignName")
        proc = text[start:end]

        self.assertIn("GetReference", proc)
        self.assertIn("GetEffectivePropStringValue", proc)
        self.assertIn("GetVariantProp", proc)
        self.assertIn("IsPrimitive", text)

    def test_tcl_template_uses_hidden_launcher_and_ascii_default_menu(self) -> None:
        text = TCL_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("launch_tool_suite_hidden.vbs", text)
        self.assertIn("wscript.exe", text)
        self.assertIn('"insta360_HW"', text)
        self.assertIn('AddAccessoryMenu "insta360_HW" "Open Platform"', text)
        self.assertIn('AddAccessoryMenu "insta360_HW" "Export and Process BOM"', text)
        self.assertIn('"action" "Open Platform"', text)
        self.assertIn('"action" "Export and Process BOM"', text)
        self.assertNotIn('AddAccessoryMenu "insta360_HW" "进入平台"', text)
        self.assertNotIn('AddAccessoryMenu "insta360_HW" "导出并处理BOM"', text)

    def test_tcl_template_exposes_capture_command_window_diagnostics(self) -> None:
        text = TCL_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("proc Diagnose", text)
        self.assertIn("proc iacdiag", text)
        self.assertIn("IAC: diagnostics", text)
        self.assertIn("info commands RegisterAction", text)
        self.assertIn("launch_tool_suite_hidden.vbs", text)
        self.assertIn("convert_cadence_bom.py", text)
        self.assertIn("IAC_ROOT", text)

    def test_tcl_template_writes_capture_loader_probe_log(self) -> None:
        text = TCL_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("proc Probe", text)
        self.assertIn("cadence_loader_probe.log", text)
        self.assertIn("IAC: loader probe", text)
        self.assertIn("RegisterAction=", text)
        self.assertIn("InsertXMLMenu=", text)
        self.assertIn("AddAccessoryMenu=", text)
        self.assertIn("::IAC::Probe", text)

    def test_tcl_template_does_not_load_custom_enhanced_tools_until_platform_registry_exists(self) -> None:
        text = TCL_TEMPLATE.read_text(encoding="utf-8")

        self.assertNotIn("LoadEnhancedTools", text)
        self.assertNotIn("orcad_enhanced_tools.tcl", text)
        self.assertNotIn("rename RegisterAction", text)
        self.assertNotIn("proc ::RegisterAction", text)
        self.assertNotIn('AddAccessoryMenu "insta360_HW" "选中器件切换NC"', text)
        self.assertNotIn('AddAccessoryMenu "insta360_HW" "其他脚本"', text)


if __name__ == "__main__":
    unittest.main()

