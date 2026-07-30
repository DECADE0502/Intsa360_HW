from __future__ import annotations

import os
from pathlib import Path

from app.backend.smt_analysis.ingest import scan_source_directory, source_fingerprint


def _asset_by_name(folder: Path) -> dict[str, object]:
    return {asset.relative_path: asset for asset in scan_source_directory(folder)}


def test_scan_keeps_unknown_and_unsupported_files(tmp_path: Path) -> None:
    (tmp_path / "unknown.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / "model.step").write_text("ISO-10303-21;", encoding="ascii")
    (tmp_path / "archive.rar").write_bytes(b"Rar!\x1a\x07\x01\x00")

    assets = _asset_by_name(tmp_path)

    assert assets["unknown.bin"].roles == ["unknown"]
    assert assets["unknown.bin"].classification_state == "unresolved"
    assert assets["model.step"].roles == ["unrelated"]
    assert assets["archive.rar"].roles == ["unrelated"]
    assert len(assets) == 3


def test_scan_identifies_cadence_xy_by_content_not_filename(tmp_path: Path) -> None:
    coordinate = tmp_path / "vendor_export.dat"
    coordinate.write_text(
        "VERSION=2.0\nUUNITS=MM\nR1 ! 1.2 ! 3.4 ! 0 ! ! R0402\n",
        encoding="utf-8",
    )

    asset = _asset_by_name(tmp_path)["vendor_export.dat"]

    assert asset.roles == ["placement_coordinate"]
    assert asset.classification_state == "classified"
    assert any(item.weight == "strong" for item in asset.evidence)


def test_scan_does_not_silently_choose_between_multiple_drawings(tmp_path: Path) -> None:
    (tmp_path / "panel.dxf").write_text("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n", encoding="ascii")
    (tmp_path / "assembly.dxf").write_text("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n", encoding="ascii")

    assets = _asset_by_name(tmp_path)

    assert "panel_drawing" in assets["panel.dxf"].roles
    assert "assembly_drawing" in assets["assembly.dxf"].roles
    assert assets["panel.dxf"].classification_state == "candidate"
    assert assets["assembly.dxf"].classification_state == "candidate"


def test_source_fingerprint_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    target = tmp_path / "XY.txt"
    target.write_text("UUNITS=MM\nR1 ! 1 ! 2 ! 0 ! ! R0402\n", encoding="utf-8")
    first = scan_source_directory(tmp_path)
    second = scan_source_directory(tmp_path)

    assert source_fingerprint(first) == source_fingerprint(second)

    target.write_text("UUNITS=MM\nR1 ! 2 ! 3 ! 0 ! ! R0402\n", encoding="utf-8")
    assert source_fingerprint(first) != source_fingerprint(scan_source_directory(tmp_path))


def test_real_sample_distinguishes_assembly_and_schematic_when_opted_in(
) -> None:
    raw = os.environ.get("SMT_REAL_SAMPLE_DIR", "")
    if not raw:
        return
    folder = Path(raw)
    assets = scan_source_directory(folder)
    pdfs = {asset.relative_path: asset for asset in assets if asset.media_type == "application/pdf"}

    assembly = next(asset for name, asset in pdfs.items() if "SMD" in name.upper())
    schematic = next(asset for name, asset in pdfs.items() if "原理图" in name)
    assert assembly.roles == ["assembly_drawing"]
    assert "schematic_drawing" in schematic.roles
    assert assembly.asset_id != schematic.asset_id
