import { act, renderHook } from "@testing-library/react";
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

  it("discards unversioned v1 data", () => {
    window.localStorage.setItem(`${PREFIX}legacy`, JSON.stringify({ query: "旧数据", result: { stale: true } }));

    const { result } = renderHook(() => useToolWorkspace("legacy", { query: "", result: null as any }));

    expect(result.current[0]).toEqual({ query: "", result: null });
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
    expect(warning).toHaveBeenCalled();
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
});
