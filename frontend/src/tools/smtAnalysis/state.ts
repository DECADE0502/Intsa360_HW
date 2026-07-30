import type { SmtAnalysisRunResponse, SmtRunState } from "./types";


export type SmtWorkflowStage =
  | "source"
  | "identify"
  | "register"
  | "review"
  | "deliver";

export type SmtAnalysisWorkspace = {
  schemaVersion: 2;
  runId: string;
  stage: SmtWorkflowStage;
  historyBom: string;
  historyDecisionManifest: string;
  historySemanticManifest: string;
  sourceLabel: string;
  bomLabel: string;
  netlistLabel: string;
};

export const EMPTY_SMT_WORKSPACE: SmtAnalysisWorkspace = {
  schemaVersion: 2,
  runId: "",
  stage: "source",
  historyBom: "",
  historyDecisionManifest: "",
  historySemanticManifest: "",
  sourceLabel: "",
  bomLabel: "",
  netlistLabel: "",
};

const STAGE_BY_STATE: Record<SmtRunState, SmtWorkflowStage> = {
  source: "source",
  identifying: "identify",
  needs_confirmation: "identify",
  needs_calibration: "register",
  review: "review",
  deliver: "deliver",
  failed: "source",
};

export function stageForRun(
  run: Pick<SmtAnalysisRunResponse, "state">,
): SmtWorkflowStage {
  return STAGE_BY_STATE[run.state];
}

export function workspaceWithRun(
  current: SmtAnalysisWorkspace,
  run: SmtAnalysisRunResponse,
): SmtAnalysisWorkspace {
  return {
    ...current,
    runId: run.run_id,
    stage: stageForRun(run),
  };
}

export function invalidateSmtWorkspace(
  current: SmtAnalysisWorkspace,
): SmtAnalysisWorkspace {
  return {
    ...current,
    runId: "",
    stage: "source",
  };
}

export function migrateSmtWorkspace(raw: unknown): SmtAnalysisWorkspace {
  if (!raw || typeof raw !== "object") return { ...EMPTY_SMT_WORKSPACE };
  const candidate = raw as Record<string, unknown>;
  const current =
    candidate.schemaVersion === 2 && typeof candidate.runId === "string";
  if (current) {
    const stage = candidate.stage;
    return {
      ...EMPTY_SMT_WORKSPACE,
      ...candidate,
      stage:
        stage === "source" ||
        stage === "identify" ||
        stage === "register" ||
        stage === "review" ||
        stage === "deliver"
          ? stage
          : "source",
    } as SmtAnalysisWorkspace;
  }
  return {
    ...EMPTY_SMT_WORKSPACE,
    historyBom:
      typeof candidate.historyBom === "string" ? candidate.historyBom : "",
    historyDecisionManifest:
      typeof candidate.historyDecisionManifest === "string"
        ? candidate.historyDecisionManifest
        : "",
    historySemanticManifest:
      typeof candidate.historySemanticManifest === "string"
        ? candidate.historySemanticManifest
        : "",
  };
}
