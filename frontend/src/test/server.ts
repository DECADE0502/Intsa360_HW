import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";

export const server = setupServer(
  http.get("/api/assets", () =>
    HttpResponse.json({
      status: "ok",
      groups: { processed_bom: [] },
      summary: { processed_bom: 0 },
    }),
  ),
);
