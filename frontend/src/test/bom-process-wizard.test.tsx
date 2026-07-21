import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProcessMaterialConfirm } from "../tools/BomProcessWizard";
import { renderWithProviders } from "./render";

const candidates = [
  {
    key: "TP-PN|TP5",
    part_number: "TP-PN",
    refs: ["TP5"],
    description: "测试点 探针",
    name: "探针",
    matched_keyword: "测试点",
  },
];

describe("BOM process material confirmation", () => {
  it("shows the matched process keyword and updates selected keeps", async () => {
    const user = userEvent.setup();
    const onSelectedKeysChange = vi.fn();
    renderWithProviders(
      <ProcessMaterialConfirm
        candidates={candidates}
        selectedKeys={[]}
        onSelectedKeysChange={onSelectedKeysChange}
        onApply={vi.fn()}
        onDefault={vi.fn()}
        running={false}
      />,
    );

    expect(screen.getByText("测试点", { exact: true })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /TP5/ }));
    expect(onSelectedKeysChange).toHaveBeenCalledWith(["TP-PN|TP5"]);
  });

  it("persists process material keeps in the v2 workspace", () => {
    const source = readFileSync(resolve(process.cwd(), "src", "tools", "BomProcessWizard.tsx"), "utf-8");
    expect(source).toContain("processMaterialKeeps: [] as string[]");
    expect(source).toMatch(/setWorkspace\(\{[^}]*processMaterialKeeps/s);
    expect(source).toContain('{ heavyKeys: ["pres", "rres"] }');
  });
});
