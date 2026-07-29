import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";

import { SmtLayoutPane } from "../tools/SmtLayoutPane";
import { renderWithProviders } from "./render";
import { server } from "./server";


describe("SMT layout pane skeleton", () => {
  beforeEach(() => {
    window.localStorage.clear();
    server.use(
      http.get("/api/assets", () => HttpResponse.json({
        status: "ok",
        groups: { processed_bom: [] },
        summary: { processed_bom: 0 },
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the three Chinese workflow tabs", () => {
    renderWithProviders(<SmtLayoutPane />);

    expect(screen.getByRole("tab", { name: "NC 布局对照" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "首件核对表" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "三向一致性" })).toBeInTheDocument();
  });

  it("disables the sanity tab and explains the missing netlist", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SmtLayoutPane />);

    const sanityTab = screen.getByRole("tab", { name: "三向一致性" });
    expect(sanityTab).toHaveAttribute("aria-disabled", "true");
    await user.hover(screen.getByText("三向一致性"));
    expect(await screen.findByText("需网表文件夹")).toBeInTheDocument();
  });

  it("persists the result as a v2 heavy workspace key", () => {
    const source = readFileSync(resolve(process.cwd(), "src", "tools", "SmtLayoutPane.tsx"), "utf-8");

    expect(source).toContain('{ heavyKeys: ["result"] }');
  });

  it("uses native file and folder selection instead of editable path fields", () => {
    const { container } = renderWithProviders(<SmtLayoutPane />);

    expect(screen.getByRole("button", { name: "选择 SMT 资料目录" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择 PLM/OA BOM" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择网表目录" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /决策清单|语义清单/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "SMT 资料文件夹" })).not.toBeInTheDocument();
    expect(container.querySelectorAll('input[type="file"]')).toHaveLength(3);
  });

  it("uploads selected sources and runs with server-side paths", async () => {
    const user = userEvent.setup();
    let uploadIndex = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/session") {
        return new Response(JSON.stringify({ status: "ok", token: "session-smt-picker" }), { status: 200 });
      }
      if (path === "/api/assets") {
        return new Response(
          JSON.stringify({ status: "ok", groups: { processed_bom: [] }, summary: { processed_bom: 0 } }),
          { status: 200 },
        );
      }
      if (path === "/api/upload") {
        uploadIndex += 1;
        const folders = ["C:/uploads/smt", "C:/uploads/bom", "C:/uploads/netlist"];
        const files = [
          [{ name: "XY.txt", path: "C:/uploads/smt/XY.txt" }],
          [{ name: "PLM.xlsx", path: "C:/uploads/bom/PLM.xlsx" }],
          [
            { name: "pstxnet.dat", path: "C:/uploads/netlist/pstxnet.dat" },
            { name: "pstxprt.dat", path: "C:/uploads/netlist/pstxprt.dat" },
          ],
        ];
        return new Response(
          JSON.stringify({ status: "ok", folder: folders[uploadIndex - 1], files: files[uploadIndex - 1] }),
          { status: 200 },
        );
      }
      if (path === "/api/tools/smt_layout/run") {
        return new Response(
          JSON.stringify({
            status: "ok",
            tool: "smt_layout",
            outputs: [],
            board: { outline_rings: [[[0, 0], [10, 0], [10, 10], [0, 10]]], bbox_mm: [0, 0, 10, 10], source: "dxf" },
            components: [],
            nc_summary: { total: 0, refs: [] },
            sanity: { missing_layout: [], missing_bom: [], missing_netlist: [], footprint_conflicts: [] },
            fai_table: { headers: [], rows: [] },
            summary: { total_components: 0, top_count: 0, bottom_count: 0, nc_count: 0, high_risk_count: 0 },
          }),
          { status: 200 },
        );
      }
      throw new Error(`unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderWithProviders(<SmtLayoutPane />);
    const inputs = Array.from(container.querySelectorAll<HTMLInputElement>('input[type="file"]'));

    await user.upload(inputs[0], [new File(["VERSION=2.0\nUUNITS=MM\n"], "XY.txt"), new File(["dxf"], "outline.dxf")]);
    await user.upload(inputs[1], new File(["bom"], "PLM.xlsx"));
    await user.upload(inputs[2], [new File(["net"], "pstxnet.dat"), new File(["parts"], "pstxprt.dat")]);
    await user.click(screen.getByRole("button", { name: "开始分析" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/tools/smt_layout/run", expect.anything()));
    const runCall = fetchMock.mock.calls.find(([input]) => String(input) === "/api/tools/smt_layout/run");
    expect(JSON.parse(String((runCall?.[1] as RequestInit | undefined)?.body))).toEqual({
      smt_folder: "C:/uploads/smt",
      processed_bom: "C:/uploads/bom/PLM.xlsx",
      netlist_folder: "C:/uploads/netlist",
    });
  });

  it("invalidates a displayed result when the SMT source changes", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(
      "insta360_hw_tool_workspace:smt_layout",
      JSON.stringify({
        __v: 2,
        saved_at: Date.now(),
        data: {
          historyBom: "",
          historyDecisionManifest: "",
          historySemanticManifest: "",
          activeTab: "nc",
          result: {
            status: "ok",
            tool: "smt_layout",
            outputs: [],
            board: { outline_rings: [[[0, 0], [10, 0], [10, 10], [0, 10]]], bbox_mm: [0, 0, 10, 10], source: "dxf" },
            components: [{
              ref: "R1",
              x_mm: 5,
              y_mm: 5,
              rotation: 0,
              side: "top",
              footprint: "R0201",
              part_number: "PN1",
              description: "",
              model: "",
              grade: "",
              status: "installed",
              high_risk: false,
            }],
            nc_summary: { total: 0, refs: [] },
            sanity: { status: "skipped_no_netlist" },
            fai_table: { headers: [], rows: [] },
            summary: { total_components: 1, top_count: 1, bottom_count: 0, nc_count: 0, high_risk_count: 0 },
          },
        },
      }),
    );
    const { container } = renderWithProviders(<SmtLayoutPane />);

    expect(container.querySelector('[data-ref="R1"]')).toBeInTheDocument();
    const smtInput = container.querySelectorAll<HTMLInputElement>('input[type="file"]')[0];
    await user.upload(smtInput, new File(["VERSION=2.0\nUUNITS=MM\n"], "XY.txt"));

    expect(container.querySelector('[data-ref="R1"]')).not.toBeInTheDocument();
    expect(screen.getByText("完成分析后在此查看 NC 布局")).toBeInTheDocument();
  });
});
