import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  PlacementReview,
  placementResolutionComplete,
  placementResolutionsComplete,
  seedPlacementResolutions,
  type PlacementGroup,
  type PlacementResolution,
} from "../tools/PlacementReview";
import { renderWithProviders } from "./render";

function group(overrides: Partial<PlacementGroup> = {}): PlacementGroup {
  return {
    key: "material-a",
    row_numbers: [12],
    refs: ["X1"],
    position_count: 1,
    state: "suspected_material",
    category: "suspected_material",
    confidence: "strong",
    recommended_action: "keep",
    suggested_code: "PART-100",
    sh_review: false,
    rule_id: "R5",
    evidence: [{
      kind: "code_shape",
      field: "value",
      value: "PART-100",
      polarity: "material+",
      strength: "strong",
      display: "Value 命中编码形状（厂商 MPN）",
    }],
    original_fields: { part_number: "", value: "PART-100", name: "", model: "", desc: "" },
    inferred_fields: { part_number: "PART-100", value: "PART-100", name: "结构件", model: "", desc: "" },
    ...overrides,
  };
}

describe("BOM placement review", () => {
  it("seeds inferred fields without silently accepting the recommendation", () => {
    const item = group();
    const seeded = seedPlacementResolutions([item], {});

    expect(seeded[item.key].part_number).toBe("PART-100");
    expect(seeded[item.key].field_patch.name).toBe("结构件");
    expect(seeded[item.key].action).toBe("");
    expect(placementResolutionsComplete([item], seeded, ["suspected_material"])).toBe(false);
  });

  it("sanitizes stale workspace placeholders without discarding valid manual decisions", () => {
    const item = group({
      original_fields: { part_number: "", value: "PART-100", name: "", model: "", desc: "{" },
      inferred_fields: { part_number: "PART-100", value: "PART-100", name: "", model: "", desc: "" },
      evidence: [{
        kind: "placeholder_residue",
        field: "desc",
        value: "{",
        polarity: "neutral",
        strength: "strong",
        display: "描述含 Capture 占位残渣",
      }],
    });
    const stale: PlacementResolution = {
      action: "keep",
      part_number: "\ufffd",
      field_patch: { name: "手工名称", model: "", desc: "{", grade: "A", unit: "PCS" },
      decision_source: "manual",
    };

    const seeded = seedPlacementResolutions([item], { [item.key]: stale });

    expect(seeded[item.key]).toEqual({
      ...stale,
      part_number: "PART-100",
      field_patch: { name: "手工名称", model: "", desc: "", grade: "A", unit: "PCS" },
    });
    expect(seeded[item.key].action).toBe("keep");
    expect(seeded[item.key].decision_source).toBe("manual");
    expect(placementResolutionComplete(item, seeded[item.key])).toBe(true);
  });

  it("requires a code and descriptive metadata before a kept group is complete", () => {
    const item = group({ inferred_fields: { part_number: "PART-100", name: "", model: "", desc: "" } });
    const resolution: PlacementResolution = {
      action: "keep",
      part_number: "PART-100",
      field_patch: { name: "", model: "", desc: "", grade: "", unit: "" },
    };

    expect(placementResolutionComplete(item, resolution)).toBe(false);
    resolution.field_patch.desc = "焊接结构件";
    expect(placementResolutionComplete(item, resolution)).toBe(true);
  });

  it("requires visiting the insufficient-data tab before accepting its default", async () => {
    const user = userEvent.setup();
    const material = group();
    const insufficient = group({
      key: "insufficient-a",
      refs: ["X2"],
      state: "insufficient_data",
      category: "insufficient_data",
      confidence: "weak",
      recommended_action: "exclude",
      suggested_code: "",
      rule_id: "R8",
      original_fields: { part_number: "", value: "", name: "", model: "", desc: "{" },
      inferred_fields: { part_number: "", value: "", name: "", model: "", desc: "" },
    });
    const onApply = vi.fn();
    function Harness() {
      const [resolutions, setResolutions] = useState(() => ({
        ...seedPlacementResolutions([material, insufficient], {}),
        [material.key]: {
          ...seedPlacementResolutions([material], {})[material.key],
          action: "keep" as const,
          decision_source: "manual" as const,
        },
      }));
      const [visitedTabs, setVisitedTabs] = useState<string[]>([]);
      return (
        <PlacementReview
          groups={[material, insufficient]}
          readonlyNc={{ count: 0, items: [] }}
          resolutions={resolutions}
          visitedTabs={visitedTabs}
          onResolutionsChange={setResolutions}
          onVisitedTabsChange={setVisitedTabs}
          onApply={onApply}
          onBack={vi.fn()}
          running={false}
        />
      );
    }
    renderWithProviders(<Harness />);

    await waitFor(() => expect(screen.getByRole("button", { name: /按审查结果继续/ })).toBeDisabled());
    expect(screen.getByText(/还有 1 组未完成/)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /数据不足/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /按审查结果继续/ })).toBeEnabled());
    expect(onApply).not.toHaveBeenCalled();
  });

  it("applies page recommendations only after the summary is confirmed", async () => {
    const user = userEvent.setup();
    const item = group();
    function Harness() {
      const [resolutions, setResolutions] = useState(() => seedPlacementResolutions([item], {}));
      return (
        <PlacementReview
          groups={[item]}
          readonlyNc={{ count: 0, items: [] }}
          resolutions={resolutions}
          visitedTabs={["suspected_material"]}
          onResolutionsChange={setResolutions}
          onVisitedTabsChange={vi.fn()}
          onApply={vi.fn()}
          onBack={vi.fn()}
          running={false}
        />
      );
    }
    renderWithProviders(<Harness />);

    const continueButton = screen.getByRole("button", { name: /按审查结果继续/ });
    expect(continueButton).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "采纳本页建议" }));
    expect(screen.getByText("将纳入 1 组、确认不装 0 组。无推荐和已人工选择的组不会被改动。")).toBeInTheDocument();
    expect(continueButton).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "确认采纳" }));
    await waitFor(() => expect(continueButton).toBeEnabled());
  });

  it("lets the user explicitly accept a recommendation", async () => {
    const user = userEvent.setup();
    const item = group();
    const onApply = vi.fn();
    function Harness() {
      const [resolutions, setResolutions] = useState(() => seedPlacementResolutions([item], {}));
      return (
        <PlacementReview
          groups={[item]}
          readonlyNc={{ count: 0, items: [] }}
          resolutions={resolutions}
          visitedTabs={["suspected_material"]}
          onResolutionsChange={setResolutions}
          onVisitedTabsChange={vi.fn()}
          onApply={onApply}
          onBack={vi.fn()}
          running={false}
        />
      );
    }
    renderWithProviders(<Harness />);

    expect(screen.getByRole("button", { name: /按审查结果继续/ })).toBeDisabled();
    await user.click(screen.getByText("纳入 BOM", { exact: true }));
    await waitFor(() => expect(screen.getByRole("button", { name: /按审查结果继续/ })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /按审查结果继续/ }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it("hides the no-recommendation warning after an explicit decision", () => {
    const item = group({
      state: "conflicting",
      category: "conflicting",
      recommended_action: null,
      original_fields: { part_number: "PART-100", value: "NC", name: "器件", model: "M1", desc: "冲突项" },
      inferred_fields: { part_number: "PART-100", value: "NC", name: "器件", model: "M1", desc: "冲突项" },
    });
    const resolution: PlacementResolution = {
      action: "keep_as_is",
      part_number: "PART-100",
      field_patch: { name: "器件", model: "M1", desc: "冲突项", grade: "", unit: "" },
      decision_source: "manual",
    };

    renderWithProviders(
      <PlacementReview
        groups={[item]}
        readonlyNc={{ count: 0, items: [] }}
        resolutions={{ [item.key]: resolution }}
        visitedTabs={["conflicting"]}
        onResolutionsChange={vi.fn()}
        onVisitedTabsChange={vi.fn()}
        onApply={vi.fn()}
        onBack={vi.fn()}
        running={false}
      />,
    );

    expect(screen.queryByText("存在没有明确建议的项目")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /按审查结果继续/ })).toBeEnabled();
  });

  it("persists only the unified placement state in the workspace", () => {
    const source = readFileSync(resolve(process.cwd(), "src", "tools", "BomProcessWizard.tsx"), "utf-8");
    expect(source).toContain("placementResolutions: {} as Record<string, PlacementResolution>");
    expect(source).toContain("placementVisitedTabs: [] as string[]");
    expect(source).toContain("placement_resolutions: placementResolutions");
    expect(source).not.toContain("missing_part_number_resolutions");
    expect(source).not.toContain("process_material_keeps");
    expect(source).not.toContain("confirm_shields");
  });
});
