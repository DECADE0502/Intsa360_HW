from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from fixture_builders import build_capture_bom, build_processed_bom


FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED_CODES = {"C.C1105M21", "C.C1225M21", "C.C2106M21"}


def load_fixture(relative_path: str) -> dict[str, object]:
    return json.loads((FIXTURES / relative_path).read_text(encoding="utf-8"))


def parse_net_nodes(text: str) -> dict[str, set[str]]:
    nets: dict[str, set[str]] = {}
    current: str | None = None
    expect_name = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "NET_NAME":
            expect_name = True
            continue
        if expect_name:
            match = re.fullmatch(r"'([^']+)'", line)
            if match:
                current = match.group(1)
                nets[current] = set()
                expect_name = False
            continue
        tokens = line.split()
        if current and len(tokens) >= 3 and tokens[0] == "NODE_NAME":
            nets[current].add(f"{tokens[1]}.{tokens[2]}")
    return nets


def parse_part_packages(text: str) -> dict[str, str]:
    packages: dict[str, str] = {}
    for raw in text.splitlines():
        match = re.fullmatch(r"\s*([A-Za-z]+\d+)\s+'([^']+)':;", raw)
        if match:
            packages[match.group(1)] = match.group(2)
    return packages


class GoldenFixtureTests(unittest.TestCase):
    def test_sanitized_bom_cases_preserve_conflicts_and_risk_expectations(self) -> None:
        cases = load_fixture("bom/conflict_cases.json")
        expected = load_fixture("bom/expected_recommendations.json")
        rows = cases["rows"]
        self.assertIsInstance(rows, dict)
        row_values = list(rows.values())

        codes = {row["Part Number"] for row in row_values}
        self.assertTrue(EXPECTED_CODES <= codes)

        recommendations = expected["recommendations"]
        self.assertEqual(set(recommendations), EXPECTED_CODES)
        for code, expectation in recommendations.items():
            source_signatures = {
                (
                    row["Model"],
                    row["Description"],
                    row["Name"],
                    row["Grade"],
                    row["Unit"],
                )
                for row in row_values
                if row["Part Number"] == code
            }
            allowed = {
                tuple(signature[field] for field in ("model", "description", "name", "grade", "unit"))
                for signature in expectation["allowed_signatures"]
            }
            self.assertTrue(allowed <= source_signatures)
            if expectation["manual_choice_required"]:
                self.assertEqual(expectation["expected_confidence"], "low")
            else:
                selected = expectation["selected_signature"]
                self.assertIn(
                    tuple(selected[field] for field in ("model", "description", "name", "grade", "unit")),
                    source_signatures,
                )

        risks = expected["risk_expectations"]
        shield = risks["shield_candidate"]
        self.assertTrue(shield["requires_confirmation"])
        self.assertTrue(shield["enters_final_bom"])
        self.assertTrue(shield["excluded_from_nc"])
        self.assertTrue(any(row["Reference"] == shield["reference"] for row in row_values))
        self.assertEqual({warning["kind"] for warning in risks["version_warnings"]}, {"DDR", "eMMC"})
        duplicate = risks["duplicate_reference"]
        duplicate_rows = [row for row in row_values if duplicate["reference"] in row["Reference"].split()]
        self.assertEqual({row["Part Number"] for row in duplicate_rows}, set(duplicate["part_numbers"]))

    def test_capture_builder_writes_the_full_sanitized_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capture.xlsx"
            result = build_capture_bom(path, "golden")

            self.assertEqual(result, path)
            self.assertTrue(path.exists())
            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                sheet = workbook.active
                headers = [cell.value for cell in sheet[1]]
                records = [dict(zip(headers, row)) for row in sheet.iter_rows(min_row=2, values_only=True)]
            finally:
                workbook.close()

        self.assertIn("{Reference}", headers)
        self.assertIn("{Part Number}", headers)
        self.assertTrue(EXPECTED_CODES <= {record["{Part Number}"] for record in records})
        self.assertEqual(sum("R7701" in record["{Reference}"].split() for record in records), 2)
        shield = next(record for record in records if record["{Reference}"] == "SH1")
        self.assertEqual(shield["{Part Number}"], "MECH.SHIELD.01")

    def test_processed_bom_builders_emit_complete_19_column_rows(self) -> None:
        for template in ("plm", "oa"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{template}.xlsx"
                result = build_processed_bom(path, template)

                self.assertEqual(result, path)
                workbook = load_workbook(path, read_only=True, data_only=True)
                try:
                    sheet = workbook.active
                    self.assertEqual(sheet.title, template.upper())
                    headers = [cell.value for cell in sheet[1]]
                    row = [cell.value for cell in sheet[2]]
                finally:
                    workbook.close()

                self.assertEqual(len(headers), 19)
                self.assertEqual(len(row), 19)
                self.assertEqual(row[0], "PARENT.SANITIZED.01")
                self.assertEqual(row[2], "C.C1105M21")
                self.assertEqual(row[8], "C1105,C1106")
                self.assertEqual(row[16:19], ["DIRECT", "YES", "NO"])

    def test_netlist_samples_keep_real_format_and_expected_edge_case_tokens(self) -> None:
        netlist = (FIXTURES / "netlist/pstxnet_sample.dat").read_text(encoding="utf-8")
        parts = (FIXTURES / "netlist/pstxprt_sample.dat").read_text(encoding="utf-8")
        nets = parse_net_nodes(netlist)
        packages = parse_part_packages(parts)

        self.assertIn("FILE_TYPE = EXPANDEDNETLIST;", netlist)
        self.assertEqual(nets["RENAME_OLD"], nets["RENAME_NEW"])
        self.assertEqual(nets["SPLIT_OLD"], nets["SPLIT_NEW_A"] | nets["SPLIT_NEW_B"])
        self.assertEqual(nets["MERGE_NEW"], nets["MERGE_OLD_A"] | nets["MERGE_OLD_B"])
        self.assertEqual(nets["MIXED_TOPOLOGY"], {"R401.1", "U401.A1", "U401.B1", "C401.1"})
        self.assertIn("NC_7", nets)
        self.assertIn("NCLK", nets)
        self.assertIn("nCS0", nets)
        self.assertEqual(nets["NC_7"], {"C701.1"})
        self.assertIn("FILE_TYPE = EXPANDEDPARTLIST;", parts)
        self.assertEqual(packages["R501"], "RES_R0402_10K")
        self.assertEqual(packages["R502"], "RES_R0603_10K")
        self.assertNotEqual(packages["R501"], packages["R502"])
        self.assertEqual(packages["C701"], "CAP_NP_C0201_NC")


if __name__ == "__main__":
    unittest.main()
