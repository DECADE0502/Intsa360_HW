import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  PlacementReview,
  placementResolutionComplete,
  placementResolutionIssue,
  placementResolutionsComplete,
  seedPlacementResolutions,
  type PlacementGroup,
  type PlacementResolution,
} from "../tools/PlacementReview";
import { renderWithProviders } from "./render";

function group(overrides: Partial<PlacementGroup> = {}): PlacementGroup {
  return {
    key: "material-a",
    group_id: "material-a",
    row_numbers: [12],
    source_rows: [12],
    refs: ["X1"],
    physical_refs: ["X1"],
    position_count: 1,
    state: "suspected_material",
    category: "suspected_material",
    confidence: "strong",
    recommended_action: "keep",
    suggested_destination: "smt",
    exclusion_kind: "",
    suggested_code: "PART-100",
    suggested_mpn: "",
    sh_review: false,
    rule_id: "R5",
    rule_version: "placement-v2",
    identity_status: "identity_candidate_internal",
    role: "electronic",
    role_confidence: "strong",
    blocking_reasons: [],
    decision_fingerprint: "fingerprint-a",
    evidence: [{
      kind: "code_shape",
      field: "value",
      value: "PART-100",
      polarity: "material+",
      strength: "strong",
      priority: 1,
      display: "Value 符合内部编码形态",
    }],
    original_fields: { part_number: "", value: "PART-100", name: "", model: "", desc: "" },
    inferred_fields: { part_number: "PART-100", value: "PART-100", name: "结构件", model: "", desc: "" },
    ...overrides,
  };
}

function patch(overrides: Partial<PlacementResolution["field_patch"]> = {}): PlacementResolution["field_patch"] {
  return {
    name: "结构件",
    model: "",
    desc: "",
    grade: "",
    unit: "",
    manufacturer: "",
    pcb_footprint: "",
    pcb_package: "",
    ...overrides,
  };
}

function resolution(overrides: Partial<PlacementResolution> = {}): PlacementResolution {
  return {
    destination: "",
    exclusion_kind: "",
    role: "electronic",
    subtype: "",
    part_number_override: "PART-100",
    field_patch: patch(),
    decision_source: "user",
    ...overrides,
  };
}

