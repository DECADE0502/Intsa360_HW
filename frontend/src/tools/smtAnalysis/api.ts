import { apiCall } from "../../api/client";
import type {
  SmtAnalysisRunResponse,
  SmtBoardSide,
  SmtCoordinateScope,
  SmtPlacementRole,
  SmtRegistrationAnchor,
} from "./types";


export type UploadedTree = {
  folder: string;
  files: Array<{
    name: string;
    relative_path: string;
    path: string;
  }>;
};

export type StartSmtAnalysisInput = {
  smt_folder: string;
  processed_bom: string;
  netlist_folder?: string;
  decision_manifest?: string;
  semantic_manifest?: string;
};

export type SourceConfirmationInput = {
  coordinate_set_id: string;
  scope_semantics: SmtCoordinateScope;
  pages: Record<string, SmtBoardSide>;
  unit?: "mm" | "mil" | "inch";
  side_mapping?: Record<string, SmtBoardSide>;
};

export type RegistrationInput = {
  coordinate_set_id: string;
  page_id: string;
  side: "top" | "bottom";
  model: "similarity" | "similarity_with_mirror" | "affine";
  anchors: SmtRegistrationAnchor[];
  confirmed: boolean;
};

export type PlacementDecisionInput = {
  action:
    | "confirm_installed"
    | "confirm_nc"
    | "mark_process"
    | "mark_non_smt"
    | "leave_unresolved"
    | "change_role";
  role?: SmtPlacementRole;
  reason?: string;
  operator?: string;
};

export type SmtAnalysisExportArtifact = {
  label: string;
  path: string;
  media_type: string;
  size: number;
  sha256: string;
};

export type SmtAnalysisExportResponse = {
  status: "ok";
  run_id: string;
  snapshot_fingerprint: string;
  generated_at: string;
  package_path: string;
  package_sha256: string;
  artifacts: SmtAnalysisExportArtifact[];
};

function relativeUploadName(file: File) {
  const candidate =
    (file as File & { webkitRelativePath?: string }).webkitRelativePath ||
    file.name;
  return candidate.replaceAll("\\", "/").replace(/^\/+/, "");
}

export async function uploadDirectoryTree(files: File[]): Promise<UploadedTree> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file, relativeUploadName(file)));
  return apiCall<UploadedTree>(
    "/api/upload/tree",
    { method: "POST", body: form },
    { timeoutMs: 300_000 },
  );
}

export async function startSmtAnalysis(
  input: StartSmtAnalysisInput,
): Promise<SmtAnalysisRunResponse> {
  return apiCall<SmtAnalysisRunResponse>(
    "/api/smt-analysis/runs",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
    { timeoutMs: 300_000 },
  );
}

export async function fetchSmtAnalysis(
  runId: string,
): Promise<SmtAnalysisRunResponse> {
  return apiCall<SmtAnalysisRunResponse>(
    `/api/smt-analysis/runs/${encodeURIComponent(runId)}`,
  );
}

export async function confirmSmtSources(
  runId: string,
  input: SourceConfirmationInput,
): Promise<SmtAnalysisRunResponse> {
  return apiCall<SmtAnalysisRunResponse>(
    `/api/smt-analysis/runs/${encodeURIComponent(runId)}/sources/confirm`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
    { timeoutMs: 300_000 },
  );
}

export async function createSmtRegistration(
  runId: string,
  input: RegistrationInput,
): Promise<SmtAnalysisRunResponse> {
  return apiCall<SmtAnalysisRunResponse>(
    `/api/smt-analysis/runs/${encodeURIComponent(runId)}/registrations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
    { timeoutMs: 300_000 },
  );
}

export async function decideSmtPlacement(
  runId: string,
  placementId: string,
  input: PlacementDecisionInput,
): Promise<SmtAnalysisRunResponse> {
  return apiCall<SmtAnalysisRunResponse>(
    (
      `/api/smt-analysis/runs/${encodeURIComponent(runId)}` +
      `/placements/${encodeURIComponent(placementId)}/decision`
    ),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export async function decideSmtPlacements(
  runId: string,
  placementIds: string[],
  input: PlacementDecisionInput,
): Promise<SmtAnalysisRunResponse> {
  return apiCall<SmtAnalysisRunResponse>(
    `/api/smt-analysis/runs/${encodeURIComponent(runId)}/placements/decisions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...input, placement_ids: placementIds }),
    },
  );
}

export async function finalizeSmtAnalysis(
  runId: string,
): Promise<SmtAnalysisRunResponse> {
  return apiCall<SmtAnalysisRunResponse>(
    `/api/smt-analysis/runs/${encodeURIComponent(runId)}/finalize`,
    { method: "POST" },
  );
}

export async function exportSmtAnalysis(
  runId: string,
): Promise<SmtAnalysisExportResponse> {
  return apiCall<SmtAnalysisExportResponse>(
    `/api/smt-analysis/runs/${encodeURIComponent(runId)}/export`,
    { method: "POST" },
    { timeoutMs: 300_000 },
  );
}

export async function deleteSmtAnalysis(runId: string): Promise<void> {
  await apiCall(
    `/api/smt-analysis/runs/${encodeURIComponent(runId)}`,
    { method: "DELETE" },
  );
}
