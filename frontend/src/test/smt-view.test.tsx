import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { BoardCanvas } from "../tools/smtView/BoardCanvas";
import { parseRefQuery } from "../tools/smtView/RefList";
import type { SmtBoard } from "../tools/smtView/types";

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class {
    observe() {}
    disconnect() {}
  });
});

const registration = {
  anchor_count: 120,
  rejected_count: 2,
  median_mm: 0.08,
  p90_mm: 0.14,
  max_mm: 0.27,
  trusted: true,
};

const board: SmtBoard = {
  schema_version: 2,
  board_id: "1234567890abcdef",
  label: "test",
  xy_file_name: "XY.txt",
  xy_version: "2.0",
  xy_units: "mm",
  drawings: {
    top: { page_number: 1, image_url: "/top.png", pixel_width: 1000, pixel_height: 600, registration },
    bottom: { page_number: 2, image_url: "/bottom.png", pixel_width: 1000, pixel_height: 600, registration },
  },
  placements: [
    {
      ref: "R1", x_mm: 2, y_mm: 3, drawing_x: 200, drawing_y: 180, rotation: 0, side: "top",
      footprint: "R0201", status: "placed", material_code: "3101", name: "电阻", model: "100K",
      description: "", grade: "优选", package: "R0201", reason: "成品 BOM 中存在",
      package_status: "通过", package_kind: "", net_package: "R0201", package_note: "",
    },
    {
      ref: "R2", x_mm: 4, y_mm: 5, drawing_x: 400, drawing_y: 300, rotation: 90, side: "bottom",
      footprint: "R0201", status: "nc", material_code: "", name: "", model: "", description: "",
      grade: "", package: "", reason: "XY 有、成品 BOM 无", package_status: "", package_kind: "",
      net_package: "", package_note: "",
    },
  ],
  bom_only: [],
  summary: { total: 2, top: 1, bottom: 1, placed: 1, nc: 1, bom_only: 0 },
  reference_drawing_name: "board_SMD.pdf",
  reference_drawing_url: "/drawing.pdf",
  package_report_outputs: [],
  notices: [],
};

describe("贴片视图", () => {
  it("supports comma-separated reference searches", () => {
    expect(parseRefQuery("r1，C2;u3\nR1")).toEqual(["R1", "C2", "U3"]);
  });

  it("uses the registered PDF page without mirroring and keeps list-to-drawing selection", () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <BoardCanvas board={board} side="top" mode="placement" selectedRef="" highlightedRefs={[]} onSelect={onSelect} />,
    );
    expect(screen.getByAltText("正面位号图")).toHaveAttribute("src", "/top.png");
    expect(screen.getByLabelText("R1")).toBeInTheDocument();
    expect(screen.queryByLabelText("R2")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("R1"));
    expect(onSelect).toHaveBeenCalledWith("R1");

    rerender(<BoardCanvas board={board} side="bottom" mode="nc" selectedRef="R2" highlightedRefs={[]} onSelect={onSelect} />);
    expect(screen.getByAltText("背面位号图")).toHaveAttribute("src", "/bottom.png");
    expect(screen.getByText(/背面 · 第 2 页/)).toBeInTheDocument();
    expect(screen.queryByText(/镜像/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("R2")).toBeInTheDocument();
  });
});
