import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Descriptions, List, Space, Typography, message } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { fetchDiagnosticReport, fetchLifecycleCheck, type LifecyclePayload } from "../api/client";

const statusMap = {
  ok: { status: "success" as const, text: "正常" },
  warn: { status: "warning" as const, text: "需确认" },
  fail: { status: "error" as const, text: "异常" },
};

export function SystemStatus({ status }: { status: any }) {
  const [lifecycle, setLifecycle] = useState<LifecyclePayload | null>(null);
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
      anchor.download = `insta360_hw_diagnostic_${Date.now()}.txt`;
      document.body.appendChild(anchor);
      anchor.click();
      setTimeout(() => {
        URL.revokeObjectURL(url);
        anchor.remove();
      }, 4000);
      message.success("诊断报告已下载");
    } catch (err: any) {
      message.error(`诊断报告生成失败: ${err?.userMessage || err?.message || err}`);
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

  const summary = lifecycle?.summary;
  const manifestVersion = lifecycle?.manifest?.version ? String(lifecycle.manifest.version) : "-";
  const cadencePresent = lifecycle?.checks?.find((item) => item.id === "cadence_present");

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
            生成诊断报告
          </Button>
        }
      >
        <Descriptions column={1} size="small">
          <Descriptions.Item label="平台">{status?.platform || "Insta360硬件提效平台"}</Descriptions.Item>
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
