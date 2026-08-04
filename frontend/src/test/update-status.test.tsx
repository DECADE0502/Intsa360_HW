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
    started_at: "",
    updated_at: "",
    detail_current: 0,
    detail_total: 0,
    detail_unit: "",
    detail_bytes_current: 0,
    detail_bytes_total: 0,
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

function runningStatus() {
  return {
    ...idleStatus(),
    cancellable: true,
    job_id: "update-job-1",
    message: "正在下载更新。",
    phase: "downloading",
    progress: 5,
    running: true,
    step: "downloading",
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

  it("waits for the active status poll before scheduling another one", async () => {
    let statusCalls = 0;
    let releasePoll: (() => void) | undefined;
    const blockedPoll = new Promise<void>((resolve) => {
      releasePoll = resolve;
    });
    server.use(
      http.get("/api/update/check", () =>
        HttpResponse.json({
          can_update: false,
          display_remote: "0.4.0",
          download_strategy: "none",
          error: "",
          expected_sha256: "",
          has_update: false,
          installed_runtime: true,
          integrity_status: "verified",
          integrity_verified: true,
          message: "已是最新版本。",
          minimum_launcher_version: "",
          notice_status: "ok",
          remote_revision: "a".repeat(40),
          remote_revision_status: "same",
          remote_status: "ok",
          remote_version: "0.4.0",
          revision: "a".repeat(40),
          status: "ok",
          update_notice: {},
          update_reason: "up_to_date",
          version: "0.4.0",
        }),
      ),
      http.get("/api/update/status", async () => {
        statusCalls += 1;
        if (statusCalls > 1) await blockedPoll;
        return HttpResponse.json(runningStatus());
      }),
    );

    renderWithProviders(<UpdateStatus version="0.4.0" />);
    await waitFor(() => expect(statusCalls).toBe(2));
    await new Promise((resolve) => window.setTimeout(resolve, 2_200));

    try {
      expect(statusCalls).toBe(2);
    } finally {
      releasePoll?.();
    }
  });

  it("shows elapsed time, file counts, and recent update activity", async () => {
    const started = new Date(Date.now() - 65_000).toISOString();
    const status = {
      ...runningStatus(),
      cancellable: false,
      detail_current: 42,
      detail_total: 100,
      detail_unit: "files",
      detail_bytes_current: 1024 * 1024,
      detail_bytes_total: 4 * 1024 * 1024,
      bytes_per_second: 512 * 1024,
      log_tail: ["下载与 SHA256 校验完成，开始展开运行包。", "运行包展开 20%。"],
      message: "正在安全展开候选运行时并同步计算完整性指纹。",
      phase: "staging",
      progress: 63,
      started_at: started,
      updated_at: new Date().toISOString(),
    };
    server.use(
      http.get("/api/update/check", () =>
        HttpResponse.json({
          can_update: false,
          display_remote: "0.5.3",
          download_strategy: "none",
          error: "",
          expected_sha256: "",
          has_update: false,
          installed_runtime: true,
          integrity_status: "verified",
          integrity_verified: true,
          message: "已是最新版本。",
          minimum_launcher_version: "",
          notice_status: "ok",
          remote_revision: "a".repeat(40),
          remote_revision_status: "same",
          remote_status: "ok",
          remote_version: "0.5.3",
          revision: "a".repeat(40),
          status: "ok",
          update_notice: {},
          update_reason: "up_to_date",
          version: "0.5.3",
        }),
      ),
      http.get("/api/update/status", () => HttpResponse.json(status)),
    );

    renderWithProviders(<UpdateStatus version="0.5.3" />);

    expect(await screen.findByText("执行明细")).toBeInTheDocument();
    expect(screen.getByText(/已用时 1 分/)).toBeInTheDocument();
    expect(screen.getByText("已展开文件 42 / 100")).toBeInTheDocument();
    expect(screen.getByText("当前阶段：暂存")).toBeInTheDocument();
    expect(screen.getByText(/已展开 1.0 MB \/ 4.0 MB/)).toBeInTheDocument();
    expect(screen.getAllByText("正在安全展开候选运行时并同步计算完整性指纹。").length).toBeGreaterThan(0);
  });
});
