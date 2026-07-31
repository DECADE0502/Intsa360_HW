import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SmtBoardViewport } from "../components/SmtBoardViewport";
import { AnchorEditor } from "../tools/smtAnalysis/AnchorEditor";
import { IdentificationStep } from "../tools/smtAnalysis/IdentificationStep";
import { RegistrationStep } from "../tools/smtAnalysis/RegistrationStep";
import { ReviewWorkbench } from "../tools/smtAnalysis/ReviewWorkbench";
import { SmtLayoutPane } from "../tools/SmtLayoutPane";
import type {
  SmtAnalysisRunResponse,
  SmtCoordinateOccurrence,
} from "../tools/smtAnalysis/types";
import { renderWithProviders } from "./render";


function loadRun(): SmtAnalysisRunResponse {
  const path = resolve(
    process.cwd(),
    "..",
    "tests",
    "fixtures",
    "smt",
    "contracts",
    "analysis_run_v2.json",
  );
  return JSON.parse(readFileSync(path, "utf-8")) as SmtAnalysisRunResponse;
}


describe("SMT analysis workflow components", () => {
  it("shows real page previews and blocks duplicate side assignments", async () => {
    const user = userEvent.setup();
    const run = loadRun();
    run.drawing_pages.push({
      ...run.drawing_pages[0],
      page_id: "page-top-duplicate",
      page_number: 2,
      side_candidate: "unknown",
    });
    const onConfirm = vi.fn();
    renderWithProviders(
      <IdentificationStep
        run={run}
        busy={false}
        error=""
        onConfirm={onConfirm}
      />,
    );

    expect(
      screen.getByRole("img", { name: /assembly\.pdf 第 1 页/ }),
    ).toHaveAttribute("src", run.drawing_pages[0].preview_url);
    const topChoices = screen.getAllByText("正面");
    expect(topChoices).toHaveLength(2);
    await user.click(topChoices[1]);

    expect(
      screen.getByText("同一面选择了多个位号图页面，请保留一个。"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /确认识别结果/ }),
    ).toBeDisabled();
  });

  it("creates an anchor by pairing a coordinate ref with a drawing click", async () => {
    const user = userEvent.setup();
    const run = loadRun();
    const onChange = vi.fn();
    renderWithProviders(
      <AnchorEditor
        page={run.drawing_pages[0]}
        occurrences={run.coordinate_sets[0].occurrences}
        anchors={[]}
        onChange={onChange}
      />,
    );

    await user.click(
      screen.getByRole("combobox", { name: "选择校准位号" }),
    );
    await user.click(await screen.findByText("R1 · R0402"));
    const editor = screen.getByRole("img", { name: "位号图锚点编辑器" });
    vi.spyOn(editor, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 400,
      bottom: 300,
      width: 400,
      height: 300,
      toJSON: () => ({}),
    });
    fireEvent.click(editor, { clientX: 100, clientY: 75 });

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        ref: "R1",
        coordinate_x: 10,
        coordinate_y: 20,
        image_x: 400,
        image_y: 300,
        source: "user",
      }),
    ]);
  });

  it("does not calculate registration with fewer than three anchors", () => {
    const run = loadRun();
    run.registrations = [];
    const base = run.coordinate_sets[0].occurrences[0];
    run.coordinate_sets[0].occurrences = [
      base,
      {
        ...base,
        occurrence_id: "occ-R2",
        raw_ref: "R2",
        ref: "R2",
        raw_x: "30",
        normalized_x: 30,
      },
      {
        ...base,
        occurrence_id: "occ-R3",
        raw_ref: "R3",
        ref: "R3",
        raw_y: "40",
        normalized_y: 40,
      },
    ] as SmtCoordinateOccurrence[];
    renderWithProviders(
      <RegistrationStep
        run={run}
        busy={false}
        error=""
        onRegister={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: "计算叠加预览" }),
    ).toBeDisabled();
  });

  it("renders the PDF page directly and overlays only coordinate hotspots", async () => {
    const run = loadRun();
    const onSelect = vi.fn();
    renderWithProviders(
      <SmtBoardViewport run={run} side="top" onSelect={onSelect} />,
    );

    const viewport = screen.getByRole("img", {
      name: "正面 PDF 位号图与坐标热点",
    });
    expect(viewport.tagName).toBe("DIV");
    expect(viewport).toHaveAttribute("data-pdf-source", "true");
    expect(viewport).toHaveAttribute("data-marker-count", "1");
    expect(viewport.querySelector("img")).toHaveAttribute(
      "src",
      run.drawing_pages[0].preview_url,
    );
    expect(viewport.querySelector('[data-ref="R1"]')).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: "器件区域" }),
    ).toBeChecked();
    vi.spyOn(viewport, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 900,
      bottom: 560,
      width: 900,
      height: 560,
      toJSON: () => ({}),
    });
    fireEvent.pointerDown(viewport, {
      button: 0,
      pointerId: 1,
      clientX: 194,
      clientY: 131,
    });
    fireEvent.pointerUp(viewport, {
      button: 0,
      pointerId: 1,
      clientX: 194,
      clientY: 131,
    });
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ ref: "R1" }),
    );
  });

  it("does not revive the legacy synthetic board from an old saved result", () => {
    window.localStorage.setItem(
      "insta360_hw_tool_workspace:smt_layout",
      JSON.stringify({
        data: {
          historyBom: "D:/old/processed.xlsx",
          result: { board: { outline_rings: [] }, components: [] },
        },
      }),
    );

    renderWithProviders(<SmtLayoutPane />);

    expect(
      screen.getByRole("button", { name: "选择 SMT 资料目录" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "PCB 布局视图" })).not.toBeInTheDocument();
    window.localStorage.removeItem("insta360_hw_tool_workspace:smt_layout");
  });

  it("keeps thousand-part review lists virtualized", () => {
    const run = loadRun();
    const base = run.placements[0];
    run.placements = Array.from({ length: 1200 }, (_, index) => ({
      ...base,
      placement_id: `placement-R${index + 1}`,
      ref: `R${index + 1}`,
      image_x: 120 + (index % 40) * 5,
      image_y: 160 + Math.floor(index / 40) * 5,
      assembly_state: "candidate_nc" as const,
      blocking_reasons: ["坐标范围尚未确认"],
    }));
    run.summary.placement_count = 1200;
    run.summary.candidate_nc_count = 1200;
    run.summary.unresolved_count = 1200;

    renderWithProviders(
      <ReviewWorkbench
        run={run}
        busy={false}
        onDecide={vi.fn().mockResolvedValue(undefined)}
        onBatchDecide={vi.fn().mockResolvedValue(undefined)}
        onComplete={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getAllByRole("option").length).toBeLessThan(80);
    expect(
      screen.queryByTestId("smt-placement-R1200"),
    ).not.toBeInTheDocument();
  });

  it("keeps conflicting and candidate rows out of one bulk decision", async () => {
    const user = userEvent.setup();
    const run = loadRun();
    run.placements = [
      {
        ...run.placements[0],
        placement_id: "placement-R1-candidate",
        ref: "R1",
        assembly_state: "candidate_nc",
        blocking_reasons: ["坐标范围尚未确认"],
      },
      {
        ...run.placements[0],
        placement_id: "placement-R2-conflict",
        ref: "R2",
        assembly_state: "conflicting",
        blocking_reasons: ["BOM 与坐标证据冲突"],
      },
    ];
    run.summary.placement_count = 2;
    run.summary.candidate_nc_count = 1;
    run.summary.unresolved_count = 2;
    const onDecide = vi.fn().mockResolvedValue(undefined);
    const onBatchDecide = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <ReviewWorkbench
        run={run}
        busy={false}
        onDecide={onDecide}
        onBatchDecide={onBatchDecide}
        onComplete={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    for (const ref of ["R1", "R2"]) {
      await user.click(
        within(screen.getByTestId(`smt-placement-${ref}`)).getByRole(
          "checkbox",
        ),
      );
    }
    expect(
      screen.getByRole("button", { name: "批量确认装机" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "批量确认 NC" }),
    ).toBeDisabled();

    await user.click(
      within(screen.getByTestId("smt-placement-R1")).getByText("R1"),
    );
    await user.click(screen.getByRole("button", { name: "确认为 NC" }));
    expect(onDecide).toHaveBeenCalledWith(
      "placement-R1-candidate",
      expect.objectContaining({ action: "confirm_nc" }),
    );
  });
});
