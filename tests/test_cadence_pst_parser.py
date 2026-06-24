from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.backend.parsers.cadence_pst import parse_net_file, parse_part_file


def write_netlist(folder: Path, nets: str = "", parts: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pstxnet.dat").write_text(nets, encoding="utf-8")
    (folder / "pstxprt.dat").write_text(parts, encoding="utf-8")


class CadencePstParserTests(unittest.TestCase):
    def test_parse_pstxnet_keeps_ref_pin_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_netlist(
                folder,
                nets="""FILE_TYPE = EXPANDEDNETLIST;
NET_NAME
'USB_DP'
 '@DSN(SCH_1):USB_DP':
 C_SIGNAL='usb_dp';
NODE_NAME\tR80 2
 '@DSN(SCH_1):INS1@LIB.RES.NORMAL(CHIPS)':
 '2':;
NODE_NAME\tU400 U24
 '@DSN(SCH_1):INS2@LIB.IC.NORMAL(CHIPS)':
 'GPIO3_16':;
""",
            )

            nets = parse_net_file(folder)

            self.assertEqual(nets["USB_DP"]["refs"], ["R80", "U400"])
            self.assertEqual(nets["USB_DP"]["nodes"], ["R80.2", "U400.U24"])
            self.assertEqual(nets["USB_DP"]["pins"], ["2", "U24"])

    def test_parse_pstxprt_reads_ref_and_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_netlist(
                folder,
                parts="""FILE_TYPE = EXPANDEDPARTLIST;
PART_NAME
 C1 'CAP_NP_C0201-0P4-B_1UF/6.3V':;
PART_NAME
 U400 'A380H_BGA356':;
""",
            )

            parts = parse_part_file(folder)

            self.assertEqual(parts["C1"], "CAP_NP_C0201-0P4-B_1UF/6.3V")
            self.assertEqual(parts["U400"], "A380H_BGA356")


if __name__ == "__main__":
    unittest.main()
