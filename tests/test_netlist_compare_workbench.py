from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.backend.tools import analysis_tools


ROOT = Path(__file__).resolve().parents[1]


def write_netlist(folder: Path, nets: str, parts: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pstxnet.dat").write_text(nets, encoding="utf-8")
    (folder / "pstxprt.dat").write_text(parts or "PART_NAME\n", encoding="utf-8")


class NetlistCompareWorkbenchTests(unittest.TestCase):
    def test_netlist_compare_classifies_rename_split_merge_and_critical_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "left"
            right = root / "right"
            write_netlist(
                left,
                nets="""NET_NAME
'OLD_NAME'
NODE_NAME R1 1
NODE_NAME C1 1
NET_NAME
'BUS'
NODE_NAME U1 A1
NODE_NAME U2 A1
NODE_NAME U3 A1
NET_NAME
'M1'
NODE_NAME U4 A1
NET_NAME
'M2'
NODE_NAME U5 A1
NET_NAME
'USB_DP'
NODE_NAME U10 A1
NODE_NAME R10 1
""",
                parts="""PART_NAME
 U10 'BGA100_OLD':;
""",
            )
            write_netlist(
                right,
                nets="""NET_NAME
'NEW_NAME'
NODE_NAME R1 1
NODE_NAME C1 1
NET_NAME
'BUS_A'
NODE_NAME U1 A1
NET_NAME
'BUS_B'
NODE_NAME U2 A1
NODE_NAME U3 A1
NET_NAME
'MERGED'
NODE_NAME U4 A1
NODE_NAME U5 A1
NET_NAME
'USB_DP'
NODE_NAME U10 A1
NODE_NAME R10 2
NET_NAME
'VDD_MAIN'
NODE_NAME U20 VDD
NODE_NAME C20 1
""",
                parts="""PART_NAME
 U10 'BGA100_NEW':;
""",
            )

            result = analysis_tools.run_netlist_compare(
                ROOT,
                {"netlist1": str(left), "netlist2": str(right), "output_dir": str(root)},
            )

            self.assertEqual(result["status"], "ok")
            review = result["netlist_review"]
            self.assertEqual(review["status_counts"]["rename"], 1)
            self.assertEqual(review["status_counts"]["split"], 1)
            self.assertEqual(review["status_counts"]["merge"], 1)
            self.assertEqual(review["status_counts"]["node_change"], 1)
            self.assertEqual(review["status_counts"]["added"], 1)
            statuses = {item["status"] for item in review["items"]}
            self.assertIn("网络改名", statuses)
            self.assertIn("疑似拆网", statuses)
            self.assertIn("疑似并网", statuses)
            self.assertIn("关键网络变化", statuses)
            self.assertTrue(any(item["key"] == "USB_DP" and item["severity"] == "high" for item in review["focus_items"]))
            self.assertEqual(result["summary"]["critical_changes"], 2)

    def test_netlist_compare_accepts_uploaded_file_list_by_inferring_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "upload_left"
            right = root / "upload_right"
            write_netlist(left, "NET_NAME\n'N1'\nNODE_NAME R1 1\n", "PART_NAME\n R1 'R0201':;\n")
            write_netlist(right, "NET_NAME\n'N1'\nNODE_NAME R1 2\n", "PART_NAME\n R1 'R0201':;\n")

            result = analysis_tools.run_netlist_compare(
                ROOT,
                {
                    "netlist1": [str(left / "pstxnet.dat"), str(left / "pstxprt.dat")],
                    "netlist2": [str(right / "pstxnet.dat"), str(right / "pstxprt.dat")],
                    "output_dir": str(root),
                },
            )

            self.assertEqual(result["status"], "ok")
            self.assertGreaterEqual(result["summary"]["node_diffs"], 1)

    def test_netlist_compare_allows_missing_pstxprt_for_node_only_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "pstxnet.dat").write_text("NET_NAME\n'USB_DP'\nNODE_NAME U1 A1\nNODE_NAME R1 1\n", encoding="utf-8")
            (right / "pstxnet.dat").write_text("NET_NAME\n'USB_DP'\nNODE_NAME U1 A1\nNODE_NAME R1 2\n", encoding="utf-8")

            result = analysis_tools.run_netlist_compare(
                ROOT,
                {"netlist1": str(left), "netlist2": str(right), "output_dir": str(root)},
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["summary"]["package_diffs"], 0)
            self.assertEqual(result["summary"]["package_check"], "skipped")
            self.assertTrue(any("pstxprt.dat" in warning for warning in result["warnings"]))
            self.assertGreaterEqual(result["summary"]["node_diffs"], 1)

    def test_registry_netlist_tools_run_without_missing_module_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "left"
            right = root / "right"
            write_netlist(left, "NET_NAME\n'N1'\nNODE_NAME R1 1\n", "PART_NAME\n R1 'R0201':;\n")
            write_netlist(right, "NET_NAME\n'N1'\nNODE_NAME R1 2\n", "PART_NAME\n R1 'R0201':;\n")
            registry = analysis_tools.create_analysis_tools(ROOT)
            tool = next(item for item in registry if item.id == "netlist_compare")

            result = tool.runner({"netlist1": str(left), "netlist2": str(right), "output_dir": str(root)})

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["tool"], "netlist_compare")


if __name__ == "__main__":
    unittest.main()
