import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { SmtComponent, SmtLayoutResponse } from "../api/client";
import { SmtLayoutPane } from "../tools/SmtLayoutPane";
import { renderWithProviders } from "./render";


function component(
  ref: string,
  x_mm: number,
  y_mm: number,
  side: "top" | "bottom",
  overrides: Partial<SmtComponent> = {},
): SmtComponent {
  return {
    ref,
    x_mm,
    y_mm,
    rotation: 0,
    side,
    footprint: "R0402",
    part_number: `PN-${ref}`,
    description: `器件 ${ref}`,
    model: "10K",
    grade: "优选",
    status: "nc",
    high_risk: false,
    ...overrides,
  };
}

const result: SmtLayoutResponse = {
  status: "ok",
  tool: "smt_layout",
  outputs: ["C:/outputs/首件核对表.xlsx"],
  board: {
    outline_rings: [[[0, 0], [100, 0], [100, 80], [0, 80]]],
    bbox_mm: [0, 0, 100, 80],
    source: "dxf",
  },
  components: [
    component("R1", 10, 20, "top"),
    component("SH1", 70, 50, "bottom", { status: "candidate_nc", high_risk: true }),
    component("U9", 55, 60, "top", { status: "unverified" }),
    component("C1", 40, 35, "top", { status: "installed" }),
  ],
  nc_summary: {
    total: 2,
    refs: ["R1", "SH1"],
    confirmed_refs: ["R1"],
    candidate_refs: ["SH1"],
    unverified_refs: ["U9"],
    conflict_refs: [],
    inference_mode: "with_netlist",
    explicit_summary_used: false,
  },
  sanity: { status: "skipped_no_netlist" },
  fai_table: { headers: [], rows: [] },
  summary: { total_components: 4, top_count: 3, bottom_count: 1, nc_count: 2, high_risk_count: 1 },
};

function seedWorkspace() {
  window.localStorage.setItem(
    "insta360_hw_tool_workspace:smt_layout",
    JSON.stringify({
      __v: 2,
      saved_at: Date.now(),
      data: {
        smt: "C:/project/smt",
        bom: "C:/project/bom.xlsx",
        netlist: "",
        result,
        activeTab: "nc",
      },
    }),
  );
}

function renderPane() {
  seedWorkspace();
  return renderWithProviders(<SmtLayoutPane />);
}

function mockCanvasRect(svg: SVGSVGElement) {
  vi.spyOn(svg, "getBoundingClientRect").mockReturnValue({
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    right: 1100,
    bottom: 880,
    width: 1100,
    height: 880,
    toJSON: () => ({}),
  });
}


describe("SMT layout NC tab", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("shows every NC ref from the payload", () => {
    renderPane();

    expect(screen.getByTestId("nc-row-R1")).toBeInTheDocument();
    expect(screen.getByTestId("nc-row-SH1")).toBeInTheDocument();
    expect(screen.queryByTestId("nc-row-U9")).not.toBeInTheDocument();
    expect(screen.getByTestId("nc-row-R1")).toHaveTextContent("确定 NC");
    expect(screen.getByTestId("nc-row-SH1")).toHaveTextContent("候选 NC");
    expect(screen.getByText("网表已交叉验证")).toBeInTheDocument();
  });

  it("shows XY-only anomalies under the unverified evidence filter", async () => {
    const user = userEvent.setup();
    renderPane();

    await user.click(screen.getByText("待确认", { selector: ".ant-segmented-item-label" }));

    expect(screen.getByTestId("nc-row-U9")).toHaveTextContent("待确认");
    expect(screen.queryByTestId("nc-row-R1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nc-row-SH1")).not.toBeInTheDocument();
  });

  it("highlights the canvas component while hovering its NC row", async () => {
    const user = userEvent.setup();
    const { container } = renderPane();

    await user.hover(screen.getByTestId("nc-row-R1"));

    expect(container.querySelector('[data-ref="R1"]')?.getAttribute("class")).toContain("pcb-comp--highlight");
  });

  it("selects the corresponding NC row after a canvas click", async () => {
    const { container } = renderPane();

    fireEvent.click(container.querySelector('[data-ref="R1"]')!);

    await waitFor(() => expect(screen.getByTestId("nc-row-R1")).toHaveAttribute("data-selected", "true"));
  });

  it("filters the NC list to refs inside a canvas frame", async () => {
    const { container } = renderPane();
    const svg = container.querySelector<SVGSVGElement>('svg[aria-label="PCB 布局视图"]')!;
    mockCanvasRect(svg);

    fireEvent.mouseDown(svg, { button: 0, clientX: 100, clientY: 200 });
    fireEvent.mouseMove(svg, { clientX: 200, clientY: 300 });
    fireEvent.mouseUp(svg, { button: 0, clientX: 200, clientY: 300 });

    await waitFor(() => expect(screen.queryByTestId("nc-row-SH1")).not.toBeInTheDocument());
    expect(screen.getByTestId("nc-row-R1")).toBeInTheDocument();
    expect(screen.getByText("框选 1 项")).toBeInTheDocument();
  });

  it("hides bottom components after switching to the top side", async () => {
    const user = userEvent.setup();
    const { container } = renderPane();

    await user.click(screen.getByTitle("正面"));

    expect(container.querySelector('[data-ref="R1"]')).toBeInTheDocument();
    expect(container.querySelector('[data-ref="SH1"]')).not.toBeInTheDocument();
  });

  it("shows only SH refs when the SH layer is enabled", async () => {
    const user = userEvent.setup();
    const { container } = renderPane();

    await user.click(screen.getByRole("switch", { name: "仅显示 SH 位号" }));

    expect(screen.queryByTestId("nc-row-R1")).not.toBeInTheDocument();
    expect(screen.getByTestId("nc-row-SH1")).toBeInTheDocument();
    expect(container.querySelector('[data-ref="R1"]')).not.toBeInTheDocument();
    expect(container.querySelector('[data-ref="SH1"]')).toBeInTheDocument();
  });
});
