import { describe, expect, it } from "vitest";

const sources = import.meta.glob(["../**/*.ts", "../**/*.tsx", "!../test/**"], {
  eager: true,
  import: "default",
  query: "?raw",
}) as Record<string, string>;

describe("user-visible error fallback gate", () => {
  it("does not render raw exception messages or English request fallbacks", () => {
    const violations: string[] = [];
    const forbidden = [
      /Request failed/,
      /statusText\s*\?\?/,
      /(?:err|error|e)(?:\?\.)?\.message\s*(?:\|\||\?\?)/,
      /message\.error\([^\n]*(?:err|error|e)(?:\?\.)?\.message/,
      /error:\s*(?:err|error|e)(?:\?\.)?\.message/,
      /String\([^\n]*(?:err|error|e)(?:\?\.)?\.message/,
    ];
    for (const [path, source] of Object.entries(sources)) {
      if (path.endsWith("/api/errors.ts")) continue;
      source.split(/\r?\n/).forEach((line, index) => {
        if (/console\.(?:warn|error|debug)/.test(line)) return;
        if (forbidden.some((pattern) => pattern.test(line))) {
          violations.push(`${path}:${index + 1}: ${line.trim()}`);
        }
      });
    }
    expect(violations).toEqual([]);
  });
});
