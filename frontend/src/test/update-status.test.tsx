import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { UpdateStatus } from "../components/UpdateStatus";
import { renderWithProviders } from "./render";
import { server } from "./server";

const NOT_PUBLISHED_MESSAGE = "当前仓库尚未发布与此客户端兼容的更新清单。";

function idleStatus() {
  return {
    bytes_downloaded: 0,
    bytes_per_second: 0,
    bytes_total: 0,
    cancellable: false,
    cancelled: false,
    cleanup_pending: false,
    cleanup_warning: "",
    done: false,
    error: "",
    failed: false,
    interrupted: false,
    job_id: "",
    log_tail: [],
    message: "",
    phase: "idle",
    progress: 0,
    recovery_required: false,
    rollback_error: "",
    rolled_back: false,
    running: false,
    status: "ok",
    step: "idle",
  };
}

describe("UpdateStatus", () => {
  it("reuses one update-check notification instead of stacking duplicates", async () => {
    const user = userEvent.setup();
    let checkCount = 0;
    server.use(
      http.get("/api/update/check", () => {
        checkCount += 1;
        return HttpResponse.json({
          can_update: false,
          display_remote: "",
          download_strategy: "none",
          error: "",
          expected_sha256: "",
          has_update: false,
          installed_runtime: true,
          integrity_status: "manifest_not_published",
          integrity_verified: false,
          message: NOT_PUBLISHED_MESSAGE,
          minimum_launcher_version: "",
          notice_status: "not_published",
          remote_revision: "",
          remote_revision_status: "not_published",
          remote_status: "not_published",
          remote_version: "",
          revision: "a".repeat(40),
          status: "ok",
          update_notice: {},
          update_reason: "manifest_not_published",
          version: "0.4.0",
        });
      }),
      http.get("/api/update/status", () => HttpResponse.json(idleStatus())),
    );

    renderWithProviders(<UpdateStatus version="0.4.0" />);
    await waitFor(() => expect(checkCount).toBe(1));

    const checkButton = screen.getByRole("button", { name: /检查更新$/ });
    await user.click(checkButton);
    await waitFor(() => expect(checkCount).toBe(2));
    await user.click(checkButton);
    await waitFor(() => expect(checkCount).toBe(3));

    await waitFor(() => {
      // One inline result plus one global notification.
      expect(screen.getAllByText(NOT_PUBLISHED_MESSAGE)).toHaveLength(2);
    });
  });
});
