import { afterEach, describe, expect, it, vi } from "vitest";

import { runSmtLayout, type SmtLayoutResponse } from "../api/client";


const fixture: SmtLayoutResponse = {
  status: "ok",
  tool: "smt_layout",
  outputs: [],
  board: {
    outline_rings: [[[0, 0], [100, 0], [100, 80], [0, 80]]],
    bbox_mm: [0, 0, 100, 80],
    source: "dxf",
  },
  components: [
    {
      ref: "R1",
      x_mm: 10,
      y_mm: 20,
      rotation: 90,
      side: "top",
      footprint: "R0402",
      part_number: "PN-1",
      description: "Resistor",
      model: "10K",
      grade: "preferred",
      status: "installed",
      high_risk: false,
    },
  ],
  nc_summary: {
    total: 0,
    refs: [],
    confirmed_refs: [],
    candidate_refs: [],
    unverified_refs: [],
    conflict_refs: [],
    inference_mode: "without_netlist",
    explicit_summary_used: false,
  },
  sanity: { status: "skipped_no_netlist" },
  fai_table: { headers: ["Reference"], rows: [["R1"]] },
  summary: {
    total_components: 1,
    top_count: 1,
    bottom_count: 0,
    nc_count: 0,
    high_risk_count: 0,
  },
};


describe("SMT layout API contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps the typed response fixture aligned with the backend payload", () => {
    expect(fixture.tool).toBe("smt_layout");
    expect(fixture.components[0].ref).toBe("R1");
  });

  it("runs the SMT layout tool through the shared API client", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok", token: "session-one" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(fixture), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await runSmtLayout({
      smt_folder: "C:/project/SMT",
      processed_bom: "C:/project/BOM.xlsx",
    });

    expect(response.summary?.total_components).toBe(1);
    expect(fetchMock.mock.calls[1][0]).toBe("/api/tools/smt_layout/run");
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      smt_folder: "C:/project/SMT",
      processed_bom: "C:/project/BOM.xlsx",
    });
  });
});
