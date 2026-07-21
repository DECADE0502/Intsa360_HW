from __future__ import annotations

from pathlib import Path

import ezdxf


ROOT = Path(__file__).resolve().parent


def write_dxf(name: str, points: list[tuple[float, float]]) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("OUTLINE")
    document.modelspace().add_lwpolyline(points, close=True, dxfattribs={"layer": "OUTLINE"})
    document.saveas(ROOT / name)


def main() -> None:
    write_dxf("outline_rect.dxf", [(0, 0), (100, 0), (100, 80), (0, 80)])
    write_dxf("outline_lshape.dxf", [(0, 0), (100, 0), (100, 30), (40, 30), (40, 80), (0, 80)])
    (ROOT / "outline_bbox.art").write_text(
        "%FSLAX24Y24*%\n%MOMM*%\nX000000Y000000D02*\nX1000000Y000000D01*\n"
        "X1000000Y0800000D01*\nX000000Y0800000D01*\nM02*\n",
        encoding="ascii",
    )


if __name__ == "__main__":
    main()
