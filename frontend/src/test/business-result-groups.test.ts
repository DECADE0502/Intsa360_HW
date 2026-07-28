import { describe, expect, it } from "vitest";
import {
  groupByBusinessOutcome,
  naturalReferenceSort,
  referenceSummary,
} from "../utils/businessResultGroups";

describe("business result grouping", () => {
  it("merges only records with the same complete outcome key", () => {
    const groups = groupByBusinessOutcome(
      [
        { ref: "C10", oldCode: "A", newCode: "B" },
        { ref: "C2", oldCode: "A", newCode: "B" },
        { ref: "C3", oldCode: "A", newCode: "C" },
      ],
      (item) => `${item.oldCode}|${item.newCode}`,
      (item) => [item.ref],
    );

    expect(groups).toHaveLength(2);
    expect(groups[0].references).toEqual(["C2", "C10"]);
    expect(groups[1].references).toEqual(["C3"]);
  });

  it("deduplicates and naturally sorts references", () => {
    expect(naturalReferenceSort(["R10", "R2", "R2", "R1"])).toEqual([
      "R1",
      "R2",
      "R10",
    ]);
    expect(referenceSummary(["R1", "R2", "R3", "R4", "R5"])).toBe(
      "R1, R2, R3, R4 等 5 个",
    );
  });
});
