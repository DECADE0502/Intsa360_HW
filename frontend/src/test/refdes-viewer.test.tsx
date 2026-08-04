import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RefdesList } from "../tools/refdes/RefdesList";
import { RefdesPageView } from "../tools/refdes/RefdesPageView";
import { groupMarks, type RefdesDrawingPage, type RefdesMark } from "../tools/refdes/types";
import { renderWithProviders } from "./render";


const PAGE_WIDTH = 1000;
const PAGE_HEIGHT = 800;

/** Build a mark from stage pixels, mirroring the normalised wire format. */
function mark(ref: string, stageX: number, stageY: number, order = 0): RefdesMark {
  const halfW = 8 / PAGE_WIDTH;
  const halfH = 5 / PAGE_HEIGHT;
  const x = stageX / PAGE_WIDTH;
  const y = stageY / PAGE_HEIGHT;
  return {
    ref,
    x,
    y,
    left: x - halfW,
    top: y - halfH,
    right: x + halfW,
    bottom: y + halfH,
    order,
  };
}

function page(marks: RefdesMark[]): RefdesDrawingPage {
  return {
    page_number: 1,
    pixel_width: PAGE_WIDTH,
    pixel_height: PAGE_HEIGHT,
    image_url: "/api/v1/refdes/drawings/dwg-1/pages/1/image",
    side_guess: "top",
    has_text_layer: true,
    ref_count: new Set(marks.map((item) => item.ref)).size,
    marks,
  };
}

function frameOf(container: HTMLElement) {
  const frame = container.querySelector('[role="application"]') as HTMLElement;
  frame.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 900, height: 620 }) as DOMRect;
  return frame;
}

function click(frame: HTMLElement, x: number, y: number) {
  fireEvent.pointerDown(frame, { button: 0, clientX: x, clientY: y, pointerId: 1 });
  fireEvent.pointerUp(frame, { button: 0, clientX: x, clientY: y, pointerId: 1 });
}

describe("位号图查看", () => {
  it("lists every refdes on the page in natural order", () => {
    const entries = groupMarks([
      mark("C10", 100, 100),
      mark("C2", 200, 100),
      mark("C1", 300, 100),
    ]);

    renderWithProviders(
      <RefdesList entries={entries} selectedRef="" markIndex={0} onSelect={() => {}} />,
    );

    expect(screen.getAllByRole("option").map((row) => row.textContent)).toEqual([
      "C1",
      "C2",
      "C10",
    ]);
  });

  it("locates a refdes when its row is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const entries = groupMarks([mark("R5", 100, 100), mark("C1", 200, 200)]);

    renderWithProviders(
      <RefdesList entries={entries} selectedRef="" markIndex={0} onSelect={onSelect} />,
    );
    await user.click(screen.getByTestId("refdes-row-R5"));

    expect(onSelect).toHaveBeenCalledWith("R5");
  });

  it("filters the list by search text", async () => {
    const user = userEvent.setup();
    const entries = groupMarks([
      mark("C1", 100, 100),
      mark("R5", 200, 100),
      mark("R6", 300, 100),
    ]);

    renderWithProviders(
      <RefdesList entries={entries} selectedRef="" markIndex={0} onSelect={() => {}} />,
    );
    await user.type(screen.getByLabelText("搜索位号"), "R");

    expect(screen.getAllByRole("option").map((row) => row.textContent)).toEqual([
      "R5",
      "R6",
    ]);
  });

  it("shows which instance of a repeated refdes is active", () => {
    const entries = groupMarks([mark("C1", 100, 100, 0), mark("C1", 500, 400, 1)]);

    renderWithProviders(
      <RefdesList entries={entries} selectedRef="C1" markIndex={1} onSelect={() => {}} />,
    );

    expect(within(screen.getByTestId("refdes-row-C1")).getByText("2/2")).toBeTruthy();
  });

  it("outlines only the selected refdes so the drawing stays readable", () => {
    const marks = [mark("C1", 100, 100), mark("R5", 400, 300)];

    const { container } = renderWithProviders(
      <RefdesPageView page={page(marks)} selectedRef="R5" target={null} onPick={() => {}} />,
    );

    const drawn = container.querySelectorAll("g[data-ref]");
    expect(drawn.length).toBe(1);
    expect(drawn[0].getAttribute("data-ref")).toBe("R5");
    expect(within(drawn[0] as unknown as HTMLElement).getByText("R5")).toBeTruthy();
  });

  it("picks a refdes when its position on the drawing is clicked", () => {
    const onPick = vi.fn();
    const { container } = renderWithProviders(
      <RefdesPageView
        page={page([mark("C1", 100, 100)])}
        selectedRef=""
        target={null}
        onPick={onPick}
      />,
    );
    const frame = frameOf(container);

    // The 1000x800 stage fits a 900x620 viewport, putting stage (100,100) at
    // screen (164, 95).
    click(frame, 164, 95);
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0][0].ref).toBe("C1");

    onPick.mockClear();
    click(frame, 820, 560);
    expect(onPick).not.toHaveBeenCalled();
  });

  it("does not pick while the drawing is being panned", () => {
    const onPick = vi.fn();
    const { container } = renderWithProviders(
      <RefdesPageView
        page={page([mark("C1", 100, 100)])}
        selectedRef=""
        target={null}
        onPick={onPick}
      />,
    );
    const frame = frameOf(container);

    fireEvent.pointerDown(frame, { button: 0, clientX: 164, clientY: 95, pointerId: 1 });
    fireEvent.pointerMove(frame, { clientX: 260, clientY: 190, pointerId: 1 });
    fireEvent.pointerUp(frame, { button: 0, clientX: 260, clientY: 190, pointerId: 1 });

    expect(onPick).not.toHaveBeenCalled();
  });

  it("loads exactly one page image and keeps it usable without refdes text", () => {
    const { container } = renderWithProviders(
      <RefdesPageView
        page={{ ...page([]), has_text_layer: false }}
        selectedRef=""
        target={null}
        onPick={() => {}}
      />,
    );

    const images = container.querySelectorAll("img");
    expect(images.length).toBe(1);
    expect(images[0].getAttribute("src")).toContain("/pages/1/image");
    expect(container.querySelectorAll("g[data-ref]").length).toBe(0);
  });
});
