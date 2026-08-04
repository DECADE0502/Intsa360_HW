import { apiCall } from "../../api/client";
import type { CreateBoardRequest, SmtBoard } from "./types";

export function createSmtBoard(request: CreateBoardRequest) {
  return apiCall<SmtBoard>(
    "/api/v1/smt-view/boards",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
    { timeoutMs: 300_000 },
  );
}

export function getSmtBoard(boardId: string) {
  return apiCall<SmtBoard>(`/api/v1/smt-view/boards/${encodeURIComponent(boardId)}`);
}
