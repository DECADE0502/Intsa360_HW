import { describe, expect, it } from "vitest";
import { outputHref } from "../utils/outputHref";

const sources = import.meta.glob(["../**/*.ts", "../**/*.tsx", "!../test/**"], {
  eager: true,
  import: "default",
  query: "?raw",
}) as Record<string, string>;

describe("outputHref", () => {
  it("encodes every output path segment without changing directory boundaries", () => {
    const href = outputHref("C:\\runtime\\data\\outputs\\bom\\主板 #1+A&B.xlsx");

    expect(href).toBe("/outputs/bom/%E4%B8%BB%E6%9D%BF%20%231%2BA%26B.xlsx");
    expect(
      href
        .slice("/outputs/".length)
        .split("/")
        .map((segment) => decodeURIComponent(segment))
        .join("/"),
    ).toBe("bom/主板 #1+A&B.xlsx");
  });

  it("accepts paths already relative to data outputs", () => {
    expect(outputHref("data/outputs/risk/检查 结果.xlsx")).toBe(
      "/outputs/risk/%E6%A3%80%E6%9F%A5%20%E7%BB%93%E6%9E%9C.xlsx",
    );
  });

  it("keeps one implementation and forbids encodeURI", () => {
    const combined = Object.values(sources).join("\n");
    expect(combined).not.toMatch(/encodeURI\(/);
    expect((combined.match(/function\s+outputHref\s*\(/g) || []).length).toBe(1);
  });
});
