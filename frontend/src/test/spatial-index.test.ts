import { describe, expect, it } from "vitest";

import { GridSpatialIndex } from "../components/spatialIndex";


describe("GridSpatialIndex", () => {
  it("returns only points inside the requested viewport", () => {
    const index = new GridSpatialIndex(
      [
        { x: 5, y: 5, value: "R1" },
        { x: 15, y: 15, value: "R2" },
        { x: 100, y: 100, value: "R3" },
      ],
      10,
    );

    expect(
      index
        .query({ minX: 0, minY: 0, maxX: 20, maxY: 20 })
        .map((item) => item.value),
    ).toEqual(["R1", "R2"]);
  });
});
