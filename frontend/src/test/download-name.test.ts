import { describe, expect, it } from "vitest";
import { packageDownloadName } from "../utils/downloadName";

describe("packageDownloadName", () => {
  it("uses the UTF-8 filename supplied by the package endpoint", () => {
    const header =
      'attachment; filename="IAC4_MB_POWER_V02_20260715_204500.zip"; filename*=UTF-8\'\'%E5%8A%9F%E8%80%97%E7%89%88_20260715_204500.zip';

    expect(packageDownloadName(header, "ignored", new Date("2026-07-15T12:45:00Z"))).toBe(
      "功耗版_20260715_204500.zip",
    );
  });

  it("keeps the board name and timestamp when the response header is unavailable", () => {
    expect(packageDownloadName(null, "IAC4_MB_POWER_V02", new Date(2026, 6, 15, 20, 45, 7))).toBe(
      "IAC4_MB_POWER_V02_20260715_204507.zip",
    );
  });

  it("strips path components from an unexpected server filename", () => {
    expect(packageDownloadName('attachment; filename="../unsafe.zip"', "BOARD", new Date())).toBe("unsafe.zip");
  });
});
