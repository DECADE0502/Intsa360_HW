import { useEffect, useState } from "react";
import { App as AntdApp, Button, ConfigProvider, Layout, Menu, Result, Space, Spin, Typography } from "antd";
import zhCN from "antd/locale/zh_CN";
import { fetchCapabilities, fetchPlatformStatus, fetchTools, runTool, uploadFiles, type Capability, type ToolInfo } from "./api/client";
import { FileInputField } from "./components/FileInputField";
import { ResultPanel } from "./components/ResultPanel";
import { UpdateStatus } from "./components/UpdateStatus";
import { uiText } from "./i18n/zhCN";
import { PlatformHome } from "./platform/PlatformHome";
import { ScriptManager } from "./platform/ScriptManager";
import { SystemStatus } from "./platform/SystemStatus";
import { BomProcessWizard } from "./tools/BomProcessWizard";
import { toolInputs } from "./tools/toolConfig";
import "./styles.css";

const { Sider, Content } = Layout;

export default function App() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [platformStatus, setPlatformStatus] = useState<any>(null);
  const [active, setActive] = useState<string>("__home");
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    Promise.all([fetchTools(), fetchCapabilities(), fetchPlatformStatus()])
      .then(([items, capabilityPayload, statusPayload]) => {
        setTools(items);
        setCapabilities(capabilityPayload.capabilities || []);
        setPlatformStatus(statusPayload);
        const requested = new URLSearchParams(window.location.search).get("tool");
        setActive(items.some((item) => item.id === requested) ? requested || "__home" : "__home");
      })
      .catch((err) => setError(err.message || "加载失败"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin fullscreen tip={uiText.loadingTools} />;
  if (error) return <Result status="error" title={uiText.startupFailed} subTitle={error} />;

  const current = tools.find((tool) => tool.id === active);
  const inputs = toolInputs[active] || [];
  const platformItems = [
    { key: "__home", label: "工作台" },
    { key: "__scripts", label: "脚本管理" },
    { key: "__status", label: "系统状态" },
  ];
  const toolItems = tools.map((tool) => ({ key: tool.id, label: tool.name }));

  async function handleRun() {
    if (!current) return;
    setRunning(true);
    try {
      const params: Record<string, unknown> = {};
      for (const input of inputs) {
        const selected = files[input.key] || [];
        if (!selected.length) continue;
        const uploaded = await uploadFiles(selected);
        params[input.key] = input.multiple ? uploaded.files.map((file) => file.path) : uploaded.files[0]?.path;
      }
      setResult(await runTool(current.id, params));
    } catch (err: any) {
      setResult({ status: "error", error: err.message || "运行失败" });
    } finally {
      setRunning(false);
    }
  }

  return (
    <ConfigProvider locale={zhCN}>
      <AntdApp>
        <Layout className="app-shell">
          <Sider width={260} theme="light" className="app-sider">
            <Typography.Title level={4}>{uiText.appTitle}</Typography.Title>
            <Menu selectedKeys={[active]} items={[...platformItems, ...toolItems]} onClick={(item) => setActive(item.key)} />
          </Sider>
          <Content className="app-content">
            <div className="app-topbar">
              <Typography.Title level={3}>
                {active === "__home" ? "工作台" : active === "__scripts" ? "脚本管理" : active === "__status" ? "系统状态" : current?.name}
              </Typography.Title>
              <UpdateStatus />
            </div>
            {active === "__home" ? <PlatformHome capabilities={capabilities} /> : null}
            {active === "__scripts" ? (
              <ScriptManager
                capabilities={capabilities}
                onCapabilityChange={(updated) =>
                  setCapabilities((prev) => prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)))
                }
              />
            ) : null}
            {active === "__status" ? <SystemStatus status={platformStatus} /> : null}
            {current ? <Typography.Paragraph type="secondary">{current.description}</Typography.Paragraph> : null}
            {current?.id === "bom_process" ? (
              <BomProcessWizard />
            ) : current ? (
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                {inputs.map((input) => (
                  <FileInputField
                    key={input.key}
                    label={input.label}
                    accept={input.accept}
                    multiple={input.multiple}
                    value={files[input.key] || []}
                    onChange={(value) => setFiles((prev) => ({ ...prev, [input.key]: value }))}
                  />
                ))}
                <Space>
                  <Button type="primary" loading={running} onClick={handleRun}>
                    {uiText.run}
                  </Button>
                  <Button onClick={() => setFiles({})}>{uiText.clear}</Button>
                </Space>
                <ResultPanel result={result} />
              </Space>
            ) : null}
          </Content>
        </Layout>
      </AntdApp>
    </ConfigProvider>
  );
}
