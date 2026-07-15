import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { HistoryBomPicker } from "../components/HistoryBomPicker";
import { renderWithProviders } from "./render";
import { server } from "./server";

const ASSET_PATH = "C:/Program Files/Insta360/HWAgent/data/outputs/bom/Board_PLM_BOM.xlsx";

function useAssetResponse() {
  let requestCount = 0;
  server.use(
    http.get("/api/assets", () => {
      requestCount += 1;
      return HttpResponse.json({
        status: "ok",
        groups: {
          processed_bom: [
            {
              id: "asset-1",
              kind: "processed_bom",
              name: "Board_PLM_BOM.xlsx",
              path: ASSET_PATH,
              format: "PLM",
              time: "2026-07-15 10:00:00",
            },
          ],
        },
        summary: { processed_bom: 1 },
      });
    }),
  );
  return () => requestCount;
}

async function chooseAsset(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /选择历史 BOM$/ }));
  const combobox = screen.getByRole("combobox");
  await user.click(combobox);
  await user.click(await screen.findByText("Board_PLM_BOM.xlsx"));
}

describe("HistoryBomPicker", () => {
  it("keeps a modal selection as a draft until the user confirms", async () => {
    const getRequestCount = useAssetResponse();
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<HistoryBomPicker onChange={onChange} />);
    await waitFor(() => expect(getRequestCount()).toBe(1));

    await chooseAsset(user);
    expect(onChange).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /取\s*消/ }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("commits the selected historical BOM when confirmed", async () => {
    const getRequestCount = useAssetResponse();
    const onChange = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<HistoryBomPicker onChange={onChange} />);
    await waitFor(() => expect(getRequestCount()).toBe(1));

    await chooseAsset(user);
    await user.click(screen.getByRole("button", { name: "使用所选 BOM" }));

    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenCalledWith(ASSET_PATH);
  });

  it("reports asset loading failures instead of leaving an unhandled rejection", async () => {
    server.use(
      http.get("/api/assets", () => HttpResponse.json({ error: "历史库暂时不可用" }, { status: 503 })),
    );

    renderWithProviders(<HistoryBomPicker onChange={() => {}} />);

    expect(await screen.findByText("历史库暂时不可用")).toBeInTheDocument();
  });
});
