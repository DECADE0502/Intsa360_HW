import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BomProcessWizard } from "../tools/BomProcessWizard";
import { renderWithProviders } from "./render";

describe("BOM Capture export config", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/?tool=bom_process");
  });

  it("shows and copies the complete sampling fields on the source page", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    renderWithProviders(<BomProcessWizard />);

    expect(screen.getByText("Capture 手动导出字段")).toBeInTheDocument();
    const config = screen.getByDisplayValue(/\{器件描述（旧）\}/) as HTMLTextAreaElement;
    expect(config.value).toContain("{OriginalSymbolOrigin}");
    expect(config.value).toContain("{Color}");
    await user.click(screen.getByRole("button", { name: /复制字段/ }));

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText.mock.calls[0][0]).toContain("{制造商}\\t{datasheet}");
    expect(await screen.findByRole("button", { name: /已复制/ })).toBeInTheDocument();
  });

  it("falls back to a selected textarea when the Clipboard API is unavailable", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
    const legacyCopy = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, "execCommand", { configurable: true, value: legacyCopy });

    renderWithProviders(<BomProcessWizard />);
    await user.click(screen.getByRole("button", { name: /复制字段/ }));

    expect(legacyCopy).toHaveBeenCalledWith("copy");
    expect(await screen.findByRole("button", { name: /已复制/ })).toBeInTheDocument();
  });
});
