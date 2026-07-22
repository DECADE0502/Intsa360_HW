import { describe, expect, it } from "vitest";
import {
  buildRecommendedConflictChoices,
  conflictChoiceComplete,
  normalizeConflictChoice,
} from "../tools/bomConflictChoices";

describe("BOM conflict choices v2", () => {
  it("preserves manual choices and fills only high-confidence recommendations", () => {
    const choices = buildRecommendedConflictChoices(
      [
        { code: "P1", recommended_index: 1, high_confidence: true, variants: [{}, {}] },
        { code: "P2", recommended_index: null, high_confidence: false, variants: [{}, {}, {}] },
        { code: "P3", recommended_index: 0, high_confidence: false, variants: [{}, {}] },
      ],
      { P2: { action: "select_variant", variant_index: 2 } },
    );

    expect(choices).toEqual({
      P1: { action: "select_variant", variant_index: 1 },
      P2: { action: "select_variant", variant_index: 2 },
    });
  });

  it("migrates a valid legacy numeric choice but rejects out-of-range values", () => {
    const conflict = { code: "P1", variants: [{}, {}] };
    expect(normalizeConflictChoice(conflict, 1)).toEqual({ action: "select_variant", variant_index: 1 });
    expect(normalizeConflictChoice(conflict, 2)).toBeUndefined();
  });

  it("requires complete unique codes for split-by-reference decisions", () => {
    const conflict = { code: "P1", variants: [{}, {}] };
    expect(conflictChoiceComplete(conflict, {
      action: "split_refs",
      assignments: [
        { variant_index: 0, part_number: "P1-A" },
        { variant_index: 1, part_number: "" },
      ],
    })).toBe(false);
    expect(conflictChoiceComplete(conflict, {
      action: "split_refs",
      assignments: [
        { variant_index: 0, part_number: "P1-A" },
        { variant_index: 1, part_number: "P1-B" },
      ],
    })).toBe(true);
  });

  it("never treats return-to-Capture as a completed platform decision", () => {
    expect(conflictChoiceComplete(
      { code: "P1", variants: [{}, {}] },
      { action: "return_to_capture" },
    )).toBe(false);
  });
});
