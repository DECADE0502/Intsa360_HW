import { render, screen } from "@testing-library/react";
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

const board: SmtBoard = {
  schema_version: 1,
  board_id: "1234567890abcdef",
  label: "test",
  xy_file_name: "XY.txt",
  xy_version: "2.0",
  xy_units: "mm",
  bbox: { min_x: 0, min_y: 0, max_x: 20, max_y: 10, width: 20, height: 10 },
  source_span: { width: 18, height: 8 },
  placements: [
    { ref: "R1", x_mm: 2, y_mm: 3, rotation: 0, side: "top", footprint: "R0201", status: "placed", material_code: "3101", name: "电阻", model: "100K", description: "", grade: "优选", package: "R0201", reason: "", decision_kind: "", version_change: "none", baseline_material_code: "" },
    { ref: "R2", x_mm: 2, y_mm: 3, rotation: 90, side: "bottom", footprint: "R0201", status: "nc", material_code: "", name: "", model: "", description: "", grade: "", package: "", reason: "未贴", decision_kind: "nc", version_change: "none", baseline_material_code: "" },
  ],
  bom_only: [],
  xy_only: [],
  summary: { total: 2, top: 1, bottom: 1 },
  notices: [],
};

describe("贴片位号视图", () => {
  it("supports comma-separated reference searches", () => {
    expect(parseRefQuery("r1， C2;u3\nR1")).toEqual(["R1", "C2", "U3"]);
  });

  it("renders only the selected board side and labels the mirrored bottom view", () => {
    const { rerender } = render(<BoardCanvas board={board} side="top" mode="placement" selectedRef="" highlightedRefs={[]} onSelect={() => {}} />);
    expect(screen.getByLabelText("R1")).toBeInTheDocument();
    expect(screen.queryByLabelText("R2")).not.toBeInTheDocument();

    rerender(<BoardCanvas board={board} side="bottom" mode="nc" selectedRef="" highlightedRefs={[]} onSelect={() => {}} />);
    expect(screen.getByText(/背面（已镜像）/)).toBeInTheDocument();
    expect(screen.getByLabelText("R2")).toBeInTheDocument();
  });
});
