import { afterEach, describe, expect, it, vi } from "vitest";

describe("secure API client", () => {
  afterEach(() => {
    vi.useRealTimers();
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

  it("passes through an external abort signal without accumulating listeners", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const addListener = vi.spyOn(controller.signal, "addEventListener");
    const { apiCall } = await import("../api/client");

    await apiCall("/api/update/status", {}, { signal: controller.signal });

    expect(addListener).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  it("removes merged abort listeners after a timed request settles", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const addListener = vi.spyOn(controller.signal, "addEventListener");
    const removeListener = vi.spyOn(controller.signal, "removeEventListener");
    const { apiCall } = await import("../api/client");

    await apiCall("/api/update/status", {}, { signal: controller.signal, timeoutMs: 5_000 });

    expect(addListener).toHaveBeenCalledOnce();
    expect(removeListener).toHaveBeenCalledOnce();
  });

  it.each(["fetchPlatformStatus", "fetchVersion"])("times out a stalled %s health probe", async (method) => {
    vi.useFakeTimers();
    let requestSignal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        requestSignal = init?.signal || undefined;
        return new Promise<Response>((_resolve, reject) => {
          requestSignal?.addEventListener(
            "abort",
            () => reject(new DOMException("The operation was aborted", "AbortError")),
            { once: true },
          );
        });
      }),
    );
    const client = await import("../api/client");

    const request = method === "fetchPlatformStatus" ? client.fetchPlatformStatus() : client.fetchVersion();
    const rejected = expect(request).rejects.toMatchObject({ name: "ApiError", kind: "TimeoutError" });
    await vi.advanceTimersByTimeAsync(3_000);

    await rejected;
    expect(requestSignal?.aborted).toBe(true);
  });

  it("times out a stalled update-status poll even when the dialog supplies a cancel signal", async () => {
    vi.useFakeTimers();
    let requestSignal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        requestSignal = init?.signal || undefined;
        return new Promise<Response>((_resolve, reject) => {
          requestSignal?.addEventListener(
            "abort",
            () => reject(new DOMException("The operation was aborted", "AbortError")),
            { once: true },
          );
        });
      }),
    );
    const caller = new AbortController();
    const client = await import("../api/client");
    const request = client.fetchUpdateStatus({ signal: caller.signal });
    void request.catch(() => {});

    try {
      await vi.advanceTimersByTimeAsync(3_000);
      expect(requestSignal?.aborted).toBe(true);
      expect(caller.signal.aborted).toBe(false);
      await expect(request).rejects.toMatchObject({ name: "ApiError", kind: "TimeoutError" });
    } finally {
      caller.abort();
      await request.catch(() => {});
    }
  });

  it("bounds the session-token handshake before sending a mutation", async () => {
    vi.useFakeTimers();
    let sessionSignal: AbortSignal | undefined;
    let rejectSession: ((reason?: unknown) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        sessionSignal = init?.signal || undefined;
        return new Promise<Response>((_resolve, reject) => {
          rejectSession = reject;
          sessionSignal?.addEventListener(
            "abort",
            () => reject(new DOMException("The operation was aborted", "AbortError")),
            { once: true },
          );
        });
      }),
    );
    const { apiCall } = await import("../api/client");
    const request = apiCall("/api/update/run", { method: "POST" }, { timeoutMs: 10_000 });
    void request.catch(() => {});

    try {
      await vi.advanceTimersByTimeAsync(3_000);
      expect(sessionSignal?.aborted).toBe(true);
      await expect(request).rejects.toMatchObject({ name: "ApiError", kind: "SessionTimeout" });
      await expect(request).rejects.toThrow("安全会话建立超时");
    } finally {
      rejectSession?.(new Error("test cleanup"));
      await request.catch(() => {});
    }
  });

  it("applies the shared timeout to legacy JSON endpoints", async () => {
    vi.useFakeTimers();
    let requestSignal: AbortSignal | undefined;
    let rejectRequest: ((reason?: unknown) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        requestSignal = init?.signal || undefined;
        return new Promise<Response>((_resolve, reject) => {
          rejectRequest = reject;
          requestSignal?.addEventListener(
            "abort",
            () => reject(new DOMException("The operation was aborted", "AbortError")),
            { once: true },
          );
        });
      }),
    );
    const { fetchTools } = await import("../api/client");
    const request = fetchTools();
    void request.catch(() => {});

    try {
      await vi.advanceTimersByTimeAsync(60_000);
      expect(requestSignal?.aborted).toBe(true);
      await expect(request).rejects.toThrow("请求超时");
    } finally {
      rejectRequest?.(new Error("test cleanup"));
      await request.catch(() => {});
    }
  });
});
