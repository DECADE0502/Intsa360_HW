import { lazy, Suspense, useEffect, useState } from "react";
import { ConfigProvider, Layout, Menu, Spin, Typography } from "antd";
import zhCN from "antd/locale/zh_CN";
import {
  fetchCapabilities,
  fetchHistory,
  fetchPlatformStatus,
  fetchPlugins,
  fetchTools,
  fetchVersion,
  type Capability,
  type HistoryRun,
  type PluginInfo,
  type ToolInfo,
} from "./api/client";
import { HistoryView } from "./platform/HistoryView";
import { PlatformHome } from "./platform/PlatformHome";
import { ScriptManager } from "./platform/ScriptManager";
import { SystemStatus } from "./platform/SystemStatus";
import { UpdateStatus } from "./components/UpdateStatus";
import "./styles.css";

const { Sider, Content } = Layout;
type PluginGroups = { system: PluginInfo[]; platform: PluginInfo[]; user: PluginInfo[] };
const BomProcessWizard = lazy(() => import("./tools/BomProcessWizard").then((module) => ({ default: module.BomProcessWizard })));
const LegacyToolPane = lazy(() => import("./tools/LegacyToolPane").then((module) => ({ default: module.LegacyToolPane })));

export default function App() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [caps, setCaps] = useState<Capability[]>([]);
  const [plugins, setPlugins] = useState<PluginGroups>({ system: [], platform: [], user: [] });
  const [historyRuns, setHistoryRuns] = useState<HistoryRun[]>([]);
  const [status, setStatus] = useState<any>(null);
  const [active, setActive] = useState("__home");
  const [loading, setLoading] = useState(true);

  async function refreshPlugins() {
    const payload = await fetchPlugins();
    setPlugins({ system: [], platform: [], user: [], ...(payload.groups || {}) });
    return payload;
  }

  useEffect(() => {
    Promise.allSettled([fetchTools(), fetchCapabilities(), fetchPlugins(), fetchHistory(), fetchPlatformStatus(), fetchVersion()])
      .then(([toolsResult, capsResult, pluginsResult, historyResult, statusResult, versionResult]) => {
        const tls = toolsResult.status === "fulfilled" ? toolsResult.value : [];
        const cp = capsResult.status === "fulfilled" ? capsResult.value : { capabilities: [] };
        const pl =
          pluginsResult.status === "fulfilled"
            ? pluginsResult.value
            : {
                groups: {
                  system: [],
                  platform: (cp.capabilities || [])
                    .filter((item) => item.type === "cadence_tcl")
                    .map((item) => ({
                      ...item,
                      source: "platform" as const,
                      readonly: false,
                      manageable: true,
                      menu: "insta360_HW",
                    })),
                  user: [],
                },
              };
        const st = statusResult.status === "fulfilled" ? statusResult.value : {};
        const version = versionResult.status === "fulfilled" ? versionResult.value : "";
        setTools(tls);
        setCaps(cp.capabilities || []);
        setPlugins({ system: [], platform: [], user: [], ...(pl.groups || {}) });
        setHistoryRuns(historyResult.status === "fulfilled" ? historyResult.value : []);
        setStatus({ ...st, version: version || st?.version });
        let requested = new URLSearchParams(window.location.search).get("tool") || "";
        if (requested && !tls.some((tool) => tool.id === requested)) requested = "";
        setActive(requested || "__home");
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const bom = tools.filter((t) => ["bom_process", "bom_compare", "bom_risk_check"].includes(t.id));
  const netlist = tools.filter((t) => !["bom_process", "bom_compare", "bom_risk_check"].includes(t.id));

  const menu = [
    { key: "__home", label: "工作台" },
    { type: "group" as const, label: "BOM 工具" },
    ...bom.map((t) => ({ key: t.id, label: t.name })),
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

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <Spin />
      </div>
    );
  }

  return (
    <ConfigProvider locale={zhCN}>
      <Layout className="app-shell">
        <Sider width={232} className="app-sider">
          <div className="app-brand">
            <img className="app-brand-logo" src="/assets/insta360_logo.png" alt="Insta360" />
            <div className="app-brand-copy">
              <Typography.Text className="app-brand-title">硬件提效平台</Typography.Text>
              <div className="app-brand-meta">
                <span className="app-brand-dot" />v{status?.version || "-"} · 运行中
              </div>
            </div>
          </div>
          <Menu mode="inline" selectedKeys={[active]} items={menu} onClick={({ key }) => setActive(key)} className="app-menu" />
          <div className="app-footer">
            <UpdateStatus version={status?.version} />
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
        </Sider>
        <Content className="app-content" style={{ overflow: "auto" }}>
          {active === "__home" ? <PlatformHome caps={caps} tools={tools} plugins={plugins} /> : null}
          {active === "__scripts" ? <ScriptManager plugins={plugins} onPluginChange={updatePlugin} onRefresh={refreshPlugins} /> : null}
          {active === "__history" ? <HistoryView runs={historyRuns} onChange={setHistoryRuns} /> : null}
          {active === "__status" ? <SystemStatus status={status} /> : null}
          <Suspense fallback={<Spin />}>
            <div style={{ display: active === "bom_process" ? "block" : "none" }}>
              <BomProcessWizard />
            </div>
            {tools
              .filter((t) => t.id !== "bom_process")
              .map((t) => (
                <div key={t.id} style={{ display: active === t.id ? "block" : "none" }}>
                  <LegacyToolPane tool={t} />
                </div>
              ))}
          </Suspense>
        </Content>
      </Layout>
    </ConfigProvider>
  );
}
