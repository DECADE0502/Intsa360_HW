from __future__ import annotations

from pathlib import Path

import ezdxf
from openpyxl import Workbook


ROOT = Path(__file__).resolve().parent
COMPONENTS = [
    ("R1", 10.0, 70.0, 0, "", "R0402"),
    ("R2", 20.0, 70.0, 90, "", "R0402"),
    ("R3", 30.0, 70.0, 180, "", "R0402"),
    ("R4", 40.0, 70.0, 270, "", "R0402"),
    ("R5", 50.0, 70.0, 0, "", "R0603"),
    ("R6", 60.0, 70.0, 90, "", "R0603"),
    ("R7", 70.0, 70.0, 180, "", "R0603"),
    ("R8", 80.0, 70.0, 270, "", "R0603"),
    ("C1", 12.0, 55.0, 0, "", "C0402"),
    ("C2", 27.0, 55.0, 90, "", "C0402"),
    ("C3", 42.0, 55.0, 180, "", "C0603"),
    ("C4", 57.0, 55.0, 270, "", "C0603"),
    ("C5", 72.0, 55.0, 0, "", "C0603"),
    ("U1", 20.0, 35.0, 0, "", "BGA153"),
    ("U2", 45.0, 35.0, 90, "", "QFN48"),
    ("U3", 70.0, 35.0, 180, "", "QFN32"),
    ("SH1", 12.0, 15.0, 0, "m", "SHIELD_BRACKET"),
    ("JP1", 32.0, 15.0, 90, "m", "CONN_2P"),
    ("TP1", 52.0, 15.0, 0, "m", "TESTPOINT"),
    ("D1", 72.0, 15.0, 180, "m", "SOD323"),
]


def _write_xy() -> None:
    rows = ["VERSION=2.0", "UUNITS=MM", ""]
    rows.extend(
        f"{ref} ! {x} ! {y} ! {rotation} ! {mirror} ! {footprint}"
        for ref, x, y, rotation, mirror, footprint in COMPONENTS
    )
    (ROOT / "xy.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_outline() -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("OUTLINE")
    document.modelspace().add_lwpolyline(
        [(0, 0), (100, 0), (100, 80), (0, 80)],
        close=True,
        dxfattribs={"layer": "OUTLINE"},
    )
    document.saveas(ROOT / "outline.dxf")


def _write_bom(path: Path, refs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    footprint_by_ref = {ref: footprint for ref, _, _, _, _, footprint in COMPONENTS}
    workbook = Workbook()
    try:
        sheet = workbook.active
        sheet.title = "BOM"
        sheet.append(
            [
                "Reference",
                "Part Number",
                "Description",
                "Quantity",
                "Name",
                "Model",
                "PCB Footprint",
                "Grade",
            ]
        )
        for index, ref in enumerate(refs, start=1):
            footprint = footprint_by_ref.get(ref, "R0402")
            sheet.append(
                [
                    ref,
                    f"PN-{index:04d}",
                    f"Synthetic {footprint} component",
                    1,
                    "Component",
                    footprint,
                    footprint,
                    "\u4f18\u9009",
                ]
            )
        workbook.save(path)
    finally:
        workbook.close()


def _write_nc_bom(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    try:
        sheet = workbook.active
        sheet.title = "NC"
        sheet.append(["Reference", "Part Number", "Description", "Quantity"])
        sheet.append(["R8", "PN-NC-0001", "Synthetic NC resistor", 1])
        sheet.append(["C5", "PN-NC-0002", "Synthetic NC capacitor", 1])
        workbook.save(path)
    finally:
        workbook.close()


def _write_netlist() -> None:
    folder = ROOT / "netlist"
    folder.mkdir(parents=True, exist_ok=True)
    refs = [ref for ref, *_ in COMPONENTS if ref != "TP1"] + ["R99"]
    nodes = " ".join(f"{ref}.1" for ref in refs)
    (folder / "pstxnet.dat").write_text(f"NET SYNTHETIC_NET {nodes}\n", encoding="utf-8")

    footprint_by_ref = {ref: footprint for ref, _, _, _, _, footprint in COMPONENTS}
    part_rows = []
    for ref in refs:
        footprint = footprint_by_ref.get(ref, "R0402")
        if ref == "U1":
            footprint = "BGA169"
        part_rows.append(f"{ref} '{footprint}'")
    (folder / "pstxprt.dat").write_text("\n".join(part_rows) + "\n", encoding="utf-8")


def main() -> None:
    _write_xy()
    _write_outline()
    all_refs = [ref for ref, *_ in COMPONENTS if ref not in {"R8", "C5", "TP1"}] + ["R99"]
    processed = ROOT / "bom_processed"
    _write_bom(processed / "PLM.xlsx", all_refs)
    _write_nc_bom(processed / "NC.xlsx")
    _write_nc_bom(processed / "SYNTHETIC_NC\u672a\u8d34\u6c47\u603b.xlsx")
    _write_netlist()


if __name__ == "__main__":
    main()
