import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SmtLayoutPane } from "../tools/SmtLayoutPane";
import { renderWithProviders } from "./render";


describe("SMT layout pane skeleton", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the three Chinese workflow tabs", () => {
    renderWithProviders(<SmtLayoutPane />);

    expect(screen.getByRole("tab", { name: "NC 布局对照" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "首件核对表" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "三向一致性" })).toBeInTheDocument();
  });

  it("disables the sanity tab and explains the missing netlist", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SmtLayoutPane />);

    const sanityTab = screen.getByRole("tab", { name: "三向一致性" });
    expect(sanityTab).toHaveAttribute("aria-disabled", "true");
    await user.hover(screen.getByText("三向一致性"));
    expect(await screen.findByText("需网表文件夹")).toBeInTheDocument();
  });

  it("persists the result as a v2 heavy workspace key", () => {
    const source = readFileSync(resolve(process.cwd(), "src", "tools", "SmtLayoutPane.tsx"), "utf-8");

    expect(source).toContain('{ heavyKeys: ["result"] }');
  });
});
