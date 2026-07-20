import { describe, expect, it } from "vitest";
import { riskStatusText } from "../utils/statusText";

describe("riskStatusText", () => {
  it.each([
    ["warn", "警告"],
    ["ok", "通过"],
    ["info", "提示"],
    ["unknown", "提示"],
  ])("maps %s to Chinese", (value, expected) => {
    expect(riskStatusText(value)).toBe(expected);
  });
});
