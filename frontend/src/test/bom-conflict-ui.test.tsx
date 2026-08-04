import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { BomProcessWizard } from "../tools/BomProcessWizard";
import { renderWithProviders } from "./render";
import { server } from "./server";

const STORAGE_KEY = "insta360_hw_tool_workspace:bom_process";

describe("BOM conflict workbench", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/?tool=bom_process");
  });

  it("submits an explicit split-by-reference decision with unique replacement codes", async () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
      __v: 2,
      saved_at: Date.now(),
      data: {
        stage: "process",
        sp: "C:/uploads/board.xlsx",
        name: "BOARD",
        pcode: "203010100819",
        pdesc: "",
        fmts: ["plm"],
        extras: [],
        pres: {
          status: "needs_confirmation",
          reason: "part_property_conflicts",
          conflicts: [{
            code: "MAT-1",
            reason: "numeric_or_version_conflict",
            recommended_index: null,
            high_confidence: false,
            variants: [
              { name: "电阻", model: "R0402-A", desc: "10K", refs: ["R1"], count: 1 },
              { name: "电阻", model: "R0402-B", desc: "22K", refs: ["R2"], count: 1 },
            ],
          }],
          summary: {},
        },
        rres: null,
        conflictChoices: {},
        placementResolutions: {},
      },
    }));
    let submitted: Record<string, any> | null = null;
    server.use(
      http.get("/api/session", () => HttpResponse.json({ token: "test-session" })),
      http.post("/api/tools/bom_process/run", async ({ request }) => {
        submitted = await request.json() as Record<string, any>;
        return HttpResponse.json({
          status: "ok",
          process_file: "C:/outputs/board.xlsx",
          outputs: ["C:/outputs/board.xlsx"],
          summary: {},
          preview: { headers: [], rows: [] },
        });
      }),
      http.post("/api/tools/bom_risk_check/run", () => HttpResponse.json({
        status: "ok",
        source_file: "C:/outputs/board.xlsx",
        risk_report: { findings: [], grade_flags: [], type_flags: [] },
        outputs: [],
      })),
    );
    const user = userEvent.setup();
    renderWithProviders(<BomProcessWizard />);

    const continueButton = await screen.findByRole("button", { name: "按全部决议继续处理" });
    expect(continueButton).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "按位号拆组并改码" }));
    await user.type(screen.getByRole("textbox", { name: "候选 1 新料号" }), "MAT-1-A");
    await user.type(screen.getByRole("textbox", { name: "候选 2 新料号" }), "MAT-1-B");
    await waitFor(() => expect(continueButton).toBeEnabled());
    await user.click(continueButton);

    await waitFor(() => {
      expect(submitted).not.toBeNull();
      expect((submitted as Record<string, any>).conflict_choices).toEqual({
        "MAT-1": {
          action: "split_refs",
          assignments: [
            { variant_index: 0, part_number: "MAT-1-A" },
            { variant_index: 1, part_number: "MAT-1-B" },
          ],
        },
      });
    });
  });

  it("submits the first candidate for every conflict after one explicit confirmation", async () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
      __v: 2,
      saved_at: Date.now(),
      data: {
        stage: "process",
        sp: "C:/uploads/board.xlsx",
        name: "BOARD",
        pcode: "203010100819",
        pdesc: "",
        fmts: ["plm"],
        extras: [],
        pres: {
          status: "needs_confirmation",
          reason: "part_property_conflicts",
          conflicts: [
            { code: "MAT-1", high_confidence: false, variants: [{ name: "候选一" }, { name: "候选二" }] },
            { code: "MAT-2", high_confidence: false, variants: [{ name: "候选甲" }, { name: "候选乙" }] },
          ],
          summary: {},
        },
        rres: null,
        conflictChoices: {},
        placementResolutions: {},
      },
    }));
    let submitted: Record<string, any> | null = null;
    server.use(
      http.get("/api/session", () => HttpResponse.json({ token: "test-session" })),
      http.post("/api/tools/bom_process/run", async ({ request }) => {
        submitted = await request.json() as Record<string, any>;
        return HttpResponse.json({
          status: "ok",
          process_file: "C:/outputs/board.xlsx",
          outputs: ["C:/outputs/board.xlsx"],
          summary: {},
          preview: { headers: [], rows: [] },
        });
      }),
      http.post("/api/tools/bom_risk_check/run", () => HttpResponse.json({
        status: "ok",
        source_file: "C:/outputs/board.xlsx",
        risk_report: { findings: [], grade_flags: [], type_flags: [] },
        outputs: [],
      })),
    );
    const user = userEvent.setup();
    renderWithProviders(<BomProcessWizard />);

    await user.click(await screen.findByRole("button", { name: "一键合并为第一候选" }));
    await user.click(await screen.findByRole("button", { name: "确认合并" }));

    await waitFor(() => expect((submitted as Record<string, any> | null)?.conflict_choices).toEqual({
      "MAT-1": { action: "select_variant", variant_index: 0 },
      "MAT-2": { action: "select_variant", variant_index: 0 },
    }));
  });
});
