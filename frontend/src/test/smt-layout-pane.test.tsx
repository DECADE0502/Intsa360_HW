import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";

import { LegacySmtLayoutPane, SmtLayoutPane } from "../tools/SmtLayoutPane";
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

  it("renders the five-stage Chinese assembly-review workflow", () => {
    renderWithProviders(<SmtLayoutPane />);

    expect(screen.getByRole("heading", { name: "SMT 装配审查" })).toBeInTheDocument();
    ["资料", "识别", "配准", "复核", "交付"].forEach((stage) => {
      expect(screen.getByText(stage)).toBeInTheDocument();
    });
  });

  it("keeps internal decision data hidden from the source form", () => {
    renderWithProviders(<SmtLayoutPane />);

    expect(screen.queryByText(/决策清单|语义清单/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/完整选择供应商资料目录/),
    ).toBeInTheDocument();
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
    const fixture = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          "..",
          "tests",
          "fixtures",
          "smt",
          "contracts",
          "analysis_run_v2.json",
        ),
        "utf-8",
      ),
    );
    fixture.state = "needs_confirmation";
    fixture.blocking_reasons = ["请确认坐标覆盖范围和位号图页面。"];
    let treeUploadIndex = 0;
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
      if (path === "/api/upload/tree") {
        treeUploadIndex += 1;
        const folder =
          treeUploadIndex === 1 ? "C:/uploads/smt" : "C:/uploads/netlist";
        const files =
          treeUploadIndex === 1
            ? [
                {
                  name: "XY.txt",
                  relative_path: "SMT/XY.txt",
                  path: "C:/uploads/smt/SMT/XY.txt",
                },
                {
                  name: "assembly.pdf",
                  relative_path: "SMT/assembly.pdf",
                  path: "C:/uploads/smt/SMT/assembly.pdf",
                },
              ]
            : [
                {
                  name: "pstxnet.dat",
                  relative_path: "netlist/pstxnet.dat",
                  path: "C:/uploads/netlist/netlist/pstxnet.dat",
                },
                {
                  name: "pstxprt.dat",
                  relative_path: "netlist/pstxprt.dat",
                  path: "C:/uploads/netlist/netlist/pstxprt.dat",
                },
              ];
        return new Response(
          JSON.stringify({ status: "ok", folder, files }),
          { status: 200 },
        );
      }
      if (path === "/api/upload") {
        return new Response(
          JSON.stringify({
            status: "ok",
            folder: "C:/uploads/bom",
            files: [
              {
                name: "PLM.xlsx",
                path: "C:/uploads/bom/PLM.xlsx",
              },
            ],
          }),
          { status: 200 },
        );
      }
      if (path === "/api/smt-analysis/runs") {
        return new Response(JSON.stringify(fixture), { status: 200 });
      }
      throw new Error(`unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderWithProviders(<SmtLayoutPane />);
    const inputs = Array.from(container.querySelectorAll<HTMLInputElement>('input[type="file"]'));

    const xy = new File(["VERSION=2.0\nUUNITS=MM\n"], "XY.txt");
    Object.defineProperty(xy, "webkitRelativePath", {
      value: "SMT/XY.txt",
    });
    const drawing = new File(["pdf"], "assembly.pdf");
    Object.defineProperty(drawing, "webkitRelativePath", {
      value: "SMT/assembly.pdf",
    });
    const pstxnet = new File(["net"], "pstxnet.dat");
    Object.defineProperty(pstxnet, "webkitRelativePath", {
      value: "netlist/pstxnet.dat",
    });
    const pstxprt = new File(["parts"], "pstxprt.dat");
    Object.defineProperty(pstxprt, "webkitRelativePath", {
      value: "netlist/pstxprt.dat",
    });
    await user.upload(inputs[0], [xy, drawing]);
    await user.upload(inputs[1], new File(["bom"], "PLM.xlsx"));
    await user.upload(inputs[2], [pstxnet, pstxprt]);
    await user.click(screen.getByRole("button", { name: "扫描并识别资料" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/smt-analysis/runs",
        expect.anything(),
      ),
    );
    const runCall = fetchMock.mock.calls.find(
      ([input]) => String(input) === "/api/smt-analysis/runs",
    );
    expect(JSON.parse(String((runCall?.[1] as RequestInit | undefined)?.body))).toEqual({
      smt_folder: "C:/uploads/smt",
      processed_bom: "C:/uploads/bom/PLM.xlsx",
      netlist_folder: "C:/uploads/netlist",
    });
    expect((await screen.findAllByText("位号图页面")).length).toBeGreaterThan(0);
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
    const { container } = renderWithProviders(<LegacySmtLayoutPane />);

    expect(container.querySelector('[data-ref="R1"]')).toBeInTheDocument();
    const smtInput = container.querySelectorAll<HTMLInputElement>('input[type="file"]')[0];
    await user.upload(smtInput, new File(["VERSION=2.0\nUUNITS=MM\n"], "XY.txt"));

    expect(container.querySelector('[data-ref="R1"]')).not.toBeInTheDocument();
    expect(screen.getByText("完成分析后在此查看 NC 布局")).toBeInTheDocument();
  });

  it("generates and exposes the verified delivery package", async () => {
    const user = userEvent.setup();
    const fixture = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          "..",
          "tests",
          "fixtures",
          "smt",
          "contracts",
          "analysis_run_v2.json",
        ),
        "utf-8",
      ),
    );
    fixture.state = "deliver";
    fixture.summary.blocking_count = 0;
    fixture.summary.unresolved_count = 0;
    fixture.blocking_reasons = [];
    window.localStorage.setItem(
      "insta360_hw_tool_workspace:smt_analysis",
      JSON.stringify({
        __v: 2,
        saved_at: Date.now(),
        data: {
          schemaVersion: 2,
          runId: fixture.run_id,
          stage: "deliver",
          historyBom: "",
          historyDecisionManifest: "",
          historySemanticManifest: "",
          sourceLabel: "SMT",
          bomLabel: "PLM.xlsx",
          netlistLabel: "",
        },
      }),
    );
    const exportHandler = vi.fn(() =>
      HttpResponse.json({
            status: "ok",
            run_id: fixture.run_id,
            snapshot_fingerprint: "f".repeat(64),
            generated_at: "2026-07-30T00:00:00Z",
            package_path: "SMT审查/SMT装配审查交付包.zip",
            package_sha256: "e".repeat(64),
            artifacts: [
              {
                label: "SMT装配审查报告",
                path: "SMT审查/SMT装配审查报告.xlsx",
                media_type:
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                size: 100,
                sha256: "d".repeat(64),
              },
            ],
          }),
    );
    server.use(
      http.get(
        `/api/smt-analysis/runs/${fixture.run_id}`,
        () => HttpResponse.json(fixture),
      ),
      http.get(
        "/api/session",
        () =>
          HttpResponse.json({
            status: "ok",
            token: "delivery-session",
          }),
      ),
      http.post(
        `/api/smt-analysis/runs/${fixture.run_id}/export`,
        exportHandler,
      ),
    );
    renderWithProviders(<SmtLayoutPane />);

    expect(
      await screen.findByText("装配审查已完成"),
    ).toBeInTheDocument();
    const generate = screen.getByRole("button", { name: "生成交付包" });
    await waitFor(() => {
      expect(generate).not.toBeDisabled();
      expect(generate).not.toHaveClass("ant-btn-loading");
    });
    await user.click(generate);
    await waitFor(() => expect(exportHandler).toHaveBeenCalledTimes(1));

    const download = (await screen.findByText("下载交付包")).closest("a");
    expect(download).not.toBeNull();
    expect(download).toHaveAttribute(
      "href",
      "/outputs/SMT%E5%AE%A1%E6%9F%A5/SMT%E8%A3%85%E9%85%8D%E5%AE%A1%E6%9F%A5%E4%BA%A4%E4%BB%98%E5%8C%85.zip",
    );
    expect(screen.getByText("SMT装配审查报告")).toBeInTheDocument();
  });
});
