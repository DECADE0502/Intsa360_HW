import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { BomComparePane } from "../tools/BomComparePane";
import { renderWithProviders } from "./render";
import { server } from "./server";


const tool = {
  id: "bom_compare",
  name: "BOM 差异比较",
  description: "语义对比",
  status: "available",
  category: "BOM",
};

const source = {
  envelope: {
    profile: "plm_single_board",
    source_path: "C:/upload/source.xlsx",
    source_fingerprint: "source-fingerprint",
  },
  boards: [
    {
      parent_code: "BOARD-A",
      hardware_version: "V10",
      placements: [{}, {}, {}, {}],
      substitute_groups: [{}],
      items: [],
    },
  ],
  findings: [],
  can_compare: true,
};

const response = {
  status: "ok",
  tool: "bom_compare",
  schema_version: 2,
  action: "compare",
  outputs: [
    "C:/outputs/BOM差异报告.xlsx",
    "C:/outputs/BOM四层差异报告.xlsx",
    "C:/outputs/BOM语义对比.json",
  ],
  source_inspections: { old: source, new: source },
  semantic: {
    schema_version: 2,
    model_version: "1.0.0",
    analysis_fingerprint: "analysis-fingerprint",
    summary: {
      parent_count_old: 1,
      parent_count_new: 1,
      material_count_old: 3,
      material_count_new: 3,
      actual_reference_count_old: 4,
      actual_reference_count_new: 4,
      substitute_group_count_old: 1,
      substitute_group_count_new: 1,
      changed_event_count: 1,
      blocker_count: 0,
      event_counts: { main_changed_refs_migrated: 1 },
    },
    events: [
      {
        event_id: "evt-1",
        kind: "main_changed_refs_migrated",
        parent_code: "BOARD-A",
        title: "替代组主料由 MAT-A 调整为 MAT-B",
        impact: "supply",
        references: ["C1"],
        group_codes: ["MAT-A", "MAT-B"],
        oa_change_type: "替代(AB共存)",
      },
    ],
    placement_diff: [
      {
        parent_code: "BOARD-A",
        reference: "C1",
        status: "migrated",
        old_material_code: "MAT-A",
        new_material_code: "MAT-B",
      },
    ],
    substitute_diff: [
      {
        status: "changed",
        old: {
          parent_code: "BOARD-A",
          group_code: "MAT-A",
          main_material_code: "MAT-A",
          alternative_material_codes: ["MAT-B"],
          priorities: { "MAT-A": 0, "MAT-B": 1 },
          references: ["C1"],
        },
        new: {
          parent_code: "BOARD-A",
          group_code: "MAT-B",
          main_material_code: "MAT-B",
          alternative_material_codes: ["MAT-A"],
          priorities: { "MAT-B": 0, "MAT-A": 1 },
          references: ["C1"],
        },
      },
    ],
    raw_row_diff: [],
    board_metadata_diff: [],
    metadata_diff: [],
    blockers: [],
    warnings: [],
    can_export: true,
  },
};

