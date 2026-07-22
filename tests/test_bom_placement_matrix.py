from __future__ import annotations

import os
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.backend.tools.bom_classify import (
    analyze_placement,
    apply_resolutions,
    build_normalized_row,
    classification_config,
    classify,
    make_field_value,
)
from app.backend.tools.bom_process import ParsedSource
from app.backend.tools import bom_process


BASE_FIELDS = {
    "part_number": "",
    "value": "",
    "name": "",
    "model": "",
    "desc": "",
    "grade": "",
    "unit": "",
    "pcb_footprint": "",
    "pcb_package": "",
    "source_package": "",
    "source_part": "",
}


def make_row(
    row_number: int = 2,
    refs: tuple[str, ...] = ("X1",),
    **fields: str,
):
    values = {**BASE_FIELDS, **fields}
    return build_normalized_row(row_number, refs, values)


def test_normal_part_number_is_confirmed_material() -> None:
    result = classify(make_row(part_number="P-ALPHA-01", desc="普通器件"), classification_config())

    assert result.state == "confirmed_material"
    assert result.requires_review is False


@pytest.mark.parametrize("ref", ["TP9", "JP7", "H3", "MH4", "MTG8", "CUSTOM2"])
def test_nonstandard_reference_prefix_does_not_block_a_valid_material(ref: str) -> None:
    result = classify(
        make_row(refs=(ref,), part_number="P-ALPHA-01", desc="普通贴片物料"),
        classification_config(),
    )

    assert result.state == "confirmed_material"
    assert result.requires_review is False


@pytest.mark.parametrize("field", ["value", "model", "desc", "name", "source_part", "source_package"])
def test_code_candidates_are_collected_from_all_supported_fields(field: str) -> None:
    row = make_row(**{field: "AB.CD1234", "pcb_footprint": "PKG_100"})
    result = classify(row, classification_config())

    assert result.state == "suspected_material"
    assert result.confidence == "medium"
    assert result.suggested_code == "AB.CD1234"
    assert any(item.kind == "code_shape" and item.field == field for item in result.evidence)
    assert all(any("\u4e00" <= char <= "\u9fff" for char in item.display) for item in result.evidence)


@pytest.mark.parametrize("prefix", ["MTG", "TP", "JP", "H", "CUSTOM", "X"])
def test_reference_prefix_never_changes_material_recommendation(prefix: str) -> None:
    row = make_row(refs=(f"{prefix}17",), value="AB.CD1234", pcb_footprint="PKG_100")
    result = classify(row, classification_config())

    assert result.state == "suspected_material"
    assert result.recommended_action == "keep"


def test_process_description_without_role_corroboration_cannot_exclude() -> None:
    row = make_row(refs=("ANY17",), value="SHORT_L2", desc="JUMPER test link")
    result = classify(row, classification_config())

    assert result.state == "suspected_material"
    assert result.recommended_action is None


@pytest.mark.parametrize("description", ["镀金测试点", "PCB安装孔"])
def test_valid_code_with_description_only_process_text_is_a_conflict(description: str) -> None:
    result = classify(
        make_row(part_number="P-ALPHA-01", desc=description),
        classification_config(),
    )

    assert result.state == "conflicting"
    assert result.recommended_action is None
    assert result.rule_id == "R4D"
    assert result.requires_review is True


@pytest.mark.parametrize("description", ["焊接铜柱", "M3螺母柱结构件"])
def test_valid_code_with_ambiguous_mechanical_text_is_material_review(description: str) -> None:
    result = classify(
        make_row(part_number="P-ALPHA-01", desc=description),
        classification_config(),
    )

    assert result.state == "suspected_material"
    assert result.recommended_action is None
    assert result.rule_id == "R4A"


def test_jumper_resistor_phrase_remains_a_confirmed_material() -> None:
    result = classify(
        make_row(part_number="R-ALPHA-01", value="0R", name="电阻", desc="跳线电阻 0402"),
        classification_config(),
    )

    assert result.state == "confirmed_material"
    assert result.requires_review is False


def test_ambiguous_mechanical_text_without_a_code_has_no_default_exclusion() -> None:
    result = classify(make_row(desc="焊接铜柱结构件"), classification_config())

    assert result.state == "suspected_material"
    assert result.confidence == "weak"
    assert result.recommended_action is None


def test_vendor_mpn_with_long_prefix_remains_a_material_candidate() -> None:
    candidate = "LONGPREFIX12-M3-10ET"
    result = classify(
        make_row(refs=("MTG17",), value=candidate, desc="表贴螺母柱", pcb_footprint="PKG_100"),
        classification_config(),
    )

    assert result.state == "suspected_material"
    assert result.recommended_action is None
    assert result.suggested_code == ""
    assert result.suggested_mpn == candidate
    assert result.identity_status == "identity_candidate_mpn"


