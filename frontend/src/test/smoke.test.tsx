import { App as AntdApp, Button } from "antd";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { renderWithProviders } from "./render";
import { server } from "./server";

const navigationLabels = ["工作台", "BOM 工具", "网表工具", "插件管理", "历史记录", "系统状态"];

function AntdMessageProbe() {
  const { message } = AntdApp.useApp();

  return <Button onClick={() => message.success("测试消息已显示")}>显示测试消息</Button>;
}

describe("App startup", () => {
  beforeEach(() => {
    server.use(
      http.get("/api/tools", () =>
        HttpResponse.json({
          tools: [
            {
              category: "bom",
              description: "比较两个 BOM 文件",
              id: "bom_compare",
              name: "BOM 对比",
              status: "ready",
            },
          ],
        }),
      ),
      http.get("/api/capabilities", () =>
        HttpResponse.json({
          capabilities: [],
          platform: { cadence_menu: "insta360_HW", name: "Insta360 硬件提效平台" },
        }),
      ),
      http.get("/api/plugins", () =>
        HttpResponse.json({
          groups: { platform: [], system: [], user: [] },
          platform: { cadence_menu: "insta360_HW", name: "Insta360 硬件提效平台" },
          plugins: [],
          summary: { enabled: 0, platform: 0, system: 0, total: 0, user: 0 },
        }),
      ),
      http.get("/api/history", () => HttpResponse.json({ runs: [] })),
      http.get("/api/platform/status", () => HttpResponse.json({ status: "ok" })),
      http.get("/api/health", () =>
        HttpResponse.json({ status: "ok", service: "Insta360_HW", version: "0.4.0", revision: "test" }),
      ),
      http.get("/api/version", () => HttpResponse.json({ status: "ok", version: "0.4.0" })),
      http.get("/api/update/check", () =>
        HttpResponse.json({
          can_update: false,
          display_remote: "0.4.0",
          download_strategy: "none",
          error: "",
          expected_sha256: "",
          has_update: false,
          installed_runtime: true,
          integrity_status: "ok",
          integrity_verified: true,
          message: "",
          minimum_launcher_version: "0.4.0",
          notice_status: "none",
          remote_revision: "test",
          remote_revision_status: "ok",
          remote_status: "ok",
          remote_version: "0.4.0",
          revision: "test",
          status: "ok",
          update_notice: {},
          update_reason: "",
          version: "0.4.0",
        }),
      ),
      http.get("/api/update/status", () =>
        HttpResponse.json({
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
        }),
      ),
    );
  });

  it("renders Chinese navigation after startup APIs settle", async () => {
    renderWithProviders(<App />);

    for (const label of navigationLabels) {
      expect(await screen.findByText(label, { exact: true })).toBeInTheDocument();
    }

    expect(await screen.findByRole("menuitem", { name: "BOM 对比" })).toBeInTheDocument();
    expect(await screen.findByText(/v0\.4\.0 · 运行中/)).toBeInTheDocument();
  });

  it("keeps the service online when only the platform summary is slow or unavailable", async () => {
    server.use(
      http.get("/api/platform/status", () =>
        HttpResponse.json({ status: "error", error: "summary timeout" }, { status: 503 }),
      ),
    );

    renderWithProviders(<App />);

    expect(await screen.findByText(/v0\.4\.0 · 运行中/)).toBeInTheDocument();
    expect(screen.queryByText("后端服务已断开")).not.toBeInTheDocument();
  });

  it("reports an incomplete catalog and retries it without restarting the platform", async () => {
    const user = userEvent.setup();
    let toolRequests = 0;
    server.use(
      http.get("/api/tools", () => {
        toolRequests += 1;
        if (toolRequests === 1) {
          return HttpResponse.json({ status: "error", error: "temporary catalog failure" }, { status: 503 });
        }
        return HttpResponse.json({
          tools: [
            {
              category: "bom",
              description: "比较两个 BOM 文件",
              id: "bom_compare",
              name: "BOM 对比",
              status: "ready",
            },
          ],
        });
      }),
    );

    renderWithProviders(<App />);

    expect(await screen.findByText("平台数据加载不完整")).toBeInTheDocument();
    expect(screen.getByText(/工具清单/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /重试加载/ }));

    expect(await screen.findByRole("menuitem", { name: "BOM 对比" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("平台数据加载不完整")).not.toBeInTheDocument());
  });
});

describe("frontend test foundation", () => {
  it("exposes Ant Design message context through the shared renderer", async () => {
    const user = userEvent.setup();

    renderWithProviders(<AntdMessageProbe />);

    await user.click(screen.getByRole("button", { name: "显示测试消息" }));

    expect(await screen.findByText("测试消息已显示")).toBeInTheDocument();
  });
});
