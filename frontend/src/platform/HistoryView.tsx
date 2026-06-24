import { App, Button, Descriptions, Drawer, Empty, Popconfirm, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import { clearHistory, deleteHistoryRun, fetchHistoryRun, type HistoryRun } from "../api/client";

function compactSummary(summary: unknown) {
  if (!summary || typeof summary !== "object") return "-";
  const entries = Object.entries(summary as Record<string, unknown>).slice(0, 4);
  if (!entries.length) return "-";
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(" · ");
}

export function HistoryView({
  runs,
  onChange,
}: {
  runs: HistoryRun[];
  onChange: (runs: HistoryRun[]) => void;
}) {
  const { message } = App.useApp();
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  async function openDetail(id: string) {
    setLoadingDetail(true);
    try {
      setDetail(await fetchHistoryRun(id));
      setDetailOpen(true);
    } catch (err: any) {
      message.error(err.message || "历史详情加载失败");
    } finally {
      setLoadingDetail(false);
    }
  }

  async function removeRun(id: string) {
    try {
      await deleteHistoryRun(id);
      onChange(runs.filter((run) => run.id !== id));
      message.success("已删除记录");
    } catch (err: any) {
      message.error(err.message || "删除记录失败");
    }
  }

  async function removeAll() {
    try {
      await clearHistory();
      onChange([]);
      message.success("已清空历史");
    } catch (err: any) {
      message.error(err.message || "清空历史失败");
    }
  }

  const columns = [
    { title: "时间", dataIndex: "time", width: 170 },
    {
      title: "工具",
      dataIndex: "tool_name",
      width: 150,
      render: (value: string, run: HistoryRun) => <Tag color={run.tool === "bom_process" ? "blue" : "default"}>{value || run.tool}</Tag>,
    },
    {
      title: "输入文件",
      dataIndex: "inputs",
      render: (inputs: string[] = []) => inputs.length ? inputs.join(", ") : "-",
    },
    {
      title: "输出文件",
      dataIndex: "outputs",
      render: (outputs: string[] = []) => (
        outputs.length ? (
          <Space size={4} wrap>
            {outputs.slice(0, 4).map((name) => (
              <a key={name} href={`/outputs/${encodeURIComponent(name)}`}>{name}</a>
            ))}
            {outputs.length > 4 ? <Tag>+{outputs.length - 4}</Tag> : null}
          </Space>
        ) : "-"
      ),
    },
    {
      title: "摘要",
      dataIndex: "summary",
      ellipsis: true,
      render: compactSummary,
    },
    {
      title: "操作",
      width: 150,
      render: (_: unknown, run: HistoryRun) => (
        <Space size={8}>
          <Button size="small" type="link" loading={loadingDetail} onClick={() => openDetail(run.id)}>
            查看详情
          </Button>
          <Popconfirm title="删除记录" description="只删除历史索引和详情，不删除输出文件。" okText="删除" cancelText="取消" onConfirm={() => removeRun(run.id)}>
            <Button size="small" type="link" danger>
              删除记录
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <div className="history-head">
        <div>
          <Typography.Title level={3}>历史记录</Typography.Title>
          <Typography.Text type="secondary">自动保留成功运行的处理记录，可回看输入、输出和完整结果。</Typography.Text>
        </div>
        <Popconfirm title="清空历史" description="只清空历史记录，不删除输出文件。" okText="清空" cancelText="取消" onConfirm={removeAll}>
          <Button danger disabled={!runs.length}>清空历史</Button>
        </Popconfirm>
      </div>

      {runs.length ? (
        <Table size="middle" rowKey="id" dataSource={runs} columns={columns} pagination={{ pageSize: 10 }} />
      ) : (
        <Empty description="暂无历史记录。成功运行工具后会自动保留在这里。" />
      )}

      <Drawer width={720} title="历史详情" open={detailOpen} onClose={() => setDetailOpen(false)}>
        {detail ? (
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="记录 ID">{String((detail._meta as any)?.id || "-")}</Descriptions.Item>
              <Descriptions.Item label="工具">{String((detail._meta as any)?.tool_name || "-")}</Descriptions.Item>
              <Descriptions.Item label="时间">{String((detail._meta as any)?.time || "-")}</Descriptions.Item>
            </Descriptions>
            <Typography.Title level={5}>完整结果</Typography.Title>
            <pre className="history-json">{JSON.stringify(detail, null, 2)}</pre>
          </Space>
        ) : null}
      </Drawer>
    </Space>
  );
}
