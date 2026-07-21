import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, waitFor } from "@testing-library/react";

import { PcbCanvas } from "../components/PcbCanvas";
import type { SmtComponent } from "../api/client";


const outline: Array<Array<[number, number]>> = [
  [[0, 0], [100, 0], [100, 80], [0, 80]],
];

function component(ref: string, x_mm: number, y_mm: number, side: "top" | "bottom" = "top"): SmtComponent {
  return {
    ref,
    x_mm,
    y_mm,
    rotation: 0,
    side,
    footprint: "R0402",
    part_number: `PN-${ref}`,
    description: "Resistor",
    model: "10K",
    grade: "优选",
    status: "installed",
    high_risk: false,
  };
}

const components = [component("R1", 10, 20), component("R2", 70, 50, "bottom")];

function renderCanvas(overrides: Partial<React.ComponentProps<typeof PcbCanvas>> = {}) {
  return render(
    <PcbCanvas
      outline={outline}
      components={components}
      side="both"
      highlightedRefs={new Set()}
      {...overrides}
    />,
  );
}

function mockCanvasRect(svg: SVGSVGElement) {
  vi.spyOn(svg, "getBoundingClientRect").mockReturnValue({
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    right: 1100,
    bottom: 880,
    width: 1100,
    height: 880,
    toJSON: () => ({}),
  });
}

function matrixValues(transform: string): number[] {
  return transform
    .replace(/^matrix\(/, "")
    .replace(/\)$/, "")
    .split(/\s+/)
    .map(Number);
}


describe("PcbCanvas", () => {
  it("renders an outline ring as an SVG polygon", () => {
    const { container } = renderCanvas();

    expect(container.querySelector("polygon")?.getAttribute("points")).toBe("0,0 100,0 100,80 0,80");
  });

  it("places components at their board coordinates", () => {
    const { container } = renderCanvas();
    const rect = container.querySelector<SVGRectElement>('[data-ref="R1"]');

    expect(rect?.getAttribute("x")).toBe("9.5");
    expect(rect?.getAttribute("y")).toBe("19.5");
  });

  it("highlights refs supplied through controlled props", () => {
    const { container } = renderCanvas({ highlightedRefs: new Set(["R1"]) });

    expect(container.querySelector('[data-ref="R1"]')?.getAttribute("class")).toContain("pcb-comp--highlight");
  });

  it("fires onSelect with the clicked component ref", () => {
    const onSelect = vi.fn();
    const { container } = renderCanvas({ onSelect });

    fireEvent.click(container.querySelector('[data-ref="R1"]')!);

    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith("R1");
  });

  it("returns refs inside a dragged selection frame", () => {
    const onFrameSelect = vi.fn();
    const { container } = renderCanvas({ onFrameSelect });
    const svg = container.querySelector("svg")!;
    mockCanvasRect(svg);

    fireEvent.mouseDown(svg, { button: 0, clientX: 100, clientY: 200 });
    fireEvent.mouseMove(svg, { clientX: 200, clientY: 300 });
    fireEvent.mouseUp(svg, { button: 0, clientX: 200, clientY: 300 });

    expect(onFrameSelect).toHaveBeenCalledWith(["R1"]);
  });

  it("keeps the wheel focus point stable while zooming", async () => {
    const { container } = renderCanvas();
    const svg = container.querySelector("svg")!;
    mockCanvasRect(svg);

    fireEvent.wheel(svg, { clientX: 150, clientY: 240, deltaY: -100 });

    await waitFor(() => {
      const transform = container.querySelector('[data-testid="pcb-transform"]')?.getAttribute("transform") || "";
      const [scaleX, , , scaleY, tx, ty] = matrixValues(transform);
      expect(10 * scaleX + tx).toBeCloseTo(10, 2);
      expect(20 * scaleY + ty).toBeCloseTo(20, 2);
    });
  });
});