describe("BOM placement review v2", () => {
  it("prefills inferred fields without silently accepting a destination", () => {
    const item = group();
    const seeded = seedPlacementResolutions([item], {});

    expect(seeded[item.key].part_number_override).toBe("PART-100");
    expect(seeded[item.key].field_patch.name).toBe("结构件");
    expect(seeded[item.key].destination).toBe("");
    expect(placementResolutionsComplete([item], seeded)).toBe(false);
  });

  it("discards legacy action-only workspace decisions after the rule upgrade", () => {
    const item = group();
    const legacy = { action: "exclude", part_number: "OLD" } as unknown as PlacementResolution;
    const seeded = seedPlacementResolutions([item], { [item.key]: legacy });

    expect(seeded[item.key].destination).toBe("");
    expect(seeded[item.key].part_number_override).toBe("PART-100");
    expect(seeded[item.key].decision_source).toBe("user");
  });

  it("automatically reuses only an exact history resolution", () => {
    const item = group({
      history_exact_resolution: resolution({ destination: "smt", decision_source: "user" }),
    });
    const seeded = seedPlacementResolutions([item], {});

    expect(seeded[item.key].destination).toBe("smt");
    expect(seeded[item.key].decision_source).toBe("history_exact");
    expect(placementResolutionComplete(item, seeded[item.key])).toBe(true);
  });

  it("requires an internal code and descriptive field for the SMT zone", () => {
    const item = group({ inferred_fields: { part_number: "", name: "", model: "", desc: "" } });
    const selected = resolution({
      destination: "smt",
      part_number_override: "",
      field_patch: patch({ name: "", model: "", desc: "" }),
    });

    expect(placementResolutionComplete(item, selected)).toBe(false);
    selected.part_number_override = "PART-100";
    expect(placementResolutionComplete(item, selected)).toBe(false);
    selected.field_patch.desc = "焊接结构件";
    expect(placementResolutionComplete(item, selected)).toBe(true);
  });

  it("completes a non-SMT decision from the destination alone", () => {
    const item = group();
    const selected = resolution({ destination: "non_smt" });

    expect(placementResolutionComplete(item, selected)).toBe(true);
    expect(placementResolutionIssue(item, selected)).toBe("");
  });

  it("uses shield subtype as an editable default instead of another completion gate", () => {
    const shield = group({
      refs: ["SH1"],
      physical_refs: ["SH1"],
      sh_review: true,
      role: "shield",
      state: "material@shield",
      suggested_destination: "non_smt",
      shield_subtype: "cover",
    });

    const seeded = seedPlacementResolutions([shield], {});
    expect(seeded[shield.key].subtype).toBe("cover");
    expect(placementResolutionComplete(shield, resolution({ destination: "smt", role: "shield" }))).toBe(true);
    expect(placementResolutionComplete(shield, resolution({ destination: "non_smt", role: "shield" }))).toBe(true);
  });

  it("leaves R8 unresolved instead of silently excluding it", () => {
    const insufficient = group({
      key: "insufficient-a",
      refs: ["X2"],
      physical_refs: ["X2"],
      state: "insufficient_data",
      category: "insufficient_data",
      confidence: "weak",
      recommended_action: null,
      suggested_destination: null,
      suggested_code: "",
      rule_id: "R8",
      identity_status: "identity_missing",
      role: "unknown",
      original_fields: { part_number: "", value: "", name: "", model: "", desc: "" },
      inferred_fields: { part_number: "", value: "", name: "", model: "", desc: "" },
    });
    const seeded = seedPlacementResolutions([insufficient], {});

    expect(seeded[insufficient.key].destination).toBe("");
    expect(seeded[insufficient.key].exclusion_kind).toBe("");
    expect(placementResolutionComplete(insufficient, seeded[insufficient.key])).toBe(false);
  });

  it("lets the user confirm the suggested zone without moving out and back", async () => {
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
          onResolutionsChange={setResolutions}
          onApply={onApply}
          onBack={vi.fn()}
          running={false}
        />
      );
    }
    renderWithProviders(<Harness />);

    const continueButton = screen.getByRole("button", { name: /按审查结果继续/ });
    expect(continueButton).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "确认 X1 保留在贴片区" }));
    await waitFor(() => expect(continueButton).toBeEnabled());
    await user.click(continueButton);
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it("keeps the confirmation entry visible and explains missing SMT fields", () => {
    const item = group({ inferred_fields: { part_number: "", name: "", model: "", desc: "" } });
    const selected = resolution({
      destination: "smt",
      part_number_override: "",
      field_patch: patch({ name: "", model: "", desc: "" }),
    });
    renderWithProviders(
      <PlacementReview
        groups={[item]}
        readonlyNc={{ count: 0, items: [] }}
        resolutions={{ [item.key]: selected }}
        onResolutionsChange={vi.fn()}
        onApply={vi.fn()}
        onBack={vi.fn()}
        running={false}
      />,
    );

    expect(placementResolutionIssue(item, selected)).toBe("纳入贴片 BOM 时必须填写内部子项编码。");
    expect(screen.getByRole("button", { name: "确认 X1 保留在贴片区" })).toBeInTheDocument();
  });

  it("batch applies only strong non-conflicting non-SH recommendations on the visible page", async () => {
    const user = userEvent.setup();
    const safe = group();
    const shield = group({ key: "shield", refs: ["SH1"], role: "shield", sh_review: true });
    function Harness() {
      const [resolutions, setResolutions] = useState(() => seedPlacementResolutions([safe, shield], {}));
      return (
        <PlacementReview
          groups={[safe, shield]}
          readonlyNc={{ count: 0, items: [] }}
          resolutions={resolutions}
          onResolutionsChange={setResolutions}
          onApply={vi.fn()}
          onBack={vi.fn()}
          running={false}
        />
      );
    }
    renderWithProviders(<Harness />);

    await user.click(screen.getByRole("button", { name: "采纳当前页安全建议" }));
    expect(screen.getByText(/冲突项、SH 和弱证据项不会被批量处理/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认采纳" }));
    await waitFor(() => expect(screen.getByText("已确认 1/2")).toBeInTheDocument());
    expect(screen.getByText("还有 1 组未完成")).toBeInTheDocument();
  });

  it("renders the coded-process verification list without blocking continuation", async () => {
    const item = group();
    function Harness() {
      const [resolutions, setResolutions] = useState(() => ({
        [item.key]: resolution({ destination: "smt" }),
      }));
      return (
        <PlacementReview
          groups={[item]}
          readonlyNc={{ count: 0, items: [] }}
          codeVerification={[{
            part_number: "TP-PN",
            keyword: "测试点",
            reason: "编码已按物料纳入，请查验是否为库占位名",
            description: "镀金测试点",
            refs: ["TP5"],
            row_numbers: [12],
          }]}
          resolutions={resolutions}
          onResolutionsChange={setResolutions}
          onApply={vi.fn()}
          onBack={vi.fn()}
          running={false}
        />
      );
    }
    renderWithProviders(<Harness />);

    expect(screen.getByRole("button", { name: /按审查结果继续/ })).toBeEnabled();
    expect(screen.getByText(/编码与描述查验 1 项/)).toBeInTheDocument();
  });

  it("persists only the unified v2 placement state in the workspace", () => {
    const source = readFileSync(resolve(process.cwd(), "src", "tools", "BomProcessWizard.tsx"), "utf-8");
    expect(source).toContain("placementResolutions: {} as Record<string, PlacementResolution>");
    expect(source).toContain("placement_resolutions: placementResolutions");
    expect(source).not.toContain("placementVisitedTabs");
    expect(source).not.toContain("missing_part_number_resolutions");
    expect(source).not.toContain("process_material_keeps");
    expect(source).not.toContain("confirm_shields");
  });
});