def test_process_value_beats_capture_library_object_that_looks_like_a_code() -> None:
    row = make_row(
        refs=("JP17",),
        value="SHORT_L2",
        source_package="Short_L3",
        source_part="Short_L3.Normal",
    )
    result = classify(row, classification_config())

    assert result.state == "suspected_process"
    assert result.recommended_action == "exclude"
    assert result.suggested_code == ""


def test_capture_source_part_suffix_is_removed_before_code_detection() -> None:
    result = classify(make_row(source_part="AB.CD1234.Normal"), classification_config())

    assert result.state == "suspected_material"
    assert result.suggested_code == "AB.CD1234"


@pytest.mark.parametrize("marker", ["NC", "DNP", "DNI", "No Load", "NOFIT", "不贴", "未贴", "空贴"])
def test_configured_nc_markers_are_exact_system_nc(marker: str) -> None:
    result = classify(make_row(value=marker), classification_config())

    assert result.state == "confirmed_nc"
    assert result.requires_review is False


def test_nc_marker_does_not_match_part_number_substring() -> None:
    result = classify(make_row(part_number="NCP1117", value="1.2V"), classification_config())

    assert result.state == "confirmed_material"


def test_nc_value_with_slash_separators_is_not_mistaken_for_a_file_path() -> None:
    field = make_field_value("NC/10uF/6.3V")

    assert "path_like" not in field.flags


@pytest.mark.parametrize("value", [r"D:\\cadence\\library\\part.olb", r"\\\\server\\library\\part.olb"])
def test_real_windows_paths_are_flagged(value: str) -> None:
    field = make_field_value(value)

    assert "path_like" in field.flags


def test_path_misplaced_in_a_material_field_requires_conflict_review() -> None:
    result = classify(
        make_row(model=r"D:\\cadence\\library\\part.olb"),
        classification_config(),
    )

    assert result.state == "conflicting"
    assert result.recommended_action is None
    assert any(
        item.kind == "field_misplacement" and item.shape_id == "path_like"
        for item in result.evidence
    )


@pytest.mark.parametrize("field", ["source_library", "implementation_path", "datasheet"])
def test_path_in_capture_diagnostic_field_is_valid(field: str) -> None:
    result = classify(
        make_row(part_number="P-ALPHA-01", desc="普通器件", **{field: r"Z:\\cadence\\library\\part.olb"}),
        classification_config(),
    )

    assert result.state == "confirmed_material"
    assert not any(item.kind == "field_misplacement" for item in result.evidence)


@pytest.mark.parametrize("value", ["NC", "DNP", "NC/备用", "No Load", "dnp（本版）"])
def test_valid_code_with_pure_nc_value_is_system_nc(value: str) -> None:
    # 器件库自带编码 + Value 整格为 NC 标记，是 Capture 最常见的 NC 表达，
    # 必须按系统明确 NC 处理，不得升级为需要人工逐组裁决的属性冲突。
    result = classify(make_row(part_number="P-ALPHA-01", value=value), classification_config())

    assert result.state == "confirmed_nc"
    assert result.recommended_action == "exclude"
    assert result.rule_id == "R2C"
    assert not result.sh_review


def test_valid_code_with_embedded_nc_text_requires_conflict_review() -> None:
    # NC 词嵌在更长的描述文本里（而非 Value 整格标记）才是真正的属性冲突，需要人工裁决。
    result = classify(
        make_row(part_number="P-ALPHA-01", value="0402 NC 备用", desc="正常物料描述"),
        classification_config(),
    )

    assert result.state == "conflicting"
    assert result.recommended_action is None


def test_shield_ref_with_pure_nc_value_still_requires_review() -> None:
    # SH 位号即使 Value 整格为 NC，也必须经人工审查确认，不允许静默排除。
    result = classify(make_row(refs=("SH1",), part_number="P-ALPHA-02", value="NC"), classification_config())

    assert result.state == "conflicting"
    assert result.requires_review


def test_description_text_in_part_number_column_requires_conflict_review() -> None:
    result = classify(
        make_row(part_number="这是一段误填到编码列中的完整器件描述", model="MODEL-A"),
        classification_config(),
    )

    assert result.state == "conflicting"
    assert result.recommended_action is None
    assert any(item.kind == "field_misplacement" for item in result.evidence)


def test_blank_material_with_only_description_has_no_default_action() -> None:
    result = classify(make_row(desc="焊接结构件"), classification_config())

    assert result.state == "suspected_material"
    assert result.confidence == "weak"
    assert result.recommended_action is None


