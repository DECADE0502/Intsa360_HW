import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { SmtLayoutResponse } from "../api/client";
import { LegacySmtLayoutPane } from "../tools/SmtLayoutPane";
import { renderWithProviders } from "./render";


const headers = ["位号", "面", "X(mm)", "Y(mm)", "封装", "应贴料号", "应贴型号", "应贴描述", "优选等级", "QC", "备注"];
const result: SmtLayoutResponse = {
  status: "ok",
  tool: "smt_layout",
  outputs: ["C:/runtime/data/outputs/smt/首件核对表_BOARD_A.xlsx"],
  board: {
    outline_rings: [[[0, 0], [100, 0], [100, 80], [0, 80]]],
    bbox_mm: [0, 0, 100, 80],
    source: "dxf",
  },
  components: [],
  nc_summary: {
    total: 0,
    refs: [],
    confirmed_refs: [],
    candidate_refs: [],
    unverified_refs: [],
    conflict_refs: [],
    non_nc_refs: [],
    inference_mode: "without_netlist",
    decision_manifest_used: false,
    explicit_summary_used: false,
  },
  sanity: { status: "skipped_no_netlist" },
  fai_table: {
    headers,
    rows: [
      ["R1", "正面", 10, 20, "R0402", "PN-1", "10K", "Resistor", "优选", "", ""],
      ["R2", "正面", 12, 22, "R0402", "PN-2", "20K", "Resistor", "限制使用", "", "⚠ 等级"],
      ["B1", "背面", 30, 40, "BGA", "PN-3", "DDR", "Memory", "正常", "", ""],
    ],
  },
  summary: { total_components: 3, top_count: 2, bottom_count: 1, nc_count: 0, high_risk_count: 1 },
};

function renderPane() {
  window.localStorage.setItem(
    "insta360_hw_tool_workspace:smt_layout",
    JSON.stringify({
      __v: 2,
      saved_at: Date.now(),
      data: { smt: "C:/smt", bom: "C:/bom.xlsx", netlist: "", result, activeTab: "fai" },
    }),
  );
  return renderWithProviders(<LegacySmtLayoutPane />);
}


describe("SMT layout FAI tab", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the expected headers and every FAI row", () => {
    const { container } = renderPane();

    headers.forEach((header) => expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument());
    expect(container.querySelectorAll('[data-testid^="fai-row-"]')).toHaveLength(3);
  });

  it("updates the row count after filtering by side", async () => {
    const user = userEvent.setup();
    const { container } = renderPane();

    await user.click(within(screen.getByLabelText("首件表面别筛选")).getByText("正面"));

    await waitFor(() => expect(container.querySelectorAll('[data-testid^="fai-row-"]')).toHaveLength(2));
    expect(screen.queryByText("B1")).not.toBeInTheDocument();
  });

  it("marks warning rows with a distinct background class", () => {
    const { container } = renderPane();

    expect(container.querySelector('[data-row-ref="R2"]')?.getAttribute("class")).toContain("smt-fai-row--warn");
    expect(container.querySelector('[data-row-ref="R1"]')?.getAttribute("class")).not.toContain("smt-fai-row--warn");
  });

  it("links the download button to the generated xlsx output", () => {
    renderPane();

    expect(screen.getByRole("link", { name: "下载 XLSX" })).toHaveAttribute(
      "href",
      "/outputs/smt/%E9%A6%96%E4%BB%B6%E6%A0%B8%E5%AF%B9%E8%A1%A8_BOARD_A.xlsx",
    );
  });

  it("defines an A3 landscape print stylesheet", () => {
    const css = readFileSync(resolve(process.cwd(), "src", "tools", "SmtLayoutPane.module.css"), "utf-8");

    expect(css).toContain("@media print");
    expect(css).toMatch(/@page\s*{[^}]*size:\s*A3 landscape/s);
  });
});
