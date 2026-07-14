import { App as AntdApp, Button } from "antd";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "./render";

const navigationLabels = ["工作台", "BOM 工具", "网表工具"];

function PlatformShellProbe() {
  const { message } = AntdApp.useApp();

  return (
    <>
      <nav aria-label="平台导航">
        {navigationLabels.map((label) => (
          <a href={`#${label}`} key={label}>
            {label}
          </a>
        ))}
      </nav>
      <Button onClick={() => message.success("测试消息已显示")}>显示测试消息</Button>
    </>
  );
}

describe("frontend test foundation", () => {
  it("renders Chinese navigation and exposes Ant Design message context", async () => {
    const user = userEvent.setup();

    renderWithProviders(<PlatformShellProbe />);

    expect(screen.getByRole("navigation", { name: "平台导航" })).toBeInTheDocument();
    for (const label of navigationLabels) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }

    await user.click(screen.getByRole("button", { name: "显示测试消息" }));

    expect(await screen.findByText("测试消息已显示")).toBeInTheDocument();
  });
});
