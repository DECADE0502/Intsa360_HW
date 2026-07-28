import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { BomRiskPane } from "../tools/BomRiskPane";
import { renderWithProviders } from "./render";
import { server } from "./server";


const tool = {
  id: "bom_risk_check",
  name: "BOM 风险检查",
  description: "检查单份 BOM 的结构、贴装范围与物料风险。",
  status: "available",
  category: "BOM",
};

const response = {
  status: "ok",
  outputs: ["C:/outputs/BOM风险检查.xlsx"],
  risk_report: {
    profile: "plm_single_board",
    stats: { 数据行: 143, 位号数: 800, 替代组数: 26 },
    counts_by_level: { blocker: 0, warn: 2, info: 5, ok: 14 },
    findings: [
      {
        code: "material_grade",
        name: "物料优选等级",
        level: "warn",
        status: "warn",
        message: "61 项需要核对",
        detail_count: 1,
        details: [{ source_row: 3, code: "MAT-1", refs: "R1", grade: "验证中" }],
      },
      {
        code: "substitute_groups",
        name: "替代组结构",
        level: "info",
        status: "info",
        message: "共 26 个替代组",
        detail_count: 0,
        details: [],
      },
    ],
    grade_flags: [{ code: "MAT-1", refs: "R1", grade: "验证中" }],
    type_flags: [],
    substitute_groups: [{ group_code: "MAT-A", main_code: "MAT-A", alternative_codes: ["MAT-B"] }],
    shield_items: [{ code: "SH-PN", refs: "SH1", subtype: "屏蔽类型待确认" }],
    mechanical_items: [],
    process_items: [],
    nc_items: [],
    version_sensitive: [],
  },
};

describe("BomRiskPane", () => {
  it("uploads a local BOM and presents the structured risk report", async () => {
    let runPayload: Record<string, unknown> | undefined;
    server.use(
      http.get("/api/session", () =>
        HttpResponse.json({ status: "ok", token: "risk-test-session" }),
      ),
      http.post("/api/upload", () =>
        HttpResponse.json({
          status: "ok",
          folder: "C:/uploads/run",
          files: [{ name: "board.xlsx", path: "C:/uploads/run/board.xlsx" }],
        }),
      ),
      http.post("/api/tools/bom_risk_check/run", async ({ request }) => {
        runPayload = await request.json() as Record<string, unknown>;
        return HttpResponse.json(response);
      }),
    );
    const user = userEvent.setup();
    const { container } = renderWithProviders(<BomRiskPane tool={tool} />);
    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(fileInput).not.toBeNull();

    await user.upload(fileInput!, new File(["bom"], "board.xlsx"));
    expect(await screen.findByText("board.xlsx")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /开始风险检查/ }));

    await waitFor(() => expect(runPayload).toEqual({ bom: "C:/uploads/run/board.xlsx" }));
    expect(await screen.findByText("没有阻断项，仍有 1 个风险需要确认")).toBeInTheDocument();
    expect(screen.getByText("plm_single_board")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /替代组 1/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /专项物料 1/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /报告文件 1/ })).toBeInTheDocument();
  });
});
