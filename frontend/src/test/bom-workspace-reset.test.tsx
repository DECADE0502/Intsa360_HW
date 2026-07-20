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
});
