from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from app.backend.tools import bom_process
from app.backend.tools.analysis_tools import run_bom_process
from fixture_builders import build_capture_bom


FIXTURES = Path(__file__).parent / "fixtures" / "bom"


def record_signature(record: dict[str, object]) -> dict[str, str]:
    return {
        "model": str(record.get("model") or ""),
        "description": str(record.get("desc") or ""),
        "name": str(record.get("name") or ""),
        "grade": str(record.get("grade") or ""),
        "unit": str(record.get("unit") or ""),
    }


def make_source(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Item", "Quantity", "Reference", "Part Number", "Value", "规格型号", "器件描述（新整理）", "物料名称", "等级"])
    ws.append([1, 1, "R1", "P1", "10K", "M1", "D1", "电阻", "正常"])
    ws.append([2, 1, "R2", "P1", "10K", "M2", "D2", "电阻", "优选"])
    ws.append([3, 1, "C1", "P2", "1uF", "CM1", "CD1", "电容", "正常"])
    wb.save(path)


class BomProcessConflictTests(unittest.TestCase):
    def test_load_source_prefers_new_description_over_content_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Item", "Quantity", "Reference", "Part Number", "内容", "器件描述（新整理）"])
            ws.append([1, 1, "R1", "P1", "", "new desc"])
            wb.save(source)

            rows, _ = bom_process.load_source(source)

            self.assertEqual(rows[0]["desc"], "new desc")

    def test_run_bom_process_requires_confirmation_for_same_code_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.xlsx"
            make_source(source)

            result = run_bom_process(
                root,
                {
                    "source_bom": str(source),
                    "formats": ["plm"],
                    "parent_code": "203010100819",
                    "name": "TEST",
                },
            )

            self.assertEqual(result["status"], "needs_confirmation")
            self.assertEqual(result["reason"], "part_property_conflicts")
            self.assertEqual(result["conflict_count"], 1)
            self.assertEqual(result["summary"]["conflicts"], 1)
            self.assertEqual(result["conflicts"][0]["code"], "P1")
            self.assertEqual(result["conflicts"][0]["total_refs"], 2)

    def test_recommended_merge_leaves_low_confidence_conflicts_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            make_source(source)

            result = bom_process.process(
                source,
                ["plm"],
                "203010100819",
                "",
                "TEST",
                [],
                tmp_path,
                "STAMP",
                None,
                merge_conflicts=True,
            )

            records = result["records"]
            p1_records = [record for record in records if record["code"] == "P1"]
            self.assertEqual(len(p1_records), 2)
            self.assertEqual([record["refs"] for record in p1_records], [["R1"], ["R2"]])
            self.assertEqual(
                {(record["model"], record["desc"], record["grade"]) for record in p1_records},
                {("M1", "D1", "正常"), ("M2", "D2", "优选")},
            )
            self.assertEqual(result["summary"]["unresolved_conflicts"], 1)

            wb = load_workbook(result["outputs"][0], read_only=True, data_only=True)
            ws = wb.active
            rows = [[ws.cell(r, c).value for c in range(1, 12)] for r in range(3, ws.max_row + 1)]
            wb.close()
            p1_rows = [row for row in rows if row[2] == "P1"]
            self.assertEqual(len(p1_rows), 2)

    def test_golden_conflict_recommendations_select_only_existing_signatures(self) -> None:
        expectations = json.loads((FIXTURES / "expected_recommendations.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            source = build_capture_bom(Path(tmp) / "conflicts.xlsx", "known_conflicts")
            rows, _ = bom_process.load_source(source)
            conflicts = {item["code"]: item for item in bom_process.detect_part_conflicts(rows)}

        self.assertEqual(set(conflicts), set(expectations["conflict_codes"]))
        for code, expected in expectations["recommendations"].items():
            conflict = conflicts[code]
            actual_signatures = {
                json.dumps(
                    {
                        "model": variant["model"],
                        "description": variant["desc"],
                        "name": variant["name"],
                        "grade": variant["grade"],
                        "unit": variant["unit"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                for variant in conflict["variants"]
            }
            expected_signatures = {
                json.dumps(signature, ensure_ascii=False, sort_keys=True)
                for signature in expected["allowed_signatures"]
            }
            self.assertEqual(actual_signatures, expected_signatures, code)
            self.assertEqual(conflict["confidence"], expected["expected_confidence"], code)
            self.assertEqual(conflict["reason"], expected["expected_reason"], code)
            self.assertEqual(conflict["high_confidence"], expected["high_confidence"], code)
            self.assertEqual(conflict["manual_choice_required"], expected["manual_choice_required"], code)
            if expected["high_confidence"]:
                selected = conflict["recommended_signature"]
                self.assertEqual(
                    {
                        "model": selected["model"],
                        "description": selected["desc"],
                        "name": selected["name"],
                        "grade": selected["grade"],
                        "unit": selected["unit"],
                    },
                    expected["selected_signature"],
                    code,
                )
                self.assertIn(conflict["recommended_index"], range(len(conflict["variants"])))
            else:
                self.assertNotIn("recommended_signature", conflict)

    def test_bulk_recommendation_merges_only_high_confidence_golden_groups(self) -> None:
        expectations = json.loads((FIXTURES / "expected_recommendations.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            source = build_capture_bom(Path(tmp) / "conflicts.xlsx", "known_conflicts")
            records = bom_process.build_records(source, merge_conflicts=True)

        by_code: dict[str, list[dict[str, object]]] = {}
        for record in records:
            by_code.setdefault(str(record["code"]), []).append(record)
        for code, expected in expectations["recommendations"].items():
            allowed = expected["allowed_signatures"]
            actual = by_code[code]
            if expected["high_confidence"]:
                self.assertEqual(len(actual), 1, code)
                self.assertEqual(record_signature(actual[0]), expected["selected_signature"], code)
            else:
                self.assertEqual(len(actual), len(allowed), code)
                self.assertEqual(
                    {json.dumps(record_signature(record), ensure_ascii=False, sort_keys=True) for record in actual},
                    {json.dumps(signature, ensure_ascii=False, sort_keys=True) for signature in allowed},
                    code,
                )

    def test_complementary_blanks_never_synthesize_a_new_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "complementary.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Reference", "Part Number", "规格型号", "器件描述（新整理）", "物料名称", "等级", "单位"])
            ws.append(["R1", "P1", "M1", "", "RESISTOR", "优选", "ea"])
            ws.append(["R2", "P1", "", "D1", "RESISTOR", "优选", "ea"])
            wb.save(source)

            rows, _ = bom_process.load_source(source)
            conflict = bom_process.detect_part_conflicts(rows)[0]
            records = bom_process.build_records(source, merge_conflicts=True)

        self.assertEqual(conflict["confidence"], "low")
        self.assertEqual(conflict["reason"], "complementary_incomplete_candidates")
        self.assertEqual(len(records), 2)
        self.assertNotIn(
            {"model": "M1", "description": "D1", "name": "RESISTOR", "grade": "优选", "unit": "ea"},
            [record_signature(record) for record in records],
        )

    def test_blank_completion_is_high_confidence_and_uses_complete_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "blank-completion.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Reference", "Part Number", "规格型号", "器件描述（新整理）", "物料名称", "等级", "单位"])
            ws.append(["R1", "P1", "M1", "D1", "", "优选", "ea"])
            ws.append(["R2", "P1", "M1", "D1", "RESISTOR", "优选", "ea"])
            wb.save(source)

            rows, _ = bom_process.load_source(source)
            conflict = bom_process.detect_part_conflicts(rows)[0]
            records = bom_process.build_records(source, merge_conflicts=True)

        self.assertEqual(conflict["confidence"], "high")
        self.assertEqual(conflict["reason"], "blank_completion")
        self.assertEqual(len(records), 1)
        self.assertEqual(
            record_signature(records[0]),
            {"model": "M1", "description": "D1", "name": "RESISTOR", "grade": "优选", "unit": "ea"},
        )

    def test_recommended_api_merge_reprompts_for_low_confidence_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.xlsx"
            make_source(source)

            result = run_bom_process(
                root,
                {
                    "source_bom": str(source),
                    "formats": ["plm"],
                    "parent_code": "203010100819",
                    "name": "TEST",
                    "merge_conflicts": True,
                    "conflict_choices": {},
                },
            )

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(result["reason"], "part_property_conflicts")
        self.assertEqual(result["conflict_count"], 1)
        self.assertEqual(result["conflicts"][0]["confidence"], "low")

    def test_recommended_api_merge_finishes_a_grade_only_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "grade-only.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Reference", "Part Number", "规格型号", "器件描述（新整理）", "物料名称", "等级", "单位"])
            ws.append(["R1", "P1", "M1", "D1", "RESISTOR", "正常", "ea"])
            ws.append(["R2", "P1", "M1", "D1", "RESISTOR", "优选", "ea"])
            wb.save(source)

            result = run_bom_process(
                root,
                {
                    "source_bom": str(source),
                    "formats": ["plm"],
                    "parent_code": "203010100819",
                    "name": "TEST",
                    "merge_conflicts": True,
                    "conflict_choices": {},
                },
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["summary"]["records"], 1)
        self.assertEqual(result["preview"]["rows"][0][5], "优选")

    def test_manual_choice_preserves_the_selected_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "unit-conflict.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Reference", "Part Number", "规格型号", "器件描述（新整理）", "物料名称", "等级", "单位"])
            ws.append(["R1", "P1", "M1", "D1", "RESISTOR", "优选", "ea"])
            ws.append(["R2", "P1", "M1", "D1", "RESISTOR", "优选", "pcs"])
            wb.save(source)

            records = bom_process.build_records(
                source,
                merge_conflicts=True,
                conflict_choices={"P1": 1},
            )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["unit"], "pcs")

    def test_process_uses_user_selected_conflict_variant_when_merging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            make_source(source)

            result = bom_process.process(
                source,
                ["plm"],
                "203010100819",
                "",
                "TEST",
                [],
                tmp_path,
                "STAMP",
                None,
                merge_conflicts=True,
                conflict_choices={"P1": 1},
            )

            p1 = next(record for record in result["records"] if record["code"] == "P1")
            self.assertEqual(p1["name"], "电阻")
            self.assertEqual(p1["model"], "M2")
            self.assertEqual(p1["desc"], "D2")
            self.assertEqual(p1["grade"], "优选")

    def test_process_keeps_conflicts_split_when_not_confirmed_to_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            make_source(source)

            result = bom_process.process(
                source,
                ["plm"],
                "203010100819",
                "",
                "TEST",
                [],
                tmp_path,
                "STAMP",
                None,
                merge_conflicts=False,
            )

            p1_records = [record for record in result["records"] if record["code"] == "P1"]
            self.assertEqual(len(p1_records), 2)
            self.assertEqual([record["qty"] for record in p1_records], [1, 1])

    def test_run_bom_process_requires_confirmation_for_sh_shield_brackets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Item", "Quantity", "Reference", "Part Number", "Value", "规格型号", "器件描述（新整理）", "物料名称", "等级"])
            ws.append([1, 1, "SH1", "SH-PN", "SHIELD", "shield bracket", "屏蔽支架", "屏蔽支架", "正常"])
            wb.save(source)

            result = run_bom_process(
                root,
                {
                    "source_bom": str(source),
                    "formats": ["plm"],
                    "parent_code": "203010100819",
                    "name": "TEST",
                },
            )

            self.assertEqual(result["status"], "needs_confirmation")
            self.assertEqual(result["reason"], "shield_bracket_candidates")
            self.assertEqual(result["shield_count"], 1)
            self.assertEqual(result["shield_candidates"][0]["refs"], ["SH1"])
            self.assertEqual(result["shield_candidates"][0]["code"], "SH-PN")

    def test_confirmed_sh_shield_brackets_enter_final_bom_not_nc_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Item", "Quantity", "Reference", "Part Number", "Value", "规格型号", "器件描述（新整理）", "物料名称", "等级"])
            ws.append([1, 1, "SH1", "SH-PN", "SHIELD", "shield bracket", "屏蔽支架", "屏蔽支架", "正常"])
            wb.save(source)

            result = bom_process.process(
                source,
                ["plm"],
                "203010100819",
                "",
                "TEST",
                [],
                tmp_path,
                "STAMP",
                None,
                confirm_shields=True,
            )

            shield = next(record for record in result["records"] if record["code"] == "SH-PN")
            self.assertEqual(shield["refs"], ["SH1"])
            self.assertEqual(shield["qty"], 1)
            self.assertEqual(shield["name"], "屏蔽支架")
            self.assertEqual(result["summary"]["shield_candidates"], 1)
            self.assertEqual(result["summary"]["excluded"], 0)

    def test_run_bom_process_requires_confirmation_for_sh_even_when_value_is_nc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Item", "Quantity", "Reference", "Part Number", "Value", "Model", "Description", "Name"])
            ws.append([1, 1, "SH1", "SH-PN", "NC", "shield bracket", "shield bracket", "shield bracket"])
            wb.save(source)

            result = run_bom_process(
                root,
                {
                    "source_bom": str(source),
                    "formats": ["plm"],
                    "parent_code": "203010100819",
                    "name": "TEST",
                },
            )

            self.assertEqual(result["status"], "needs_confirmation")
            self.assertEqual(result["reason"], "shield_bracket_candidates")
            self.assertEqual(result["shield_candidates"][0]["refs"], ["SH1"])

    def test_confirmed_sh_with_nc_value_enters_final_bom_not_nc_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Item", "Quantity", "Reference", "Part Number", "Value", "Model", "Description", "Name"])
            ws.append([1, 1, "SH1", "SH-PN", "NC", "shield bracket", "shield bracket", "shield bracket"])
            wb.save(source)

            result = bom_process.process(
                source,
                ["plm"],
                "203010100819",
                "",
                "TEST",
                [],
                tmp_path,
                "STAMP",
                None,
                confirm_shields=True,
            )

            shield = next(record for record in result["records"] if record["code"] == "SH-PN")
            self.assertEqual(shield["refs"], ["SH1"])
            self.assertEqual(shield["qty"], 1)
            self.assertEqual(result["summary"]["excluded"], 0)

            nc_wb = load_workbook(result["nc_summary"], data_only=True)
            nc_rows = list(nc_wb.active.iter_rows(values_only=True))
            self.assertEqual(len(nc_rows), 1)

    def test_nc_prefix_is_case_insensitive_but_not_nc_dash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Item", "Quantity", "Reference", "Part Number", "Value", "Model", "Description", "Name"])
            ws.append([1, 1, "R1", "P-NC-LOWER", "nc/not-mounted", "M1", "lower nc", "Resistor"])
            ws.append([2, 1, "R2", "P-NC-MIXED", "Nc/not-mounted", "M2", "mixed nc", "Resistor"])
            ws.append([3, 1, "R3", "P-NC-DASH", "NC-keep", "M3", "dash should stay", "Resistor"])
            ws.append([4, 1, "R4", "P-NC-EXACT", "NC", "M4", "exact nc", "Resistor"])
            wb.save(source)

            result = bom_process.process(
                source,
                ["plm"],
                "203010100819",
                "",
                "TEST",
                [],
                tmp_path,
                "STAMP",
                None,
            )

            codes = {record["code"] for record in result["records"]}
            self.assertNotIn("P-NC-LOWER", codes)
            self.assertNotIn("P-NC-MIXED", codes)
            self.assertNotIn("P-NC-EXACT", codes)
            self.assertIn("P-NC-DASH", codes)

            nc_wb = load_workbook(result["nc_summary"], data_only=True)
            try:
                nc_rows = list(nc_wb.active.iter_rows(values_only=True))
            finally:
                nc_wb.close()
            excluded_codes = {row[2] for row in nc_rows[1:]}
            self.assertIn("P-NC-LOWER", excluded_codes)
            self.assertIn("P-NC-MIXED", excluded_codes)
            self.assertIn("P-NC-EXACT", excluded_codes)
            self.assertNotIn("P-NC-DASH", excluded_codes)


if __name__ == "__main__":
    unittest.main()
