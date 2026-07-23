from __future__ import annotations

from app.backend.bom_semantics.field_mapping import (
    infer_profile,
    map_header_values,
    normalize_header,
)
from app.backend.bom_semantics.models import WorkbookProfile


def test_plm_duplicate_description_columns_are_disambiguated() -> None:
    headers = [
        "父项编码",
        "描述",
        "子项编码",
        "名称",
        "型号",
        "描述",
        "数量",
        "位号",
    ]
    mapping, candidates, _ = map_header_values(headers)

    assert mapping["parent_description"] == 2
    assert mapping["description"] == 6
    assert candidates["description"][0] == 6


def test_oa_suffixes_and_braces_are_removed() -> None:
    assert normalize_header("编码（子）*##bm") == normalize_header("编码（子）")
    assert normalize_header("{Part Number}") == normalize_header("Part Number")


def test_profiles_are_inferred_from_semantic_fields() -> None:
    assert infer_profile({"parent_code": 1, "material_code": 3, "quantity": 8}, 1) == WorkbookProfile.PLM_SINGLE_BOARD
    assert infer_profile({"parent_code": 2, "material_code": 4, "quantity": 9}, 2) == WorkbookProfile.PLM_MULTI_BOARD
    assert infer_profile({"level": 2, "material_code": 3, "quantity": 8}) == WorkbookProfile.OA_BOM
    assert infer_profile({"change_type": 2, "change_status": 3, "material_code": 4}) == WorkbookProfile.OA_ECR
