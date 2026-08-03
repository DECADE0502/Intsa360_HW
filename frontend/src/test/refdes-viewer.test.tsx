import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RefdesCanvas } from "../tools/refdesViewer/RefdesCanvas";
import { RefdesList } from "../tools/refdesViewer/RefdesList";
import type {
  RefdesEntry,
  RefdesOccurrence,
  RefdesPage,
} from "../tools/refdesViewer/types";
import { renderWithProviders } from "./render";


function occurrence(
  ref: string,
  x: number,
  y: number,
  suffix = "a",
): RefdesOccurrence {
  return {
    occurrence_id: `${ref}-${suffix}`,
    ref,
    x,
    y,
    left: x - 8,
    top: y - 5,
    right: x + 8,
    bottom: y + 5,
  };
}

function page(occurrences: RefdesOccurrence[]): RefdesPage {
  return {
    page_id: "page-1",
    page_number: 1,
    pixel_width: 1000,
    pixel_height: 800,
    preview_url: "/api/v1/refdes-viewer/docs/doc-1/pages/page-1/preview",
    side_guess: "top",
    text_layer: "vector",
    ref_count: new Set(occurrences.map((item) => item.ref)).size,
    occurrence_count: occurrences.length,
    occurrences,
  };
}

function entries(occurrences: RefdesOccurrence[]): RefdesEntry[] {
  const grouped = new Map<string, RefdesOccurrence[]>();
  occurrences.forEach((item) => {
    const bucket = grouped.get(item.ref);
    if (bucket) bucket.push(item);
    else grouped.set(item.ref, [item]);
  });
  return Array.from(grouped.entries())
    .map(([ref, items]) => ({ ref, occurrences: items }))
    .sort((left, right) =>
      left.ref.localeCompare(right.ref, undefined, { numeric: true }),
    );
}

describe("位号图查看", () => {
  it("lists every refdes printed on the page in natural order", () => {
    const list = entries([
      occurrence("C10", 100, 100),
      occurrence("C2", 200, 100),
      occurrence("C1", 300, 100),
    ]);

    renderWithProviders(
      <RefdesList
        entries={list}
        selectedRef=""
        occurrenceIndex={0}
        onSelect={() => {}}
      />,
    );

    const rows = screen.getAllByRole("option");
    expect(rows.map((row) => row.textContent)).toEqual(["C1", "C2", "C10"]);
  });

  it("locates a refdes when its row is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const list = entries([occurrence("R5", 100, 100), occurrence("C1", 200, 200)]);

    renderWithProviders(
      <RefdesList
        entries={list}
        selectedRef=""
        occurrenceIndex={0}
        onSelect={onSelect}
      />,
    );
    await user.click(screen.getByTestId("refdes-row-R5"));

    expect(onSelect).toHaveBeenCalledWith("R5");
  });

  it("filters the list by search text", async () => {
    const user = userEvent.setup();
    const list = entries([
      occurrence("C1", 100, 100),
      occurrence("R5", 200, 100),
      occurrence("R6", 300, 100),
    ]);

    renderWithProviders(
      <RefdesList
        entries={list}
        selectedRef=""
        occurrenceIndex={0}
        onSelect={() => {}}
      />,
    );
    await user.type(screen.getByLabelText("搜索位号"), "R");

    const rows = screen.getAllByRole("option");
    expect(rows.map((row) => row.textContent?.replace(/×\d+/, ""))).toEqual([
      "R5",
      "R6",
    ]);
  });

  it("shows which instance is active for a repeated refdes", () => {
    const list = entries([
      occurrence("C1", 100, 100, "a"),
      occurrence("C1", 500, 400, "b"),
    ]);

    renderWithProviders(
      <RefdesList
        entries={list}
        selectedRef="C1"
        occurrenceIndex={1}
        onSelect={() => {}}
      />,
    );

    expect(
      within(screen.getByTestId("refdes-row-C1")).getByText("2/2"),
    ).toBeTruthy();
  });

  it("renders a marker for every refdes and highlights the selected one", () => {
    const occurrences = [occurrence("C1", 100, 100), occurrence("R5", 400, 300)];

    const { container } = renderWithProviders(
      <RefdesCanvas
        page={page(occurrences)}
        selectedRef="R5"
        target={null}
        onSelect={() => {}}
      />,
    );

    expect(container.querySelectorAll("g[data-ref]").length).toBe(2);
    const selected = container.querySelector('g[data-ref="R5"]');
    expect(selected?.getAttribute("data-selected")).toBe("true");
    expect(within(selected as unknown as HTMLElement).getByText("R5")).toBeTruthy();
  });

  it("selects a refdes when its marker is clicked on the drawing", () => {
    const onSelect = vi.fn();
    const target = occurrence("C1", 100, 100);
    const { container } = renderWithProviders(
      <RefdesCanvas
        page={page([target])}
        selectedRef=""
        target={null}
        onSelect={onSelect}
      />,
    );

    const frame = container.querySelector('[role="application"]') as HTMLElement;
    frame.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 900, height: 600 }) as DOMRect;

    // The 1000x800 page is fitted into the 900x600 viewport, so image point
    // (100,100) lands at screen (174,93).
    const click = (x: number, y: number) => {
      fireEvent.pointerDown(frame, { button: 0, clientX: x, clientY: y, pointerId: 1 });
      fireEvent.pointerUp(frame, { button: 0, clientX: x, clientY: y, pointerId: 1 });
    };

    click(174, 93);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].ref).toBe("C1");

    onSelect.mockClear();
    click(800, 550);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("does not select while the drawing is being panned", () => {
    const onSelect = vi.fn();
    const { container } = renderWithProviders(
      <RefdesCanvas
        page={page([occurrence("C1", 100, 100)])}
        selectedRef=""
        target={null}
        onSelect={onSelect}
      />,
    );

    const frame = container.querySelector('[role="application"]') as HTMLElement;
    frame.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 900, height: 600 }) as DOMRect;

    fireEvent.pointerDown(frame, { button: 0, clientX: 174, clientY: 93, pointerId: 1 });
    fireEvent.pointerMove(frame, { clientX: 260, clientY: 180, pointerId: 1 });
    fireEvent.pointerUp(frame, { button: 0, clientX: 260, clientY: 180, pointerId: 1 });

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("keeps the drawing usable when the page carries no refdes text", () => {
    const { container } = renderWithProviders(
      <RefdesCanvas
        page={{ ...page([]), text_layer: "absent" }}
        selectedRef=""
        target={null}
        onSelect={() => {}}
      />,
    );

    expect(container.querySelector("img")?.getAttribute("src")).toContain(
      "/preview",
    );
    expect(container.querySelectorAll("g[data-ref]").length).toBe(0);
  });
});
