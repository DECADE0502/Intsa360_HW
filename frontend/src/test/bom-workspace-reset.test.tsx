import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { BomProcessWizard } from "../tools/BomProcessWizard";
import { renderWithProviders } from "./render";
import { server } from "./server";

const STORAGE_KEY = "insta360_hw_tool_workspace:bom_process";

describe("BOM workspace reset", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/?tool=bom_process");
  });

  it("requires shield confirmation again after returning from delivery", async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        __v: 2,
        saved_at: Date.now(),
        data: {
          stage: "deliver",
          sp: "C:/uploads/board.xlsx",
          name: "BOARD",
          pcode: "203010100819",
          pdesc: "",
          fmts: ["plm"],
          extras: [],
          pres: { status: "ok", outputs: ["C:/data/outputs/bom/BOARD.xlsx"], summary: {} },
          rres: { status: "ok", outputs: [] },
          conflictChoices: { "1001": 0 },
          confirmShields: true,
        },
      }),
    );
    let processBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/session", () => HttpResponse.json({ token: "test-session" })),
      http.post("/api/tools/bom_process/run", async ({ request }) => {
        processBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ status: "ok", process_file: "C:/data/outputs/bom/BOARD.xlsx", outputs: [] });
      }),
      http.post("/api/tools/bom_risk_check/run", () =>
        HttpResponse.json({ status: "ok", risk_report: { findings: [] }, outputs: [] }),
      ),
    );
    const user = userEvent.setup();

    renderWithProviders(<BomProcessWizard />);
    await user.click(await screen.findByRole("button", { name: /返回修改并重新处理/ }));
    await user.click(await screen.findByRole("button", { name: /确认无误，开始处理/ }));

    await waitFor(() => expect(processBody).not.toBeNull());
    expect(processBody).not.toHaveProperty("confirm_shields", true);
  });

  it("treats an explicit Cadence source launch as new even when the path is unchanged", async () => {
    const source = "C:/uploads/board.xlsx";
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        __v: 2,
        saved_at: Date.now(),
        data: {
          stage: "deliver",
          sp: source,
          name: "OLD_BOARD",
          pcode: "203010100819",
          pdesc: "",
          fmts: ["plm"],
          extras: [],
          pres: { status: "ok", process_file: "C:/outputs/old.xlsx", outputs: ["C:/outputs/old.xlsx"] },
          rres: { status: "ok", source_file: "C:/outputs/old.xlsx", outputs: [] },
          conflictChoices: { OLD: 0 },
          placementResolutions: { old: { action: "exclude" } },
          placementVisitedTabs: ["insufficient_data"],
        },
      }),
    );
    window.history.replaceState(
      {},
      "",
      `/?tool=bom_process&source=${encodeURIComponent(source)}&name=NEW_BOARD`,
    );
    let processBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/session", () => HttpResponse.json({ token: "test-session" })),
      http.post("/api/tools/bom_process/run", async ({ request }) => {
        processBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          status: "needs_confirmation",
          reason: "placement_review",
          groups: [],
          readonly_nc: { count: 0, items: [] },
          summary: {},
        });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<BomProcessWizard />);
    await user.click(await screen.findByRole("button", { name: /确认无误，开始处理/ }));

    await waitFor(() => expect(processBody).not.toBeNull());
    const submitted = processBody as unknown as Record<string, unknown>;
    expect(submitted.source_bom).toBe(source);
    expect(submitted.name).toBe("NEW_BOARD");
    expect(submitted.placement_resolutions).toEqual({});
  });

  it("reruns risk review for the newly generated BOM after returning to modify", async () => {
    const oldBom = "C:/outputs/board_old.xlsx";
    const newBom = "C:/outputs/board_new.xlsx";
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        __v: 2,
        saved_at: Date.now(),
        data: {
          stage: "risk",
          sp: "C:/uploads/board.xlsx",
          name: "BOARD",
          pcode: "203010100819",
          pdesc: "",
          fmts: ["plm"],
          extras: [],
          pres: { status: "ok", process_file: oldBom, outputs: [oldBom], summary: {}, preview: { headers: [], rows: [] } },
          rres: {
            status: "ok",
            source_file: oldBom,
            risk_report: { source_file: oldBom, findings: [], grade_flags: [], type_flags: [] },
            outputs: [],
          },
          conflictChoices: {},
          placementResolutions: {},
          placementVisitedTabs: [],
        },
      }),
    );
    let riskBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/session", () => HttpResponse.json({ token: "test-session" })),
      http.post("/api/tools/bom_process/run", () => HttpResponse.json({
        status: "ok",
        process_file: newBom,
        outputs: [newBom],
        summary: {},
        preview: { headers: [], rows: [] },
      })),
      http.post("/api/tools/bom_risk_check/run", async ({ request }) => {
        riskBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          status: "ok",
          source_file: newBom,
          risk_report: { source_file: newBom, findings: [], grade_flags: [], type_flags: [] },
          outputs: [],
        });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<BomProcessWizard />);
    await user.click(await screen.findByRole("button", { name: "返回上一步" }));
    await user.click(await screen.findByRole("button", { name: "返回修改" }));
    await user.click(await screen.findByRole("button", { name: /确认无误，开始处理/ }));

    await waitFor(() => expect(riskBody?.bom).toBe(newBom));
  });

  it("persists only high-confidence conflict recommendations and leaves manual conflicts unresolved", async () => {
    const processedBom = "C:/outputs/board_merged.xlsx";
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
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
              { code: "P1", recommended_index: 1, high_confidence: true, variants: [{}, {}] },
              { code: "P2", recommended_index: 0, high_confidence: false, variants: [{}, {}] },
            ],
            summary: {},
          },
          rres: null,
          conflictChoices: {},
          placementResolutions: {},
          placementVisitedTabs: [],
        },
      }),
    );
    server.use(
      http.get("/api/session", () => HttpResponse.json({ token: "test-session" })),
      http.post("/api/tools/bom_process/run", () => HttpResponse.json({
        status: "ok",
        process_file: processedBom,
        outputs: [processedBom],
        summary: {},
        preview: { headers: [], rows: [] },
      })),
      http.post("/api/tools/bom_risk_check/run", () => HttpResponse.json({
        status: "ok",
        source_file: processedBom,
        risk_report: { source_file: processedBom, findings: [], grade_flags: [], type_flags: [] },
        outputs: [],
      })),
    );
    const user = userEvent.setup();

    renderWithProviders(<BomProcessWizard />);
    await user.click(await screen.findByRole("button", { name: "一键采用安全推荐" }));

    await waitFor(() => {
      const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
      expect(saved.data?.conflictChoices).toEqual({
        P1: { action: "select_variant", variant_index: 1 },
      });
    }, { timeout: 3000 });
  });
});
