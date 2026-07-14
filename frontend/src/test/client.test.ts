import { afterEach, describe, expect, it, vi } from "vitest";

describe("secure API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("adds the local session header to mutations", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok", token: "session-one" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { secureFetch } = await import("../api/client");

    await secureFetch("/api/history", { method: "DELETE" });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/session");
    const headers = new Headers(fetchMock.mock.calls[1][1]?.headers);
    expect(headers.get("X-Insta360-Session")).toBe("session-one");
  });

  it("refreshes an expired session once after backend restart", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok", token: "old-token" }), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "error", error_kind: "session_required" }), { status: 403 }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok", token: "new-token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { secureFetch } = await import("../api/client");

    const response = await secureFetch("/api/update/cancel", { method: "POST" });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    const retryHeaders = new Headers(fetchMock.mock.calls[3][1]?.headers);
    expect(retryHeaders.get("X-Insta360-Session")).toBe("new-token");
  });
});
