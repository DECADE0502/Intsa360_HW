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
});

