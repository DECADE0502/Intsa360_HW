import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PluginInfo } from "../api/client";
import { ScriptManager } from "../platform/ScriptManager";
import { renderWithProviders } from "./render";

function plugin(id: string, activation: PluginInfo["activation"]): PluginInfo {
  return {
    activation,
    id,
    manageable: true,
    menu: "insta360_HW",
    name: id,
    readonly: false,
    show_in_cadence: true,
    show_in_platform: true,
    source: "platform",
    status: "available",
    type: "cadence_tcl",
  };
}

describe("ScriptManager activation guidance", () => {
  it("distinguishes restart-only shortcuts from hot-reloadable scripts", () => {
    renderWithProviders(
      <ScriptManager
        plugins={{
          platform: [plugin("快速 NC 切换", "restart"), plugin("显示 GND 网络名", "hot_reload")],
          system: [],
          user: [],
        }}
        onPluginChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByText("需重启 Capture")).toBeInTheDocument();
    expect(screen.getByText("支持热更新")).toBeInTheDocument();
    expect(screen.getByText(/快速 NC 切换需重启/)).toBeInTheDocument();
  });
});