def test_placeholder_only_row_is_reviewed_as_insufficient_data() -> None:
    row = make_row(desc="{")
    result = classify(row, classification_config())
    analysis = analyze_placement([row], classification_config())

    assert result.state == "insufficient_data"
    assert result.requires_review is True
    assert result.recommended_action is None
    assert analysis.review_groups[0].inferred_fields["desc"] == ""


def test_blank_code_shield_is_reviewed_once_in_shield_category() -> None:
    row = make_row(refs=("SH11",), value="ZXCV-A7-55", pcb_footprint="SHIELD_FIX")
    analysis = analyze_placement([row], classification_config())

    assert len(analysis.review_groups) == 1
    group = analysis.review_groups[0]
    assert group.category == "shield"
    assert group.classification.recommended_action is None


def test_coded_sh_material_outweighs_lower_priority_process_metadata() -> None:
    row = make_row(
        refs=("SH12",),
        part_number="P-ALPHA-01",
        value="TP0P4",
        desc="测试点",
        pcb_footprint="TP0P4",
    )
    analysis = analyze_placement([row], classification_config())

    assert len(analysis.review_groups) == 1
    group = analysis.review_groups[0]
    assert group.category == "shield"
    assert group.classification.state == "conflicting"
    assert group.classification.recommended_action is None
    assert group.classification.rule_id == "R3C"
    assert any(item.kind == "process_keyword" for item in group.classification.evidence)


def test_multi_unit_references_merge_only_with_matching_identity_and_package(tmp_path: Path) -> None:
    path = tmp_path / "multi-unit.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Item", "Quantity", "Reference", "Part Number", "Value", "PCB Footprint"])
    for index, ref in enumerate(("U1A", "U1B", "U1C"), start=1):
        sheet.append([index, 1, ref, "MAT-0001", "IC", "BGA100"])
    workbook.save(path)
    workbook.close()

    parsed = bom_process.parse_source(path)

    assert {ref for row in parsed.normalized_rows for ref in row.refs} == {"U1"}
    assert parsed.physical_parts[0].merge_kind == "multi_unit"
    assert parsed.quality_report.payload()["code_counts"]["multi_unit_merged"] == 1


def test_multi_unit_suffix_is_not_removed_without_matching_formal_identity(tmp_path: Path) -> None:
    path = tmp_path / "multi-unit-weak.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Item", "Quantity", "Reference", "Part Number", "Value", "PCB Footprint"])
    sheet.append([1, 1, "U1A", "", "VENDOR-A1", "BGA100"])
    sheet.append([2, 1, "U1B", "", "VENDOR-A1", "BGA100"])
    workbook.save(path)
    workbook.close()

    parsed = bom_process.parse_source(path)

    assert {ref for row in parsed.normalized_rows for ref in row.refs} == {"U1A", "U1B"}


def test_low_information_rows_do_not_collapse_into_one_resolution_group() -> None:
    rows = [
        make_row(2, ("A1",), value="UNCLASSIFIED"),
        make_row(8, ("B1",), value="UNCLASSIFIED"),
    ]
    analysis = analyze_placement(rows, classification_config())

    assert len(analysis.review_groups) == 2
    assert analysis.review_groups[0].key != analysis.review_groups[1].key


def test_code_only_rows_with_different_refs_do_not_share_one_resolution() -> None:
    rows = [
        make_row(2, ("A1",), value="AB.CD1234"),
        make_row(8, ("B1",), value="AB.CD1234"),
    ]
    analysis = analyze_placement(rows, classification_config())

    assert len(analysis.review_groups) == 2
    assert analysis.review_groups[0].key != analysis.review_groups[1].key


def test_group_fingerprint_is_stable_and_changes_with_content() -> None:
    original = analyze_placement(
        [make_row(value="AB.CD1234", pcb_footprint="PKG_100")],
        classification_config(),
    ).review_groups[0]
    same = analyze_placement(
        [make_row(value="AB.CD1234", pcb_footprint="PKG_100")],
        classification_config(),
    ).review_groups[0]
    changed = analyze_placement(
        [make_row(value="AB.CD1235", pcb_footprint="PKG_100")],
        classification_config(),
    ).review_groups[0]

    assert original.key == same.key
    assert original.key != changed.key