describe("BOM semantic compare workbench", () => {
  beforeEach(() => {
    window.localStorage.clear();
    let uploadIndex = 0;
    server.use(
      http.get("/api/assets", () => HttpResponse.json({
        status: "ok",
        groups: { processed_bom: [] },
        summary: { processed_bom: 0 },
      })),
      http.get("/api/session", () => HttpResponse.json({ status: "ok", token: "compare-session" })),
      http.post("/api/upload", () => {
        uploadIndex += 1;
        return HttpResponse.json({
          status: "ok",
          folder: `C:/upload/${uploadIndex}`,
          files: [{ name: uploadIndex === 1 ? "old.xlsx" : "new.xlsx", path: `C:/upload/${uploadIndex}/bom.xlsx` }],
        });
      }),
      http.post("/api/tools/bom_compare/run", async ({ request }) => {
        const body = await request.json() as Record<string, unknown>;
        expect(body).toEqual({
          action: "compare",
          bom1: "C:/upload/1/bom.xlsx",
          bom2: "C:/upload/2/bom.xlsx",
        });
        return HttpResponse.json(response);
      }),
    );
  });

  it("uses the full width semantic layers and keeps both local inputs", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<BomComparePane tool={tool} />);
    const inputs = Array.from(container.querySelectorAll<HTMLInputElement>('input[type="file"]'));

    expect(screen.getByText("四层语义对比")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始语义对比" })).toBeInTheDocument();
    expect(inputs).toHaveLength(2);

    await user.upload(inputs[0], new File(["old"], "old.xlsx"));
    await user.upload(inputs[1], new File(["new"], "new.xlsx"));
    await user.click(screen.getByRole("button", { name: "开始语义对比" }));

    expect(await screen.findByRole("tab", { name: "实际贴装 1" })).toBeInTheDocument();
    expect(screen.getByText("MAT-A")).toBeInTheDocument();
    expect(screen.getByText("MAT-B")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "替代关系 1" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "风险与交付 0" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "替代关系 1" }));
    await waitFor(() => expect(screen.getAllByText("BOARD-A").length).toBeGreaterThan(0));
    expect(screen.getByText("MAT-A / MAT-B")).toBeInTheDocument();
    expect(screen.getByText("MAT-B / MAT-A")).toBeInTheDocument();
  });

  it("paginates large blocker lists instead of mounting every finding", async () => {
    const blockers = Array.from({ length: 10 }, (_, index) => ({
      code: `material_variant_conflict_${index + 1}`,
      severity: "blocker",
      message: `物料冲突 ${index + 1}`,
      parent_code: "BOARD-A",
      details: { material_code: `MAT-${index + 1}` },
    }));
    server.use(
      http.post("/api/tools/bom_compare/run", () =>
        HttpResponse.json({
          ...response,
          semantic: {
            ...response.semantic,
            summary: { ...response.semantic.summary, blocker_count: blockers.length },
            blockers,
            can_export: false,
          },
        }),
      ),
    );
    const user = userEvent.setup();
    const { container } = renderWithProviders(<BomComparePane tool={tool} />);
    const inputs = Array.from(container.querySelectorAll<HTMLInputElement>('input[type="file"]'));

    await user.upload(inputs[0], new File(["old"], "old.xlsx"));
    await user.upload(inputs[1], new File(["new"], "new.xlsx"));
    await user.click(screen.getByRole("button", { name: "开始语义对比" }));

    expect(await screen.findByRole("tab", { name: "风险与交付 10" })).toBeInTheDocument();
    expect(container.querySelectorAll(".bom-finding-page article")).toHaveLength(8);
    expect(screen.getByText("共 10 项")).toBeInTheDocument();
    expect(screen.queryByText("物料冲突 9")).not.toBeInTheDocument();
  });

  it("requires explicit confirmation before comparing different parent codes", async () => {
    const requestBodies: Array<Record<string, unknown>> = [];
    server.use(
      http.post("/api/tools/bom_compare/run", async ({ request }) => {
        const body = await request.json() as Record<string, unknown>;
        requestBodies.push(body);
        if (!body.scope_confirmation) {
          return HttpResponse.json({
            status: "ok",
            tool: "bom_compare",
            schema_version: 2,
            action: "compare",
            needs_scope_confirmation: true,
            can_export: false,
            outputs: [],
            source_inspections: { old: source, new: source },
            comparison_scope: {
              status: "suggested",
              needs_confirmation: true,
              unresolved_old_parent_codes: ["BOARD-OLD"],
              unresolved_new_parent_codes: ["BOARD-NEW"],
              pairs: [
                {
                  old_parent_code: "BOARD-OLD",
                  new_parent_code: "BOARD-NEW",
                  old_parent_description: "旧版板卡",
                  new_parent_description: "新版板卡",
                  status: "suggested",
                  evidence: {
                    old_reference_count: 799,
                    new_reference_count: 800,
                    shared_reference_count: 795,
                    reference_overlap: 0.9888,
                    old_material_count: 122,
                    new_material_count: 143,
                    shared_material_count: 117,
                    material_overlap: 0.7905,
                  },
                },
              ],
            },
          });
        }
        return HttpResponse.json(response);
      }),
    );
    const user = userEvent.setup();
    const firstRender = renderWithProviders(<BomComparePane tool={tool} />);
    const { container } = firstRender;
    const inputs = Array.from(container.querySelectorAll<HTMLInputElement>('input[type="file"]'));

    await user.upload(inputs[0], new File(["old"], "old.xlsx"));
    await user.upload(inputs[1], new File(["new"], "new.xlsx"));
    await user.click(screen.getByRole("button", { name: "开始语义对比" }));

    expect(await screen.findByText("这是同一块板的不同版本吗？")).toBeInTheDocument();
    expect(screen.getByText("BOARD-OLD")).toBeInTheDocument();
    expect(screen.getByText("共享位号")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /实际贴装/ })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(
        window.localStorage.getItem("insta360_hw_tool_workspace:bom_compare"),
      ).toContain("comparison_scope");
    });

    firstRender.unmount();
    renderWithProviders(<BomComparePane tool={tool} />);
    expect(await screen.findByText("这是同一块板的不同版本吗？")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认按同一板卡不同版本对比" }));

    expect(await screen.findByRole("tab", { name: "实际贴装 1" })).toBeInTheDocument();
    expect(requestBodies).toHaveLength(2);
    expect(requestBodies[0].scope_confirmation).toBeUndefined();
    expect(requestBodies[1].scope_confirmation).toBe(true);
    expect(requestBodies[1].bom1).toBe("C:/upload/source.xlsx");
    expect(requestBodies[1].bom2).toBe("C:/upload/source.xlsx");
  });
});
