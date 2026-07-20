import { describe, expect, it, vi } from "vitest";
import { ApiError, toUserMessage } from "../api/errors";

describe("toUserMessage", () => {
  it("returns the API user message", () => {
    expect(toUserMessage(new ApiError("ValidationError", "请选择有效的 BOM 文件。", 400))).toBe(
      "请选择有效的 BOM 文件。",
    );
  });

  it("maps fetch failures to the disconnected-service message", () => {
    expect(toUserMessage(new TypeError("Failed to fetch"))).toBe(
      "后端服务已断开，请重新启动平台或点击重新连接。",
    );
  });

  it("maps abort errors to a timeout message", () => {
    expect(toUserMessage(new DOMException("The operation was aborted", "AbortError"))).toBe(
      "请求超时，请稍后重试。",
    );
  });

  it("does not expose an unknown English exception", () => {
    const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(toUserMessage(new Error("internal parser exploded"))).toBe("操作失败，请重试或查看系统状态。");
    expect(warning).toHaveBeenCalled();
    warning.mockRestore();
  });

  it("does not misreport a programming TypeError as a disconnected service", () => {
    const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(toUserMessage(new TypeError("cannot read properties of undefined"))).toBe(
      "操作失败，请重试或查看系统状态。",
    );
    warning.mockRestore();
  });
});
