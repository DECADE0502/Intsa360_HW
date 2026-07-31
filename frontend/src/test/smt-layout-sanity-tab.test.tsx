import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import type { SmtComponent, SmtLayoutResponse, SmtSanity } from "../api/client";
import { LegacySmtLayoutPane } from "../tools/SmtLayoutPane";
import { renderWithProviders } from "./render";


function component(ref: string, x_mm: number, y_mm: number, status: SmtComponent["status"] = "installed"): SmtComponent {
  return {
    ref,
    x_mm,
    y_mm,
    rotation: 0,
    side: "top",
    footprint: "R0402",
    part_number: `PN-${ref}`,
    description: `器件 ${ref}`,
    model: "10K",
    grade: "优选",
    status,
    high_risk: false,
  };
}

const findings: SmtSanity = {
  missing_layout: [
    { ref: "R2", note: "低优先级示例", severity: "low" },
    { ref: "R10", note: "高优先级示例", severity: "high" },
  ],
  missing_bom: [{ ref: "R1", note: "布局有但 BOM 无", severity: "high" }],
  missing_netlist: [{ ref: "C1", note: "布局有但网表无", severity: "medium" }],
  footprint_conflicts: [
    {
      ref: "U1",
      xy_footprint: "BGA153",
      netlist_footprint: "BGA169",
      bom_footprint: "BGA153",
      note: "XY 与网表封装不一致",
    },
  ],
};

function makeResult(sanity: SmtSanity = findings): SmtLayoutResponse {
  return {
    status: "ok",
    tool: "smt_layout",
    outputs: [],
    board: {
      outline_rings: [[[0, 0], [100, 0], [100, 80], [0, 80]]],
      bbox_mm: [0, 0, 100, 80],
      source: "dxf",
    },
    components: [
      component("R1", 10, 20, "missing_bom"),
      component("C1", 30, 30),
      component("U1", 60, 45),
    ],
    nc_summary: {
      total: 0,
      refs: [],
      confirmed_refs: [],
      candidate_refs: [],
      unverified_refs: ["R1"],
      conflict_refs: [],
      non_nc_refs: [],
      inference_mode: "with_netlist",
      decision_manifest_used: false,
      explicit_summary_used: false,
    },
    sanity,
    fai_table: { headers: [], rows: [] },
    summary: { total_components: 3, top_count: 3, bottom_count: 0, nc_count: 0, high_risk_count: 0 },
  };
}

function renderPane(result = makeResult()) {
  window.localStorage.setItem(
    "insta360_hw_tool_workspace:smt_layout",
    JSON.stringify({
      __v: 2,
      saved_at: Date.now(),
      data: { smt: "C:/smt", bom: "C:/bom.xlsx", netlist: "C:/netlist", result, activeTab: "sanity" },
    }),
  );
  return renderWithProviders(<LegacySmtLayoutPane />);
}


describe("SMT layout sanity tab", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("shows four grouped finding lists with counts", () => {
    renderPane();

    expect(screen.getByTestId("sanity-group-missing_layout")).toHaveTextContent("布局缺失");
    expect(screen.getByTestId("sanity-group-missing_layout")).toHaveTextContent("2");
    expect(screen.getByTestId("sanity-group-missing_bom")).toHaveTextContent("BOM 缺失");
    expect(screen.getByTestId("sanity-group-missing_netlist")).toHaveTextContent("网表缺失");
    expect(screen.getByTestId("sanity-group-footprint_conflicts")).toHaveTextContent("封装冲突");
  });

  it("orders high-severity findings before lower-severity findings", () => {
    const { container } = renderPane();

    const refs = Array.from(container.querySelectorAll('[data-sanity-group="missing_layout"]')).map((row) => row.getAttribute("data-ref"));
    expect(refs).toEqual(["R10", "R2"]);
  });

  it("highlights only the current group refs on its mini canvas", () => {
    renderPane();

    const canvas = screen.getByTestId("sanity-canvas-missing_bom");
    expect(canvas.querySelector('[data-ref="R1"]')?.getAttribute("class")).toContain("pcb-comp--highlight");
    expect(canvas.querySelector('[data-ref="U1"]')?.getAttribute("class")).not.toContain("pcb-comp--highlight");
  });

  it("jumps to the NC tab and selects a ref after a finding click", async () => {
    renderPane();

    fireEvent.click(screen.getByTestId("sanity-row-missing_bom-R1"));

    await waitFor(() => expect(screen.getByRole("tab", { name: "NC 布局对照" })).toHaveAttribute("aria-selected", "true"));
    const ncPanel = screen.getByRole("tabpanel");
    expect(within(ncPanel).getByTestId("nc-row-R1")).toHaveAttribute("data-selected", "true");
  });

  it("shows a clear empty state when all three sources agree", () => {
    renderPane(
      makeResult({ missing_layout: [], missing_bom: [], missing_netlist: [], footprint_conflicts: [] }),
    );

    expect(screen.getByText("三方一致，无发现问题")).toBeInTheDocument();
  });
});
