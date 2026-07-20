import { useEffect, useState } from "react";
import { Alert, App, Badge, Button, Card, Descriptions, List, Space, Typography } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { fetchDiagnosticReport, fetchLifecycleCheck, fetchServiceHealth, type LifecyclePayload } from "../api/client";

const statusMap = {
  ok: { status: "success" as const, text: "正常" },
  warn: { status: "warning" as const, text: "需确认" },
  fail: { status: "error" as const, text: "异常" },
};

const componentStatusText: Record<string, string> = {
  ok: "正常",
  checking: "检查中",
  degraded: "需确认",
  error: "异常",
  disabled: "已禁用",
  missing: "缺失",
  not_configured: "未配置",
  not_initialized: "未初始化",
};

export function SystemStatus({ status }: { status: any }) {
  const { message } = App.useApp();
  const [lifecycle, setLifecycle] = useState<LifecyclePayload | null>(null);
  const [serviceHealth, setServiceHealth] = useState<any>(null);
  const [error, setError] = useState("");
  const [diagnosticLoading, setDiagnosticLoading] = useState(false);

  async function downloadDiagnostic() {
    if (diagnosticLoading) return;
    setDiagnosticLoading(true);
    try {
      const blob = await fetchDiagnosticReport();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `insta360_hw_diagnostic_${Date.now()}.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      setTimeout(() => {
        URL.revokeObjectURL(url);
        anchor.remove();
      }, 4000);
      message.success("诊断包已下载");
    } catch (err: any) {
      message.error(`诊断包生成失败: ${err?.userMessage || err?.message || err}`);
    } finally {
      setDiagnosticLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    fetchLifecycleCheck()
      .then((payload) => {
        if (!cancelled) setLifecycle(payload);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message || "安装自检加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const loadHealth = () => {
      fetchServiceHealth()
        .then((payload: any) => {
          if (cancelled) return;
          setServiceHealth(payload);
          const database = payload?.components?.database || payload?.database;
          if (database?.quick_check === "pending") {
            timer = window.setTimeout(loadHealth, 250);
          }
        })
        .catch(() => {
          if (!cancelled) setServiceHealth(null);
        });
    };
    loadHealth();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  const summary = lifecycle?.summary;
  const manifestVersion = lifecycle?.manifest?.version ? String(lifecycle.manifest.version) : "-";
  const cadencePresent = lifecycle?.checks?.find((item) => item.id === "cadence_present");
  const databaseHealth = serviceHealth?.components?.database || serviceHealth?.database;
  const cadenceHealth = serviceHealth?.components?.cadence || serviceHealth?.cadence;
  const databaseDegraded = ["degraded", "error"].includes(databaseHealth?.status);

  return (
    <Space direction="vertical" size={14} style={{ width: "100%" }}>
      <Card
        title="系统状态"
        extra={
          <Button
            size="small"
            icon={<DownloadOutlined />}
            loading={diagnosticLoading}
            onClick={downloadDiagnostic}
          >
            生成诊断包
          </Button>
        }
      >
        {databaseDegraded ? (
          <Alert
            type="warning"
            showIcon
            message="数据库自检异常，不影响服务运行"
            description={databaseHealth?.error || `完整性检查结果：${databaseHealth?.quick_check || "异常"}`}
            style={{ marginBottom: 12 }}
          />
        ) : null}
        <Descriptions column={1} size="small">
          <Descriptions.Item label="平台">{status?.platform || "Insta360硬件提效平台"}</Descriptions.Item>
          <Descriptions.Item label="服务状态">
            <Badge status={serviceHealth?.status === "ok" ? "success" : "default"} text={serviceHealth?.status === "ok" ? "正常运行" : "正在读取"} />
          </Descriptions.Item>
          <Descriptions.Item label="数据库自检">
            {componentStatusText[databaseHealth?.status] || "未初始化"}
          </Descriptions.Item>
          <Descriptions.Item label="Cadence 集成状态">{componentStatusText[cadenceHealth?.status] || "未配置"}</Descriptions.Item>
          <Descriptions.Item label="工具数量">{status?.tools ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="Cadence 脚本">{status?.cadence_scripts ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="可挂载脚本">{status?.enableable_scripts ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="已挂载脚本">{status?.enabled_scripts ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="待拆分脚本">{status?.pending_scripts ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="安装目录">{status?.root || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title="安装自检"
        extra={
          summary ? (
            <Space size={10}>
              <Badge status="success" text={`正常 ${summary.ok}`} />
              <Badge status="warning" text={`确认 ${summary.warnings}`} />
              <Badge status="error" text={`异常 ${summary.failed}`} />
            </Space>
          ) : null
        }
      >
        {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
        {cadencePresent && cadencePresent.status !== "ok" ? (
          <Alert
            type="warning"
            showIcon
            message="未检测到 Cadence 集成环境"
            description={cadencePresent.message}
            style={{ marginBottom: 12 }}
          />
        ) : null}
        <Descriptions column={1} size="small" style={{ marginBottom: 12 }}>
          <Descriptions.Item label="发布清单版本">{manifestVersion}</Descriptions.Item>
        </Descriptions>
        <List
          size="small"
          dataSource={lifecycle?.checks || []}
          locale={{ emptyText: "正在读取安装自检" }}
          renderItem={(item) => {
            const visual = statusMap[item.status] || statusMap.fail;
            return (
              <List.Item>
                <List.Item.Meta
                  title={<Badge status={visual.status} text={`${item.name} · ${visual.text}`} />}
                  description={<Typography.Text type="secondary">{item.message}</Typography.Text>}
                />
              </List.Item>
            );
          }}
        />
      </Card>
    </Space>
  );
}
