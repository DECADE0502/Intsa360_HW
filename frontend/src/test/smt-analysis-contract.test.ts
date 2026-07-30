import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  SMT_ASSEMBLY_STATES,
  SMT_COORDINATE_SCOPES,
  SMT_PLACEMENT_ROLES,
  SMT_REGISTRATION_STATES,
  SMT_RUN_STATES,
  SMT_SOURCE_ROLES,
  type SmtAnalysisRunResponse,
} from "../tools/smtAnalysis/types";


function loadFixture(): SmtAnalysisRunResponse {
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


describe("SMT analysis v2 contract", () => {
  it("reads the shared backend fixture with the public TypeScript shape", () => {
    const run = loadFixture();

    expect(run.schema_version).toBe(2);
    expect(run.state).toBe("review");
    expect(run.coordinate_sets[0].scope_semantics).toBe("unknown");
    expect(run.registrations[0].confidence_state).toBe("needs_calibration");
    expect(run.placements[0].assembly_state).toBe("installed");
  });

  it("keeps every fixture enum value inside the exported contract lists", () => {
    const run = loadFixture();

    expect(SMT_RUN_STATES).toContain(run.state);
    run.sources.flatMap((source) => source.roles).forEach((role) => {
      expect(SMT_SOURCE_ROLES).toContain(role);
    });
    run.coordinate_sets.forEach((coordinateSet) => {
      expect(SMT_COORDINATE_SCOPES).toContain(coordinateSet.scope_semantics);
    });
    run.registrations.forEach((registration) => {
      expect(SMT_REGISTRATION_STATES).toContain(registration.confidence_state);
    });
    run.placements.forEach((placement) => {
      expect(SMT_PLACEMENT_ROLES).toContain(placement.role);
      expect(SMT_ASSEMBLY_STATES).toContain(placement.assembly_state);
    });
  });
});
