import { apiCall } from "../../api/client";
import type { RefdesDrawing } from "./types";


// Opening only reads page geometry and refdes text, but a very large PDF can
// still take a few seconds, so allow more than the default request timeout.
const OPEN_TIMEOUT_MS = 120_000;

export async function openRefdesDrawing(
  path: string,
  label?: string,
): Promise<RefdesDrawing> {
  return apiCall<RefdesDrawing>(
    "/api/v1/refdes/drawings",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(label ? { path, label } : { path }),
    },
    { timeoutMs: OPEN_TIMEOUT_MS },
  );
}

export async function fetchRefdesDrawing(
  drawingId: string,
): Promise<RefdesDrawing> {
  return apiCall<RefdesDrawing>(
    `/api/v1/refdes/drawings/${encodeURIComponent(drawingId)}`,
  );
}
