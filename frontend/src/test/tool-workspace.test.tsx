import { act, renderHook } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useToolWorkspace } from "../state/toolWorkspace";

const PREFIX = "insta360_hw_tool_workspace:";

describe("useToolWorkspace v2", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("migrates safe v1 fields into a v2 envelope", () => {
    window.localStorage.setItem(`${PREFIX}legacy`, JSON.stringify({ query: "旧数据", result: { stale: true } }));

    const { result } = renderHook(() =>
      useToolWorkspace(
        "legacy",
        { query: "", result: null as any },
        { heavyKeys: ["result"] },
      ),
    );

    expect(result.current[0]).toEqual({ query: "旧数据", result: null });
    expect(JSON.parse(window.localStorage.getItem(`${PREFIX}legacy`) || "{}")).toMatchObject({
      __v: 2,
      data: { query: "旧数据" },
    });
  });

  it("discards a v2 envelope whose data is not an object", () => {
    window.localStorage.setItem(
      `${PREFIX}invalid`,
      JSON.stringify({ __v: 2, saved_at: Date.now(), data: ["not", "an", "object"] }),
    );

    const { result } = renderHook(() => useToolWorkspace("invalid", { query: "", result: null as any }));

    expect(result.current[0]).toEqual({ query: "", result: null });
  });

  it("debounces successive writes into one v2 envelope", () => {
    const storageWrite = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(() => useToolWorkspace("debounce", { query: "", result: null as any }));
    storageWrite.mockClear();

    act(() => {
      result.current[1]({ query: "a", result: null });
      result.current[1]({ query: "ab", result: null });
      result.current[1]({ query: "abc", result: null });
    });
    act(() => vi.advanceTimersByTime(499));
    expect(storageWrite).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));

    expect(storageWrite).toHaveBeenCalledTimes(1);
    expect(JSON.parse(window.localStorage.getItem(`${PREFIX}debounce`) || "{}")).toMatchObject({
      __v: 2,
      data: { query: "abc", result: null },
    });
  });

  it("strips declared heavy keys when the payload exceeds two megabytes", () => {
    const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result } = renderHook(() =>
      useToolWorkspace(
        "large",
        { query: "", result: null as any },
        { heavyKeys: ["result"] },
      ),
    );

    act(() => {
      result.current[1]({ query: "保留输入", result: "x".repeat(2 * 1024 * 1024 + 1024) });
    });
    act(() => vi.advanceTimersByTime(500));

    const saved = JSON.parse(window.localStorage.getItem(`${PREFIX}large`) || "{}");
    expect(saved.__v).toBe(2);
    expect(saved.data.query).toBe("保留输入");
    expect(saved.data).not.toHaveProperty("result");
    expect(saved.__truncated).toBe(true);
    expect(warning).toHaveBeenCalled();
  });

  it("emits a UI event when workspace results are truncated", () => {
    const listener = vi.fn();
    window.addEventListener("insta360_hw:workspace-truncated", listener);
    const { result } = renderHook(() =>
      useToolWorkspace(
        "large-event",
        { query: "", result: null as any },
        { heavyKeys: ["result"], maxBytes: 128 },
      ),
    );

    act(() => result.current[1]({ query: "保留输入", result: "x".repeat(1024) }));
    act(() => vi.advanceTimersByTime(500));

    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual({ key: "large-event" });
    window.removeEventListener("insta360_hw:workspace-truncated", listener);
  });

  it("reset cancels a pending write and keeps storage empty", () => {
    const { result } = renderHook(() => useToolWorkspace("reset", { query: "", result: null as any }));

    act(() => result.current[1]({ query: "待写入", result: { large: true } }));
    act(() => result.current[2]());
    act(() => vi.advanceTimersByTime(1_000));

    expect(result.current[0]).toEqual({ query: "", result: null });
    expect(window.localStorage.getItem(`${PREFIX}reset`)).toBeNull();
  });

  it("falls back to input-only state when the full write exceeds storage quota", () => {
    const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
    const nativeSetItem = Storage.prototype.setItem;
    let writes = 0;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key, value) {
      writes += 1;
      if (writes === 1) throw new DOMException("quota exceeded", "QuotaExceededError");
      return nativeSetItem.call(this, key, value);
    });
    const { result } = renderHook(() =>
      useToolWorkspace(
        "quota",
        { query: "", result: null as any },
        { heavyKeys: ["result"] },
      ),
    );

    act(() => result.current[1]({ query: "保留输入", result: { rows: [1, 2, 3] } }));
    act(() => vi.advanceTimersByTime(500));

    const saved = JSON.parse(window.localStorage.getItem(`${PREFIX}quota`) || "{}");
    expect(saved.data).toEqual({ query: "保留输入" });
    expect(writes).toBe(2);
    expect(warning).toHaveBeenCalled();
  });

  it("declares heavy result keys in every result pane", () => {
    for (const pane of [
      "BomComparePane.tsx",
      "NetlistComparePane.tsx",
      "SingleNetworkCheckPane.tsx",
    ]) {
      const source = readFileSync(resolve(process.cwd(), "src", "tools", pane), "utf-8");
      expect(source).toContain('heavyKeys: ["result"]');
    }
  });

  it("uses reconnect copy that matches the current-tab polling behavior", () => {
    const source = readFileSync(resolve(process.cwd(), "src", "App.tsx"), "utf-8");
    expect(source).toContain("正在重新连接本地服务，请稍候…");
    expect(source).not.toContain("如新窗口未自动打开");
  });
});
