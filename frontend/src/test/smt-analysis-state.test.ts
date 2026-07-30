import { describe, expect, it } from "vitest";

import {
  EMPTY_SMT_WORKSPACE,
  invalidateSmtWorkspace,
  migrateSmtWorkspace,
  stageForRun,
  workspaceWithRun,
} from "../tools/smtAnalysis/state";
import type { SmtAnalysisRunResponse } from "../tools/smtAnalysis/types";


describe("SMT analysis workspace state", () => {
  it("maps backend states to explicit workflow stages", () => {
    expect(stageForRun({ state: "needs_confirmation" })).toBe("identify");
    expect(stageForRun({ state: "needs_calibration" })).toBe("register");
    expect(stageForRun({ state: "review" })).toBe("review");
    expect(stageForRun({ state: "deliver" })).toBe("deliver");
  });

  it("keeps only reusable inputs from a legacy grey-board workspace", () => {
    const migrated = migrateSmtWorkspace({
      historyBom: "C:/data/board.xlsx",
      historyDecisionManifest: "C:/data/decision.json",
      result: { board: { source: "component_bbox" } },
      activeTab: "nc",
    });

    expect(migrated.runId).toBe("");
    expect(migrated.stage).toBe("source");
    expect(migrated.historyBom).toBe("C:/data/board.xlsx");
    expect(migrated).not.toHaveProperty("result");
  });

  it("invalidating an input cannot leave a later-stage run active", () => {
    const run = {
      run_id: "run-1",
      state: "review",
    } as SmtAnalysisRunResponse;
    const active = workspaceWithRun(EMPTY_SMT_WORKSPACE, run);

    expect(invalidateSmtWorkspace(active)).toEqual({
      ...EMPTY_SMT_WORKSPACE,
      runId: "",
      stage: "source",
    });
  });
});