def test_resolution_is_applied_by_content_key_and_preserves_excluded_snapshot() -> None:
    rows = [
        make_row(2, ("A1",), value="AB.CD1234", pcb_footprint="PKG_100"),
        make_row(3, ("B1",), desc="待确认结构件"),
    ]
    raw_rows = [
        {field: row.value(field) for field in BASE_FIELDS}
        for row in rows
    ]
    raw_rows[0]["reference"] = "A1"
    raw_rows[1]["reference"] = "B1"
    parsed = ParsedSource(Path("source.xlsx"), raw_rows, [2, 3], tuple(rows))
    analysis = analyze_placement(rows, classification_config())
    by_ref = {group.refs[0]: group for group in analysis.review_groups}
    resolutions = {
        by_ref["A1"].key: {
            "action": "keep",
            "part_number": "AB.CD1234",
            "field_patch": {"name": "结构件"},
        },
        by_ref["B1"].key: {
            "action": "exclude",
            "part_number": "",
            "field_patch": {},
        },
    }

    resolved, summary = apply_resolutions(parsed, analysis, resolutions)

    assert resolved.raw_rows[0]["part_number"] == "AB.CD1234"
    assert resolved.raw_rows[0]["value"] == ""
    assert resolved.raw_rows[0]["_user_touched"] == ["name", "part_number", "value"]
    assert resolved.raw_rows[1]["desc"] == "待确认结构件"
    assert resolved.raw_rows[1]["_placement_action"] == "exclude"
    assert resolved.raw_rows[1]["_placement_reason_kind"] == "user_excluded"
    assert summary["kept_groups"] == 1
    assert summary["excluded_groups"] == 1


def test_resolution_replay_is_idempotent() -> None:
    row = make_row(value="AB.CD1234", pcb_footprint="PKG_100")
    raw = {field: row.value(field) for field in BASE_FIELDS}
    raw["reference"] = "X1"
    parsed = ParsedSource(Path("source.xlsx"), [raw], [row.row_number], (row,))
    analysis = analyze_placement([row], classification_config())
    group = analysis.review_groups[0]
    resolutions = {
        group.key: {
            "action": "keep",
            "part_number": group.classification.suggested_code,
            "field_patch": {"desc": "结构件"},
        }
    }

    first, first_summary = apply_resolutions(parsed, analysis, resolutions)
    second, second_summary = apply_resolutions(parsed, analysis, resolutions)

    assert first.raw_rows == second.raw_rows
    assert first_summary == second_summary


def test_kept_rows_drop_placeholder_and_mojibake_fields_before_output() -> None:
    row = make_row(
        part_number="P-ALPHA-01",
        desc="正常物料",
        grade="{等级}",
        unit="锟斤拷",
    )
    raw = {field: row.fields[field].raw for field in BASE_FIELDS}
    raw["reference"] = "X1"
    parsed = ParsedSource(Path("source.xlsx"), [raw], [row.row_number], (row,))
    analysis = analyze_placement([row], classification_config())

    resolved, _ = apply_resolutions(parsed, analysis, {})

    assert resolved.raw_rows[0]["part_number"] == "P-ALPHA-01"
    assert resolved.raw_rows[0]["desc"] == "正常物料"
    assert resolved.raw_rows[0]["grade"] == ""
    assert resolved.raw_rows[0]["unit"] == ""
    assert resolved.raw_rows[0]["_sanitized_fields"] == ["grade", "unit"]


@pytest.mark.skipif(not os.environ.get("HW_BOM_GOLDEN_PATH"), reason="未配置真实 BOM 回归文件")
def test_real_capture_bom_has_generic_material_and_process_evidence() -> None:
    source = Path(os.environ["HW_BOM_GOLDEN_PATH"])
    if not source.is_file():
        pytest.skip("HW_BOM_GOLDEN_PATH 指向的文件不存在")

    parsed = bom_process.parse_source(source)
    analysis = analyze_placement(parsed.normalized_rows, classification_config())
    groups = analysis.review_groups

    assert parsed.raw_rows
    assert any(
        group.classification.state == "suspected_material"
        and group.classification.recommended_action == "keep"
        and any(item.kind == "code_shape" and item.shape_id == "digits" for item in group.classification.evidence)
        for group in groups
    )
    assert any(
        group.classification.state == "suspected_process"
        and group.classification.recommended_action == "exclude"
        for group in groups
    )
    assert any(
        group.classification.state == "suspected_material"
        and group.classification.confidence == "medium"
        and group.classification.recommended_action is None
        and any(item.kind == "code_shape" and item.shape_id == "vendor_mpn" for item in group.classification.evidence)
        for group in groups
    )
    assert any(
        group.category == "shield"
        and group.classification.state == "conflicting"
        and group.classification.recommended_action is None
        and any(item.kind == "process_keyword" for item in group.classification.evidence)
        for group in groups
    )
