import { describe, expect, it } from "vitest";
import { groupSmtItems, type SmtReviewItem } from "../tools/smtPackage/grouping";

function item(ref: string, overrides: Partial<SmtReviewItem> = {}): SmtReviewItem {
  return {
    key: ref,
    ref,
    status: "需要确认",
    kind: "manual",
    part_number: "MAT-A",
    net_package: "R0201",
    bom_package: "R0201",
    note: "封装描述需要确认",
    ...overrides,
  };
}

describe("SMT package result grouping", () => {
  it("shows identical per-reference conclusions as one review group", () => {
    const groups = groupSmtItems([item("R10"), item("R2"), item("R1")]);

    expect(groups).toHaveLength(1);
    expect(groups[0].references).toEqual(["R1", "R2", "R10"]);
  });

  it("keeps different packages, material codes or conclusions separate", () => {
    const groups = groupSmtItems([
      item("R1"),
      item("R2", { net_package: "R0402" }),
      item("R3", { part_number: "MAT-B" }),
      item("R4", { status: "高风险封装" }),
    ]);

    expect(groups).toHaveLength(4);
  });
});
