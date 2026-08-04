import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Alert, App as AntdApp, Button, ConfigProvider, Drawer, Layout, Menu, Spin, Typography, type MenuProps } from "antd";
import { CloseOutlined, MenuOutlined, ReloadOutlined } from "@ant-design/icons";
import zhCN from "antd/locale/zh_CN";
import {
  fetchCapabilities,
  fetchHistory,
  fetchPlatformStatus,
  fetchPlugins,
  fetchServiceHealth,
  fetchTools,
  HISTORY_UPDATED_EVENT,
  type Capability,
  type HistoryRun,
  type PluginInfo,
  type ToolInfo,
} from "./api/client";
import { toUserMessage } from "./api/errors";
import { HistoryView } from "./platform/HistoryView";
import { PlatformHome } from "./platform/PlatformHome";
import { ScriptManager } from "./platform/ScriptManager";
import { SystemStatus } from "./platform/SystemStatus";
import { UpdateStatus } from "./components/UpdateStatus";
import "./styles.css";

const { Sider, Content } = Layout;
type PluginGroups = { system: PluginInfo[]; platform: PluginInfo[]; user: PluginInfo[] };
const BomProcessWizard = lazy(() => import("./tools/BomProcessWizard").then((module) => ({ default: module.BomProcessWizard })));
const BomRiskPane = lazy(() => import("./tools/BomRiskPane").then((module) => ({ default: module.BomRiskPane })));
const LegacyToolPane = lazy(() => import("./tools/LegacyToolPane").then((module) => ({ default: module.LegacyToolPane })));
const SmtViewPane = lazy(() => import("./tools/smtView/SmtViewPane").then((module) => ({ default: module.SmtViewPane })));
const RECONNECT_PROTOCOL_URL = "insta360-hw://reconnect";
const WORKSPACE_TRUNCATED_EVENT = "insta360_hw:workspace-truncated";

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function WorkspacePersistenceNotice() {
  const { notification } = AntdApp.useApp();

  useEffect(() => {
    const onTruncated = () => {
      notification.warning({
        message: "结果过大未持久化",
        description: "刷新页面会丢失该结果，请重新运行工具或直接下载生成的文件。",
        key: "workspace-truncated",
      });
    };
    window.addEventListener(WORKSPACE_TRUNCATED_EVENT, onTruncated);
    return () => window.removeEventListener(WORKSPACE_TRUNCATED_EVENT, onTruncated);
  }, [notification]);

  return null;
}

function PlatformNavigation({
  active,
  items,
  version,
  serviceOnline,
  onSelect,
  onClose,
}: {
  active: string;
  items: MenuProps["items"];
  version?: string;
  serviceOnline: boolean;
  onSelect: (key: string) => void;
  onClose?: () => void;
}) {
  return (
    <>
      <div className="app-brand">
        <img className="app-brand-logo" src="/assets/insta360_logo.png" alt="Insta360" />
        <div className="app-brand-copy">
          <Typography.Text className="app-brand-title">硬件提效平台</Typography.Text>
          <div className="app-brand-meta">
            <span className={`app-brand-dot ${serviceOnline ? "" : "app-brand-dot--offline"}`} />
            v{version || "-"} · {serviceOnline ? "运行中" : "服务离线"}
          </div>
        </div>
        {onClose ? (
          <Button
            type="text"
            className="app-mobile-nav-close"
            icon={<CloseOutlined />}
            aria-label="关闭平台导航"
            onClick={onClose}
          />
        ) : null}
      </div>
      <Menu
        mode="inline"
        selectedKeys={[active]}
        items={items}
        onClick={({ key }) => onSelect(key)}
        className="app-menu"
      />
      <div className="app-footer">
        <UpdateStatus version={version || ""} />
        <div className="app-footer-meta">
          <a href="/api/logs/download" className="app-footer-link">
            导出全部日志
          </a>
          <span className="app-footer-sep">·</span>
          <a
            href="https://github.com/DECADE0502/Intsa360_HW"
            target="_blank"
            rel="noopener"
            className="app-footer-link"
          >
            源码仓库
          </a>
        </div>
        <div className="app-footer-author">wuqiyou@insta360.com</div>
      </div>
    </>
  );
}

