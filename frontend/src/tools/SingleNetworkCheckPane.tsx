import { type Dispatch, type SetStateAction, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
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
import { useToolWorkspace } from "../state/toolWorkspace";

type SingleNetworkItem = {
  key: string;
  net: string;
  category: string;
  kind: string;
  severity?: string;
  refs?: string[];
  pins?: string[];
  nodes?: string[];
  ref_count?: number;
  pin_count?: number;
  critical?: boolean;
  note?: string;
  review_hint?: string;
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

function joinList(values?: string[]) {
  return values?.length ? values.join(", ") : "-";
}

function categoryColor(category: string) {
  if (category === "重点复核") return "red";
  if (category === "NC 网络") return "orange";
  if (category === "电源/地") return "purple";
  if (category === "单一位号网络") return "gold";
  if (category === "测试点/工艺") return "cyan";
  if (category === "机械/安装孔") return "blue";
  return "default";
}

function filterOf(item: SingleNetworkItem) {
  if (item.category === "重点复核") return "focus";
  if (item.category === "NC 网络") return "nc";
  if (item.category === "单一位号网络") return "single_ref";
  if (item.category === "电源/地") return "power";
  if (item.category === "测试点/工艺") return "testpoint";
  if (item.category === "机械/安装孔") return "mechanical";
  return item.kind || "all";
}

function NetlistUploadSlot({
  files,
  onFiles,
}: {
  files: File[];
  onFiles: Dispatch<SetStateAction<File[]>>;
}) {
  return (
    <Card className="single-network-upload-card" size="small">
      <Typography.Text className="single-network-upload-title">Allegro 网表目录</Typography.Text>
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
    <div className={`single-network-metric single-network-metric-${tone || "plain"}`}>
      <div className="single-network-metric-value">{value}</div>
      <div className="single-network-metric-label">{label}</div>
    </div>
  );
}

function DetailField({ label, value }: { label: string; value?: unknown }) {
  return (
    <div className="single-network-field">
      <span>{label}</span>
      <p>{textOf(value) || "-"}</p>
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
      width: index === 0 ? 220 : index === 3 || index === 7 ? 320 : undefined,
    })) || [];
  const data =
    table?.rows?.map((row: unknown[], index: number) => ({
      key: index,
      ...Object.fromEntries(row.map((value, i) => [String(i), value])),
    })) || [];
  if (!data.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无单网络数据" />;
  return <Table size="small" columns={columns} dataSource={data} pagination={{ pageSize: 14 }} scroll={{ x: true }} />;
}

export function SingleNetworkCheckPane({ tool }: { tool: ToolInfo }) {
  const [workspace, setWorkspace, resetWorkspace] = useToolWorkspace("single_network_check", {
    result: null as any,
    filter: "focus",
    query: "",
    selectedKey: "",
  });
  const [netlistFiles, setNetlistFiles] = useState<File[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(workspace.result || null);
  const [filter, setFilter] = useState(String(workspace.filter || "focus"));
  const [query, setQuery] = useState(String(workspace.query || ""));
  const [selectedKey, setSelectedKey] = useState(String(workspace.selectedKey || ""));

  useEffect(() => {
    setWorkspace({ result, filter, query, selectedKey });
  }, [result, filter, query, selectedKey]);

  const review = result?.single_network_review;
  const items: SingleNetworkItem[] = review?.items || [];
  const focusItems: SingleNetworkItem[] = review?.focus_items || [];
  const counts = review?.status_counts || {};
  const visibleItems = useMemo(() => {
    const source = filter === "focus" ? focusItems : items;
    const q = query.trim().toLowerCase();
    return source.filter((item) => {
      const byFilter = filter === "focus" || filter === "all" || filterOf(item) === filter;
      const hay = `${item.net} ${item.category} ${item.note} ${item.review_hint} ${joinList(item.refs)} ${joinList(item.nodes)}`.toLowerCase();
      return byFilter && (!q || hay.includes(q));
    });
  }, [items, focusItems, filter, query]);
  const selected = items.find((item) => item.key === selectedKey) || visibleItems[0] || items[0];
  const filterOptions = [
    { label: "重点复核", value: "focus", count: focusItems.length },
    { label: "NC 网络", value: "nc", count: counts.nc || 0 },
    { label: "单一位号网络", value: "single_ref", count: counts.single_ref || 0 },
    { label: "电源/地", value: "power", count: counts.power || 0 },
    { label: "测试点/工艺", value: "testpoint", count: counts.testpoint || 0 },
    { label: "机械/安装孔", value: "mechanical", count: counts.mechanical || 0 },
    { label: "全部", value: "all", count: items.length },
  ];

  useEffect(() => {
    if (review) {
      setSelectedKey((prev) => {
        if (prev && items.some((item) => item.key === prev)) return prev;
        return review.focus_items?.[0]?.key || review.items?.[0]?.key || "";
      });
    }
  }, [review]);

  async function handleRun() {
    if (!netlistFiles.some((file) => file.name.toLowerCase() === "pstxnet.dat")) {
      setResult({ status: "error", error: "请选择包含 pstxnet.dat 的 Allegro 目录。" });
      return;
    }
    setRunning(true);
    try {
      const netlistUpload = await uploadFiles(netlistFiles);
      const next = await runTool("single_network_check", {
        netlist: netlistUpload.files.map((file) => file.path),
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
    <div className="single-network-workbench">
      <div className="single-network-head">
        <div>
          <Typography.Title level={4}>{tool.name}</Typography.Title>
          <Typography.Paragraph type="secondary">{tool.description}</Typography.Paragraph>
        </div>
        {result?.outputs?.length ? (
          <Space wrap>
            {result.outputs.map((path: string) => (
              <Button key={path} href={outputHref(path)} icon={<DownloadOutlined />}>
                下载单网络检查报告
              </Button>
            ))}
          </Space>
        ) : null}
      </div>

      <div className="single-network-upload-grid">
        <NetlistUploadSlot files={netlistFiles} onFiles={setNetlistFiles} />
        <Card size="small" className="single-network-run-card">
          <Space wrap>
            <Button type="primary" loading={running} onClick={handleRun} icon={<PlayCircleOutlined />}>
              开始检查
            </Button>
            <Button
              onClick={() => {
                setNetlistFiles([]);
                setResult(null);
                resetWorkspace();
              }}
              icon={<DeleteOutlined />}
            >
              清空
            </Button>
          </Space>
        </Card>
      </div>

      {!result ? (
        <Alert
          type="info"
          showIcon
          message="选择 Allegro 网表目录后开始检查"
          description="直接选择包含 pstxnet.dat 的 allegro 文件夹。系统会自动提取 NC 网络、单一位号网络，并把测试点、安装孔、电源地等场景分开复核。"
        />
      ) : null}
      {result?.status && result.status !== "ok" ? <Alert type="error" showIcon message={result.error || result.message || "运行失败"} /> : null}

      {result?.status === "ok" ? (
        <>
          <div className="single-network-summary-grid">
            <Metric label="总网络" value={result.summary?.total_nets || 0} />
            <Metric label="命中项" value={result.summary?.matched_count || 0} tone="diff" />
            <Metric label="重点复核" value={result.summary?.focus_count || 0} tone="danger" />
            <Metric label="NC 网络" value={result.summary?.nc_count || 0} tone="warn" />
            <Metric label="单一位号" value={result.summary?.single_ref_count || 0} tone="manual" />
            <Metric label="电源/地" value={counts.power || 0} tone="risk" />
            <Metric label="工艺/机械" value={(counts.testpoint || 0) + (counts.mechanical || 0)} tone="skip" />
          </div>

          <Tabs
            className="single-network-tabs"
            items={[
              {
                key: "review",
                label: "网络复核",
                children: (
                  <div className="single-network-shell">
                    <aside className="single-network-rail">
                      <div className="single-network-filter-grid">
                        {filterOptions.map((option) => (
                          <button
                            key={option.value}
                            type="button"
                            className={`single-network-filter-chip ${filter === option.value ? "is-active" : ""}`}
                            onClick={() => setFilter(option.value)}
                          >
                            <span>{option.label}</span>
                            <b>{option.count}</b>
                          </button>
                        ))}
                      </div>
                      <Input allowClear prefix={<SearchOutlined />} placeholder="搜索网络 / 位号 / Pin" value={query} onChange={(event) => setQuery(event.target.value)} />
                      <div className="single-network-focus-list">
                        {visibleItems.map((item) => (
                          <button
                            type="button"
                            key={item.key}
                            className={`single-network-focus-item ${selected?.key === item.key ? "is-active" : ""}`}
                            onClick={() => setSelectedKey(item.key)}
                          >
                            <span className="single-network-focus-top">
                              <span className="single-network-focus-net">{item.net}</span>
                              <Tag color={categoryColor(item.category)}>{item.category}</Tag>
                            </span>
                            <span className="single-network-focus-refs">{joinList(item.refs)}</span>
                            <span className="single-network-focus-msg">{item.note}</span>
                          </button>
                        ))}
                      </div>
                    </aside>

                    <main className="single-network-detail">
                      {selected ? (
                        <>
                          <div className="single-network-detail-head">
                            <div>
                              <Typography.Title level={5}>{selected.net}</Typography.Title>
                              <Typography.Text type="secondary">{selected.review_hint || selected.note}</Typography.Text>
                            </div>
                            <Tag color={categoryColor(selected.category)}>{selected.category}</Tag>
                          </div>
                          <div className="single-network-field-grid">
                            <DetailField label="位号" value={joinList(selected.refs)} />
                            <DetailField label="节点 / Pin" value={joinList(selected.nodes)} />
                            <DetailField label="位号数" value={selected.ref_count} />
                            <DetailField label="节点数" value={selected.pin_count} />
                            <DetailField label="优先级" value={selected.severity} />
                            <DetailField label="说明" value={selected.note} />
                          </div>
                          <Typography.Title level={5} className="single-network-section-title">
                            当前筛选结果
                          </Typography.Title>
                          <Table
                            size="small"
                            dataSource={visibleItems.map((item) => ({ ...item, key: item.key }))}
                            pagination={{ pageSize: 10 }}
                            scroll={{ x: true }}
                            onRow={(record) => ({ onClick: () => setSelectedKey(record.key) })}
                            columns={[
                              { title: "网络", dataIndex: "net", key: "net", ellipsis: true, width: 220 },
                              { title: "类型", dataIndex: "category", key: "category", render: (value: string) => <Tag color={categoryColor(value)}>{value}</Tag> },
                              { title: "位号", dataIndex: "refs", key: "refs", ellipsis: true, render: (value: string[]) => joinList(value) },
                              { title: "节点数", dataIndex: "pin_count", key: "pin_count", width: 80 },
                              { title: "说明", dataIndex: "note", key: "note", ellipsis: true },
                            ]}
                          />
                        </>
                      ) : (
                        <Empty description="暂无需要复核的单网络" />
                      )}
                    </main>

                    <aside className="single-network-inspector">
                      <Typography.Title level={5}>复核规则</Typography.Title>
                      <div className="single-network-guide-list">
                        {["重点复核", "单一位号网络", "NC 网络", "电源/地", "测试点/工艺", "机械/安装孔"].map((key) => (
                          <div key={key} className="single-network-guide-item">
                            <Tag color={categoryColor(key)}>{key}</Tag>
                            <Typography.Paragraph type="secondary">{review?.review_guide?.[key]}</Typography.Paragraph>
                          </div>
                        ))}
                      </div>
                    </aside>
                  </div>
                ),
              },
              { key: "table", label: "完整表格", children: <SimpleTable table={result.table} /> },
            ]}
          />
        </>
      ) : null}
    </div>
  );
}
