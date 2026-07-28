import { describe, expect, it } from "vitest";
import {
  groupFindingsByRecord,
  sourceRecordLabel,
  summarizeCompare,
} from "../tools/bomCompare/summary";
import type {
  SemanticCompare,
  ValidationFinding,
} from "../tools/bomCompare/types";

describe("BOM compare presentation summary", () => {
  it("groups multiple field findings on the same source row", () => {
    const findings: ValidationFinding[] = [
      {
        code: "missing_strategy",
        severity: "blocker",
        message: "缺少替代策略",
        parent_code: "BOARD-A",
        source_ids: ["fingerprint:Sheet1:18"],
        details: { material_code: "MAT-A" },
      },
      {
        code: "missing_mode",
        severity: "blocker",
        message: "缺少替代方式",
        parent_code: "BOARD-A",
        source_ids: ["fingerprint:Sheet1:18"],
        details: { material_code: "MAT-A" },
      },
    ];

    const groups = groupFindingsByRecord(findings);

    expect(groups).toHaveLength(1);
    expect(groups[0].messages).toEqual(["缺少替代策略", "缺少替代方式"]);
    expect(sourceRecordLabel(groups[0].sourceId)).toBe("Sheet1 第 18 行");
  });

  it("keeps review events separate from metadata events", () => {
    const semantic = {
      summary: {
        actual_reference_count_old: 799,
        actual_reference_count_new: 800,
      },
      placement_diff: [
        { status: "migrated" },
        { status: "added" },
        { status: "removed" },
      ],
      substitute_diff: [{ status: "added" }, { status: "changed" }],
      metadata_diff: [{ changed_fields: ["remark"] }],
      board_metadata_diff: [{ changed_fields: ["parent_code"] }],
      events: [
        { event_id: "review", impact: "placement" },
        { event_id: "metadata", impact: "metadata" },
      ],
      blockers: [],
      warnings: [],
    } as unknown as SemanticCompare;

    const summary = summarizeCompare(semantic);

    expect(summary.placement).toEqual({ migrated: 1, added: 1, removed: 1 });
    expect(summary.substitute).toEqual({ added: 1, changed: 1, removed: 0 });
    expect(summary.reviewEventCount).toBe(1);
    expect(summary.metadataEventCount).toBe(1);
    expect(summary.metadataChangeCount).toBe(2);
    expect(summary.metadataFieldCount).toBe(2);
    expect(summary.referenceDelta).toBe(1);
  });
});