export default function App() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [caps, setCaps] = useState<Capability[]>([]);
  const [plugins, setPlugins] = useState<PluginGroups>({ system: [], platform: [], user: [] });
  const [historyRuns, setHistoryRuns] = useState<HistoryRun[]>([]);
  const [status, setStatus] = useState<any>(null);
  const [serviceOnline, setServiceOnline] = useState(true);
  const [serviceError, setServiceError] = useState("");
  const [serviceReconnecting, setServiceReconnecting] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [catalogReloading, setCatalogReloading] = useState(false);
  const [active, setActive] = useState("__home");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const healthProbeInFlight = useRef<Promise<boolean> | null>(null);
  const healthProbeFailures = useRef(0);

  async function refreshPlugins() {
    const payload = await fetchPlugins();
    const groups = payload.groups || {};
    setPlugins({ system: groups.system || [], platform: groups.platform || [], user: groups.user || [] });
    return payload;
  }

  async function refreshHistory() {
    setHistoryRuns(await fetchHistory());
  }

  async function refreshPlatformCatalog() {
    setCatalogReloading(true);
    try {
      const [toolsResult, capsResult, pluginsResult, historyResult] = await Promise.allSettled([
        fetchTools(),
        fetchCapabilities(),
        fetchPlugins(),
        fetchHistory(),
      ]);
      const failures: string[] = [];
      if (toolsResult.status === "fulfilled") {
        setTools(toolsResult.value);
        const requested = new URLSearchParams(window.location.search).get("tool") || "";
        if (requested && toolsResult.value.some((tool) => tool.id === requested)) {
          setActive(requested);
        }
      } else {
        failures.push("工具清单");
      }
      if (capsResult.status === "fulfilled") {
        setCaps(capsResult.value.capabilities || []);
      } else {
        failures.push("能力清单");
      }
      if (pluginsResult.status === "fulfilled") {
        const groups = pluginsResult.value.groups || {};
        setPlugins({ system: groups.system || [], platform: groups.platform || [], user: groups.user || [] });
      } else {
        failures.push("插件清单");
        if (capsResult.status === "fulfilled") {
          const fallback = (capsResult.value.capabilities || [])
            .filter((item) => item.type === "cadence_tcl")
            .map((item) => ({
              ...item,
              source: "platform" as const,
              readonly: false,
              manageable: true,
              menu: "insta360_HW",
            }));
          setPlugins((current) => ({ ...current, platform: fallback }));
        }
      }
      if (historyResult.status === "fulfilled") {
        setHistoryRuns(historyResult.value);
      } else {
        failures.push("历史记录");
      }
      setCatalogError(
        failures.length
          ? `以下平台数据未加载：${failures.join("、")}。已有内容会保留，可直接重试。`
          : "",
      );
    } finally {
      setCatalogReloading(false);
    }
  }

  async function refreshRuntimeStatus(options: { preserveReconnectMessage?: boolean } = {}) {
    if (healthProbeInFlight.current) return healthProbeInFlight.current;
    const probe = (async () => {
      try {
        const health = await fetchServiceHealth();
        healthProbeFailures.current = 0;
        setStatus((prev: any) => ({
          ...(prev || {}),
          version: health.version || prev?.version,
          revision: health.revision || prev?.revision,
          pid: health.pid || prev?.pid,
          uptime_seconds: health.uptime_seconds,
        }));
        setServiceOnline(true);
        setServiceError("");
        return true;
      } catch (err: any) {
        healthProbeFailures.current += 1;
        if (healthProbeFailures.current >= 2) {
          setServiceOnline(false);
          if (!options.preserveReconnectMessage) {
            setServiceError(toUserMessage(err));
          }
        }
        return false;
      }
    })();
    healthProbeInFlight.current = probe;
    try {
      return await probe;
    } finally {
      if (healthProbeInFlight.current === probe) {
        healthProbeInFlight.current = null;
      }
    }
  }

  function triggerReconnectProtocol() {
    // A hidden iframe.src = "custom-scheme://" used to work but modern
    // browsers (Chrome 90+, Firefox) block programmatic navigation to
    // unknown schemes from iframes without a user gesture. The click on
    // the "重新连接" button IS a user gesture, so a top-level assignment
    // is the reliable path. We stash the current href first so the tab
    // does not actually navigate away if the OS blocks the scheme.
    try {
      const before = window.location.href;
      // Assigning to location for an unknown scheme causes the browser to
      // hand the URL to the OS but leaves the current page loaded, so the
      // user does NOT see a blank tab even when the handler is missing.
      window.location.href = RECONNECT_PROTOCOL_URL;
      // Some browsers race the navigation attempt; forcing a same-tab
      // restore is a no-op when the scheme was handed off but useful if
      // the browser started a real navigation.
      window.setTimeout(() => {
        if (window.location.href !== before) {
          try {
            window.history.replaceState(null, "", before);
          } catch {
            /* ignore */
          }
        }
      }, 500);
    } catch {
      /* browser refused the navigation; fall through to the poll below */
    }
  }

  async function pollBackendUntilReady() {
    for (let attempt = 0; attempt < 30; attempt += 1) {
      if (await refreshRuntimeStatus({ preserveReconnectMessage: true })) {
        return true;
      }
      await sleep(1000);
    }
    return false;
  }

  async function restartBackendAndReconnect() {
    if (serviceReconnecting) return;
    setServiceReconnecting(true);
    try {
      const alreadyReady = await refreshRuntimeStatus({ preserveReconnectMessage: true });
      if (alreadyReady) {
        await refreshPlatformCatalog();
        return;
      }
      setServiceOnline(false);
      setServiceError("正在重新连接本地服务，请稍候…");
      triggerReconnectProtocol();
      const ready = await pollBackendUntilReady();
      if (!ready) {
        setServiceError(
          "本地服务未在 30 秒内恢复。可能原因：浏览器阻止了 insta360-hw:// 协议，或平台未安装。" +
            "\n请从桌面图标手动启动 Insta360_HW，或重新运行 Insta360_HW_Setup.exe。"
        );
      } else {
        await refreshPlatformCatalog();
      }
    } finally {
      setServiceReconnecting(false);
    }
  }

  useEffect(() => {
    Promise.allSettled([refreshPlatformCatalog(), fetchPlatformStatus(), fetchServiceHealth()])
      .then(([, statusResult, healthResult]) => {
        const st = statusResult.status === "fulfilled" ? statusResult.value : {};
        const health = healthResult.status === "fulfilled" ? healthResult.value : null;
        setStatus({ ...st, version: health?.version || st?.version, revision: health?.revision });
        healthProbeFailures.current = health ? 0 : 2;
        setServiceOnline(Boolean(health));
        setServiceError(health ? "" : "后端服务已断开，请重新启动平台或点击重新连接。");
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshRuntimeStatus();
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const onHistoryUpdated = () => {
      void refreshHistory().catch(() => {});
    };
    window.addEventListener(HISTORY_UPDATED_EVENT, onHistoryUpdated);
    return () => window.removeEventListener(HISTORY_UPDATED_EVENT, onHistoryUpdated);
  }, []);

  const bom = tools.filter((t) => ["bom_process", "bom_compare", "bom_risk_check"].includes(t.id));
  const smt = tools.filter((t) => t.category === "SMT");
  const netlist = tools.filter((t) => !["bom_process", "bom_compare", "bom_risk_check"].includes(t.id) && t.category !== "SMT");

  const menu = [
    { key: "__home", label: "工作台" },
    { type: "group" as const, label: "BOM 工具" },
    ...bom.map((t) => ({ key: t.id, label: t.name })),
    { type: "group" as const, label: "SMT 工具" },
    ...smt.map((t) => ({ key: t.id, label: t.name })),
    { type: "group" as const, label: "网表工具" },
    ...netlist.map((t) => ({ key: t.id, label: t.name })),
    { type: "divider" as const },
    { key: "__scripts", label: "插件管理" },
    { key: "__history", label: "历史记录" },
    { key: "__status", label: "系统状态" },
  ];

  function updatePlugin(plugin: PluginInfo) {
    setPlugins((prev) => ({
      system: prev.system.map((item) => (item.id === plugin.id ? { ...item, ...plugin } : item)),
      platform: prev.platform.map((item) => (item.id === plugin.id ? { ...item, ...plugin } : item)),
      user: prev.user.map((item) => (item.id === plugin.id ? { ...item, ...plugin } : item)),
    }));
  }

  function selectTool(key: string) {
    setActive(key);
    setMobileNavOpen(false);
  }

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <Spin />
      </div>
    );
  }

  return (
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <WorkspacePersistenceNotice />
        <Layout className="app-shell">
        <Sider width={232} className="app-sider app-desktop-sider">
          <PlatformNavigation
            active={active}
            items={menu}
            version={status?.version}
            serviceOnline={serviceOnline}
            onSelect={selectTool}
          />
        </Sider>
        <header className="app-mobile-header">
          <Button
            type="text"
            icon={<MenuOutlined />}
            aria-label="打开平台导航"
            onClick={() => setMobileNavOpen(true)}
          />
          <img className="app-mobile-logo" src="/assets/insta360_logo.png" alt="" />
          <div className="app-mobile-title">
            <strong>硬件提效平台</strong>
            <span>
              <i className={`app-brand-dot ${serviceOnline ? "" : "app-brand-dot--offline"}`} />
              {serviceOnline ? "运行中" : "服务离线"}
            </span>
          </div>
        </header>
        <Drawer
          placement="left"
          width={304}
          open={mobileNavOpen}
          onClose={() => setMobileNavOpen(false)}
          rootClassName="app-mobile-drawer"
          title={null}
          closable={false}
        >
          <nav className="app-mobile-nav" aria-label="平台导航">
            <PlatformNavigation
              active={active}
              items={menu}
              version={status?.version}
              serviceOnline={serviceOnline}
              onSelect={selectTool}
              onClose={() => setMobileNavOpen(false)}
            />
          </nav>
        </Drawer>
        <Content className="app-content" style={{ overflow: "auto" }}>
          {!serviceOnline ? (
            <Alert
              type="error"
              showIcon
              className="service-offline-alert"
              message="后端服务已断开"
              description={serviceError || "当前页面仍在浏览器中，但本地服务不可用，工具操作会失败。请重新启动平台或点击重新连接。"}
              action={
                <Button size="small" danger loading={serviceReconnecting} onClick={restartBackendAndReconnect}>
                  {serviceReconnecting ? "正在重新连接" : "重新连接"}
                </Button>
              }
            />
          ) : null}
          {catalogError ? (
            <Alert
              type="warning"
              showIcon
              className="platform-load-alert"
              message="平台数据加载不完整"
              description={catalogError}
              action={
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  loading={catalogReloading}
                  onClick={() => void refreshPlatformCatalog()}
                >
                  重试加载
                </Button>
              }
            />
          ) : null}
          {active === "__home" ? <PlatformHome caps={caps} tools={tools} plugins={plugins} /> : null}
          {active === "__scripts" ? <ScriptManager plugins={plugins} onPluginChange={updatePlugin} onRefresh={refreshPlugins} /> : null}
          {active === "__history" ? <HistoryView runs={historyRuns} onChange={setHistoryRuns} /> : null}
          {active === "__status" ? <SystemStatus status={status} /> : null}
          <Suspense fallback={<Spin />}>
            <div style={{ display: active === "bom_process" ? "block" : "none" }}>
              <BomProcessWizard />
            </div>
            {tools
              .filter((tool) => tool.id === "bom_risk_check")
              .map((tool) => (
                <div key={tool.id} style={{ display: active === tool.id ? "block" : "none" }}>
                  <BomRiskPane tool={tool} />
                </div>
              ))}
            <div style={{ display: active === "smt_view" ? "block" : "none" }}>
              <SmtViewPane />
            </div>
            {tools
              .filter((t) => !["bom_process", "bom_risk_check", "smt_view"].includes(t.id))
              .map((t) => (
                <div key={t.id} style={{ display: active === t.id ? "block" : "none" }}>
                  <LegacyToolPane tool={t} />
                </div>
              ))}
          </Suspense>
        </Content>
        </Layout>
      </AntdApp>
    </ConfigProvider>
  );
}
