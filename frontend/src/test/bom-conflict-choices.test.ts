import { describe, expect, it } from "vitest";
import { buildRecommendedConflictChoices } from "../tools/bomConflictChoices";

describe("buildRecommendedConflictChoices", () => {
  it("preserves manual choices and fills every remaining conflict recommendation", () => {
    const choices = buildRecommendedConflictChoices(
      [
        { code: "P1", recommended_index: 1, variants: [{}, {}] },
        { code: "P2", recommended_index: 2, variants: [{}, {}, {}] },
        { code: "P3", variants: [{}, {}] },
      ],
      { P1: 0 },
    );

    expect(choices).toEqual({ P1: 0, P2: 2, P3: 0 });
  });
});
