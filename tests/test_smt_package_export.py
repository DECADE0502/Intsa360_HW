from __future__ import annotations

from collections import Counter

from app.backend.tools.smt_package import _build_smt_package_review


def _bom_row(refs: list[str], part_number: str, package: str, name: str = "") -> dict[str, object]:
    return {
        "refs": refs,
        "part_number": part_number,
        "package": package,
        "model": package,
        "description": package,
        "name": name,
        "grade": "A",
    }


def _export_status(status: str) -> str:
    if status in {"通过", "近似通过"}:
        return "机器初筛通过"
    return status


def test_export_rows_cover_all_review_items() -> None:
    parts = {
        "U1": "BGA153",
        "C1": "CAP_0402",
        "C2": "CAP_0603",
        "R1": "RES_0402",
        "U9": "NC",
        "TP1": "TEST_POINT",
    }
    bom_rows = [
        _bom_row(["U1"], "U.001", "BGA153", "eMMC"),
        _bom_row(["C1"], "C.001", "CAP_0402", "电容"),
        _bom_row(["C2"], "C.001", "CAP_0603", "电容"),
        _bom_row(["R99"], "R.099", "RES_0402", "电阻"),
    ]

    review = _build_smt_package_review(parts, bom_rows)

    item_projection = Counter(
        (str(item["ref"]), _export_status(str(item["status"])))
        for item in review["items"]
    )
    row_projection = Counter((str(row[0]), str(row[5])) for row in review["table_rows"])
    assert row_projection == item_projection


def test_export_row_preserves_review_item_details() -> None:
    review = _build_smt_package_review(
        {"U1": "BGA153"},
        [_bom_row(["U1"], "U.001", "BGA153", "eMMC")],
    )

    high_risk = next(item for item in review["items"] if item["status"] == "高风险封装")
    exported = next(row for row in review["table_rows"] if row[0] == "U1" and row[5] == "高风险封装")
    assert exported == [
        high_risk["ref"],
        high_risk["net_package"],
        high_risk["bom_package"] or high_risk["model"],
        high_risk["description"],
        high_risk["name"],
        high_risk["status"],
        high_risk["note"],
    ]
