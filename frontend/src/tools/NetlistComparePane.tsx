import { type Dispatch, type SetStateAction, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Segmented,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from "antd";
import {
  DeleteOutlined,
  DownloadOutlined,
  FileOutlined,
  PlayCircleOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { runTool, uploadFiles, type ToolInfo } from "../api/client";

type ReviewItem = {
  key: string;
  status: string;
  kind: string;
  severity?: string;
  message?: string;
  critical?: boolean;
  left?: Record<string, unknown> | null;
  right?: Record<string, unknown> | null;
  diff?: string[];
};

function outputHref(path: string) {
  const normalized = path.replaceAll("\\", "/");
  const marker = "/data/outputs/";
  const index = normalized.indexOf(marker);
  const rel = index >= 0 ? normalized.slice(index + marker.length) : normalized.replace(/^data\/outputs\//, "");
  return `/outputs/${encodeURI(rel)}`;
}

function textOf(value: unknown) {
  return String(value ?? "");
}

function statusColor(status: string) {
  if (status.includes("关键") || status.includes("拆") || status.includes("并")) return "red";
  if (status.includes("新增")) return "blue";
  if (status.includes("删除")) return "orange";
  if (status.includes("封装")) return "purple";
  if (status.includes("改名")) return "cyan";
  return "gold";
}

function groupOf(item: ReviewItem) {
  if (item.status === "关键网络变化") return "critical";
  if (item.status === "疑似拆网") return "split";
  if (item.status === "疑似并网") return "merge";
  if (item.status === "网络改名") return "rename";
  if (item.status === "封装变化") return "package";
  if (item.status === "网络新增") return "added";
  if (item.status === "网络删除") return "removed";
  return "node";
}

function NetlistUploadSlot({
  title,
  files,
  onFiles,
}: {
  title: string;
  files: File[];
  onFiles: Dispatch<SetStateAction<File[]>>;
}) {
  return (
    <Card className="netlist-upload-card" size="small">
      <Typography.Text className="netlist-upload-title">{title}</Typography.Text>
      <Upload
        accept=".dat"
        directory="true"
        webkitdirectory="true"
        multiple
        fileList={files.map((file, index) => ({ uid: String(index), name: file.name, status: "done" as const }))}
        beforeUpload={(file) => {
          if (file.name.toLowerCase().endsWith(".dat")) {
            onFiles((prev) => {
              if (prev.some((item) => item.name === file.name && item.size === file.size)) return prev;
              return [...prev, file];
            });
          }
          return false;
        }}
        onRemove={(file) => {
          onFiles((prev) => prev.filter((_, index) => String(index) !== file.uid));
          return true;
        }}
      >
        <Button icon={<FileOutlined />}>选择 Allegro 目录</Button>
      </Upload>
    </Card>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className={`netlist-metric netlist-metric-${tone || "plain"}`}>
      <div className="netlist-metric-value">{value}</div>
      <div className="netlist-metric-label">{label}</div>
    </div>
  );
}

function NodeSide({ title, data }: { title: string; data?: Record<string, unknown> | null }) {
  return (
    <div className="netlist-side">
      <Typography.Text className="netlist-side-title">{title}</Typography.Text>
      <div className="netlist-side-field">
        <span>网络</span>
        <p>{textOf(data?.["网络"]) || "-"}</p>
      </div>
      <div className="netlist-side-field">
        <span>位号</span>
        <p>{textOf(data?.["位号"]) || textOf(data?.["位号"]) || "-"}</p>
      </div>
      <div className="netlist-side-field">
        <span>节点</span>
        <p>{textOf(data?.["节点"]) || textOf(data?.["封装"]) || "-"}</p>
      </div>
    </div>
  );
}

function SimpleTable({ table }: { table?: any }) {
  const columns =
    table?.headers?.map((header: string, index: number) => ({
      title: header,
      dataIndex: String(index),
      key: String(index),
      ellipsis: true,
      width: index === 0 ? 180 : undefined,
    })) || [];
  const data =
    table?.rows?.map((row: unknown[], index: number) => ({
      key: index,
      ...Object.fromEntries(row.map((value, i) => [String(i), value])),
    })) || [];
  if (!data.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />;
  return <Table size="small" columns={columns} dataSource={data} pagination={{ pageSize: 12 }} scroll={{ x: true }} />;
}

export function NetlistComparePane({ tool }: { tool: ToolInfo }) {
  const [leftFiles, setLeftFiles] = useState<File[]>([]);
  const [rightFiles, setRightFiles] = useState<File[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [filter, setFilter] = useState("focus");
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState("");

  const review = result?.netlist_review;
  const items: ReviewItem[] = review?.items || [];
  const focusItems: ReviewItem[] = review?.focus_items || [];
  const visibleItems = useMemo(() => {
    const source = filter === "focus" ? focusItems : items;
    const q = query.trim().toLowerCase();
    return source.filter((item) => {
      const byFilter = filter === "focus" || filter === "all" || groupOf(item) === filter;
      const hay = `${item.key} ${item.status} ${item.message} ${textOf(item.left?.["节点"])} ${textOf(item.right?.["节点"])}`.toLowerCase();
      return byFilter && (!q || hay.includes(q));
    });
  }, [items, focusItems, filter, query]);
  const selected = items.find((item) => item.key === selectedKey) || visibleItems[0] || items[0];
  const counts = review?.status_counts || {};

  useEffect(() => {
    if (review) setSelectedKey(review.focus_items?.[0]?.key || review.items?.[0]?.key || "");
  }, [review]);

  async function handleRun() {
    if (!leftFiles.some((file) => file.name.toLowerCase() === "pstxnet.dat") || !rightFiles.some((file) => file.name.toLowerCase() === "pstxnet.dat")) {
      setResult({ status: "error", error: "两版网表都需要至少选择 pstxnet.dat，建议同时选择 pstxprt.dat。" });
      return;
    }
    setRunning(true);
    try {
      const [leftUpload, rightUpload] = await Promise.all([uploadFiles(leftFiles), uploadFiles(rightFiles)]);
      const next = await runTool("netlist_compare", {
        netlist1: leftUpload.files.map((file) => file.path),
        netlist2: rightUpload.files.map((file) => file.path),
      });
      setResult(next);
      setFilter("focus");
      setQuery("");
    } catch (err: any) {
      setResult({ status: "error", error: err.message || "运行失败" });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="netlist-workbench">
      <div className="netlist-head">
        <div>
          <Typography.Title level={4}>{tool.name}</Typography.Title>
          <Typography.Paragraph type="secondary">{tool.description}</Typography.Paragraph>
        </div>
        {result?.outputs?.length ? (
          <Space wrap>
            {result.outputs.map((path: string) => (
              <Button key={path} href={outputHref(path)} icon={<DownloadOutlined />}>
                下载网表差异报告
              </Button>
            ))}
          </Space>
        ) : null}
      </div>

      <div className="netlist-upload-grid">
        <NetlistUploadSlot title="旧版 / 基准网表" files={leftFiles} onFiles={setLeftFiles} />
        <NetlistUploadSlot title="新版 / 待确认网表" files={rightFiles} onFiles={setRightFiles} />
        <Card size="small" className="netlist-run-card">
          <Space wrap>
            <Button type="primary" loading={running} onClick={handleRun} icon={<PlayCircleOutlined />}>
              开始对比
            </Button>
            <Button
              onClick={() => {
                setLeftFiles([]);
                setRightFiles([]);
                setResult(null);
              }}
              icon={<DeleteOutlined />}
            >
              清空
            </Button>
          </Space>
        </Card>
      </div>

      {!result ? <Alert type="info" showIcon message="选择两版 Allegro 目录" description="直接选择包含 pstxnet.dat 的 allegro 文件夹；pstxprt.dat 可选，若目录中存在会额外检查器件封装变化。" /> : null}
      {result?.status && result.status !== "ok" ? <Alert type="error" showIcon message={result.error || result.message || "运行失败"} /> : null}
      {result?.status === "ok" && result.warnings?.length ? (
        <Alert type="warning" showIcon message="部分检查已跳过" description={result.warnings.join("；")} />
      ) : null}

      {result?.status === "ok" ? (
        <>
          <div className="netlist-summary-grid">
            <Metric label="总差异" value={result.summary?.diff_count || 0} tone="diff" />
            <Metric label="关键网络" value={result.summary?.critical_changes || 0} tone="critical" />
            <Metric label="节点变化" value={counts.node_change || 0} tone="node" />
            <Metric label="改名" value={counts.rename || 0} tone="rename" />
            <Metric label="拆网" value={counts.split || 0} tone="critical" />
            <Metric label="并网" value={counts.merge || 0} tone="critical" />
            <Metric label="封装变化" value={counts.package || 0} tone="package" />
          </div>

          <Tabs
            className="netlist-tabs"
            items={[
              {
                key: "review",
                label: "网络审查",
                children: (
                  <div className="netlist-shell">
                    <aside className="netlist-rail">
                      <Segmented
                        block
                        value={filter}
                        onChange={(value) => setFilter(String(value))}
                        options={[
                          { label: "重点", value: "focus" },
                          { label: "关键", value: "critical" },
                          { label: "拆网", value: "split" },
                          { label: "并网", value: "merge" },
                          { label: "改名", value: "rename" },
                          { label: "全部", value: "all" },
                        ]}
                      />
                      <Input allowClear prefix={<SearchOutlined />} placeholder="搜索网络 / 位号 / 节点" value={query} onChange={(event) => setQuery(event.target.value)} />
                      <div className="netlist-focus-list">
                        {visibleItems.map((item) => (
                          <button
                            type="button"
                            key={item.key}
                            className={`netlist-focus-item ${selected?.key === item.key ? "is-active" : ""}`}
                            onClick={() => setSelectedKey(item.key)}
                          >
                            <span className="netlist-focus-key">{item.key}</span>
                            <Tag color={statusColor(item.status)}>{item.status}</Tag>
                            <span className="netlist-focus-msg">{item.message}</span>
                          </button>
                        ))}
                      </div>
                    </aside>

                    <main className="netlist-detail">
                      {selected ? (
                        <>
                          <div className="netlist-detail-head">
                            <div>
                              <Typography.Title level={5}>{selected.key}</Typography.Title>
                              <Typography.Text type="secondary">{review?.review_guide?.[selected.status] || selected.message}</Typography.Text>
                            </div>
                            <Tag color={statusColor(selected.status)}>{selected.status}</Tag>
                          </div>
                          <div className="netlist-side-grid">
                            <NodeSide title="网表1" data={selected.left} />
                            <NodeSide title="网表2" data={selected.right} />
                          </div>
                          <Typography.Title level={5} className="netlist-section-title">
                            当前筛选结果
                          </Typography.Title>
                          <Table
                            size="small"
                            dataSource={visibleItems.map((item) => ({ ...item, key: item.key }))}
                            pagination={{ pageSize: 10 }}
                            scroll={{ x: true }}
                            onRow={(record) => ({ onClick: () => setSelectedKey(record.key) })}
                            columns={[
                              { title: "对象", dataIndex: "key", key: "key", ellipsis: true },
                              { title: "状态", dataIndex: "status", key: "status", render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag> },
                              { title: "说明", dataIndex: "message", key: "message", ellipsis: true },
                            ]}
                          />
                        </>
                      ) : (
                        <Empty description="暂无网络差异" />
                      )}
                    </main>

                    <aside className="netlist-inspector">
                      <Typography.Title level={5}>复核重点</Typography.Title>
                      <div className="netlist-guide-list">
                        {["关键网络变化", "疑似拆网", "疑似并网", "网络改名", "封装变化"].map((key) => (
                          <div key={key} className="netlist-guide-item">
                            <Tag color={statusColor(key)}>{key}</Tag>
                            <Typography.Paragraph type="secondary">{review?.review_guide?.[key]}</Typography.Paragraph>
                          </div>
                        ))}
                      </div>
                    </aside>
                  </div>
                ),
              },
              { key: "nodes", label: "节点差异表", children: <SimpleTable table={result.table} /> },
              { key: "packages", label: "封装差异表", children: <SimpleTable table={result.package_table} /> },
            ]}
          />
        </>
      ) : null}
    </div>
  );
}
