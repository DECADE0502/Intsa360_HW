import { apiCall } from "../../api/client";
import type { RefdesDocument } from "./types";


// Opening renders every page at full resolution, so allow well beyond the
// default request timeout for large multi-page drawings.
const OPEN_TIMEOUT_MS = 300_000;

export async function openRefdesDocument(
  path: string,
  label?: string,
): Promise<RefdesDocument> {
  return apiCall<RefdesDocument>(
    "/api/v1/refdes-viewer/docs",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(label ? { path, label } : { path }),
    },
    { timeoutMs: OPEN_TIMEOUT_MS },
  );
}

export async function fetchRefdesDocument(
  docId: string,
): Promise<RefdesDocument> {
  return apiCall<RefdesDocument>(
    `/api/v1/refdes-viewer/docs/${encodeURIComponent(docId)}`,
  );
}
