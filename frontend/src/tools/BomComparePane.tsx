import { useEffect, useMemo, useState } from "react";
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
  FileExcelOutlined,
  PlayCircleOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { runTool, uploadFiles, type ToolInfo } from "../api/client";

type CompareItem = {
  key: string;
  status: string;
  kind: string;
  badge?: string;
  left?: Record<string, unknown> | null;
  right?: Record<string, unknown> | null;
  diff?: string[];
};

type TablePayload = { headers?: string[]; rows?: unknown[][]; total_rows?: number };

function outputHref(path: string) {
  const normalized = path.replaceAll("\\", "/");
  const marker = "/data/outputs/";
  const index = normalized.indexOf(marker);
  const rel = index >= 0 ? normalized.slice(index + marker.length) : normalized.replace(/^data\/outputs\//, "");
  return `/outputs/${encodeURI(rel)}`;
}

const statusMeta: Record<string, { label: string; color: string; tone: string; filter: string }> = {
  same: { label: "一致", color: "green", tone: "ok", filter: "same" },
  swap: { label: "换料", color: "red", tone: "high", filter: "swap" },
  added: { label: "新增", color: "blue", tone: "medium", filter: "added" },
  removed: { label: "删除", color: "orange", tone: "medium", filter: "removed" },
  param: { label: "参数", color: "purple", tone: "low", filter: "param" },
};

function itemGroup(item: CompareItem) {
  if (item.status === "换料") return "swap";
  if (item.status === "新增贴装") return "added";
  if (item.status === "删除/未贴") return "removed";
  if (item.status === "参数差异") return "param";
  return "same";
}

function countByGroup(items: CompareItem[]) {
  return items.reduce(
    (acc, item) => {
      acc[itemGroup(item)] += 1;
      return acc;
    },
    { same: 0, swap: 0, added: 0, removed: 0, param: 0 },
  );
}

function textOf(value: unknown) {
  return String(value ?? "");
}

function UploadSlot({
  title,
  file,
  onFile,
}: {
  title: string;
  file?: File;
  onFile: (file?: File) => void;
}) {
  return (
    <Card className="compare-upload-card" size="small">
      <Typography.Text className="compare-upload-title">{title}</Typography.Text>
      <Upload
        accept=".xlsx,.xls"
        maxCount={1}
        fileList={file ? [{ uid: "0", name: file.name, status: "done" as const }] : []}
        beforeUpload={(next) => {
          onFile(next);
          return false;
        }}
        onRemove={() => {
          onFile(undefined);
          return true;
        }}
      >
        <Button icon={<FileExcelOutlined />}>选择 Excel</Button>
      </Upload>
    </Card>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className={`compare-metric compare-metric-${tone || "plain"}`}>
      <div className="compare-metric-value">{value}</div>
      <div className="compare-metric-label">{label}</div>
    </div>
  );
}

function MiniTable({ table, maxRows = 8 }: { table?: TablePayload; maxRows?: number }) {
  const columns =
    table?.headers?.map((header, index) => ({
      title: header,
      dataIndex: String(index),
      key: String(index),
      ellipsis: true,
      width: index === 2 ? 180 : undefined,
    })) || [];
  const data =
    table?.rows?.slice(0, maxRows).map((row, index) => ({
      key: index,
      ...Object.fromEntries(row.map((value, i) => [String(i), value])),
    })) || [];
  if (!table?.rows?.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无变化" />;
  return <Table size="small" columns={columns} dataSource={data} pagination={false} scroll={{ x: true }} />;
}

function RiskList({ findings }: { findings?: Array<{ name: string; status: string; message: string }> }) {
  if (!findings?.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无风险数据" />;
  return (
    <div className="compare-risk-list">
      {findings.map((item) => (
        <div className="compare-risk-item" key={item.name}>
          <Tag color={item.status === "warn" ? "orange" : item.status === "ok" ? "green" : "blue"}>
            {item.status === "warn" ? "警告" : item.status === "ok" ? "通过" : "提示"}
          </Tag>
          <div>
            <Typography.Text strong>{item.name}</Typography.Text>
            <Typography.Paragraph type="secondary">{item.message}</Typography.Paragraph>
          </div>
        </div>
      ))}
    </div>
  );
}

function FieldPair({ name, selected }: { name: string; selected?: CompareItem }) {
  const changed = selected?.diff?.includes(name);
  return (
    <div className={`compare-field-pair ${changed ? "is-changed" : ""}`}>
      <div className="compare-field-label">{name}</div>
      <div className="compare-field-values">
        <div>
          <span>BOM1</span>
          <p>{textOf(selected?.left?.[name]) || "-"}</p>
        </div>
        <div>
          <span>BOM2</span>
          <p>{textOf(selected?.right?.[name]) || "-"}</p>
        </div>
      </div>
    </div>
  );
}

function OriginRows({ origin, side }: { origin: any; side: "left" | "right" }) {
  const rows = side === "left" ? origin?.left_rows : origin?.right_rows;
  const columns =
    origin?.columns?.map((header: string, index: number) => ({
      title: header,
      dataIndex: String(index),
      key: String(index),
      ellipsis: true,
      width: index === 2 ? 220 : undefined,
    })) || [];
  const data =
    rows?.slice(0, 200).map((row: any, index: number) => ({
      key: index,
      status: row.status,
      ...Object.fromEntries((row.cells || []).map((value: unknown, i: number) => [String(i), value])),
    })) || [];
  return <Table size="small" columns={columns} dataSource={data} pagination={{ pageSize: 12 }} scroll={{ x: true }} />;
}

export function BomComparePane({ tool }: { tool: ToolInfo }) {
  const [bom1, setBom1] = useState<File | undefined>();
  const [bom2, setBom2] = useState<File | undefined>();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [filter, setFilter] = useState<string>("diff");
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState("");

  const items: CompareItem[] = result?.compare?.items || [];
  const counts = result?.summary?.status_counts || countByGroup(items);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => {
      const group = itemGroup(item);
      const byFilter = filter === "all" || (filter === "diff" ? group !== "same" : group === filter);
      const hay = `${item.key} ${item.status} ${textOf(item.left?.["编号"])} ${textOf(item.right?.["编号"])} ${textOf(item.left?.["描述"])} ${textOf(item.right?.["描述"])}`.toLowerCase();
      return byFilter && (!q || hay.includes(q));
    });
  }, [items, filter, query]);
  const selected = items.find((item) => item.key === selectedKey) || filtered[0] || items[0];

  useEffect(() => {
    if (result?.status === "ok") {
      const focus = result.focus_items?.[0]?.key;
      setSelectedKey(focus || filtered[0]?.key || items[0]?.key || "");
    }
  }, [result]);

  async function handleRun() {
    if (!bom1 || !bom2) {
      setResult({ status: "error", error: "请先选择两份 BOM 文件" });
      return;
    }
    setRunning(true);
    try {
      const [leftUpload, rightUpload] = await Promise.all([uploadFiles([bom1]), uploadFiles([bom2])]);
      const next = await runTool("bom_compare", {
        bom1: leftUpload.files[0]?.path,
        bom2: rightUpload.files[0]?.path,
      });
      setResult(next);
      setFilter("diff");
      setQuery("");
    } catch (err: any) {
      setResult({ status: "error", error: err.message || "运行失败" });
    } finally {
      setRunning(false);
    }
  }

  const listColumns = [
    { title: "位号", dataIndex: "key", key: "key", width: 100 },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (value: string) => {
        const meta = statusMeta[itemGroup({ status: value } as CompareItem)];
        return <Tag color={meta.color}>{value}</Tag>;
      },
    },
    { title: "BOM1编号", dataIndex: ["left", "编号"], key: "leftCode", ellipsis: true },
    { title: "BOM2编号", dataIndex: ["right", "编号"], key: "rightCode", ellipsis: true },
  ];

  const tableData = filtered.map((item) => ({ ...item, key: item.key }));

  return (
    <div className="compare-workbench">
      <div className="compare-head">
        <div>
          <Typography.Title level={4}>{tool.name}</Typography.Title>
          <Typography.Paragraph type="secondary">{tool.description}</Typography.Paragraph>
        </div>
        {result?.outputs?.length ? (
          <Space wrap>
            {result.outputs.map((path: string) => (
              <Button key={path} href={outputHref(path)} icon={<DownloadOutlined />}>
                下载差异报告
              </Button>
            ))}
          </Space>
        ) : null}
      </div>

      <div className="compare-upload-grid">
        <UploadSlot title="旧版 / 基准 BOM" file={bom1} onFile={setBom1} />
        <UploadSlot title="新版 / 待确认 BOM" file={bom2} onFile={setBom2} />
        <Card size="small" className="compare-run-card">
          <Space wrap>
            <Button type="primary" loading={running} onClick={handleRun} icon={<PlayCircleOutlined />}>
              开始对比
            </Button>
            <Button
              onClick={() => {
                setBom1(undefined);
                setBom2(undefined);
                setResult(null);
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
          message="选择两份 BOM 后开始对比"
          description="工作台会按位号、料号用量、原表标注和风险检查四个视角拆解差异。"
        />
      ) : null}
      {result?.status && result.status !== "ok" ? <Alert type="error" showIcon message={result.error || result.message || "运行失败"} /> : null}

      {result?.status === "ok" ? (
        <>
          <div className="compare-summary-grid">
            <Metric label="总位号" value={result.summary?.total_positions || 0} />
            <Metric label="差异位号" value={result.summary?.changed_positions || 0} tone="diff" />
            <Metric label="换料" value={counts.swap || 0} tone="high" />
            <Metric label="新增" value={counts.added || 0} tone="medium" />
            <Metric label="删除" value={counts.removed || 0} tone="medium" />
            <Metric label="参数差异" value={counts.param || 0} tone="low" />
            <Metric label="料号变化" value={result.summary?.part_changes || 0} tone="part" />
          </div>

          <Tabs
            className="compare-tabs"
            items={[
              {
                key: "position",
                label: "位号审查",
                children: (
                  <div className="compare-shell">
                    <aside className="compare-rail">
                      <Segmented
                        block
                        value={filter}
                        onChange={(value) => setFilter(String(value))}
                        options={[
                          { label: "差异", value: "diff" },
                          { label: "换料", value: "swap" },
                          { label: "新增", value: "added" },
                          { label: "删除", value: "removed" },
                          { label: "参数", value: "param" },
                          { label: "全部", value: "all" },
                        ]}
                      />
                      <Input
                        allowClear
                        prefix={<SearchOutlined />}
                        placeholder="搜索位号 / 编码 / 描述"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                      />
                      <div className="compare-focus-list">
                        {filtered.map((item) => {
                          const meta = statusMeta[itemGroup(item)];
                          return (
                            <button
                              type="button"
                              className={`compare-focus-item ${selected?.key === item.key ? "is-active" : ""}`}
                              key={item.key}
                              onClick={() => setSelectedKey(item.key)}
                            >
                              <span className="compare-focus-ref">{item.key}</span>
                              <Tag color={meta.color}>{item.status}</Tag>
                              <span className="compare-focus-code">
                                {textOf(item.left?.["编号"]) || "-"} → {textOf(item.right?.["编号"]) || "-"}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </aside>

                    <main className="compare-detail">
                      {selected ? (
                        <>
                          <div className="compare-detail-head">
                            <div>
                              <Typography.Title level={5}>位号 {selected.key}</Typography.Title>
                              <Typography.Text type="secondary">
                                {result.review_guide?.[selected.status] || result.review_guide?.[selected.badge || ""] || "核对两份 BOM 在该位号上的差异。"}
                              </Typography.Text>
                            </div>
                            <Tag color={statusMeta[itemGroup(selected)].color}>{selected.status}</Tag>
                          </div>
                          {["编号", "型号", "描述"].map((field) => (
                            <FieldPair key={field} name={field} selected={selected} />
                          ))}
                          <Typography.Title level={5} className="compare-section-title">
                            筛选结果
                          </Typography.Title>
                          <Table
                            size="small"
                            columns={listColumns}
                            dataSource={tableData}
                            pagination={{ pageSize: 10 }}
                            scroll={{ x: true }}
                            onRow={(record) => ({ onClick: () => setSelectedKey(record.key) })}
                          />
                        </>
                      ) : (
                        <Empty description="暂无可审查位号" />
                      )}
                    </main>

                    <aside className="compare-inspector">
                      <Tabs
                        size="small"
                        items={[
                          {
                            key: "parts",
                            label: "料号用量",
                            children: (
                              <div>
                                <Typography.Paragraph type="secondary">{result.review_guide?.["料号用量"]}</Typography.Paragraph>
                                <MiniTable table={result.part_summary} maxRows={10} />
                              </div>
                            ),
                          },
                          {
                            key: "risk",
                            label: "风险提示",
                            children: (
                              <Tabs
                                size="small"
                                items={[
                                  { key: "left", label: result.risks?.left_label || "BOM1", children: <RiskList findings={result.risks?.left} /> },
                                  { key: "right", label: result.risks?.right_label || "BOM2", children: <RiskList findings={result.risks?.right} /> },
                                ]}
                              />
                            ),
                          },
                        ]}
                      />
                    </aside>
                  </div>
                ),
              },
              {
                key: "parts",
                label: "料号用量",
                children: <MiniTable table={result.part_summary} maxRows={1000} />,
              },
              {
                key: "origin",
                label: "原表标注",
                children: (
                  <Tabs
                    items={[
                      { key: "left", label: result.origin?.left_label || "BOM1", children: <OriginRows origin={result.origin} side="left" /> },
                      { key: "right", label: result.origin?.right_label || "BOM2", children: <OriginRows origin={result.origin} side="right" /> },
                    ]}
                  />
                ),
              },
              {
                key: "risk",
                label: "风险检查",
                children: (
                  <Tabs
                    items={[
                      { key: "left", label: result.risks?.left_label || "BOM1", children: <RiskList findings={result.risks?.left} /> },
                      { key: "right", label: result.risks?.right_label || "BOM2", children: <RiskList findings={result.risks?.right} /> },
                    ]}
                  />
                ),
              },
            ]}
          />
        </>
      ) : null}
    </div>
  );
}
